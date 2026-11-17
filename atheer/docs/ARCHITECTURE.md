# Atheer — System Architecture

## 1. Design principles

| Principle | Consequence |
|---|---|
| **The LLM talks, deterministic code decides.** | The language model only interprets intent and phrases replies. Every booking, calculation, and data access is a typed, validated Python function it calls as a tool. The model never writes SQL and never computes a dose. |
| **Clinical safety over autonomy.** | Dose checks are *verification* against a clinic-supplied formulary and always return `requires_clinician_review=True`. Atheer never prescribes. |
| **PHI stays local by default.** | STT (faster-whisper) and TTS (Piper) run on-premises. Cloud LLM/voice APIs are only enabled behind a signed BAA/DPA, and receive redacted context. |
| **Privacy-safe announcements.** | Speakers call queue numbers or "first name + last initial" — never full names, reasons for visit, or doctor specialty tied to a patient. |
| **No unattended code self-modification.** | "Self-updating" means signed *content* updates (terminology, prompts, voice models) applied in a maintenance window, with rollback. Code releases go through CI and a human-approved deploy. |
| **Event-driven proactivity.** | Domain services emit events; the receptionist layer subscribes and decides what to say or whom to alert. |

## 2. Component view

```
                ┌──────────────────────────────────────────────────────────┐
  Microphone ──►│ voice/   VAD → STT (faster-whisper) → transcript         │
  Speakers   ◄──│          TTS (Piper, AR/EN voices) ◄── utterance queue    │
                └───────────────┬──────────────────────────▲───────────────┘
                                │ text                     │ text
  Web chat / ──► api/ (FastAPI REST + WebSocket) ──┐       │
  staff UI                                         ▼       │
                ┌──────────────────────────────────────────┴───────────────┐
                │ dialogue/  Orchestrator: persona, language detection,     │
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
         │ receptionist/  queue caller, arrivals, proactive        │
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
atheer/
├── pyproject.toml
├── .env.example
├── docs/ARCHITECTURE.md
├── src/atheer/
│   ├── core/           config, clock, event bus                         [Inc 1 ✔]
│   ├── db/             models, UTC types, engine/session                 [Inc 1 ✔]
│   ├── appointments/   booking service, schemas, errors                  [Inc 1 ✔]
│   ├── calculations/   dosage, billing, wait time, inventory             [Inc 1 ✔]
│   ├── api/            FastAPI app, routers, WebSocket chat, Alembic     [Inc 2]
│   ├── voice/          audio I/O, VAD, STT, TTS, barge-in                [Inc 3]
│   ├── dialogue/       LLM orchestrator, tool registry, persona, guards  [Inc 4]
│   ├── memory/         operational context store, PHI redaction          [Inc 4]
│   ├── receptionist/   queue announcements, proactive monitors           [Inc 5]
│   └── updater/        signed bundle fetch/verify/apply/rollback         [Inc 6]
└── tests/
```

## 4. Technology choices

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.11+, asyncio | Voice + text + monitors run concurrently in one process. |
| Persistence | SQLAlchemy 2.0; SQLite → PostgreSQL | SQLite for single-desk pilots; PostgreSQL for multi-terminal concurrency (row locks, exclusion constraints). |
| Validation | Pydantic v2 | Typed boundaries for API, LLM tool arguments, and config. |
| STT | faster-whisper (`large-v3` / `medium`) | Local, accurate Arabic + English, GPU or CPU int8. |
| TTS | Piper (neural, local) | Natural voice offline. `pyttsx3` is rejected: robotic, poor Arabic. |
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

1. **Core domain** — config, DB, appointment service, calculation engine, tests. ✔
2. **API layer** — FastAPI routers, auth (staff roles), Alembic migrations, PostgreSQL exclusion constraint.
3. **Voice engine** — async audio pipeline, VAD, STT, TTS, barge-in, Arabic/English.
4. **Dialogue & memory** — LLM tool-calling orchestrator, persona, guardrails, PHI redaction, daily context.
5. **Receptionist behaviours** — queue calling, arrivals, proactive monitors wired to the event bus.
6. **Updater** — signed content bundles, maintenance window, health checks, rollback.
