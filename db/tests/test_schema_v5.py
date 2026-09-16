"""cluster_stock 재사용·재시도 컬럼 검증 — V5 (WP-44 재오픈·-49·-50).

conftest 픽스처(conn)가 V1~V5 를 순서대로 적재한다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402


def _stock(conn, ticker: str) -> None:
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES (%s, %s, 'NYSE')", ticker, ticker)


def _cluster(conn, **cols) -> int:
    base = {"snapshot_ts": "now()", "pulse_score": "1.0"}
    base.update(cols)
    keys = ", ".join(base)
    vals = ", ".join(str(v) for v in base.values())
    x(conn, f"INSERT INTO issue_cluster ({keys}) VALUES ({vals})")
    return q(conn, "SELECT max(id) FROM issue_cluster")[0][0]


def test_새_컬럼_기본값(conn):
    """check_state 기본 PENDING, attempt_count 기본 0 — V1 방식 삽입이 그대로 돈다."""
    _stock(conn, "RUS1")
    cid = _cluster(conn)
    x(conn, "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'RUS1', 'BOTH')", cid)
    row = q(
        conn,
        "SELECT check_state, attempt_count, issue_key, prompt_version, confidence "
        "FROM cluster_stock WHERE ticker = 'RUS1'",
    )[0]
    assert row == ("PENDING", 0, None, None, None)


def test_check_state는_정해진_값만_받는다(conn):
    _stock(conn, "RUS2")
    cid = _cluster(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_stock (cluster_id, ticker, tier, check_state) "
            "VALUES (%s, 'RUS2', 'BOTH', 'RUNNING')",  # 오타/미정의 값
            cid,
        )


def test_confidence는_strong_weak만_받는다(conn):
    _stock(conn, "RUS3")
    cid = _cluster(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_stock (cluster_id, ticker, tier, confidence) "
            "VALUES (%s, 'RUS3', 'BOTH', 'medium')",
            cid,
        )


def test_attempt_count는_음수_불가(conn):
    _stock(conn, "RUS4")
    cid = _cluster(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_stock (cluster_id, ticker, tier, attempt_count) "
            "VALUES (%s, 'RUS4', 'BOTH', -1)",
            cid,
        )


def test_같은_issue_key_ticker가_여러_스냅샷_cluster_id에_걸쳐_반복된다(conn):
    """cluster_id 는 스냅샷마다 새로 생긴다 — issue_key+ticker 중복은 제약 위반이 아니다.

    UNIQUE 로 묶었으면 두 번째 INSERT 가 깨졌어야 한다(V5 마이그레이션 설명 참고).
    """
    _stock(conn, "RUS5")
    c1 = _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-09T12:00Z'")
    c2 = _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-09T13:00Z'")

    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified, match_path, rationale) "
        "VALUES (%s, 'RUS5', 'BOTH', 'milton-2024', 'v1', 'DONE', true, "
        " 'REGION', '근거 문장')",
        c1,
    )
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified, match_path, rationale) "
        "VALUES (%s, 'RUS5', 'BOTH', 'milton-2024', 'v1', 'DONE', true, "
        " 'REGION', '근거 문장')",
        c2,
    )

    rows = q(
        conn,
        "SELECT cluster_id FROM cluster_stock WHERE issue_key = 'milton-2024' AND ticker = 'RUS5' "
        "ORDER BY cluster_id",
    )
    assert [r[0] for r in rows] == [c1, c2]


def test_재사용_조회는_가장_최근_DONE_행을_찾는다(conn):
    """-49 재사용 조회 패턴 — issue_key+ticker+prompt_version 으로 DONE 행을 찾는다."""
    _stock(conn, "RUS6")
    c1 = _cluster(conn, issue_key="'iran-2026'", snapshot_ts="'2026-08-01T00:00Z'")
    c2 = _cluster(conn, issue_key="'iran-2026'", snapshot_ts="'2026-08-02T00:00Z'")

    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified) "
        "VALUES (%s, 'RUS6', 'BOTH', 'iran-2026', 'v1', 'FAILED', false)",
        c1,
    )
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified, match_path, rationale, verified_at) "
        "VALUES (%s, 'RUS6', 'BOTH', 'iran-2026', 'v1', 'DONE', true, "
        " 'DIRECT_MENTION', '근거', '2026-08-02T01:00Z')",
        c2,
    )

    row = q(
        conn,
        "SELECT cluster_id, verified, match_path FROM cluster_stock "
        "WHERE issue_key = 'iran-2026' AND ticker = 'RUS6' AND prompt_version = 'v1' "
        "  AND check_state = 'DONE' "
        "ORDER BY verified_at DESC LIMIT 1",
    )[0]
    assert row == (c2, True, "DIRECT_MENTION")  # FAILED 행(c1)은 재사용 대상에서 빠진다


def test_프롬프트_버전이_다르면_재사용_안_된다(conn):
    """-49: prompt_version 을 올리면 이전 판정은 캐시 히트 대상이 아니다."""
    _stock(conn, "RUS7")
    cid = _cluster(conn, issue_key="'nvidia-2026'")
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified) "
        "VALUES (%s, 'RUS7', 'BOTH', 'nvidia-2026', 'v1', 'DONE', true)",
        cid,
    )
    rows = q(
        conn,
        "SELECT * FROM cluster_stock WHERE issue_key = 'nvidia-2026' AND ticker = 'RUS7' "
        "  AND prompt_version = 'v2' AND check_state = 'DONE'",
    )
    assert rows == []
