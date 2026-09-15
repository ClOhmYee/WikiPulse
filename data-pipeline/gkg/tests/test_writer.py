"""cluster_org_mention 저장 왕복 검증. 진짜 PostgreSQL(pgserver)에 쓴다.

rank() 출력 + ticker 를 persist_org_mentions 로 저장하고 다시 읽어, 스키마 제약
(PK·FK·NOT NULL)을 통과하고 계약대로 저장되는지, 재계산이 멱등인지, 제약이 실제로
강제되는지(음성 경로)까지 본다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

psycopg = pytest.importorskip("psycopg")
import psycopg.errors  # noqa: E402

from gkg.lift import OrgLift  # noqa: E402
from gkg.writer import persist_org_mentions  # noqa: E402


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


def test_매칭과_미매칭을_함께_저장한다(conn):
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


def test_재계산은_멱등이다(conn):
    cid = _cluster(conn)
    _stock(conn, "DUK", "Duke Energy Corporation")

    persist_org_mentions(conn, cid, [(OrgLift("duke energy", 8, 20, 8.4), "DUK")])
    # 같은 클러스터 재계산 — 다른 값으로 덮어쓴다.
    persist_org_mentions(conn, cid, [(OrgLift("duke energy", 9, 18, 9.0), "DUK")])

    rows = _rows(conn, cid)
    assert len(rows) == 1
    assert rows[0] == ("duke energy", "DUK", 9, 18, 9.0)


def test_NULL_ticker_저장_가능(conn):
    cid = _cluster(conn)
    persist_org_mentions(conn, cid, [(OrgLift("associated press", 14, 900, 1.1), None)])
    assert _rows(conn, cid) == [("associated press", None, 14, 900, 1.1)]


def test_stock_삭제시_ticker만_NULL이_되고_행은_남는다(conn):
    # 스키마의 ON DELETE SET NULL 실동작 — CASCADE 였다면 행이 통째로 사라진다.
    cid = _cluster(conn)
    _stock(conn, "DUK", "Duke Energy Corporation")
    persist_org_mentions(conn, cid, [(OrgLift("duke energy", 8, 20, 8.4), "DUK")])
    with conn.cursor() as cur:
        cur.execute("DELETE FROM stock WHERE ticker = 'DUK'")
    rows = _rows(conn, cid)
    assert rows == [("duke energy", None, 8, 20, 8.4)]  # 행 생존, ticker 만 NULL


def test_빈_목록은_기존_행을_지운다(conn):
    cid = _cluster(conn)
    persist_org_mentions(conn, cid, [(OrgLift("x", 3, 5, 4.0), None)])
    persist_org_mentions(conn, cid, [])  # 재계산 결과 0건이면 기존도 지운다
    assert _rows(conn, cid) == []


# --- 제약이 실제로 강제되는가 (음성 경로) ---------------------------------


def test_없는_cluster_id는_FK_위반(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        persist_org_mentions(conn, 999999, [(OrgLift("x", 3, 5, 4.0), None)])


def test_없는_ticker는_FK_위반(conn):
    cid = _cluster(conn)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        persist_org_mentions(conn, cid, [(OrgLift("x", 3, 5, 4.0), "ZZZZ")])


def test_중복_org_name은_PK_위반(conn):
    # rank() 가 org_name 유일성을 보장한다는 writer 전제의 회귀 가드.
    cid = _cluster(conn)
    dup = [(OrgLift("dup", 3, 5, 4.0), None), (OrgLift("dup", 4, 6, 3.0), None)]
    with pytest.raises(psycopg.errors.UniqueViolation):
        persist_org_mentions(conn, cid, dup)
