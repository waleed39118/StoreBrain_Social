# Atheer (أثير) — سجل خطوات العمل / Work Log

Each step is committed and pushed separately so work can be resumed from any point.
كل خطوة تُحفظ في commit مستقل وتُرفع مباشرة، ليمكن استئناف العمل من أي نقطة.

| # | Step / الخطوة | Status |
|---|---|---|
| 1 | Architecture, config, DB models (SQLite/PostgreSQL), appointment service, queue service, calculation engine, voice engines | ✅ committed |
| 2 | Assistant brain (AR/EN intents, staff gating) + runtime wiring text & voice loops | ✅ committed |
| 3 | Signed self-update mechanism (content bundles, rollback) | ✅ committed |
| 4 | Tests, `requirements.txt`, `schema.sql`, README | ⏳ |

## How to resume / طريقة الاستئناف

```bash
git fetch origin claude/youthful-planck-3agwbh
git checkout claude/youthful-planck-3agwbh
cd atheer && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
