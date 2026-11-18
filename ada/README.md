# Ada (أدا) — Smart Store Assistant & Inventory Manager

A voice and text shop assistant (Arabic and English) built on FastAPI, SQLite, SQLAlchemy 2, Pandas, Whisper, pyttsx3 and Telegram.

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
│   └── services/telegram_notifier.py
└── tests/
```

## Schema
| Table | Purpose |
|---|---|
| `products` | catalog, live `stock_qty` (CHECK ≥ 0), reorder policy, condition, expiry |
| `sales` / `sale_items` | receipts; line price snapshotted at sale time |
| `stock_movements` | append-only audit ledger of every stock change |
| `alerts` | sent owner alerts; per-SKU cooldown dedup |
| `catalog_patches` | applied patch versions (idempotency) |

## Run
```bash
sudo apt-get install -y ffmpeg espeak-ng      # Whisper + pyttsx3 system deps
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                           # set ADA_API_KEY, Telegram, updater
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

## Key endpoints (header `X-API-Key`)
- `POST /api/v1/ada/chat` `{"text":"بيع 2 حليب","speak":true}`
- `POST /api/v1/ada/voice` (multipart `audio`) → transcript, reply, `audio_url`
- `POST /api/v1/sales`, `POST /api/v1/products`, `POST /api/v1/products/{sku}/restock`
- `GET /api/v1/analytics/{best-sellers|conditions|obsolete|reorder|diversification}`
- `POST /api/v1/system/patches` (push) or set `ADA_UPDATER_URL` (pull)

## Engineering notes
- **No overselling:** stock is changed with a conditional `UPDATE … WHERE stock_qty >= q`, and a multi-line sale runs in one transaction.
- **SQLite transactions:** uses the official SQLAlchemy recipe (pysqlite implicit transactions disabled), so SAVEPOINTs and dry-runs roll back correctly. Writes start with `BEGIN IMMEDIATE`, so concurrent sales wait their turn instead of failing with `database is locked`.
- **Ada never makes up numbers:** intent parsing is rule-based, and every figure she gives comes from the database. An LLM can be added behind `parse_intent` later.
- **Self-updating covers data only, never code.** Patches need a valid HMAC-SHA256 signature, are applied once per version, are atomic, and run in the background without downtime.
- **Voice:** models load the first time they are used, and calls are serialised in worker threads so the event loop never blocks.
