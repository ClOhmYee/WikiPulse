"""Isolated PostgreSQL + real Spring HTTP + optional Playwright account E2E.

uv run --with pgserver --with 'psycopg[binary]' python tools/test_account_e2e.py --browser
Build backend bootJar first. Never connects to an external/production database.
"""
import argparse
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import pgserver
import psycopg

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "account-test-only-123!"


class Client:
    def __init__(self, base):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def call(self, path, method="GET", data=None, expected=200, csrf=True):
        headers = {"Content-Type": "application/json"}
        if csrf and method not in ("GET", "HEAD"):
            token = self.call("/auth/csrf")[0]["data"]
            headers[token["headerName"]] = token["token"]
        request = urllib.request.Request(self.base + path, method=method, headers=headers,
                                         data=None if data is None else json.dumps(data).encode())
        try:
            response = self.http.open(request, timeout=15)
        except urllib.error.HTTPError as failure:
            response = failure
        body = response.read().decode()
        assert response.status == expected, (method, path, response.status, body)
        return (json.loads(body) if body else None), response.headers

    def signup(self, email):
        return self.call("/auth/signup", "POST", {"email": email, "password": PASSWORD,
                                                  "displayName": "Account Test"}, 201)[0]["data"]

    def login(self, email):
        return self.call("/auth/login", "POST", {"email": email, "password": PASSWORD})


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    artifact = ROOT / "output" / "account-e2e"
    artifact.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(tempfile.mkdtemp(prefix="wikipulse-account-test-"))
    if os.name != "nt":
        # pgserver 0.1.4 disables TCP on Unix. JDBC needs a loopback listener;
        # restart only this disposable cluster and refresh its lifecycle metadata.
        from pgserver._commands import pg_ctl
        pg_ctl(["-w", "-o", f'-h 127.0.0.1 -p {port()} -k "{server.pgdata}"',
                "-l", str(server.log), "restart"],
               pgdata=server.pgdata, user=server.system_user, timeout=15)
        server.ensure_postgres_running()
    dsn = server.get_uri()
    migrations = sorted((ROOT / "db/migrations").glob("V*__*.sql"), key=lambda p: int(p.name.split("__")[0][1:]))
    with psycopg.connect(dsn, autocommit=True) as db:
        # Upgrade populated V14 schema; prove collision rejection leaves existing identities alone.
        for migration in migrations:
            if migration.name.startswith("V15__"):
                break
            db.execute(migration.read_text(encoding="utf-8"))
        db.execute("INSERT INTO member(email,display_name) VALUES ('Legacy@example.com','Legacy'),('legacy@example.com','Collision')")
        latest = next(p for p in migrations if p.name.startswith("V15__"))
        try:
            with db.transaction():
                db.execute(latest.read_text(encoding="utf-8"))
            raise AssertionError("normalization collision was not rejected")
        except psycopg.errors.RaiseException:
            pass
        assert db.execute("SELECT count(*) FROM member").fetchone()[0] == 2
        db.execute("DELETE FROM member WHERE display_name='Collision'")
        db.execute(latest.read_text(encoding="utf-8"))
        assert db.execute("SELECT email FROM member").fetchone()[0] == "Legacy@example.com"
        # Second schema verifies a clean install without touching any external DB.
        db.execute("CREATE SCHEMA fresh_install; SET search_path=fresh_install,public")
        for migration in migrations:
            db.execute(migration.read_text(encoding="utf-8"))
        db.execute("SET search_path=public")
        db.execute("INSERT INTO stock(ticker,name,exchange) VALUES ('T211','Account E2E Stock','NASDAQ')")
        cluster = db.execute("INSERT INTO issue_cluster(snapshot_ts,label,pulse_score,status,source) VALUES (now(),'Account E2E Issue',42,'CONFIRMED','live') RETURNING id").fetchone()[0]
    uri = urlparse(dsn)
    # Resolve the disposable cluster's port and user for JDBC.
    with psycopg.connect(dsn) as db:
        pg_port = db.execute("SHOW port").fetchone()[0]
        pg_user = db.execute("SELECT current_user").fetchone()[0]
    with psycopg.connect(dsn, host="127.0.0.1", port=pg_port) as db:
        assert db.execute("SELECT 1").fetchone()[0] == 1
    backend_port = port()
    env = dict(os.environ, DATABASE_URL=f"jdbc:postgresql://127.0.0.1:{pg_port}/{uri.path.lstrip('/') or 'postgres'}",
               DB_USER=pg_user, DB_PASSWORD="", SERVER_PORT=str(backend_port), SESSION_COOKIE_SECURE="false",
               WIKIPULSE_MATCHING_SCHEDULER_ENABLED="false", WIKIPULSE_MATCHING_SUMMARY_ENABLED="false",
               WIKIPULSE_MATCHING_VERIFICATION_ENABLED="false", SESSION_TIMEOUT="24h")
    java = str(Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")) if os.environ.get("JAVA_HOME") else "java"
    jar = next(p for p in (ROOT / "backend/build/libs").glob("*.jar") if not p.name.endswith("-plain.jar"))
    process = None
    logs = []

    def start(timeout="24h", secure="false"):
        nonlocal process
        log = (artifact / f"backend-{len(logs)}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen([java, "-Duser.timezone=GMT+00:00", "-jar", str(jar)], cwd=ROOT, env=dict(env, SESSION_TIMEOUT=timeout, SESSION_COOKIE_SECURE=secure), stdout=log, stderr=subprocess.STDOUT)
        for _ in range(120):
            if process.poll() is not None:
                log.flush()
                print(Path(log.name).read_text(encoding="utf-8"), flush=True)
                raise RuntimeError(f"backend exited; inspect {log.name}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{backend_port}/actuator/health", timeout=1)
                return
            except (OSError, urllib.error.URLError):
                time.sleep(0.5)
        raise RuntimeError("backend health timed out")

    def stop():
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=30)

    try:
        start()
        base = f"http://127.0.0.1:{backend_port}/api/v1"
        alice, bob, guest = Client(base), Client(base), Client(base)
        guest.call("/me", expected=401)
        guest.call("/me/bookmarks", expected=401)
        guest.call("/stocks?limit=1")
        guest.call(f"/issues/{cluster}")
        guest.call("/auth/signup", "POST", {}, 403, csrf=False)
        guest.call("/auth/signup", "POST", {"email": "wide@example.com", "password": chr(0xD55C) * 25, "displayName": "test"}, 400)
        alice.signup(" Alice@example.com ")
        alice.call("/auth/signup", "POST", {"email": "ALICE@example.com", "password": PASSWORD, "displayName": "duplicate"}, 409)
        bob.signup("bob@example.com")
        alice.call("/auth/login", "POST", {"email": "alice@example.com", "password": "wrong"}, 401)
        guest.call("/auth/login", "POST", {"email": "legacy@example.com", "password": PASSWORD}, 401)
        before = next(iter(alice.cookies)).value
        result, headers = alice.login("alice@example.com")
        assert "token" not in result["data"] and "password" not in json.dumps(result)
        assert next(iter(alice.cookies)).value != before
        cookie = headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Max-Age=86400" in cookie, cookie
        bob.login("bob@example.com")
        path = f"/me/bookmarks/{cluster}"
        alice.call(path, "PUT", expected=403, csrf=False)
        alice.call(path, "PUT", expected=204)
        alice.call(path, "PUT", expected=204)
        alice.call("/me/watchlist/T211", "PUT", expected=204)
        assert bob.call("/me/saved-state")[0]["data"] == {"issueIds": [], "tickers": []}
        assert alice.call("/me/bookmarks?q=E2E&limit=1")[0]["meta"]["pagination"]["total"] == 1
        assert alice.call("/me/bookmarks?q=absent")[0]["data"] == []
        assert alice.call("/me/watchlist")[0]["data"][0]["ticker"] == "T211"
        alice.call("/me/bookmarks?limit=101", expected=400)
        alice.call("/me/bookmarks/9223372036854775807", "PUT", expected=404)
        # Same cookie survives a real JVM restart, with refreshed expiry on use.
        stop(); start()
        alice.call("/me")
        assert alice.call("/me/saved-state")[0]["data"]["issueIds"] == [str(cluster)]
        alice.call("/auth/logout", "POST", expected=204)
        alice.call("/me", expected=401)
        alice.login("alice@example.com")
        alice.call(path, "DELETE", expected=204)
        alice.call(path, "DELETE", expected=204)
        alice.call("/me/watchlist/T211", "DELETE", expected=204)
        # Concurrent writes from independent sessions hit the DB uniqueness constraint safely.
        clients = [Client(base) for _ in range(3)]
        for client in clients:
            client.login("alice@example.com")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            list(pool.map(lambda client: client.call(path, "PUT", expected=204), clients))
        assert alice.call("/me/bookmarks")[0]["meta"]["pagination"]["total"] == 1
        if args.browser:
            browser_env = dict(env, ACCOUNT_E2E_BACKEND=f"http://127.0.0.1:{backend_port}", ACCOUNT_E2E_CLUSTER=str(cluster), WIKIPULSE_E2E_PORT=str(port()))
            subprocess.run([shutil.which("npm.cmd" if os.name == "nt" else "npm"), "run", "test:accounts"], cwd=ROOT / "frontend", env=browser_env, check=True)
        stop(); start("3s")
        expiring = Client(base)
        expiring.login("bob@example.com")
        # Expires in the repository too, not just in the browser CookieJar.
        stored_cookie = next(iter(expiring.cookies))
        stored_cookie.expires = None
        time.sleep(2)
        expiring.call("/me")
        time.sleep(2)
        expiring.call("/me")
        # Keep sending even after the client cookie lifetime, to test server rejection.
        next(iter(expiring.cookies)).expires = None
        time.sleep(4)
        expiring.call("/me", expected=401)
        stop(); start("24h", "true")
        _, headers = Client(base).call("/auth/csrf")
        assert "Secure" in headers.get("Set-Cookie", "")
        print("PASS: fresh/upgrade/collision migrations, real auth/CSRF/isolation/bookmarks/concurrency/restart/expiry/cookies", flush=True)
    finally:
        stop()
        for log in logs:
            log.close()
        # pgserver owns only the temporary cluster allocated above.
        server.cleanup()


if __name__ == "__main__":
    main()
