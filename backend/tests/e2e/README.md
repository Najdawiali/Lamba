# End-to-end checks

`e2e_run.py` checks the sign-in throttle, the proxy-header trust and the Redis client against the **real**
libraries, which the unit tests cannot do. It starts real uvicorn processes serving the real
`app/api/auth_v1.py` router (on real FastAPI, slowapi and redis-py) and drives them over HTTP.

It is not a unit test: `run_all_tests.py` and pytest ignore it, and the Docker image excludes `tests/`.
No Docker, Redis or Postgres is needed, and nothing is installed into the project.

## What it checks

- **Client IP behind Caddy:** with the Docker bridge peer untrusted, every client shares one rate-limit bucket
  (the original bug). With `FORWARDED_ALLOW_IPS=127.0.0.1,172.16.0.0/12` each client IP has its own, and an
  injected `X-Forwarded-For` entry cannot create a new bucket.
- **429 responses:** `{"detail": "Arabic\nEnglish"}` with `Retry-After`, from the real slowapi.
- **Sign-in throttle** (10 failures per account in 15 minutes): the lock holds across different IPs, a blocked
  attempt never reaches the database, unknown accounts look identical, a correct password or a password reset
  clears it (a wrong reset code does not), the window expires, and the Redis key is a hash.
- **Redis down** (refused, dropped, hung): sign-in keeps working, is never blocked, and each attempt finishes
  in under 5 s; throttling resumes by itself when Redis returns. This is what caught redis-py's default
  retries, which made every call to an unreachable Redis take seconds (see `get_redis()`).

## Run it

PowerShell, from the repo root. The venv lives outside the repo, takes its versions from
`backend/requirements.txt` (so it follows the pins production gets) and is about 20 MB from PyPI:

```powershell
$venv = "$env:TEMP\lamba-e2e"   # any folder outside the repo
uv run --no-project python -m venv $venv
$pins = (Get-Content backend\requirements.txt) -match '^(fastapi|uvicorn|slowapi|redis)\b' -replace '\[standard\]', ''
uv pip install --python "$venv\Scripts\python.exe" $pins
& "$venv\Scripts\python.exe" -B backend\tests\e2e\e2e_run.py
```

It takes about 40 seconds and ends with `E2E: ALL <n> CHECKS PASSED` and exit code 0. Delete the venv folder when
you are done. On Linux or macOS use `bin/python` instead of `Scripts\python.exe`.

The venv is created with Python's own `venv` module on purpose: on this machine Windows Smart App Control blocks
the unsigned launcher that `uv venv` writes into a new venv (error 4551, "Application Control policy").

## Real and stand-in

Real: FastAPI, slowapi (and limits), redis-py, uvicorn, and the repo's `auth_v1.py`, `rate_limit.py`,
`signin_throttle.py`, `cache.py`, `password_policy.py` and `schemas/auth_v1.py`.

Stand-ins (`e2e_app.py`, `e2e_run.py`): the database (a few users in memory), password hashing and tokens,
email sending, and the Redis *server* (`MiniRedis`, a protocol stand-in with a clock the test can move forward).
Not covered: PostgreSQL, a real Redis server, Caddy and Docker's network, `docker-compose.yml` itself (the trust
list is passed to uvicorn directly, so a change to the file would go unnoticed), and Linux-only behaviour (it was
written and run on Windows).

## When it fails

The driver prints the tail of the server logs and keeps them in a temp folder (the path is printed).

- `ImportError` in a server log after `auth_v1.py` gained a new third-party import: add a stand-in for it in
  `e2e_app.py`.
- Every Redis call fails and the S4 checks find an empty Redis: a redis-py upgrade started sending a command
  `MiniRedis.execute` does not know. The throttle then fails open and only logs "Sign-in throttle unavailable"
  with the error, which names the command.
