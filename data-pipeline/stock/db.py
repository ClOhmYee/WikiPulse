"""PostgreSQL 적재. db/migrations/V1 의 stock 테이블에 맞춘다."""

from __future__ import annotations

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
