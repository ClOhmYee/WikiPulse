"""writer 왕복 테스트용 픽스처 — 진짜 PostgreSQL(pgserver)에 마이그레이션 전체를 올린다.

Docker 없이 돈다. cluster/tests/conftest.py 와 같은 방식 — db/migrations 를 버전
순서로 적재하고, 모듈 스코프로 한 번 띄운 뒤 테스트마다 롤백한다.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

pgserver = pytest.importorskip("pgserver", reason="pgserver 미설치 — writer 왕복 테스트 건너뜀")
psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — writer 왕복 테스트 건너뜀")

# data-pipeline/gkg/tests -> 저장소 루트 -> db/migrations
MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[3] / "db" / "migrations"


def _all_migrations() -> list[pathlib.Path]:
    files = MIGRATIONS_DIR.glob("V*__*.sql")
    return sorted(files, key=lambda p: int(p.name.split("__")[0][1:]))


@pytest.fixture(scope="module")
def conn():
    data_dir = tempfile.mkdtemp(prefix="wikipulse-gkg-pg-")
    server = pgserver.get_server(data_dir)
    for migration in _all_migrations():
        server.psql(migration.read_text(encoding="utf-8"))
    connection = psycopg.connect(server.get_uri())
    connection.autocommit = False
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def rollback(conn):
    yield
    conn.rollback()
