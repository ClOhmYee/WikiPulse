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
# ⚠️ pgserver 의 `initdb` 는 **경로에 ASCII 가 아닌 문자가 있으면** 죽는다. 픽스처 단계에서
#    테스트가 전부 깨지므로 원인이 안 보인다. 실패 메시지는 이렇게 나온다 (2026-09-21 실측):
#
#      FATAL: invalid byte sequence for encoding "UTF8": 0xb9
#
#    0xb9 는 CP949 로 인코딩된 한글의 첫 바이트다. 데이터 디렉터리뿐 아니라 **pgserver 가
#    설치된 경로**도 해당한다 — Windows 사용자명이 한글이면 홈 밑이 전부 걸리므로 venv·
#    uv 캐시가 거기 있는 한 못 피한다. ASCII 경로(예: C:\pgtest)에 설치하면 그냥 된다.
#    🔴 PostgreSQL 설치 여부와는 무관하다 — pgserver 는 바이너리를 번들로 들고 있다.
#    ⚠️ `--locale=C` 로는 안 풀린다. 로케일 경고는 사라지지만 FATAL 은 그대로다.
#
#    DSN 을 주면 pgserver 를 건너뛴다:
#
#      docker compose up -d postgres
#      WIKIPULSE_TEST_DSN=postgresql://wikipulse:wikipulse@localhost:5432/wikipulse pytest
#
# 이 경로는 마이그레이션을 적재하지 않는다. 먼저 compose의 migrate 서비스를 실행한다.
# 기존 이력 없는 볼륨의 적용 버전 등록 절차는 docker/README.md를 참고한다.
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
