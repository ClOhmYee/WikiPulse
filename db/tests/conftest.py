"""스키마 테스트 공용 픽스처 — 진짜 PostgreSQL(pgserver)을 한 번 띄운다.

Docker 없이 돈다. pgserver 가 PostgreSQL 바이너리와 pgvector 를 번들로 들고 있다.
migrations/V*.sql 을 버전 순서대로 적재하므로 V1·V2·… 가 모두 반영된 스키마를
검사한다. 모듈 스코프로 한 번만 띄우고(기동 ~10초) 테스트마다 롤백한다.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 스키마 테스트 건너뜀")

# 이미 마이그레이션이 적재된 PostgreSQL 을 직접 쓰는 길(WP-168).
#
# ⚠️ pgserver 는 Windows 에서 `initdb` 가 실패해 픽스처 단계에서 전부 죽는다. 이 PC 에서는
#    그래서 스키마 테스트를 한 줄도 못 돌렸다. DSN 을 주면 pgserver 를 건너뛴다:
#
#      docker compose up -d postgres
#      WIKIPULSE_TEST_DSN=postgresql://wikipulse:wikipulse@localhost:5432/wikipulse pytest
#
# 🔴 이 경로는 마이그레이션을 적재하지 않는다 — 준 DB 에 이미 있다고 본다(compose 의
#    postgres 이미지가 최초 기동 때 db/migrations 를 넣는다). 스키마를 고쳤으면
#    `docker compose down -v` 후 다시 띄운다.
EXTERNAL_DSN = os.environ.get("WIKIPULSE_TEST_DSN")

if not EXTERNAL_DSN:
    pgserver = pytest.importorskip(
        "pgserver", reason="pgserver 미설치 — WIKIPULSE_TEST_DSN 을 주거나 설치한다")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "migrations"


def _all_migrations() -> list[pathlib.Path]:
    """V1, V2, … 버전 순서대로. Flyway 규칙(V<n>__)을 파일명 숫자로 정렬한다."""
    files = MIGRATIONS_DIR.glob("V*__*.sql")
    return sorted(files, key=lambda p: int(p.name.split("__")[0][1:]))


@pytest.fixture(scope="module")
def conn():
    if EXTERNAL_DSN:
        connection = psycopg.connect(EXTERNAL_DSN)
    else:
        data_dir = tempfile.mkdtemp(prefix="wikipulse-pg-test-")
        server = pgserver.get_server(data_dir)
        for migration in _all_migrations():
            server.psql(migration.read_text(encoding="utf-8"))
        connection = psycopg.connect(server.get_uri())

    # 🔴 autocommit 을 끄는 것이 격리의 전부다 — rollback 픽스처가 매 테스트를 되돌린다.
    #    외부 DB 를 쓸 때 이게 풀리면 남의 개발 DB 에 테스트 행이 남는다.
    connection.autocommit = False
    yield connection
    connection.rollback()
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
