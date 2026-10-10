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
    signin_throttle, refresh_tokens (session rules) + refresh_token_store (SQL), attribute_rules
    (what a product attribute may be; shared by search, merchant uploads and the enrichment job),
    attribute_filters (SQL of the search attribute filters), attribute_extraction (names-only prompt,
    parser and validator for the catalog attribute fill), query_attributes (organic/gender/temperature/
    dietary read from a query's words), qu_cache (query-understanding cache + outcome counters),
    search_budget (query understanding in parallel with the first embedding, under a time budget),
    category_match (exact taxonomy matching of the model's category).
  - `app/taxonomy.py`: single source of truth for categories and store types.
  - `app/legal_content.py`: privacy policy and terms (served at /privacy, /terms; mirrored into
    `mobile/constants/legal.ts`). After every edit run `uv run scripts/generate-legal-ts.py` to
    regenerate the mobile copy (`--check` verifies without writing). The privacy policy has its own
    date (`PRIVACY_UPDATED_*`).
  - `app/jobs/import_catalog.py`, `app/jobs/enrich_attributes.py`, `app/moderation_cli.py`: server-side
    jobs and tools.
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
  - `generate-legal-ts.py`: regenerates `mobile/constants/legal.ts` from `backend/app/legal_content.py`
    (standard library only; `--check` reports whether the file is out of date instead of writing it).
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
  (search degrades, new products go to review). Models: query understanding gemma-4-26B-A4B (priority
  tier; E4B was saturated), expansion gemma-4-26B-A4B, embeddings Qwen3-Embedding-0.6B (1024-d), reranker
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
- Mobile tests: `cd mobile; npm test` (Node's own test runner on `services/api/session.ts`: renewal,
  single refresh for parallel 401s, session end; no device, no extra packages; needs Node 22.18+).
- End-to-end checks (sign-in throttle, proxy-header trust, Redis outages, refresh-token sessions) run real
  uvicorn, FastAPI, slowapi, redis-py and PyJWT: `backend/tests/e2e/` (README inside). They need a throwaway
  venv outside the repo built from the pins in `backend/requirements.txt`; no Docker, Redis or Postgres.
- Refresh-token SQL checks: `backend/tests/test_refresh_token_store_pg.py` run against a THROWAWAY Postgres
  (never production) when `LAMBA_TEST_DATABASE_URL` is set, and are skipped otherwise (instructions inside).
  They cover row locking under concurrency, the delete cascade and the whole HTTP flow on a real database.
  `backend/tests/test_enrich_attributes_pg.py` does the same for the attribute job's SQL (a TEMP table, so
  it needs no migrations).
- Attribute and query-path tests: `test_attribute_filters.py`, `test_attributes_version_migration.py`,
  `test_enrich_attributes.py` and the SQL test in `test_category_match.py` need SQLAlchemy, and
  `test_query_understanding_service.py` needs pydantic; they skip themselves without them. A small throwaway
  venv outside the repo is enough (`uv run --no-project python -m venv <dir>`, then
  `uv pip install --python <dir>\Scripts\python.exe sqlalchemy==2.0.36 pydantic`; add `--offline` to reuse
  uv's cache); no database is needed. Modules whose dependencies are not installed locally (httpx,
  pydantic-settings) are imported against stand-ins from `backend/tests/stub_modules.py`, which installs them
  only for the length of a test and restores `sys.modules` afterwards.
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
  sign-in. A listed word with fewer than 4 trailing digits/symbols ("Rasputin_3") is refused as
  `common_variant` (own message); 4+ trailing characters pass (Microsoft Entra scoring idea); exact
  list entries stay `common`. Mirrored for instant feedback in `components/auth/PasswordRules.tsx`;
  the server decides.
- Forms with text fields use `components/KeyboardForm.tsx` (react-native-keyboard-controller).
  Android 16 is edge-to-edge, so the old adjustResize no longer works. `KeyboardProvider` is in
  `app/_layout.tsx` with statusBarTranslucent and navigationBarTranslucent.
- Code entry uses `components/auth/OtpInput.tsx` (real input laid over the boxes).
- Store location (migration 0005, PR "store-location-pin"): a store has a pin (`markets.location`) and a structured
  address: `governorate` (a KEY from `app/jordan_geo.py`, the 12 governorates; the app shows the name in its language),
  `area` (required), `street` and `landmark` (optional), all text as the merchant typed it. The server composes the
  one-line `markets.address` from street, area and the Arabic governorate name; it is the plain fallback (old
  clients, the `city` search filter) and is never sent by the app. Customer responses carry `address_parts`
  (`market_address_parts` in search results, `shop_address_parts` in offers); `mobile/utils/jordanAddress.ts`
  `formatStoreAddress` builds the line in the viewer's language and falls back to `address` for a store without parts.
  `address_ar` never had a column and is gone from code and API (`name_ar` is the same kind of phantom, left alone).
  Creating a store (`POST /market`) needs governorate, area and a pin inside the rough Jordan box (swapped
  coordinates and (0, 0) are refused); the old address-only request is refused. Existing stores change location only
  through `PUT /api/v1/merchant/market/location` (`app/services/market_location.py`, pure and tested): pin moves up
  to 200 m and area/street/landmark edits are free; a bigger move or a different governorate (once set) is a bilingual
  403 pointing to support@lambajo.com. Every accepted change is a row in `market_location_changes` (old/new pin,
  metres moved, old/new fields, user, time; cascades with the store and the user). The profile PATCH no longer takes
  an address and the address-lock fields (`is_address_locked`, `is_profile_locked`, `address_edited_at` in responses)
  are gone; the `markets.address_edited_at` column stays and records the time of the last location edit. Mobile: one
  `components/StoreLocationForm.tsx` serves create-store (أضف متجرك), `(merchant)/onboarding.tsx` and the profile
  address row (`StoreLocationEditModal`); `LocationPicker` is the fixed-centre-pin map (satellite toggle, my-location,
  GPS warning above 50 m, a 200 m ring for existing stores). The phone's geocoder (`services/deviceLocation.ts`) only
  PREFILLS governorate/area/street through `prefillFromDeviceAddress` (region, subregion, city, district, street,
  name and formattedAddress; plus codes, numbers, postal codes and the country are skipped); a merchant's own text is
  never replaced without asking, and a detect that finds nothing leaves the fields alone. The keys, names, box and
  limits in `jordanAddress.ts` mirror `app/jordan_geo.py` and `market_location.py`; `test_jordan_geo.py` compares
  them. No Google Geocoding yet (decision pending its evaluation, see Later). The HTTP-level tests
  (`test_merchant_market_location_api.py`) need the full backend dependencies; the rules, schemas and migration are
  covered by tests that run in the small throwaway venv.
- Moderation: `global_items.moderation_status` approved | pending_review | blocked. Customers only
  ever see approved products. Review tool:
  `docker compose run --rm --no-deps api python -m app.moderation_cli pending|reports|approve <id>|block <id>`
- Attributes (`global_items.attributes` JSONB; `attributes_version` SMALLINT, migration 0004, NULL = never
  processed by the catalog fill). Search reads them only through `app/services/attribute_rules.py` and
  `attribute_filters.py`: booleans and gender/temperature are matched by JSONB containment (`attributes @>`),
  never by a SQL CAST (a stored non-boolean string used to be a database error) and never by ILIKE ("male" is
  inside "female"); text keys keep the substring match plus the name fallback; an unusable value from the
  query model is skipped, which only widens results. Merchant uploads go through
  `sanitize_merchant_attributes` (known keys, right types). Filling attributes can narrow results: the
  unfiltered retry in `search_v1.py` fires only when the filtered search returns ZERO rows, so one wrongly
  tagged product switches it off. The catalog fill is `app/jobs/enrich_attributes.py` (names only, prompt v1,
  commands in its docstring); it must be graded on a dry run before the full run.
  Query-side matching: the query model is shown alef/hamza-normalized text but answers in the usual spelling
  (seen on the server 2026-10-09: "شاي اخضر" -> type "أخضر") and with inflected adjectives ("بيضاء", "بلدية")
  while stored values are masculine, so `match_variants` tries every text value as given, normalized, with
  the original alef/hamza letters put back, with and without "ال", and in its masculine form (colour
  feminines; a final "ة" dropped, which as a substring still matches the feminine form in a name). Brands are
  not inflected. Stored values stay as the model wrote them.
- Query understanding in search (PR #8, deployed 2026-10-10). Measured on the server 2026-10-09: the small model
  first used (gemma-4-E4B-it) was saturated at DeepInfra (9 of 9 calls failed: 5 read timeouts, 4 HTTP 429
  "engine_overloaded"; an hour earlier it had answered in 2.5-7.6 s); `google/gemma-4-26B-A4B-it` answered 24 of
  24 calls with correct attributes every time, median 1.77 s, 83% within 2.0 s, 96% within 2.3 s, one outlier at
  3.8 s. Production sets `QUERY_LLM_FALLBACK_MODEL=google/gemma-4-26B-A4B-it` in backend/.env (also the code
  default). `analyze_query_async` works in layers and never raises: rules (`query_attributes.py`: organic,
  gender, temperature, dietary from whole-word matches, a conflict guard, always present and winning over the
  model for those keys); a Redis cache of the model's answer (`qu_cache.py`, 7 days, key = query + model +
  prompt hash, which also makes a query's category and attributes stable); then ONE model call: no retry, 6 s
  timeout, at most 8 in flight, its own breaker `deepinfra_query_breaker` that does NOT count HTTP 429 (busy is
  not down), DeepInfra service tier `query_llm_service_tier` (priority). `fail_fast` is OFF
  (`query_llm_fail_fast`): with it on, the first two production calls were rejected with 429 although the queue
  would have served them (diagnostic 2026-10-10: around a burst of 429, priority 6 of 6 and standard 5 of 6, about
  650 ms otherwise). `search_budget.py` starts the call together with the first embedding and `_run_search`
  waits for it only until `query_understanding_budget_seconds` (2.5) after the start of both; if it is late,
  search goes on with the rules, the call keeps running and fills the cache, and that response is not put in the
  5-minute search cache. Category: only an EXACT taxonomy name (name/name_ar/name_en) counts, and the 1.5x boost
  goes to that category and its subcategories (`category_match.py`); the model's loose words (شاي, حليب, dairy)
  are ignored, so with the real taxonomy only names like "Beverages" resolve.
  Counters: `HGETALL lamba:stats:qu:<YYYY-MM-DD>` (ok, cache_hit, not_needed, timeout, overloaded, http_error,
  breaker_open, busy, no_api_key, bad_json, error) and `HGETALL lamba:stats:search:<YYYY-MM-DD>`
  (budget_answered_model | budget_answered_cache | budget_answered_rules, budget_late, budget_failed).
  `QueryIntent.source` says where an intent came from; "rules" is the rule-based fallback (model not needed,
  rejected, failed or skipped), not a model answer, so read budget_answered_model for real answers and the qu
  counters for why a fallback happened. Log lines `[QU]` and `[QU BUDGET]`.
  Service tiers (`app/services/service_tier.py`; "" = standard, "priority" = +50% per token and served first
  when the model is busy, "flex" = batch only and refused on interactive paths; an unknown value is ignored with
  a warning): `query_llm_service_tier` (priority), `classifier_service_tier_interactive` (priority: merchant
  add, rename and CSV upload, `classify_item_ensemble(..., interactive=True)`) and `classifier_service_tier_batch`
  (standard: import_catalog). Priority was measured on gemma-4-26B-A4B only. If the 31B classifier model rejects
  it (a failing classifier call sends the product to review), set `CLASSIFIER_SERVICE_TIER_INTERACTIVE=` (empty)
  in backend/.env and recreate `api`.
  Free-text values from the model can still be longer than what is stored; the reliable keys are organic,
  gender, temperature, dietary and brand.
- Golden-query comparison (before/after a change to search): run `scripts/eval_search.py --worksheet` twice
  against the live API with `data/golden_search.jsonl` and `data/attribute_queries.jsonl`, then
  `scripts/compare_search_runs.py before.jsonl after.jsonl` (per query: results that left or entered, overlap,
  top-1, a REGRESSION flag for lost results or fewer keyword-relevant ones). Use `--max-distance-km 500`:
  catalog products appear in search only once a shop within the radius stocks them. Clear the cached search
  results between runs (`lamba:search:*`; `scripts/flush_search_cache.py` does it, but `scripts/` is not in the
  image, so delete those keys from a one-off `python` in the api container).
- Synonyms: search looks words up in the Redis hash `lamba:synonyms`. It was EMPTY in production on
  2026-10-09 (HLEN 0): `scripts/` is not in the Docker image, so nothing loads it and search runs without
  dialect rewriting. The curated list is `CORE_SYNONYMS` (30 pairs) in `scripts/build_synonym_table.py`, which
  now only loads that list (run it by hand; `flush_search_cache.py` no longer touches it). Never rebuild it from catalog
  `search_terms`: that mapped a dialect word to one product's name. `scripts/reembed_catalog.py` was deleted
  (it did exactly that, and embedded a different text than `enrich_and_embed`). DECISION PENDING: whether to
  ship the 30 pairs (an app-level loader) after checking them on the golden set; some are risky rewrites
  ("شكر" also means thanks, "بندورة" may be the catalog's own word).
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
- Sessions (`app/services/refresh_tokens.py`, `refresh_token_store.py`, table `refresh_tokens`, migration
  0003): sign-in with `client_supports_refresh: true` (the app always sends it) returns a 30-minute access
  token plus an opaque refresh token; builds without the flag keep the 24-hour JWT (`JWT_EXPIRATION_MINUTES`)
  and get no refresh token, so remove that path once old builds are gone. Only the SHA-256 of a refresh token
  is stored (one family per sign-in). Every use rotates it; presenting an already-rotated token revokes the
  whole family (RFC 9700 4.14.2), except a replay within `REFRESH_REUSE_LEEWAY_SECONDS` (10, 0 = off) of the
  rotation, which is a lost response: it gets a fresh token, the unused one is revoked, and it is logged
  ("forgiven"). Reuse revocation is committed before the 401 (get_db rolls back on exceptions). Lifetimes:
  30-day sliding idle window (`REFRESH_IDLE_DAYS`), 90-day absolute cap (`REFRESH_ABSOLUTE_DAYS`).
  DEVIATION: NIST SP 800-63B-4 says the overall reauthentication timeout at AAL1 SHOULD be no more than
  30 days; we allow 90 (a shop-discovery app, not a high-risk service; only a SHOULD) and keep 30 as the idle
  window. Set `REFRESH_ABSOLUTE_DAYS=30` to comply. `/auth/refresh`, `/auth/logout` and `/auth/me` are the
  endpoints; every refresh failure is the same bilingual 401 (expired, revoked and deleted accounts look
  alike). Password reset revokes all refresh tokens and sets `users.tokens_valid_after`, which also refuses
  every older access token (including old 24-hour ones); account deletion revokes them first and the
  foreign key cascades. Raw tokens (and their hashes) are never logged. The app (`mobile/services/api/
  session.ts` + `client.ts`) renews once on a 401 that carried a token (one shared refresh call for parallel
  requests, then the request is repeated), never on guest requests or the auth endpoints; a refused renewal
  clears the session and sends the user to login with one message (`login.session_ended`); app start
  checks the session with GET /auth/me (no connection keeps the user signed in).
- Redis client (`get_redis()` in `app/services/cache.py`): redis-py's default retry policy is switched
  off (`_NO_RETRY`). With it on (10 retries with backoff in redis-py 8.1) one call to an unreachable
  Redis took 3 to 20+ seconds despite the 0.5 s timeouts; now a failure costs at most ~0.5 s.
  `requirements.txt` pins `redis==8.1.0`, the version production runs, and the end-to-end harness is
  tested against it. `httpx`, `slowapi` and `boto3` are still `>=`, so a rebuilt image gets their
  newest versions.

## Status (keep this section current)
Done: security hardening, Alembic migrations, taxonomy, classifier ensemble, merchant flow fixes,
report button, account deletion (in app + web page), legal pages, catalog import and enrichment,
images.lambajo.com, homepage, password policy, email-only auth with its fixes (keyboard-aware forms,
confirm password, code entry with paste, single-language errors; verified on a phone),
refresh-token sessions (deployed; renewal and the session-ended message verified on a phone),
structured store address with a map pin picker (branch store-location-pin: migration 0005 and the new app build are
needed together; not yet run on a phone).

In progress: Google Play personal developer account (identity verification pending; personal
accounts need a 14-day closed test with 12+ testers).

Next before the closed test: the catalog attribute fill (PR #8, with migration 0004 and the query path, is
deployed; the job and its tests are in the repo, NOT run yet: dry run of 100, graded, then the full run);
the golden-query comparison of the new query path (only meaningful if a "before" run was taken before the
deploy); review the ~49 held products;
monitoring alert for AI/credit failures; build the .aab; create review test accounts for Play "App access"; Play data safety form.

Later: Google Geocoding for store addresses, only after evaluating it on about 20 real locations in Jordan against the
phone's geocoder (language=ar, region=jo; read Google's caching terms first, results may not be stored freely; the
10,000 free requests a month and $5 per 1,000 after that were read from Google's pricing page on 2026-10-10; the
server needs its own IP-restricted key, the Maps key in app.json is Android-restricted and cannot call web services);
register Lamba as a business (unlocks Meta verification for WhatsApp codes, SMS sender ID,
Play organization account); enrichment prompt v2 with evaluation; `name_en` fill (a separate job, after the
attributes); a gender filter that also accepts unisex/any items; app.json "locales" should point
to native-only strings; consider removing expo-dev-client from release builds; review npm audit.
