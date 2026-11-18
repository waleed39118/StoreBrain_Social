# Ada (أدا) — Smart Store Assistant & Inventory Manager

A voice and text shop assistant (Arabic and English) built on FastAPI, SQLite, SQLAlchemy 2, Pandas, Whisper and pyttsx3. It makes no third-party integrations unless the owner explicitly configures one.

## Structure
```
ada/
├── app/
│   ├── main.py                  # FastAPI app + lifespan (starts AutoUpdater)
│   ├── config.py                # typed settings (ADA_* env vars)
│   ├── database.py              # engine (SQLite WAL), sessions
│   ├── models.py                # schema
│   ├── schemas.py               # API contracts
│   ├── api/{deps,routes}.py     # auth + endpoints
│   ├── core/
│   │   ├── voice_engine.py      # VoiceEngine  (Whisper STT / pyttsx3 TTS)
│   │   ├── inventory_manager.py # InventoryManager (atomic sales, alerts)
│   │   ├── market_analytics.py  # MarketAnalytics (Pandas)
│   │   ├── auto_updater.py      # AutoUpdater (signed catalog patches)
│   │   └── assistant.py         # Ada persona + bilingual intent parsing
│   ├── core/security.py         # phone normalisation, scrypt PINs, keyed token hashes
│   ├── api/auth_routes.py       # auth, staff, notifications, SMS gateway
│   └── services/{auth_service,sms,catalog_import}.py
└── tests/
```

## Schema
| Table | Purpose |
|---|---|
| `products` | catalog, live `stock_qty` (CHECK ≥ 0), reorder policy, condition, expiry |
| `sales` / `sale_items` | receipts; line price snapshotted at sale time |
| `stock_movements` | append-only audit ledger of every stock change |
| `alerts` | in-app notifications (read state); per-SKU cooldown dedup |
| `users` | owner (phone + SMS code) and staff (phone + PIN), with roles |
| `auth_sessions` | one revocable session per device; only token hashes are stored |
| `otp_codes` | hashed, expiring, attempt-limited SMS codes |
| `sms_outbox` | queued SMS for the owner's Android gateway phone; text wiped after send |
| `catalog_patches` | applied patch versions (idempotency) |

## Run
```bash
sudo apt-get install -y ffmpeg espeak-ng      # Whisper + pyttsx3 system deps
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                           # set ADA_AUTH_SECRET, ADA_OWNER_PHONE, SMS gateway
uvicorn app.main:app --host 0.0.0.0 --port 8000   # applies pending migrations on boot
pytest -q
```

## Database migrations (Alembic) — ترحيلات قاعدة البيانات
The app runs `alembic upgrade head` automatically at startup. Workflow for any future schema change:
```bash
# 1) edit app/models.py   2) generate + REVIEW the migration   3) apply
alembic revision --autogenerate -m "add supplier table"
alembic upgrade head
alembic check            # CI guard: fails if models and migrations drift
alembic downgrade -1     # roll back one revision
```
- `render_as_batch=True`: ALTER/DROP work on SQLite, and the same migrations run on PostgreSQL later.
- Constraint naming convention, plus enums stored as values in a fixed-width column, so new enum members never need a migration.
- `tests/test_migrations_import.py` fails if a model changes without a migration.

## Updating the product catalog — طرق تحديث قائمة المنتجات
| Method | Endpoint |
|---|---|
| Manual add / edit | `POST /api/v1/products`, `PATCH /api/v1/products/{sku}` |
| Barcode scan (USB/Bluetooth scanner, or camera in the UI) | `GET /api/v1/products/by-barcode/{code}`, with EAN/UPC check-digit validation |
| Excel / CSV | `POST /api/v1/products/import` (`dry_run`, `stock_mode=set\|add`, `skip_invalid`) |
| Excel template | `GET /api/v1/products/import/template` |
| Signed catalog patches | `POST /api/v1/system/patches` or pull mode |

Import accepts Arabic or English headers (`الرمز`, `الباركود`, `اسم المنتج`, `السعر`, `الكمية`…) and CSV encoded as UTF-8 or Windows-Arabic (cp1256). It validates every row first: one bad row rejects the whole file and reports each error with its Excel row number.

## Authentication & roles — تسجيل الدخول والصلاحيات
- **Owner:** only `ADA_OWNER_PHONE` can sign in, with a 6-digit SMS code: `POST /auth/otp/request` then `/auth/otp/verify`, which returns a bearer token. The owner account is created on the first successful sign-in.
- **Staff:** the owner creates them (`POST /users`, role `manager` or `cashier`). They sign in with phone + PIN (`POST /auth/pin/login`), so no SMS is sent at the till.
- Codes expire after 5 minutes, allow 5 attempts, are single-use, have a 60 s resend cooldown and a 5/hour cap. PINs are hashed with scrypt and lock for 15 minutes after 5 failures. Requesting a code returns the same response for every number, so nobody can probe which numbers are registered.
- Sessions are per device and can be revoked (`/auth/sessions`, `/auth/logout-all`). Disabling a staff member or changing their PIN or role logs them out everywhere.

| Role | Can do |
|---|---|
| cashier | sell, look up products and barcodes, stock levels, chat with Ada (sell, stock and best-seller requests only) |
| manager | the cashier's permissions, plus products, restock, import, analytics and notifications |
| owner | everything, plus staff management and updater status |

## SMS without a third party — إرسال الرسائل دون طرف ثالث
The cloud server has no SIM card, so it queues each SMS in `sms_outbox`. The owner's Android phone, with a SIM, acts as the gateway:
```
POST /api/v1/sms-gateway/claim         (header X-Gateway-Token) -> [{id, phone, body}]
POST /api/v1/sms-gateway/{id}/ack      {"ok": true}             -> message text is wiped
```
Unacked messages are re-offered after 2 minutes. Expired codes are never sent. To use an SMS provider you authorise instead, set `ADA_SMS_PROVIDER=http`.

## Key endpoints (header `Authorization: Bearer <token>`)
- `POST /api/v1/ada/chat` `{"text":"بيع 2 حليب","speak":true}`
- `POST /api/v1/ada/voice` (multipart `audio`) → transcript, reply, `audio_url`
- `POST /api/v1/sales`, `POST /api/v1/products`, `POST /api/v1/products/{sku}/restock`
- `GET /api/v1/analytics/{best-sellers|conditions|obsolete|reorder|diversification}`
- `GET /api/v1/notifications?after_id=` (poll), `/unread-count`, `/{id}/read`, `/read-all`
- `POST /api/v1/system/patches` (push, HMAC-signed, no user session) or set `ADA_UPDATER_URL` (pull)

## Engineering notes
- **No overselling:** stock is changed with a conditional `UPDATE … WHERE stock_qty >= q`, and a multi-line sale runs in one transaction.
- **SQLite transactions:** uses the official SQLAlchemy recipe (pysqlite implicit transactions disabled), so SAVEPOINTs and dry-runs roll back correctly. Writes start with `BEGIN IMMEDIATE`, so concurrent sales wait their turn instead of failing with `database is locked`.
- **Ada never makes up numbers:** intent parsing is rule-based, and every figure she gives comes from the database. An LLM can be added behind `parse_intent` later.
- **Self-updating covers data only, never code.** Patches need a valid HMAC-SHA256 signature, are applied once per version, are atomic, and run in the background without downtime.
- **Voice:** models load the first time they are used, and calls are serialised in worker threads so the event loop never blocks.
