#!/usr/bin/env bash
# Starts an isolated Ada server for end-to-end tests (fresh DB each run).
set -euo pipefail
DIR="${E2E_DIR:-$(mktemp -d)}"
cd "$(dirname "$0")/../.."
export ADA_DATABASE_URL="sqlite:///$DIR/e2e.db" ADA_BACKUP_DIR="$DIR/backups" ADA_TTS_OUTPUT_DIR="$DIR/tts" \
  ADA_AUTH_SECRET="e2e-secret-e2e-secret-e2e-secret-e2e-secret" ADA_OWNER_PHONE="0551234567" \
  ADA_SMS_PROVIDER=outbox ADA_SMS_GATEWAY_TOKEN="gateway-token-gateway-token-gateway-token" \
  ADA_SETUP_CODE="setup-code-1234" ADA_OTP_RESEND_COOLDOWN_SEC=10
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}" --log-level warning
