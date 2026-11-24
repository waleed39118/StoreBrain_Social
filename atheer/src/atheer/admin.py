"""Administration CLI: set up the database, manage doctors/patients, book, inspect, publish updates.

    atheer-admin --help
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from atheer.appointments.exceptions import AppointmentError
from atheer.appointments.schemas import BookingRequest
from atheer.appointments.service import AppointmentService
from atheer.core.config import Settings, get_settings
from atheer.core.console import configure_console
from atheer.db import Appointment, Doctor, DoctorShift, Patient, create_engine_from_settings, init_db
from atheer.db.session import make_session_factory, session_scope
from atheer.licensing import vendor_key
from atheer.licensing.license import License, LicenseError, LicenseGuard

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _hhmm(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _weekday(value: str) -> int:
    v = value.strip().lower()[:3]
    if v.isdigit() and 0 <= int(v) <= 6:
        return int(v)
    if v not in WEEKDAYS:
        raise argparse.ArgumentTypeError("weekday must be mon..sun or 0..6 (0 = Monday)")
    return WEEKDAYS[v]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atheer-admin", description="Atheer clinic administration")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create database tables")
    sd = sub.add_parser("seed-demo", help="add a demo doctor (every day 08:00–22:00) and two patients")
    sd.add_argument("--with-appointments", action="store_true", help="also book two demo appointments for today")

    d = sub.add_parser("add-doctor")
    d.add_argument("--name", required=True)
    d.add_argument("--specialty", required=True)
    d.add_argument("--slot", type=int, help="consultation minutes (default: clinic setting)")

    s = sub.add_parser("add-shift", help="weekly availability in clinic local time")
    s.add_argument("--doctor-id", type=int, required=True)
    s.add_argument("--weekday", type=_weekday, required=True, help="mon..sun or 0..6")
    s.add_argument("--start", type=_hhmm, required=True, help="HH:MM")
    s.add_argument("--end", type=_hhmm, required=True, help="HH:MM")

    pa = sub.add_parser("add-patient")
    pa.add_argument("--mrn", required=True, help="medical record number (unique)")
    pa.add_argument("--first", required=True)
    pa.add_argument("--last", required=True)
    pa.add_argument("--phone")
    pa.add_argument("--lang", default="ar", choices=["ar", "en"])
    pa.add_argument("--vip", action="store_true")

    b = sub.add_parser("book", help="book an appointment (local time)")
    b.add_argument("--patient-id", type=int, required=True)
    b.add_argument("--doctor-id", type=int, required=True)
    b.add_argument("--start", required=True, help='"YYYY-MM-DD HH:MM" clinic local time')
    b.add_argument("--duration", type=int)
    b.add_argument("--reason")

    sub.add_parser("list-doctors")
    la = sub.add_parser("list-appointments")
    la.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    sub.add_parser("alerts", help="late-running and conflicting appointments today")
    sub.add_parser("reminders", help="appointments due a reminder")

    k = sub.add_parser("update-keygen", help="create an Ed25519 signing key for content updates")
    k.add_argument("--out", type=Path, required=True, help="private key file (.pem) — keep it secret")

    u = sub.add_parser("update-build", help="build a signed content release")
    u.add_argument("--src", type=Path, required=True, help="folder with .json/.txt/.csv/.onnx files")
    u.add_argument("--version", required=True, help="e.g. 2026.11.17.1")
    u.add_argument("--base-url", required=True, help="https://host/path where files will be uploaded")
    u.add_argument("--key", type=Path, required=True)
    u.add_argument("--out", type=Path, required=True)

    lk = sub.add_parser("license-keygen", help="vendor only: create the license-signing key pair")
    lk.add_argument("--out", type=Path, required=True, help="private key file (.pem) — keep it secret, never ship it")

    li = sub.add_parser("license-issue", help="vendor only: sign a subscription license for a clinic")
    li.add_argument("--key", type=Path, required=True, help="vendor private key from license-keygen")
    li.add_argument("--customer", required=True, help="clinic or company name")
    li.add_argument("--plan", required=True, help="e.g. clinic, center, hospital")
    li.add_argument("--days", type=int, required=True, help="subscription length in days, e.g. 30 or 365")
    li.add_argument("--max-doctors", type=int, help="active doctor limit for the plan")
    li.add_argument("--grace-days", type=int, default=14)
    li.add_argument("--id", dest="license_id", help="license number (default: generated)")
    li.add_argument("--out", type=Path, required=True, help="license.json to give the clinic")

    sub.add_parser("license-status", help="show this installation's license")
    return p


def run(argv: Sequence[str] | None = None, settings: Settings | None = None,
        license_guard: LicenseGuard | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()

    if args.cmd == "license-keygen":
        from atheer.licensing.license import generate_vendor_keypair

        if args.out.exists():
            print(f"Refusing to overwrite existing key {args.out}", file=sys.stderr)
            return 1
        pem, pub = generate_vendor_keypair()
        args.out.write_bytes(pem)
        args.out.chmod(0o600)
        print(f"Vendor private key written to {args.out} (keep it secret, back it up).")
        print("Paste this into src/atheer/licensing/vendor_key.py before building customer copies:")
        print(f'VENDOR_PUBLIC_KEY = "{pub}"')
        return 0

    if args.cmd == "license-issue":
        import secrets

        from atheer.licensing.license import issue_license

        if args.days < 1:
            print("--days must be at least 1", file=sys.stderr)
            return 1
        now = datetime.now(timezone.utc).replace(microsecond=0)
        lic = License(
            license_id=args.license_id or f"ATH-{now:%Y%m%d}-{secrets.token_hex(3).upper()}",
            customer=args.customer, plan=args.plan, max_doctors=args.max_doctors,
            issued_at=now, expires_at=now + timedelta(days=args.days), grace_days=args.grace_days,
        )
        args.out.write_bytes(issue_license(args.key.read_bytes(), lic))
        print(f"License {lic.license_id} for {lic.customer} ({lic.plan}) valid until "
              f"{lic.expires_at:%Y-%m-%d} written to {args.out}. Copy it to the clinic as license.json.")
        return 0

    guard = license_guard or LicenseGuard(settings.license_path, vendor_key.VENDOR_PUBLIC_KEY)
    if args.cmd == "license-status":
        state = guard.state()
        print(f"Status: {state.status.value}")
        if state.license:
            lic = state.license
            print(f"Customer: {lic.customer} | Plan: {lic.plan} | License: {lic.license_id}")
            print(f"Expires: {lic.expires_at:%Y-%m-%d} | Doctor limit: {lic.max_doctors or 'unlimited'}")
        if state.needs_attention:
            print(state.message_ar)
            print(state.message_en)
        return 0 if state.allows_operation else 1

    if args.cmd == "update-keygen":
        from atheer.updater.publish import generate_keypair

        pem, pub = generate_keypair()
        if args.out.exists():
            print(f"Refusing to overwrite existing key {args.out}", file=sys.stderr)
            return 1
        args.out.write_bytes(pem)
        args.out.chmod(0o600)
        print(f"Private key written to {args.out}\nATHEER_UPDATE_PUBLIC_KEY={pub}")
        return 0

    if args.cmd == "update-build":
        from atheer.updater.publish import build_release

        base = args.base_url.rstrip("/")
        bundle, manifest, sig = build_release(args.src, args.version, f"{base}/{args.version}.zip", args.key.read_bytes())
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{args.version}.zip").write_bytes(bundle)
        (args.out / "manifest.json").write_bytes(manifest)
        (args.out / "manifest.json.sig").write_bytes(sig)
        print(f"Upload the contents of {args.out} to {base}/\nATHEER_UPDATE_MANIFEST_URL={base}/manifest.json")
        return 0

    engine = create_engine_from_settings(settings)
    init_db(engine)
    sf = make_session_factory(engine)
    tz = settings.tz
    appts = AppointmentService(sf, settings)

    try:
        if args.cmd == "init-db":
            print("Database ready.")
        elif args.cmd == "seed-demo":
            with session_scope(sf) as s:
                dr = Doctor(full_name="Sara Ali", specialty="Family Medicine", slot_minutes=20)
                for wd in range(7):  # every day, so a trial works whenever it runs
                    dr.shifts.append(DoctorShift(weekday=wd, start_time=time(8), end_time=time(22)))
                s.add_all([
                    dr,
                    Patient(mrn="DEMO-1", first_name="Ahmed", last_name="Hassan", preferred_language="ar"),
                    Patient(mrn="DEMO-2", first_name="Lina", last_name="Saad", is_vip=True),
                ])
            print("Demo data added: doctor #1, patients #1 and #2.")
            if args.with_appointments:
                for line in _book_demo_appointments(appts, tz):
                    print(line)
        elif args.cmd == "add-doctor":
            guard.require()
            limit = guard.doctor_limit()
            with session_scope(sf) as s:
                if limit is not None:
                    active = s.scalar(select(func.count()).select_from(Doctor).where(Doctor.is_active.is_(True))) or 0
                    if active >= limit:
                        print(f"Error: your plan allows {limit} active doctors. Upgrade the subscription to add more. "
                              f"/ باقتك تسمح بـ {limit} أطباء فقط.", file=sys.stderr)
                        return 1
                dr = Doctor(full_name=args.name, specialty=args.specialty, slot_minutes=args.slot)
                s.add(dr)
                s.flush()
                print(f"Doctor #{dr.id} added.")
        elif args.cmd == "add-shift":
            if args.start >= args.end:
                print("start must be before end", file=sys.stderr)
                return 1
            with session_scope(sf) as s:
                if s.get(Doctor, args.doctor_id) is None:
                    print(f"Doctor {args.doctor_id} not found", file=sys.stderr)
                    return 1
                s.add(DoctorShift(doctor_id=args.doctor_id, weekday=args.weekday, start_time=args.start, end_time=args.end))
            print("Shift added.")
        elif args.cmd == "add-patient":
            with session_scope(sf) as s:
                pt = Patient(mrn=args.mrn, first_name=args.first, last_name=args.last, phone=args.phone,
                             preferred_language=args.lang, is_vip=args.vip)
                s.add(pt)
                s.flush()
                print(f"Patient #{pt.id} added.")
        elif args.cmd == "book":
            guard.require()
            start = datetime.strptime(args.start, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            res = appts.book(BookingRequest(patient_id=args.patient_id, doctor_id=args.doctor_id, starts_at=start,
                                            duration_minutes=args.duration, reason=args.reason))
            a = res.appointment
            print(f"Appointment #{a.id}: {a.starts_at.astimezone(tz):%Y-%m-%d %H:%M}–{a.ends_at.astimezone(tz):%H:%M}")
            for alert in res.alerts:
                print(f"  ! {alert.message}")
        elif args.cmd == "list-doctors":
            with session_scope(sf) as s:
                for dr in s.scalars(select(Doctor).order_by(Doctor.id)):
                    shifts = ", ".join(
                        f"{list(WEEKDAYS)[sh.weekday]} {sh.start_time:%H:%M}-{sh.end_time:%H:%M}" for sh in dr.shifts
                    )
                    print(f"#{dr.id} Dr. {dr.full_name} ({dr.specialty}){'' if dr.is_active else ' [inactive]'}: {shifts or 'no shifts'}")
        elif args.cmd == "list-appointments":
            day = args.date or datetime.now(tz).date()
            start = datetime.combine(day, time.min, tzinfo=tz)
            with session_scope(sf) as s:
                rows = s.scalars(
                    select(Appointment)
                    .where(Appointment.starts_at >= start, Appointment.starts_at < start + timedelta(days=1))
                    .order_by(Appointment.starts_at)
                ).all()
                for a in rows:
                    print(f"#{a.id} {a.starts_at.astimezone(tz):%H:%M} Dr. {a.doctor.full_name} — "
                          f"{a.patient.announce_name} [{a.status.value}]")
                if not rows:
                    print("No appointments.")
        elif args.cmd == "alerts":
            alerts = appts.running_late_alerts() + appts.conflict_alerts(datetime.now(tz).date())
            for alert in alerts:
                print(f"[{alert.severity.value}] {alert.message}")
            if not alerts:
                print("No alerts.")
        elif args.cmd == "reminders":
            due = appts.due_reminders()
            print(json.dumps([d.model_dump(mode="json") for d in due], ensure_ascii=False, indent=2))
    except LicenseError as exc:
        print(f"Error: {exc.message_en}\n{exc.message_ar}", file=sys.stderr)
        return 1
    except IntegrityError as exc:
        # Duplicate MRN, or demo data already present: report plainly, no traceback.
        detail = str(exc.orig) if exc.orig else str(exc)
        print(f"Error: record already exists or violates a database rule ({detail}).", file=sys.stderr)
        return 1
    except (AppointmentError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


def _book_demo_appointments(appts: AppointmentService, tz) -> list[str]:
    """Book the next free slots (today, else tomorrow) for demo patients 1 and 2."""
    today = datetime.now(tz).date()
    for day in (today, today + timedelta(days=1)):
        slots = appts.free_slots(1, day)
        if len(slots) >= 2:
            lines = []
            for patient_id, slot in zip((1, 2), slots[1:3] if len(slots) >= 3 else slots[:2], strict=False):
                res = appts.book(BookingRequest(patient_id=patient_id, doctor_id=1, starts_at=slot.starts_at))
                a = res.appointment
                lines.append(f"Demo appointment #{a.id}: patient #{patient_id} at {a.starts_at.astimezone(tz):%Y-%m-%d %H:%M}")
            return lines
    return ["No free slots for demo appointments."]


def main() -> None:
    configure_console()
    sys.exit(run())


if __name__ == "__main__":
    main()
