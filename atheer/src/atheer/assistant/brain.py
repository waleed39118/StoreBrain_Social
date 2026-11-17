"""Bilingual (Arabic/English) intent router.

Deterministic intents cover the secretary's core duties. Anything unmatched
goes to an optional ``Fallback`` (e.g. an LLM with tool access added later),
which never touches the database directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from atheer.appointments.service import AppointmentService
from atheer.core.clock import Clock, SystemClock
from atheer.core.config import Settings
from atheer.queue.service import QueueService

_ARABIC = re.compile(r"[؀-ۿ]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def detect_language(text: str) -> str:
    return "ar" if _ARABIC.search(text) else "en"


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    language: str
    speak: bool = True  # False for staff-only content that must not go to public speakers


class Fallback(Protocol):
    def respond(self, text: str, language: str) -> Reply | None: ...


Handler = Callable[[re.Match[str], str], Reply]


class Brain:
    def __init__(
        self,
        settings: Settings,
        appointments: AppointmentService,
        queue: QueueService,
        *,
        clock: Clock | None = None,
        fallback: Fallback | None = None,
    ) -> None:
        self._s = settings
        self._appts = appointments
        self._queue = queue
        self._clock = clock or SystemClock()
        self._fallback = fallback
        # Order matters: first match wins.
        # (pattern, handler, staff_only). Staff-only intents are refused on public channels (lobby mic, kiosk).
        self._intents: list[tuple[re.Pattern[str], Handler, bool]] = [
            (re.compile(r"\bcall next\b|\bnext (patient|number)\b|نادِ?\s*التالي|(المراجع|الرقم) التالي", re.I),
             self._call_next, True),
            (re.compile(r"\b(wait|how long)\b|انتظار|كم\s*(باقي|بقي)", re.I), self._wait_time, False),
            (re.compile(r"\b(ticket|queue number)\b|تذكرة|رقم\s*(انتظار|دور)|أريد\s*دور", re.I), self._issue_ticket, False),
            (re.compile(r"\b(slots?|available|availability)\b|مواعيد|متاح", re.I), self._free_slots, False),
            (re.compile(r"\b(late|delays?)\b|متأخر|تأخير", re.I), self._late, True),
            (re.compile(r"\b(hello|hi|good (morning|evening))\b|مرحب|السلام|صباح|مساء", re.I), self._greet, False),
        ]

    def handle(self, text: str, *, staff: bool = False) -> Reply:
        text = text.strip().translate(_ARABIC_DIGITS)
        lang = detect_language(text)
        if not text:
            return Reply("", lang, speak=False)
        for pattern, handler, staff_only in self._intents:
            match = pattern.search(text)
            if match:
                if staff_only and not staff:
                    return Reply(
                        "هذا الطلب مخصص لطاقم العيادة." if lang == "ar" else "That request is for clinic staff only.",
                        lang,
                    )
                return handler(match, text)
        if self._fallback and (reply := self._fallback.respond(text, lang)):
            return reply
        return Reply(
            "عذرًا، لم أفهم طلبك. يمكنني إصدار رقم انتظار، أو عرض المواعيد المتاحة، أو تقدير وقت الانتظار."
            if lang == "ar"
            else "Sorry, I didn't catch that. I can issue a queue ticket, show available slots, or estimate waiting time.",
            lang,
        )

    # ---------------------------------------------------------------- intents

    @staticmethod
    def _number_after(text: str, *words: str) -> int | None:
        m = re.search(rf"(?:{'|'.join(words)})\s*#?\s*(\d+)", text, re.I)
        return int(m.group(1)) if m else None

    def _greet(self, _m: re.Match[str], text: str) -> Reply:
        if detect_language(text) == "ar":
            return Reply(f"أهلًا وسهلًا بك في {self._s.clinic_name}. أنا أثير، كيف أخدمك؟", "ar")
        return Reply(f"Welcome to {self._s.clinic_name}. I'm Atheer — how can I help you?", "en")

    def _issue_ticket(self, _m: re.Match[str], text: str) -> Reply:
        ticket = self._queue.issue()
        ahead = len(self._queue.waiting()) - 1
        if detect_language(text) == "ar":
            return Reply(f"رقمك هو {ticket.number}. أمامك {ahead} من المراجعين. تفضل بالجلوس.", "ar")
        return Reply(f"Your number is {ticket.number}. There are {ahead} patients ahead of you. Please have a seat.", "en")

    def _call_next(self, _m: re.Match[str], text: str) -> Reply:
        room = self._number_after(text, "room", "غرفة", "عيادة")
        counter = f"Room {room}" if room else None
        ann = self._queue.call_next(counter or "Reception")
        if ann is None:
            return Reply("لا يوجد مراجعون في الانتظار." if detect_language(text) == "ar" else "The queue is empty.",
                         detect_language(text))
        # The announcement itself is spoken via the queue.called event; this reply is for the operator.
        return Reply(ann.text_ar if detect_language(text) == "ar" else ann.text_en, detect_language(text), speak=False)

    def _wait_time(self, _m: re.Match[str], text: str) -> Reply:
        lang = detect_language(text)
        number = self._number_after(text, "ticket", "number", "رقم", "الرقم")
        waiting = self._queue.waiting()
        target = next((t for t in waiting if t.number == number), None) if number else (waiting[-1] if waiting else None)
        if target is None:
            return Reply("لم أجد هذا الرقم في قائمة الانتظار." if lang == "ar" else "I couldn't find that ticket in the queue.", lang)
        est = self._queue.estimate_wait_for(target.id)
        if lang == "ar":
            return Reply(f"الوقت المتوقع للرقم {target.number} حوالي {est.expected_minutes} دقيقة.", "ar")
        return Reply(f"Estimated wait for number {target.number} is about {est.expected_minutes} minutes.", "en")

    def _free_slots(self, _m: re.Match[str], text: str) -> Reply:
        lang = detect_language(text)
        doctor_id = self._number_after(text, "doctor", "dr\\.?", "دكتور", "الدكتور", "طبيب")
        if doctor_id is None:
            return Reply("لأي طبيب؟ مثال: مواعيد الدكتور 1 غدًا." if lang == "ar" else "Which doctor? e.g. 'slots doctor 1 tomorrow'.", lang)
        day = self._clock.now().astimezone(self._s.tz).date()
        if re.search(r"tomorrow|غد", text, re.I):
            day += timedelta(days=1)
        slots = self._appts.free_slots(doctor_id, day)[:5]
        if not slots:
            return Reply("لا توجد مواعيد متاحة في ذلك اليوم." if lang == "ar" else "No free slots that day.", lang)
        times = "، ".join(s.starts_at.astimezone(self._s.tz).strftime("%H:%M") for s in slots)
        return Reply(f"المواعيد المتاحة: {times}" if lang == "ar" else f"Available times: {times}", lang)

    def _late(self, _m: re.Match[str], text: str) -> Reply:
        alerts = self._appts.running_late_alerts()
        lang = detect_language(text)
        if not alerts:
            return Reply("لا توجد مواعيد متأخرة." if lang == "ar" else "No appointments are running late.", lang, speak=False)
        # Contains patient initials: staff screen only, never public speakers.
        return Reply("\n".join(a.message for a in alerts), "en", speak=False)
