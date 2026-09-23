"""산업(sector) 조회·저장 — 실 PostgreSQL 검증 (WP-204).

`db.save_sectors` 는 안에서 커밋하므로 롤백으로 격리할 수 없다. 테스트마다 고유
티커를 넣고 끝나면 지운다(spike/tests/test_baseline_sink_pg.py 와 같은 방식).

돌리는 법 — 저장소 루트에서 개발 스택을 띄우고:

    docker compose up -d postgres
    cd data-pipeline/stock && pytest tests/test_sectors_pg.py

DATABASE_URL 이 있으면 그걸 쓰고, 없으면 docker-compose 기본 DSN 으로 붙는다.
붙지 못하면 skip 한다.
"""

from __future__ import annotations

import os
import uuid

import pytest

from stock import db

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

#: docker-compose.yml 의 개발 기본값. 운영 자격증명이 아니다.
DEFAULT_DSN = "postgresql://wikipulse:wikipulse@localhost:5432/wikipulse"


@pytest.fixture()
def conn():
    dsn = os.environ.get("DATABASE_URL") or DEFAULT_DSN
    try:
        connection = psycopg.connect(dsn, connect_timeout=5)
    except psycopg.OperationalError as err:
        pytest.skip(f"PostgreSQL 연결 불가 — docker compose up -d postgres ({err})")
    with connection:
        yield connection


@pytest.fixture()
def tickers(conn):
    """산업 없는 종목 하나, 있는 종목 하나. 끝나면 지운다."""
    tag = uuid.uuid4().hex[:8].upper()
    empty, filled = f"ZZE{tag}", f"ZZF{tag}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stock (ticker, name, exchange, sector) VALUES "
            "(%s, 'pytest empty', 'NYSE', NULL), (%s, 'pytest filled', 'NYSE', 'Energy')",
            (empty, filled),
        )
    conn.commit()
    yield empty, filled
    with conn.cursor() as cur:
        cur.execute("DELETE FROM stock WHERE ticker IN (%s, %s)", (empty, filled))
    conn.commit()


def sector_of(conn, ticker):
    with conn.cursor() as cur:
        cur.execute("SELECT sector FROM stock WHERE ticker = %s", (ticker,))
        return cur.fetchone()[0]


def test_산업이_없는_종목만_나온다(conn, tickers):
    empty, filled = tickers
    missing = db.tickers_missing_sector(conn)

    assert empty in missing
    assert filled not in missing


def test_저장하면_값이_들어가고_대상에서_빠진다(conn, tickers):
    empty, _ = tickers
    assert db.save_sectors(conn, [(empty, "Industrials")]) == 1

    assert sector_of(conn, empty) == "Industrials"
    assert empty not in db.tickers_missing_sector(conn)


def test_저장은_다른_컬럼과_다른_종목을_건드리지_않는다(conn, tickers):
    """운영 DB 에는 sector 외 컬럼을 쓰지 않는다 — 이름·거래소·다른 종목 산업이 그대로여야 한다."""
    empty, filled = tickers
    db.save_sectors(conn, [(empty, "Industrials")])

    with conn.cursor() as cur:
        cur.execute("SELECT name, exchange FROM stock WHERE ticker = %s", (empty,))
        assert cur.fetchone() == ("pytest empty", "NYSE")
    assert sector_of(conn, filled) == "Energy"
