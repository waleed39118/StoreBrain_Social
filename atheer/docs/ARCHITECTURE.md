# Atheer — System Architecture

## 1. Design principles

| Principle | Consequence |
|---|---|
| **The LLM talks, deterministic code decides.** | The language model only interprets intent and phrases replies. Every booking, calculation, and data access is a typed, validated Python function it calls as a tool. The model never writes SQL and never computes a dose. |
| **Clinical safety over autonomy.** | Dose checks are *verification* against a clinic-supplied formulary and always return `requires_clinician_review=True`. Atheer never prescribes. |
| **PHI stays local by default.** | Speech recognition (Whisper) and speech output (pyttsx3 / Piper) run on-premises. Cloud LLM/voice APIs are only enabled behind a signed BAA/DPA, and receive redacted context. |
| **Privacy-safe announcements.** | Speakers call queue numbers or "first name + last initial" — never full names, reasons for visit, or doctor specialty tied to a patient. |
| **No unattended code self-modification.** | "Self-updating" means signed *content* updates (terminology, prompts, voice models) applied in a maintenance window, with rollback. Code releases go through CI and a human-approved deploy. |
| **Event-driven proactivity.** | Domain services emit events; the receptionist layer subscribes and decides what to say or whom to alert. |

## 2. Component view

```
                ┌──────────────────────────────────────────────────────────┐
  Microphone ──►│ voice/   VAD → STT (Whisper) → transcript                │
  Speakers   ◄──│          TTS (pyttsx3/Piper, AR/EN) ◄── utterance queue   │
                └───────────────┬──────────────────────────▲───────────────┘
                                │ text                     │ text
  Web chat / ──► api/ (FastAPI REST + WebSocket) ──┐       │
  staff UI                                         ▼       │
                ┌──────────────────────────────────────────┴───────────────┐
                │ assistant/ Orchestrator: persona, language detection,     │
                │            LLM tool-calling, guardrails, PHI redaction    │
                └───┬───────────────┬──────────────────┬───────────────────┘
                    │ tools         │ tools            │ context
         ┌──────────▼───┐  ┌────────▼────────┐  ┌──────▼──────────┐
         │appointments/ │  │ calculations/   │  │ memory/         │
         │ booking,     │  │ dosage, billing,│  │ daily ops log,  │
         │ conflicts,   │  │ wait time,      │  │ redacted patient│
         │ reminders    │  │ inventory       │  │ summaries       │
         └──────┬───────┘  └─────────────────┘  └──────┬──────────┘
                │ events (core/events.EventBus)        │
         ┌──────▼──────────────────────────────────────▼──────────┐
         │ queue/  ticket caller, arrivals, proactive        │
         │                monitors (late, VIP, conflicts)          │
         └──────────────────────────┬─────────────────────────────┘
                                    │
         ┌──────────────────────────▼─────────────────────────────┐
         │ db/  SQLAlchemy 2.0 — SQLite (dev) / PostgreSQL (prod)  │
         └────────────────────────────────────────────────────────┘
         updater/  signed content bundles, maintenance window, rollback
```

## 3. Folder structure

```
src/atheer/
├── runtime.py      composition root (Atheer.build) + `atheer` console
├── secretary.py    SecretaryCore: check-in & greeting, queue calling, doctor announcements, booking
├── admin.py        `atheer-admin` CLI
├── api/            FastAPI app, routes (REST + WebSocket), staff API key, check-in rate limiting
├── voice/          VoiceEngine (speaker queue, listening); Whisper / pyttsx3 / Piper engines; mic + VAD
├── calculations/   CalcEngine + hot-reloadable formulary; dosage, billing, wait time, stock
├── updater/        AutoUpdater (hot reload, auto-rollback); signed bundles; TerminologyStore
├── licensing/      Ed25519-signed subscription licenses; grace period; doctor limit
├── appointments/   booking, state machine, reminders, late/VIP/conflict alerts
├── queue/          daily tickets, call-next, AR/EN announcements, wait estimates
├── assistant/      bilingual intent router, staff/public gating
├── db/             models, UTC types, engine/session
└── core/           config, clock, event bus
```

### The four core classes

| Class | Owns | Delegates to |
|---|---|---|
| `VoiceEngine` | Speaker queue (thread-safe `say()`), transcription confidence gate, microphone loop | `WhisperSTT` / `OpenAIWhisperSTT`, `Pyttsx3TTS` / `PiperTTS` |
| `SecretaryCore` | Check-in identity check and greeting, staff alert feed, announcements | `AppointmentService`, `QueueService`, `Brain`, `VoiceEngine` |
| `CalcEngine` | Clinic formulary (atomic swap on reload) | `calculations.dosage / billing / operations` |
| `AutoUpdater` | Update scheduling, hot-reload listeners, rollback on rejection | `ContentUpdater` (signature, hashes, staging, atomic pointer) |

## 4. Technology choices

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.11+, asyncio | Voice + text + monitors run concurrently in one process. |
| Persistence | SQLAlchemy 2.0; SQLite → PostgreSQL | SQLite for single-desk pilots; PostgreSQL for multi-terminal concurrency (row locks, exclusion constraints). |
| Validation | Pydantic v2 | Typed boundaries for API, LLM tool arguments, and config. |
| STT | Whisper via faster-whisper (default) or openai-whisper | Same model weights; faster-whisper is ~4x faster and avoids PyTorch. |
| TTS | pyttsx3 (system voices) or Piper (neural) | pyttsx3 needs no downloads and uses OS voices (Arabic via the Windows language pack); Piper sounds more natural. |
| VAD | webrtcvad | Cheap end-of-utterance detection and barge-in. |
| LLM | Provider-agnostic tool-calling interface | Swap local/cloud models without touching business logic. |
| API | FastAPI + WebSocket | Staff dashboard, kiosk chat, integrations. |

## 5. Concurrency and integrity

* All datetimes are timezone-aware and stored in UTC (`db.types.UTCDateTime`); the clinic timezone is applied only for shift checks and speech.
* Booking locks the doctor and patient rows (`SELECT … FOR UPDATE` on PostgreSQL; SQLite serialises writers) before the overlap check, preventing double-booking races.
* `Appointment.version_id` provides optimistic locking for concurrent edits from multiple desks.
* Status changes follow an explicit state machine (`appointments.service.ALLOWED_TRANSITIONS`).
* Events are published **after** commit, so listeners never act on rolled-back data.

## 6. Delivery increments

1. Core domain, queue, calculations, voice engines ✔
2. Assistant brain + runtime ✔
3. Signed content updater ✔
4. Tests, schema, requirements ✔
5. Admin CLI, Arabic install guide ✔
6. FastAPI server, the four core classes, pyttsx3 / OpenAI Whisper engines, hot reload, review fixes ✔
7. **Possible next:** Alembic migrations + PostgreSQL exclusion constraint, per-user staff accounts and audit log, LLM fallback with tool-calling and PHI-redacted context.
