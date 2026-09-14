"""cluster_org_mention 저장 왕복 검증. 진짜 PostgreSQL(pgserver)에 쓴다.

rank() 출력 + ticker 를 persist_org_mentions 로 저장하고 다시 읽어, 스키마 제약
(PK·FK·NOT NULL)을 통과하고 계약대로 저장되는지, 재계산이 멱등인지 본다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("psycopg")

from gkg.lift import OrgLift
from gkg.writer import persist_org_mentions


def _cluster(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO issue_cluster (snapshot_ts, pulse_score, source) "
            "VALUES (%s, %s, 'replay') RETURNING id",
            (datetime(2024, 10, 10, tzinfo=timezone.utc), 9.3),
        )
        return cur.fetchone()[0]


def _stock(conn, ticker: str, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stock (ticker, name, exchange) VALUES (%s, %s, 'NYSE')",
            (ticker, name),
        )


def _rows(conn, cluster_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT org_name, ticker, issue_count, corpus_count, lift "
            "FROM cluster_org_mention WHERE cluster_id = %s ORDER BY lift DESC",
            (cluster_id,),
        )
        return cur.fetchall()


def test_persists_matched_and_unmatched(conn):
    cid = _cluster(conn)
    _stock(conn, "DUK", "Duke Energy Corporation")
    mentions = [
        (OrgLift("duke energy", 8, 20, 8.4), "DUK"),
        (OrgLift("national hurricane center", 26, 30, 12.0), None),  # 미매칭
    ]
    n = persist_org_mentions(conn, cid, mentions)
    assert n == 2

    rows = _rows(conn, cid)
    assert rows[0] == ("national hurricane center", None, 26, 30, 12.0)
    assert rows[1] == ("duke energy", "DUK", 8, 20, 8.4)


def test_recompute_is_idempotent(conn):
    cid = _cluster(conn)
    _stock(conn, "DUK", "Duke Energy Corporation")

    persist_org_mentions(conn, cid, [(OrgLift("duke energy", 8, 20, 8.4), "DUK")])
    # 같은 클러스터 재계산 — 다른 값으로 덮어쓴다.
    persist_org_mentions(conn, cid, [(OrgLift("duke energy", 9, 18, 9.0), "DUK")])

    rows = _rows(conn, cid)
    assert len(rows) == 1
    assert rows[0] == ("duke energy", "DUK", 9, 18, 9.0)


def test_null_ticker_allowed_and_fk_set_null_semantics(conn):
    cid = _cluster(conn)
    # 종목 마스터에 없는 기관 — ticker NULL 로 저장된다.
    persist_org_mentions(conn, cid, [(OrgLift("associated press", 14, 900, 1.1), None)])
    rows = _rows(conn, cid)
    assert rows == [("associated press", None, 14, 900, 1.1)]


def test_empty_mentions_clears_existing(conn):
    cid = _cluster(conn)
    persist_org_mentions(conn, cid, [(OrgLift("x", 3, 5, 4.0), None)])
    persist_org_mentions(conn, cid, [])  # 재계산 결과 0건이면 기존도 지운다
    assert _rows(conn, cid) == []
