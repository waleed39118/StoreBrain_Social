# Security — Ada

No software can honestly be called "impossible to hack". Ada is built with defence in depth, so that a single mistake doesn't become a breach. This document lists what is protected, how, and the remaining risks the operator should manage.

## Protections

**Identity and sessions**
- **Owner:** only `ADA_OWNER_PHONE` can sign in, using a 6-digit SMS code.
  - Codes are stored as HMAC hashes, expire in 5 minutes, allow 5 attempts and are single-use.
  - Requesting a new code invalidates the old one. There is a 60-second resend cooldown and a cap of 5 codes per hour.
  - Every number gets the same response, so registered numbers can't be discovered.
- **Staff:** phone + PIN.
  - PINs are hashed with scrypt (N=2¹⁴, r=8), trivially guessable PINs are rejected, and checks take the same time whether or not the user exists.
  - Lockout is progressive: 15 min, then 30, then 60, up to 24 h.
- **Rate limiting:** sign-in endpoints allow 30 attempts per IP per minute.
- **Sessions:** 256-bit random bearer tokens, one per device. Only keyed hashes are stored. Sessions expire, can be revoked one by one or all at once, and are revoked automatically when a staff member is disabled or their PIN or role changes.
- **Roles:** owner, manager and cashier, enforced on every route *and* on chat/voice intents, so the assistant can't be used to bypass them.

**Web**
- Strict CSP: `default-src 'self'`, no inline scripts, no third-party origins. Vendored libraries are pinned and their sha256 checksums recorded in `web/vendor/README.md`.
- XSS-safe rendering: the UI never uses `innerHTML`, and every value goes through `textContent`.
- Security headers: `nosniff`, `frame-ancestors 'none'`/`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`, COOP/CORP, and HSTS from Caddy.
- No CORS and no cookies, so cross-site request forgery doesn't apply.
- API docs are off by default, and API responses are `Cache-Control: no-store`. The service worker never caches API data.
- Request bodies are capped at 12 MB, counted while streaming so chunked uploads can't bypass the limit. Caddy enforces the same cap.

**Data and input**
- SQL goes only through SQLAlchemy bound parameters. SQLite runs with WAL and foreign keys, and writes use `BEGIN IMMEDIATE`.
- Stock can't go negative (a database CHECK plus a conditional `UPDATE`), and sales are idempotent (`client_ref`). Prices always come from the server, never from the till.
- Excel/CSV imports are parsed with defusedxml, under size and row limits, validated before anything is written, and applied atomically.
- File paths for audio and backups are checked against strict name patterns, so path traversal isn't possible.

**SMS gateway (Android)**
- HTTPS only, system CAs only, no redirects. The token is encrypted with an Android Keystore AES-GCM key and excluded from backups.
- The phone enforces a recipient allow-list from the pairing QR (the owner's number only) and a local 30-per-hour cap. Even a compromised server can't use the SIM to text other numbers.
- The server wipes the message text once it is sent, and expired codes are never sent.

**Local AI**
- The model URL must be loopback, a private address or the compose-internal host, so conversations never go to a cloud API.
- Output must match a fixed schema and is validated. The model holds no data authority, and small-talk replies containing digits are discarded.

**Updates and supply chain**
- Catalog patches must carry an HMAC-SHA256 signature, are applied once per version and atomically, and update data only, never code.
- Dependencies are scanned in CI (pip-audit, Bandit, Semgrep), and the Gradle wrapper is validated.
- The container runs as a non-root user, with a read-only root filesystem, all capabilities dropped and `no-new-privileges`. Ollama isn't exposed outside the private network.

## Results of this release's checks
| Check | Result |
|---|---|
| pytest (API, auth, POS, import, migrations, LLM, security) | 53 passed |
| Playwright E2E (login by SMS code, POS, offline sync, chat, dashboard, settings, mobile) | passed |
| Offline app shell + vendored ZXing under the strict CSP | passed |
| Bandit | 0 issues |
| pip-audit (core requirements) | no known vulnerabilities |
| npm audit (vendored JS libraries) | 0 vulnerabilities |
| Semgrep | runs in CI (its rules registry was unreachable from the build sandbox) |

## Operator responsibilities (residual risks)
1. Keep the server patched: `apt upgrade`, then `git pull && ./install.sh` to update Ada.
2. Keep `.env` private (it is created with mode 600). Rotating `ADA_AUTH_SECRET` signs everyone out. Rotating `ADA_SMS_GATEWAY_TOKEN` requires re-pairing the phone.
3. Protect the gateway phone: screen lock, and no other apps with SMS permission.
4. Protect the owner's SIM against SIM-swap fraud: ask your carrier for a port-out PIN. Anyone who controls that number can receive the sign-in codes.
5. Copy backups off the server regularly (Settings → Backups → Download).
6. Expose only ports 80 and 443. Don't publish the Ada or Ollama ports directly.
7. For a release, sign the APK with your own keystore (the `ADA_KEYSTORE_*` variables in CI).

Report vulnerabilities privately to the repository owner rather than in a public issue.
