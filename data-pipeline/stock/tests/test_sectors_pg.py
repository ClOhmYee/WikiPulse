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
import sys
import types
import uuid

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

# psycopg 를 모듈 최상단에서 임포트하므로 importorskip 뒤에 둬야 skip 이 먹는다.
from stock import db, sectors  # noqa: E402

#: docker-compose.yml 의 개발 기본값. 운영 자격증명이 아니다.
DEFAULT_DSN = "postgresql://wikipulse:wikipulse@localhost:5432/wikipulse"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_DSN


@pytest.fixture()
def conn():
    dsn = _dsn()
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
    conn.rollback()  # 테스트가 SQL 오류로 끝나 트랜잭션이 깨져 있어도 정리는 돌게
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


# --- run() -------------------------------------------------------------------
# yfinance 는 네트워크라 가짜 모듈로 바꾼다. run() 이 함수 안에서 import 하므로
# sys.modules 를 monkeypatch 하면 테스트가 끝날 때 원래대로 돌아온다.


def _fake_yfinance(monkeypatch, infos: dict):
    """infos: 심볼 → info dict, 또는 예외 인스턴스(그 종목 호출 시 던진다)."""

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def info(self):
            value = infos.get(self.symbol, {"trailingPegRatio": None})  # 없는 심볼 실측 형태
            if isinstance(value, Exception):
                raise value
            return value

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    # db.dsn() 은 환경변수만 본다. 픽스처가 기본 DSN 으로 붙었으면 run() 도 거기 붙게.
    monkeypatch.setenv("DATABASE_URL", _dsn())


def test_run_은_비어있는_종목만_채우고_나머지는_알린다(conn, tickers, monkeypatch, capsys):
    empty, filled = tickers
    _fake_yfinance(monkeypatch, {empty: {"sector": "Industrials"}, filled: {"sector": "WRONG"}})

    code = sectors.run(tickers=[empty, filled, "ZZNOPE_NOT_IN_MASTER"], throttle=0)

    err = capsys.readouterr().err
    assert code == 0
    assert sector_of(conn, empty) == "Industrials"
    assert sector_of(conn, filled) == "Energy"  # 이미 있는 값은 다시 부르지도 덮지도 않는다
    assert f"이미 산업이 있어 건너뜀: {filled}" in err
    assert "마스터에 없어 제외: ZZNOPE_NOT_IN_MASTER" in err


def test_run_dry_run_은_저장하지_않는다(conn, tickers, monkeypatch):
    empty, _ = tickers
    _fake_yfinance(monkeypatch, {empty: {"sector": "Industrials"}})

    assert sectors.run(tickers=[empty], dry_run=True, throttle=0) == 0
    assert sector_of(conn, empty) is None


def test_run_sector_가_없으면_NULL_로_두고_성공이다(conn, tickers, monkeypatch):
    """SPAC·없는 심볼은 예외 없이 sector 없는 dict 가 온다 — 실패가 아니다."""
    empty, _ = tickers
    _fake_yfinance(monkeypatch, {})

    assert sectors.run(tickers=[empty], throttle=0) == 0
    assert sector_of(conn, empty) is None


def test_run_전부_예외면_종료코드_1(conn, tickers, monkeypatch):
    empty, _ = tickers
    _fake_yfinance(monkeypatch, {empty: RuntimeError("Too Many Requests")})

    assert sectors.run(tickers=[empty], throttle=0) == 1
    assert sector_of(conn, empty) is None


def test_run_서킷_브레이커로_멈춰도_받은_값은_저장한다(conn, monkeypatch):
    """브레이커가 break 해도 루프 밖 최종 저장이 돌아야 한다 — 청크가 안 찬 버퍼가 버려지면 안 된다."""
    tag = uuid.uuid4().hex[:8].upper()
    ok, bad1, bad2, never = (f"ZZ{c}{tag}" for c in "ABCD")  # 정렬 순서 = 호출 순서
    names = [ok, bad1, bad2, never]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO stock (ticker, name, exchange) VALUES (%s, 'pytest', 'NYSE')",
            [(t,) for t in names],
        )
    conn.commit()
    try:
        monkeypatch.setattr(sectors, "CIRCUIT_BREAK", 2)
        _fake_yfinance(monkeypatch, {
            ok: {"sector": "Utilities"},
            bad1: RuntimeError("429"),
            bad2: RuntimeError("429"),
            never: {"sector": "Energy"},
        })

        assert sectors.run(tickers=names, throttle=0) == 1
        assert sector_of(conn, ok) == "Utilities"
        assert sector_of(conn, never) is None  # 브레이커 뒤라 호출되지 않았다
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock WHERE ticker = ANY(%s)", (names,))
        conn.commit()
