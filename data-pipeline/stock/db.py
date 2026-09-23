"""PostgreSQL 적재. db/migrations/V1 의 stock 테이블에 맞춘다."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterable, Sequence

import psycopg

from .universe import Stock


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL 이 필요하다. 예:\n"
            "  postgresql://wikipulse:pw@localhost:5432/wikipulse"
        )
    return url


def upsert_stocks(stocks: Sequence[Stock]) -> int:
    """종목 마스터를 넣는다. 이미 있으면 이름·거래소·CIK 를 갱신한다.

    임베딩 컬럼은 건드리지 않는다 — embed.py 가 따로 채운다. 마스터를 다시
    돌려도 이미 계산한 임베딩이 날아가지 않게.
    """
    rows = [(s.ticker, s.name, s.exchange, s.cik) for s in stocks]
    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stock (ticker, name, exchange, cik)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE
              SET name = EXCLUDED.name,
                  exchange = EXCLUDED.exchange,
                  cik = EXCLUDED.cik,
                  updated_at = now()
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def tickers_missing_summary(conn: psycopg.Connection) -> list[str]:
    """사업 설명이 아직 없는 종목. embed.py 가 여기부터 채운다."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM stock "
            "WHERE business_summary IS NULL ORDER BY ticker"
        )
        return [r[0] for r in cur.fetchall()]


def tickers_missing_sector(conn: psycopg.Connection) -> list[str]:
    """산업(sector)이 아직 없는 종목. sectors.py 가 여기부터 채운다 (WP-204)."""
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM stock WHERE sector IS NULL ORDER BY ticker")
        return [r[0] for r in cur.fetchall()]


def tickers_missing_embedding(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM stock "
            "WHERE business_summary IS NOT NULL AND embedding IS NULL "
            "ORDER BY ticker"
        )
        return [r[0] for r in cur.fetchall()]


def save_summaries(conn: psycopg.Connection, summaries: Iterable[tuple[str, str]]) -> int:
    rows = list(summaries)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE stock SET business_summary = %s, updated_at = now() WHERE ticker = %s",
            [(summary, ticker) for ticker, summary in rows],
        )
        conn.commit()
    return len(rows)


def save_sectors(conn: psycopg.Connection, sectors: Iterable[tuple[str, str]]) -> int:
    rows = list(sectors)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE stock SET sector = %s, updated_at = now() WHERE ticker = %s",
            [(sector, ticker) for ticker, sector in rows],
        )
        conn.commit()
    return len(rows)


def save_embeddings(
    conn: psycopg.Connection, embeddings: Iterable[tuple[str, list[float]]]
) -> int:
    rows = list(embeddings)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE stock SET embedding = %s, embedded_at = now() WHERE ticker = %s",
            [(_vec_literal(vec), ticker) for ticker, vec in rows],
        )
        conn.commit()
    return len(rows)


def _vec_literal(vec: list[float]) -> str:
    """pgvector 는 '[1,2,3]' 형태 문자열을 받는다."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


# --- 주가 (WP-64) ---------------------------------------------------

# 일봉 한 행. open/high/low/volume 은 yfinance 결측 시 None 일 수 있다.
# close 는 스키마에서 NOT NULL 이라 값이 없는 행은 prices.py 가 버린다.
PriceRow = tuple[
    str, dt.date, float | None, float | None, float | None, float, int | None
]


def all_tickers(conn: psycopg.Connection) -> list[str]:
    """마스터의 전 종목. 주가 적재 대상이다."""
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM stock ORDER BY ticker")
        return [r[0] for r in cur.fetchall()]


def last_trade_dates(conn: psycopg.Connection) -> dict[str, dt.date]:
    """종목별 가장 최근 trade_date. 증분 갱신이 여기 다음 날부터 받는다.

    한 행도 없는 종목은 결과에 없다 — prices.py 가 그런 종목은 5년 전체를 받는다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, max(trade_date) FROM stock_price GROUP BY ticker"
        )
        return {ticker: last for ticker, last in cur.fetchall()}


def save_prices(conn: psycopg.Connection, prices: Iterable[PriceRow]) -> int:
    """일봉을 upsert 한다. 같은 (ticker, trade_date) 면 값을 덮는다.

    재실행·증분 재적재에서 중복 행이 안 생긴다 (PK ticker, trade_date). 덮어쓰기는
    장 마감 후 확정값 정정(late correction)도 반영한다.
    """
    rows = list(prices)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stock_price
                (ticker, trade_date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, trade_date) DO UPDATE
              SET open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume
            """,
            rows,
        )
        conn.commit()
    return len(rows)
