"""스키마 테스트 공용 픽스처 — 진짜 PostgreSQL(pgserver)을 한 번 띄운다.

Docker 없이 돈다. pgserver 가 PostgreSQL 바이너리와 pgvector 를 번들로 들고 있다.
migrations/V*.sql 을 버전 순서대로 적재하므로 V1·V2·… 가 모두 반영된 스키마를
검사한다. 모듈 스코프로 한 번만 띄우고(기동 ~10초) 테스트마다 롤백한다.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

pgserver = pytest.importorskip("pgserver", reason="pgserver 미설치 — 스키마 테스트 건너뜀")
psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 스키마 테스트 건너뜀")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "migrations"


def _all_migrations() -> list[pathlib.Path]:
    """V1, V2, … 버전 순서대로. Flyway 규칙(V<n>__)을 파일명 숫자로 정렬한다."""
    files = MIGRATIONS_DIR.glob("V*__*.sql")
    return sorted(files, key=lambda p: int(p.name.split("__")[0][1:]))


@pytest.fixture(scope="module")
def conn():
    data_dir = tempfile.mkdtemp(prefix="wikipulse-pg-test-")
    server = pgserver.get_server(data_dir)
    for migration in _all_migrations():
        server.psql(migration.read_text(encoding="utf-8"))

    connection = psycopg.connect(server.get_uri())
    connection.autocommit = False
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def rollback(conn):
    """테스트마다 롤백해서 서로 간섭하지 않게 한다."""
    yield
    conn.rollback()


def q(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall() if cur.description else None


def x(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
