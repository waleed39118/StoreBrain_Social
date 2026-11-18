#!/usr/bin/env bash
# Ada one-command installer (Ubuntu/Debian server with Docker).
#   curl -fsSL <your-copy>/install.sh | bash      or      ./install.sh
# Asks for your domain and the owner's mobile number, generates all secrets, starts the
# stack with automatic HTTPS and local AI, and prints the first-run setup code.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 — install it first (https://docs.docker.com/engine/install/)"; exit 1; }; }
need docker; need openssl
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required"; exit 1; }

if [[ -f .env ]]; then
  say "A .env already exists — keeping your secrets and data. Updating the app…"
else
  say "أدا — Ada installer"
  read -rp "Domain pointing to this server (e.g. shop.example.com): " DOMAIN
  read -rp "Owner mobile number (e.g. +9665XXXXXXXX): " OWNER
  read -rp "Country calling code for local numbers [966]: " CC; CC=${CC:-966}
  read -rp "Enable on-server voice recognition (Whisper, ~2 GB)? [y/N]: " VOICE
  read -rp "Local AI model [qwen2.5:3b] (use qwen2.5:7b on 16 GB+ RAM): " MODEL; MODEL=${MODEL:-qwen2.5:3b}
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo "Invalid domain"; exit 1; }
  [[ "$OWNER" =~ ^\+?[0-9]{8,15}$ ]] || { echo "Invalid phone number"; exit 1; }
  rand() { openssl rand -base64 "$1" | tr -d '\n/+=' | cut -c1-"$2"; }
  SETUP_CODE="$(rand 12 4)-$(rand 12 4)-$(rand 12 4)"
  umask 077
  cat > .env <<ENV
ADA_DOMAIN=${DOMAIN}
ADA_OWNER_PHONE=${OWNER}
ADA_DEFAULT_COUNTRY_CODE=${CC}
ADA_AUTH_SECRET=$(rand 64 64)
ADA_SMS_PROVIDER=outbox
ADA_SMS_GATEWAY_TOKEN=$(rand 48 48)
ADA_SETUP_CODE=${SETUP_CODE}
ADA_UPDATER_HMAC_SECRET=$(rand 48 48)
ADA_LLM_ENABLED=true
ADA_LLM_MODEL=${MODEL}
ADA_WITH_VOICE=$([[ "${VOICE,,}" == y* ]] && echo 1 || echo 0)
ENV
  chmod 600 .env
fi

set -a; source .env; set +a
say "Building and starting Ada…"
docker compose up -d --build
say "Downloading the local AI model (${ADA_LLM_MODEL}) — first time only…"
docker compose exec -T ollama ollama pull "${ADA_LLM_MODEL}" || echo "AI model download failed — Ada keeps working with rules; rerun ./install.sh later."

say "✅ Ada is running:  https://${ADA_DOMAIN}"
cat <<MSG

  1) افتح الرابط أعلاه ← «الإعداد لأول مرة» ← أدخل رمز الإعداد:   ${ADA_SETUP_CODE}
     Open the link → "First-time setup" → enter the setup code above.
  2) ثبّت تطبيق «بوابة رسائل أدا» (APK) على هاتف أندرويد بشريحة، وامسح رمز الربط.
     Install the Ada SMS Gateway APK on an Android phone with a SIM and scan the QR.
  3) سجّل الدخول برقمك ${ADA_OWNER_PHONE} — سيصلك رمز التحقق برسالة.
     Sign in with ${ADA_OWNER_PHONE}; the code arrives by SMS.
  4) على كل جهاز (آيباد/لابتوب/نقطة بيع): افتح الرابط ← «تثبيت التطبيق».
     On each device: open the link → "Install app".

  Backups: automatic daily (Settings → Backups). Update later: git pull && ./install.sh
MSG
