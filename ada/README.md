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
uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest -q
```

## Key endpoints (header `X-API-Key`)
- `POST /api/v1/ada/chat` `{"text":"بيع 2 حليب","speak":true}`
- `POST /api/v1/ada/voice` (multipart `audio`) → transcript, reply, `audio_url`
- `POST /api/v1/sales`, `POST /api/v1/products`, `POST /api/v1/products/{sku}/restock`
- `GET /api/v1/analytics/{best-sellers|conditions|obsolete|reorder|diversification}`
- `POST /api/v1/system/patches` (push) or set `ADA_UPDATER_URL` (pull)

## Engineering notes
- **No overselling:** stock is changed with a conditional `UPDATE … WHERE stock_qty >= q`, and a multi-line sale runs in one transaction.
- **Ada never makes up numbers:** intent parsing is rule-based, and every figure she gives comes from the database. An LLM can be added behind `parse_intent` later.
- **Self-updating covers data only, never code.** Patches need a valid HMAC-SHA256 signature, are applied once per version, are atomic, and run in the background without downtime.
- **Voice:** models load the first time they are used, and calls are serialised in worker threads so the event loop never blocks.
