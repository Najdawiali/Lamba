# Lamba — project instructions for Claude Code

Lamba (لمبة) is a hyper-local discovery app for Jordan, Arabic first. Customers search for a
product or service and see which nearby shops have it (price, distance, map, chat). Merchants
list stock by scanning barcodes against a shared catalog. Status: pre-launch, preparing a
Google Play closed test. Owner: Ali, founder and sole developer.

## Working agreement
- Before a significant change, explain briefly: what's wrong, why it matters, the fix, its impact.
  When there are options, compare them and give a recommendation.
- Preserve working code. No refactoring without a clear benefit.
- Before recommending anything that costs money or depends on third-party rules (Meta/WhatsApp,
  Google Play, carriers, app stores), check the current official docs first.
- Never run commands on the production server or database without asking first.
- Never print, log or commit secrets (.env files, tokens, keystore passwords).
- Ali prefers step-by-step guidance for anything done outside the repo (dashboards, server).

## Repository layout
- `backend/` FastAPI (Python 3.13), SQLAlchemy async, Alembic, Docker.
  - `app/api/*_v1.py` routers: auth, customer, merchant, search, chat, reports, account, legal.
  - `app/services/`: llm (DeepInfra adapter), embedding, reranker, query_understanding,
    item_classifier (restriction + category), item_enrichment, whatsapp_service, password_policy,
    signin_throttle.
  - `app/taxonomy.py`: single source of truth for categories and store types.
  - `app/legal_content.py`: privacy policy and terms (served at /privacy, /terms; mirrored into
    `mobile/constants/legal.ts`; edit here, then regenerate the mobile copy). There is no generator
    script in the repo: legal.ts is its 8-line header comment, then each `DOCS` entry in order as a
    backtick-quoted template-literal export (`export const NAME = ...;`) holding `to_plain_text(doc)`,
    separated by blank lines, LF endings. The privacy policy has its own date (`PRIVACY_UPDATED_*`).
  - `app/jobs/import_catalog.py`, `app/moderation_cli.py`: server-side jobs and tools.
  - `backend/scripts/` is NOT in the Docker image (.dockerignore). Anything that must run on the
    server belongs in `app/`.
  - `evals/`: offline classifier evaluation (data lives on the server in /opt/lamba/eval_data).
- `mobile/` Expo SDK 54, React Native 0.81 (New Architecture), expo-router, TypeScript.
  - `android/` is committed (bare workflow). Do NOT run `expo prebuild`: native changes go directly
    into `android/` (app.json alone does not reach the APK).
- `website/` static homepage for lambajo.com (Cloudflare Workers static assets, uploaded in the
  Cloudflare dashboard). `_redirects` maps /privacy, /terms, /account-deletion to the API.
- `docker-compose.yml` (root; used on the server and locally): `postgres` (built from
  `backend/Dockerfile.postgres`), `redis` (password, 256 MB LRU) and `api` (built from `backend/`,
  reads `backend/.env`, mounts `backend/uploads`). Only `api` publishes a port: 127.0.0.1:8000.
  `POSTGRES_PASSWORD` and `REDIS_PASSWORD` come from the shell or a git-ignored root `.env`.
  Legacy names remain: containers `eagle_*`, database `eagle_vision`, user `eagle`.
- `Caddyfile` (root): reference copy of the server's Caddy config, only the `api.lambajo.com` block
  (-> localhost:8000, security headers); no lambajo.com/www block, Cloudflare serves the homepage.
  Source of truth: `/etc/caddy/Caddyfile` on the server, edited there directly. The repo copy may
  lag, so compare before copying anything over the live file.
- `scripts/` (root, not `backend/scripts/`):
  - `backup-db.sh`: server only (hard-coded `/opt/lamba`), the script behind the daily backup cron:
    `pg_dump` of `eagle_vision` via `docker compose exec`, gzipped to
    `/opt/lamba/backups/lamba_<time>.sql.gz`; drops an empty dump, deletes files older than 7 days.
    Keep mode 100755: a lost exec bit once broke the cron after `git pull`.
  - `start-mobile.js`: behind `npm run mobile:start` / `mobile:tunnel`. Writes
    `EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8000` to the git-ignored
    `mobile/.env.development.local` (replaced each run), then runs `npx expo start`. Expo reads
    that file only in development mode, so release builds keep using `mobile/.env`, which the
    script never touches.
- `package.json` (root, "lamba-workspace"): no dependencies, only npm shortcuts: `services:*` and
  `backend:*` wrap docker compose, `mobile:start` / `mobile:tunnel` run `scripts/start-mobile.js`.
  Not used by the build, deploy or backup workflows in this file; README.md presents it as the
  local dev quick start.

## Production
- Server: Hetzner 4 GB Ubuntu, `ssh root@167.233.213.93`, project in `/opt/lamba`.
  Docker Compose: `api` (container eagle_api), `postgres` (PostGIS + pgvector), `redis`.
  Caddy (system service, /etc/caddy/Caddyfile) serves only api.lambajo.com -> localhost:8000.
- Domains: api.lambajo.com (API and legal pages), lambajo.com + www (homepage),
  images.lambajo.com (Cloudflare R2 bucket `lamba-images`).
- Client IP behind Caddy: api.lambajo.com is DNS-only (no Cloudflare), and Caddy (default
  `reverse_proxy`, no `trusted_proxies`; live Caddyfile checked 2026-10-06) overwrites
  X-Forwarded-For with the real client IP. Caddy reaches `api` through the Docker bridge gateway
  (network `lamba_default` = 172.18.0.0/16, gateway 172.18.0.1), so uvicorn trusts proxy headers only
  from `FORWARDED_ALLOW_IPS=127.0.0.1,172.16.0.0/12` (docker-compose.yml). Without it every request
  looks like 172.18.0.1 and slowapi's per-IP limits are global. Keep the API port on 127.0.0.1,
  never use `*`, and revisit this if Cloudflare is ever put in front of the API.
- AI on DeepInfra, prepaid credit. If credit runs out, every AI call fails with HTTP 402
  (search degrades, new products go to review). Models: query understanding gemma-4-E4B,
  expansion gemma-4-26B-A4B, embeddings Qwen3-Embedding-0.6B (1024-d), reranker
  Qwen3-Reranker-4B, enrichment gemma-4-31B, classifier = ensemble of gemma-4-26B-A4B and
  gemma-4-31B (approve only when both answer "allowed"; any flag or failure -> review).
- Email: Resend sends codes (noreply@lambajo.com); support@lambajo.com via Cloudflare Email Routing.
- Backups: daily 03:00 cron to /opt/lamba/backups, 7-day retention.
- Docker logs: json-file capped at 10 MB x 5 files per container (`x-logging` in docker-compose.yml),
  so old lines are deleted automatically and the disk cannot fill up. The api logs contain client IPs
  (the privacy policy says so). A container gets the cap when it is recreated: `api` at the next
  deploy, postgres and redis only when they are recreated too.

Deploy on the server:
```bash
cd /opt/lamba && git pull origin main
docker compose build api
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d --force-recreate api
```
Schema changes only through Alembic migrations (`backend/alembic/versions/`), never create_all.

## Build and checks (Windows dev machine, PowerShell)
- Type check: `cd mobile; npx tsc --noEmit` must print nothing.
- APK: `cd mobile\android; .\gradlew.bat assembleRelease --no-daemon`
  -> `app\build\outputs\apk\release\app-release.apk`. Google Play needs an .aab (`bundleRelease`).
- Release builds inline `EXPO_PUBLIC_API_URL` from the git-ignored `mobile/.env`, which must hold
  `EXPO_PUBLIC_API_URL=https://api.lambajo.com`. If it is missing, the app falls back to
  `http://localhost:8000`. `scripts/start-mobile.js` never touches this file.
- Add native packages with `npx expo install <pkg>` (SDK-compatible versions), then rebuild.
- Windows long paths: `LongPathsEnabled=1`, and `android/app/build.gradle` (defaultConfig) points
  CMake at ninja 1.12 from Android SDK CMake 3.31.6. Both are required for New Architecture native
  libraries; keep them. If a build fails mid-way, delete `android\app\.cxx`, `android\app\build`,
  `android\build` (gradle clean can fail on a half-built tree).
- Signing: upload keystore lives outside the repo; credentials in `~/.gradle/gradle.properties`
  (LAMBA_UPLOAD_*). Package name `com.lamba.app` is permanent once uploaded to Play.

## Conventions and gotchas
- Line endings are mixed (many files CRLF, some LF). Preserve each file's own style; never convert
  a whole file. If `git diff --stat` shows hundreds of lines for a small edit, endings changed.
- Never commit `__pycache__` / `.pyc`.
- `mobile/locales/ar.json` and `en.json`: CRLF, no trailing newline. Edit entries in place; do not
  re-serialize the whole file.
- Server user-facing errors are bilingual ("Arabic\nEnglish"). The app shows one language via
  `mobile/utils/serverMessage.ts`. Rate-limit 429s follow the same shape (`app/rate_limit.py` answers
  `{"detail": ...}`; slowapi's default `{"error": ...}` is not shown by the app); `login.tsx` shows
  that message and falls back to its own text.
- Phone sign-in is OFF on purpose: `mobile/constants/features.ts` PHONE_AUTH_ENABLED=false and
  backend `PHONE_SIGNUP_ENABLED=false`. WhatsApp codes are built (`whatsapp_service.py`, number
  registered) but Meta only allows authentication templates for verified businesses. Turn both
  switches on together after business verification.
- Passwords (`app/services/password_policy.py`): min 8, max 72, English-keyboard characters only,
  blocklist (SecLists 10k), patterns, personal details; applied at sign-up and reset, never at
  sign-in. Mirrored for instant feedback in `components/auth/PasswordRules.tsx`; the server decides.
- Forms with text fields use `components/KeyboardForm.tsx` (react-native-keyboard-controller).
  Android 16 is edge-to-edge, so the old adjustResize no longer works. `KeyboardProvider` is in
  `app/_layout.tsx` with statusBarTranslucent and navigationBarTranslucent.
- Code entry uses `components/auth/OtpInput.tsx` (real input laid over the boxes).
- Moderation: `global_items.moderation_status` approved | pending_review | blocked. Customers only
  ever see approved products. Review tool:
  `docker compose run --rm --no-deps api python -m app.moderation_cli pending|reports|approve <id>|block <id>`
- Catalog: 10,508 products with GTIN-14 barcodes (`app/utils/barcode.py` normalizes scans).
  Batch jobs must wait out an open circuit breaker and retry, never fast-fail the queue.
- Merchant photos: the first photo of a catalog product becomes its catalog photo
  (POST /api/v1/merchant/items/{id}/photos); required in the scanner when a product has none.
- Sign-in throttle (`app/services/signin_throttle.py`): 10 failed sign-ins per account within 15
  minutes (fixed window from the first failure) -> HTTP 429 with a bilingual message and Retry-After.
  This is the per-account limit NIST SP 800-63B-4 3.2.2 asks for; slowapi's limits are per IP and
  separate. Counters are Redis keys `signin_fail:<sha256 of lower-cased email / normalised phone>`;
  unknown accounts are counted the same (no account enumeration); a correct password or a password
  reset clears the counter; if Redis is down it fails open (warning logged). The `/verify` and
  `/reset-password` codes have their own 5-attempt counters.
- Redis client (`get_redis()` in `app/services/cache.py`): redis-py's default retry policy is switched
  off (`_NO_RETRY`). With it on (10 retries with backoff in redis-py 8.1) one call to an unreachable
  Redis took 3 to 20+ seconds despite the 0.5 s timeouts; now a failure costs at most ~0.5 s.
  `requirements.txt` leaves `redis>=5.0.0` unpinned, so a rebuilt image gets the newest version.

## Status (keep this section current)
Done: security hardening, Alembic migrations, taxonomy, classifier ensemble, merchant flow fixes,
report button, account deletion (in app + web page), legal pages, catalog import and enrichment,
images.lambajo.com, homepage, password policy, email-only auth with keyboard/code-entry fixes.

In progress: phone test of the auth fixes; Google Play personal developer account (identity
verification pending; personal accounts need a 14-day closed test with 12+ testers).

Next before the closed test: review the ~49 held products; monitoring alert for AI/credit
failures; build the .aab; create review test accounts for Play "App access"; Play data safety form.

Later: register Lamba as a business (unlocks Meta verification for WhatsApp codes, SMS sender ID,
Play organization account); enrichment prompt v2 with evaluation; app.json "locales" should point
to native-only strings; consider removing expo-dev-client from release builds; review npm audit.
