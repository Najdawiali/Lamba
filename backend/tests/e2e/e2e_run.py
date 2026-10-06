"""
End-to-end checks: see README.md in this folder. Run it with the Python of a throwaway venv that has the pinned
fastapi, uvicorn, slowapi and redis installed (the driver itself only needs the standard library):

    <venv>\\Scripts\\python.exe -B backend\\tests\\e2e\\e2e_run.py

It starts REAL uvicorn processes serving e2e_app.py (the real auth_v1 router on real FastAPI, slowapi and
redis-py) and checks behaviour over real HTTP. A small Redis-protocol server below lets the real redis-py client
talk to "Redis" over real TCP, with a clock that can be moved forward to test the lock window. Exit code 0 means
every check passed.
"""

import asyncio
import http.client
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
LOGS = Path(tempfile.mkdtemp(prefix="lamba-e2e-"))  # server logs: outside the repo, removed when everything passes
ARABIC = re.compile(r"[؀-ۿ]")
# With Redis unreachable a sign-in must still finish quickly. With redis-py's default retries switched on (see
# get_redis() in app/services/cache.py) every failing Redis call took 3 to 6+ seconds, far above this.
MAX_SIGNIN_SECONDS = 5.0
CHECKS = 0

missing = [m for m in ("fastapi", "uvicorn", "slowapi", "redis") if importlib.util.find_spec(m) is None]
if missing:
    sys.exit("Missing in this Python: %s. Run this with the throwaway venv's python; see README.md in this folder."
             % ", ".join(missing))


def check(cond, message):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(message)


def say(text):
    print(text, flush=True)


# ------------------------------------------------------------------------ asyncio servers on their own threads
class ServerThread:
    """An asyncio TCP server on its own thread and event loop, shut down without leaving tasks behind."""

    def __init__(self, handler, port=0):
        self.writers = []
        ready = threading.Event()

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            async def wrapped(reader, writer):
                self.writers.append(writer)
                await handler(reader, writer)

            self.server = self.loop.run_until_complete(asyncio.start_server(wrapped, "127.0.0.1", port))
            self.port = self.server.sockets[0].getsockname()[1]
            ready.set()
            try:
                self.loop.run_forever()
            finally:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.close()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(5)

    def stop(self):
        def shut():
            self.server.close()
            for w in self.writers:
                w.close()
            self.loop.stop()

        self.loop.call_soon_threadsafe(shut)
        self.thread.join(5)


# ------------------------------------------------------------------------ minimal Redis server
class MiniRedis:
    """Just the commands get_redis() and the sign-in throttle use. redis-py 8 opens every connection with
    HELLO 3 (RESP3) and sends incr() as INCRBY, so a stand-in must answer both or every call fails (and the
    throttle then fails open, with only a warning in the server log)."""

    HELLO_MAP = (b"%7\r\n$6\r\nserver\r\n$5\r\nredis\r\n$7\r\nversion\r\n$5\r\n7.4.0\r\n$5\r\nproto\r\n:3\r\n"
                 b"$2\r\nid\r\n:1\r\n$4\r\nmode\r\n$10\r\nstandalone\r\n$4\r\nrole\r\n$6\r\nmaster\r\n$7\r\nmodules\r\n*0\r\n")

    def __init__(self):
        self.data, self.exp, self.offset, self.commands, self.port = {}, {}, 0.0, [], None

    def now(self):
        return time.monotonic() + self.offset

    def warp(self, seconds):
        """Move this server's clock forward, to test expiry without waiting."""
        self.offset += seconds

    def alive(self, key):
        e = self.exp.get(key)
        if e is not None and e <= self.now():
            self.data.pop(key, None)
            self.exp.pop(key, None)
        return key in self.data

    @staticmethod
    def bulk(value):
        s = str(value).encode()
        return b"$%d\r\n%s\r\n" % (len(s), s)

    def execute(self, parts, conn):
        cmd = parts[0].decode().upper()
        args = [p.decode() for p in parts[1:]]
        self.commands.append(cmd.lower())
        if cmd == "HELLO":
            conn["proto"] = int(args[0]) if args else 2
            return self.HELLO_MAP
        if cmd == "PING":
            return b"+PONG\r\n"
        if cmd == "SELECT":
            return b"+OK\r\n"
        if cmd == "CLIENT":
            return b"+OK\r\n" if args and args[0].upper() in ("SETINFO", "SETNAME") else b"-ERR unknown subcommand\r\n"
        if cmd == "GET":
            if self.alive(args[0]):
                return self.bulk(self.data[args[0]])
            return b"_\r\n" if conn.get("proto") == 3 else b"$-1\r\n"  # RESP3 null / RESP2 null bulk
        if cmd in ("INCR", "INCRBY"):
            key = args[0]
            self.alive(key)
            step = int(args[1]) if cmd == "INCRBY" else 1
            self.data[key] = int(self.data.get(key, 0)) + step  # like Redis: creates it without expiry, keeps an existing expiry
            return (":%d\r\n" % self.data[key]).encode()
        if cmd == "TTL":
            key = args[0]
            if not self.alive(key):
                return b":-2\r\n"
            e = self.exp.get(key)
            return b":-1\r\n" if e is None else (":%d\r\n" % round(e - self.now())).encode()
        if cmd == "EXPIRE":
            key = args[0]
            if not self.alive(key):
                return b":0\r\n"
            self.exp[key] = self.now() + int(args[1])
            return b":1\r\n"
        if cmd == "DEL":
            n = 0
            for key in args:
                n += 1 if self.alive(key) else 0
                self.data.pop(key, None)
                self.exp.pop(key, None)
            return (":%d\r\n" % n).encode()
        return b"-ERR unknown command '%s'\r\n" % cmd.lower().encode()

    async def handle(self, reader, writer):
        conn = {"proto": 2}
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if line[:1] == b"*":
                    parts = []
                    for _ in range(int(line[1:])):
                        length = int((await reader.readline())[1:])
                        parts.append((await reader.readexactly(length + 2))[:-2])
                else:
                    parts = line.split()
                    if not parts:
                        continue
                writer.write(self.execute(parts, conn))
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    def start(self, port=0):
        self.thread = ServerThread(self.handle, port)
        self.port = self.thread.port
        return self

    def stop(self):
        self.thread.stop()


class BadServer:
    """Accepts TCP connections, then either drops them at once ('drop': like Redis restarting) or never answers
    ('hung': like an unresponsive Redis)."""

    def __init__(self, mode, port):
        async def handle(reader, writer):
            if mode == "drop":
                writer.close()
                return
            try:
                await asyncio.sleep(3600)
            finally:
                writer.close()

        self.thread = ServerThread(handle, port)

    def stop(self):
        self.thread.stop()


# ------------------------------------------------------------------------ HTTP + server helpers
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    conn.request(method, path, json.dumps(body) if body is not None else None, hdrs)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    try:
        data = json.loads(raw)
    except ValueError:
        data = raw
    out = (resp.status, {k.lower(): v for k, v in resp.getheaders()}, data)
    conn.close()
    return out


class Server:
    """A REAL uvicorn process (the one installed in this venv) serving e2e_app."""

    def __init__(self, name, forwarded_allow_ips, redis_port):
        self.name, self.port = name, free_port()
        env = dict(os.environ, E2E_REDIS_PORT=str(redis_port), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        env.pop("FORWARDED_ALLOW_IPS", None)
        if forwarded_allow_ips is not None:
            env["FORWARDED_ALLOW_IPS"] = forwarded_allow_ips
        self.log_path = LOGS / (name + ".log")
        self.log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-B", "-m", "uvicorn", "e2e_app:app", "--host", "127.0.0.1", "--port", str(self.port),
             "--app-dir", str(HERE)],
            env=env, stdout=self.log, stderr=subprocess.STDOUT, cwd=str(HERE))
        deadline = time.time() + 40
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError("server exited early:\n" + self.text()[-3000:])
            try:
                if call(self.port, "GET", "/__stats")[0] == 200:
                    break
            except OSError:
                pass
            if time.time() > deadline:
                raise RuntimeError("server did not start:\n" + self.text()[-3000:])
            time.sleep(0.25)

    def text(self):
        if not self.log.closed:
            self.log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stats(self):
        return call(self.port, "GET", "/__stats")[2]

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


_ip = [0]


def fresh_ip():
    """A new client address each time, so the per-IP limiter never interferes with per-account tests."""
    _ip[0] += 1
    return "198.18.%d.%d" % (_ip[0] // 250, _ip[0] % 250 + 1)


def forgot(srv, xff, email="nobody@example.com"):
    return call(srv.port, "POST", "/api/v1/auth/forgot-password", {"email": email}, {"X-Forwarded-For": xff})


def signin(srv, email, password, xff=None):
    return call(srv.port, "POST", "/api/v1/auth/signin", {"email_or_phone": email, "password": password},
                {"X-Forwarded-For": xff or fresh_ip()})


def two_languages(text):
    lines = text.split("\n")
    return len(lines) == 2 and bool(ARABIC.search(lines[0])) and not ARABIC.search(lines[1])


started = time.time()
redis = MiniRedis().start()
extra_redis = []
servers = []
try:
    # ============================================================ S1: the original bug, reproduced with real uvicorn
    s1 = Server("s1_untrusted", "172.16.0.0/12", redis.port)  # loopback peer NOT trusted, like 172.18.0.1 was before FORWARDED_ALLOW_IPS
    servers.append(s1)
    real = s1.stats()
    check(os.path.samefile(real["auth_v1_file"], BACKEND / "app" / "api" / "auth_v1.py"), real["auth_v1_file"])
    check(os.path.samefile(real["rate_limit_file"], BACKEND / "app" / "rate_limit.py"), real["rate_limit_file"])
    v = real["versions"]
    say("S0  real libraries: python %s, fastapi %s, uvicorn %s, slowapi %s (limits %s), redis-py %s;"
        " the app imports the repo's own auth_v1.py and rate_limit.py" %
        (v["python"], v["fastapi"], v["uvicorn"], v["slowapi"], v["limits"], v["redis"]))
    codes = [forgot(s1, "203.0.113.%d" % i)[0] for i in range(1, 5)]
    check(codes == [200, 200, 200, 429], codes)
    say("S1  peer NOT trusted (the bug before FORWARDED_ALLOW_IPS): 4 requests from 4 different client IPs -> %s  (one shared bucket)" % codes)
    s1.stop()

    # ============================================================ S2/S3: the fix, and the 429 shape
    s2 = Server("s2_trusted", "127.0.0.1,172.16.0.0/12", redis.port)
    servers.append(s2)
    codes = [forgot(s2, "203.0.113.1")[0] for _ in range(3)]
    check(codes == [200, 200, 200], codes)
    status, headers, body = forgot(s2, "203.0.113.1")
    check(status == 429, status)
    check(forgot(s2, "203.0.113.9")[0] == 200, "another client IP must have its own bucket")
    say("S2  peer trusted (the fix): same IP 3x ok, 4th -> 429; a different IP is unaffected (per-IP limits are real)")
    check(list(body) == ["detail"], body)
    check(two_languages(body["detail"]), body["detail"])
    check(body["detail"] == s2.stats()["rate_limited_message"], "body must be the real RATE_LIMITED text")
    check(headers.get("retry-after") == "60", headers.get("retry-after"))
    check(headers["content-type"].startswith("application/json"), headers["content-type"])
    say("S3  429 body is {'detail': 'Arabic\\nEnglish'} (the app can show it); Retry-After = %s (3/minute window, from the real slowapi/limits)" % headers["retry-after"])
    codes = [forgot(s2, "198.51.100.%d, 203.0.113.50" % i)[0] for i in range(1, 5)]
    check(codes == [200, 200, 200, 429], codes)
    say("S3b spoofing: 4 requests that inject different left-hand X-Forwarded-For entries share ONE bucket (right-most untrusted wins) -> %s" % codes)
    ips = re.findall(r"INFO:\s+(\S+) - \"POST /api/v1/auth/forgot-password", s2.text())
    check(ips[:3] == ["203.0.113.1:0"] * 3, ips[:3])
    say("    uvicorn's access log shows the real client address: %s ..." % ", ".join(ips[:3]))

    # ============================================================ S4: per-account sign-in throttle over HTTP
    say("S4  per-account sign-in throttle (real router, real redis-py client -> Redis protocol over TCP):")
    for i in range(10):
        status, _, body = signin(s2, "ali@example.com", "wrong")  # a new IP every time
        check(status == 401 and body == {"detail": "Invalid Credentials"}, (i, status, body))
    keys = list(redis.data)
    check(len(keys) == 1 and keys[0].startswith("signin_fail:") and len(keys[0]) == len("signin_fail:") + 64, keys)
    check("ali" not in keys[0] and redis.data[keys[0]] == 10, (keys, redis.data))
    ttl = redis.exp[keys[0]] - redis.now()
    check(890 < ttl <= 900, ttl)
    say("    10 wrong passwords from 10 DIFFERENT IPs -> 401 each; Redis holds one hashed key signin_fail:<sha256>, count=10, ttl=%ds" % round(ttl))
    queries = s2.stats()["queries"]
    redis.commands.clear()
    status, headers, body = signin(s2, "ali@example.com", "right-pass-ali")  # the CORRECT password, 11th attempt, yet another IP
    check(status == 429, (status, body))
    check(body["detail"] == s2.stats()["signin_locked"] and two_languages(body["detail"]) and "15" in body["detail"], body)
    check(1 <= int(headers["retry-after"]) <= 900, headers["retry-after"])
    check(s2.stats()["queries"] == queries, "a blocked attempt must not touch the database")
    check(set(redis.commands) <= {"get", "ttl", "ping", "client", "select"}, redis.commands)
    say("    11th attempt (correct password, new IP) -> 429, Retry-After=%ss, message mentions 15 minutes, DB not queried, Redis only read (%s)" % (headers["retry-after"], ",".join(redis.commands)))
    status, _, body = signin(s2, "bob@example.com", "right-pass-bob")
    check(status == 200 and body["access_token"].startswith("token-") and body["user"]["email"] == "bob@example.com", (status, body))
    say("    another account signs in normally -> 200 with a token")
    for i in range(10):
        check(signin(s2, "ghost@example.com", "x")[0] == 401, i)
    ghost = signin(s2, "ghost@example.com", "x")
    locked_text = s2.stats()["signin_locked"]
    check(ghost[0] == 429 and ghost[2]["detail"] == locked_text, ghost)
    say("    unknown account 'ghost@': 10x 401, then the identical 429 message -> blocking never reveals whether an account exists")
    check(all(k.startswith("signin_fail:") and "ali" not in k and "ghost" not in k for k in redis.data), list(redis.data))
    for variant in (" Ali@Example.COM ", "ALI@example.com"):
        check(signin(s2, variant, "right-pass-ali")[0] == 429, variant)
    say("    case/whitespace variants of the same email share the counter (still blocked)")
    redis.warp(901)
    status, _, body = signin(s2, "ali@example.com", "right-pass-ali")
    live = [k for k in list(redis.data) if redis.alive(k)]  # MiniRedis expires keys lazily, so ask it
    check(status == 200 and live == [], (status, live))
    say("    15 minutes later (clock moved +901s) the account signs in again; the counter is gone")

    for i in range(10):
        signin(s2, "carol@example.com", "wrong")
    check(signin(s2, "carol@example.com", "right-pass-carol")[0] == 429, "carol should be locked")
    status, _, body = call(s2.port, "POST", "/api/v1/auth/reset-password",
                           {"email": "carol@example.com", "code": "123456", "new_password": "purple-tractor-ocean-1987"},
                           {"X-Forwarded-For": fresh_ip()})
    check(status == 200, (status, body))
    status, _, body = signin(s2, "carol@example.com", "purple-tractor-ocean-1987")
    check(status == 200, (status, body))
    say("    locked account + successful password reset -> the owner signs in immediately with the new password")

    for i in range(10):
        signin(s2, "hana@example.com", "wrong")
    status, _, body = call(s2.port, "POST", "/api/v1/auth/reset-password",
                           {"email": "hana@example.com", "code": "000000", "new_password": "purple-tractor-ocean-1987"},
                           {"X-Forwarded-For": fresh_ip()})
    check(status == 400, (status, body))
    check(signin(s2, "hana@example.com", "right-pass-hana")[0] == 429, "a WRONG reset code must not clear the lock")
    say("    wrong reset code -> the lock stays")

    for i in range(9):
        check(signin(s2, "dave@example.com", "wrong")[0] == 401, i)
    check(signin(s2, "dave@example.com", "right-pass-dave")[0] == 200, "9 failures + correct password")
    for i in range(10):
        check(signin(s2, "dave@example.com", "wrong")[0] == 401, i)
    check(signin(s2, "dave@example.com", "wrong")[0] == 429, "the count restarted from zero after the correct password")
    say("    9 failures + correct password resets the count: 10 more failures are needed to lock")

    status, _, body = signin(s2, "erin@example.com", "right-pass-erin")
    check(status == 403 and set(body["detail"]) >= {"message", "user_id", "channel", "contact", "user_type"}, (status, body))
    say("    unverified account + correct password -> 403 with the same JSON detail as before")

    ip = "192.0.2.77"
    results = [signin(s2, "nouser%d@example.com" % i, "x", ip)[:3] for i in range(11)]
    check([r[0] for r in results] == [401] * 10 + [429], [r[0] for r in results])
    check(results[10][2]["detail"] == s2.stats()["rate_limited_message"], results[10][2])
    say("    per-IP limiter still works next to it: 11 sign-ins from ONE IP -> 10x 401 then the generic 'too many requests' 429")
    s2.stop()

    # ============================================================ S5: Redis unreachable in three realistic ways, then recovery
    def outage_phase(name, port, label):
        srv = Server("s5_" + name, "127.0.0.1,172.16.0.0/12", port)
        servers.append(srv)
        slowest = 0.0
        for i in range(8):
            t0 = time.time()
            status, _, body = signin(srv, "gina@example.com", "wrong")
            slowest = max(slowest, time.time() - t0)
            check(status == 401, (name, i, status, body))  # never 429: with Redis unreachable the throttle is off, not blocking
        t0 = time.time()
        status, _, body = signin(srv, "gina@example.com", "right-pass-gina")
        slowest = max(slowest, time.time() - t0)
        check(status == 200, (name, status, body))
        check(slowest < MAX_SIGNIN_SECONDS, "%s: one sign-in took %.1fs: Redis calls must be bounded" % (name, slowest))
        warnings = srv.text().count("Sign-in throttle unavailable")
        check(warnings >= 8, (name, warnings))
        say("S5  Redis %-28s 8 wrong passwords -> 401 each, correct -> 200, never blocked; slowest sign-in %.2fs; %d warnings logged" % (label, slowest, warnings))
        return srv

    port = free_port()  # nothing listens here
    s5a = outage_phase("refused", port, "REFUSING connections:")
    late = MiniRedis().start(port)  # Redis comes back on the same port; the API process keeps running
    extra_redis.append(late)
    for i in range(10):
        signin(s5a, "ivan@example.com", "wrong")
    status, _, body = signin(s5a, "ivan@example.com", "right-pass-ivan")
    check(status == 429 and any(k.startswith("signin_fail:") for k in late.data), (status, late.data))
    say("S5b Redis comes BACK (same API process, no restart): throttling resumes by itself -> 10 failures, then 429")
    s5a.stop()

    for mode, label in (("drop", "DROPPING connections:"), ("hung", "UNRESPONSIVE (hung):")):
        port = free_port()
        bad = BadServer(mode, port)
        s5 = outage_phase(mode, port, label)
        s5.stop()
        bad.stop()

    say("\nE2E: ALL %d CHECKS PASSED in %.0fs" % (CHECKS, time.time() - started))
    code = 0
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    say("\nE2E FAILED after %d passed checks: %r" % (CHECKS, exc))
    for s in servers:
        say("---- tail of %s log ----\n%s" % (s.name, s.text()[-1500:]))
    say("(server logs kept in %s)" % LOGS)
    code = 1
finally:
    for s in servers:
        if s.proc.poll() is None:
            s.stop()
    for r in [redis] + extra_redis:
        r.stop()
if code == 0:
    shutil.rmtree(LOGS, ignore_errors=True)
sys.exit(code)
