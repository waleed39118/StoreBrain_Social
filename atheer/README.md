# Atheer (أثير) — Smart Clinic Assistant

**دليل التثبيت بالعربية: [INSTALL_AR.md](INSTALL_AR.md)**

Bilingual (Arabic/English) voice and text receptionist for medical clinics: appointments, an arrival queue with spoken call-outs, medical and billing calculations, and signed self-updates.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design, [`docs/schema.sql`](docs/schema.sql) for the database and [`docs/PROGRESS.md`](docs/PROGRESS.md) for the work log.

## Structure

```
atheer/
├── requirements.txt            pyproject.toml          .env.example
├── docs/                       ARCHITECTURE.md · schema.sql · PROGRESS.md
├── scripts/dump_schema.py      regenerates docs/schema.sql from the models
├── src/atheer/
│   ├── runtime.py              `atheer`: text + voice + speaker + updater loops (asyncio)
│   ├── admin.py                `atheer-admin`: doctors, shifts, patients, booking, alerts, update signing
│   ├── core/                   config (env), clock, event bus
│   ├── db/                     SQLAlchemy models, UTC datetime type, engine/session
│   ├── appointments/           booking, rescheduling, state machine, reminders, late/VIP/conflict alerts
│   ├── queue/                  daily tickets, call-next, AR/EN announcements, wait estimates
│   ├── calculations/           dosage verification, BSA, CrCl, billing split, wait time, stock
│   ├── assistant/              bilingual intent router with staff/public gating
│   ├── voice/                  faster-whisper STT, Piper TTS, mic + VAD segmentation
│   └── updater/                signed content bundles: verify, stage, swap, rollback; publisher tools
└── tests/                      40 tests (pytest)
```

## Run

```bash
cd atheer
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # text mode
cp .env.example .env               # adjust timezone, DB URL
atheer-admin seed-demo             # demo doctor + patients (see atheer-admin --help)
atheer                             # type at "You>"; "exit" to quit
pytest
```

Voice mode (local/offline): run `pip install -e ".[voice]"`, download Piper voices (e.g. Arabic + English `.onnx`), then set `ATHEER_VOICE_ENABLED=true`, `ATHEER_VOICE_MODEL_AR=…` and `ATHEER_VOICE_MODEL_EN=…`.

## Safety and privacy decisions

- **Dose checks verify; they do not prescribe.** No drug data ships with Atheer. Limits come from the clinic formulary (`DoseRule`) and every result has `requires_clinician_review=True`. Cockcroft–Gault refuses paediatric ages.
- **Public speakers hear ticket numbers and rooms only.** Staff alerts use "first name + last initial" and never go to the speakers.
- **Staff-only commands** ("call next", late reports) are refused on the public microphone.
- **Self-update is content only** (terminology, prompts, voice models: `.json/.txt/.csv/.onnx`). It uses Ed25519 signatures with a pinned key, per-file SHA-256 checks, no downgrades, zip-slip and zip-bomb guards, atomic swap, a health check and rollback. Code releases go through CI and a human-approved deploy.
- **Audio stays on-premises** by default (faster-whisper + Piper).
