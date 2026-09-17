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


# ─────────────────────────────────────────────────────────────────────────────
# LLM 검증 워커(WP-68)의 상태 전이 SQL 을 실 DB 에서 검증한다.
# 백엔드 VerificationRepository 의 SQL 을 그대로 옮긴다 — 그 자바 SQL 은 DB 없이 도는
# 웹 레이어 테스트뿐이라(관습), CASE UPDATE·null-on-reject 같은 DB 세만틱은 여기서 본다.
# ⚠️ 자바 SQL 을 고치면 아래 문자열도 같이 고쳐야 한다(수기 동기화 — 기존 재사용 테스트와 같은 관습).

# VerificationRepository.recordSchemaFailure 와 동일 SQL.
_RECORD_SCHEMA_FAILURE = (
    "UPDATE cluster_stock "
    "   SET attempt_count = attempt_count + 1, "
    "       check_state   = CASE WHEN attempt_count + 1 >= 3 THEN 'FAILED' ELSE check_state END "
    " WHERE cluster_id = %s AND ticker = %s"
)

# VerificationRepository.recordDone 와 동일 SQL.
_RECORD_DONE = (
    "UPDATE cluster_stock "
    "   SET check_state    = 'DONE', "
    "       verified       = %s, "
    "       match_path     = %s, "
    "       confidence     = %s, "
    "       rationale      = %s, "
    "       verified_at    = now(), "
    "       issue_key      = %s, "
    "       prompt_version = %s "
    " WHERE cluster_id = %s AND ticker = %s"
)


def _pending_candidate(conn, ticker: str) -> int:
    """-67 이 깔아놓는 미검증 후보(check_state 기본 PENDING, attempt 0)."""
    _stock(conn, ticker)
    cid = _cluster(conn)
    x(conn, "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, %s, 'BOTH')", cid, ticker)
    return cid


def test_recordSchemaFailure_3회째에_FAILED로_파킹된다(conn):
    """-50/-68: attempt_count 누적, 3 도달 시 check_state='FAILED'. 그 전까지는 PENDING 유지."""
    ticker = "RUS8"
    cid = _pending_candidate(conn, ticker)

    x(conn, _RECORD_SCHEMA_FAILURE, cid, ticker)
    assert q(conn, "SELECT attempt_count, check_state FROM cluster_stock WHERE ticker = %s", ticker)[0] == (1, "PENDING")

    x(conn, _RECORD_SCHEMA_FAILURE, cid, ticker)
    assert q(conn, "SELECT attempt_count, check_state FROM cluster_stock WHERE ticker = %s", ticker)[0] == (2, "PENDING")

    x(conn, _RECORD_SCHEMA_FAILURE, cid, ticker)
    # 3 도달 — 같은 UPDATE 안에서 attempt_count+1 과 CASE 가 갱신 전 값(2)을 함께 본다 → 3, FAILED.
    assert q(conn, "SELECT attempt_count, check_state FROM cluster_stock WHERE ticker = %s", ticker)[0] == (3, "FAILED")


def test_recordDone_통과는_판정을_저장하고_DONE으로_전이한다(conn):
    """-50/-68: 통과 시 verified/match_path/confidence/rationale + 재사용 키(issue_key·prompt_version)."""
    ticker = "RUS9"
    cid = _pending_candidate(conn, ticker)

    x(conn, _RECORD_DONE, True, "REGION", "strong", "플로리다 전력 노출.", "milton-2024", "v1", cid, ticker)

    row = q(
        conn,
        "SELECT check_state, verified, match_path, confidence, rationale, issue_key, prompt_version, "
        "       verified_at IS NOT NULL "
        "FROM cluster_stock WHERE ticker = %s",
        ticker,
    )[0]
    assert row == ("DONE", True, "REGION", "strong", "플로리다 전력 노출.", "milton-2024", "v1", True)


def test_recordDone_탈락은_경로_필드를_null로_두고_DONE으로_전이한다(conn):
    """-68: verified=false 면 match_path·confidence·rationale 은 null(억지 연결 방지), 재사용 키는 채운다."""
    ticker = "RUS10"
    cid = _pending_candidate(conn, ticker)

    x(conn, _RECORD_DONE, False, None, None, None, "iran-2026", "v1", cid, ticker)

    row = q(
        conn,
        "SELECT check_state, verified, match_path, confidence, rationale, issue_key, prompt_version "
        "FROM cluster_stock WHERE ticker = %s",
        ticker,
    )[0]
    assert row == ("DONE", False, None, None, None, "iran-2026", "v1")


# VerificationRepository.pendingCandidates 와 동일 SQL — 검증 순서(tier 우선 + 신호 강도)를 정한다.
_PENDING_CANDIDATES = (
    "SELECT ticker, tier "
    "  FROM cluster_stock "
    " WHERE cluster_id = %s AND check_state = 'PENDING' "
    " ORDER BY CASE tier WHEN 'BOTH' THEN 0 WHEN 'GDELT_ONLY' THEN 1 ELSE 2 END, "
    "          coalesce(gdelt_lift, 0) DESC, coalesce(similarity, 0) DESC"
)


def test_pendingCandidates_tier_우선_신호강도순으로_PENDING만_준다(conn):
    """-68 검증 순서: BOTH→GDELT_ONLY→EMBEDDING_ONLY, tier 안에서 lift/similarity 내림차순.

    DONE·FAILED 는 제외한다(다시 검증하지 않는다). 서비스의 3등급 게이트가 이 순서에
    의존하므로(1·2등급을 먼저 처리해야 통과 수 집계가 성립) DB 정렬을 직접 검증한다.
    """
    _stock(conn, "TA")
    _stock(conn, "TB")
    _stock(conn, "TC")
    _stock(conn, "TD")
    _stock(conn, "TE")
    cid = _cluster(conn)

    def insert(ticker, tier, *, lift=None, sim=None, state="PENDING"):
        x(
            conn,
            "INSERT INTO cluster_stock (cluster_id, ticker, tier, gdelt_lift, similarity, check_state) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            cid, ticker, tier, lift, sim, state,
        )

    insert("TA", "EMBEDDING_ONLY", sim=0.9)
    insert("TB", "BOTH", lift=5.0)
    insert("TC", "GDELT_ONLY", lift=10.0)
    insert("TD", "BOTH", lift=8.0)
    insert("TE", "GDELT_ONLY", lift=3.0, state="DONE")  # 제외돼야 한다

    rows = q(conn, _PENDING_CANDIDATES, cid)
    # BOTH(lift 8 > 5) → GDELT_ONLY(10) → EMBEDDING_ONLY. DONE(TE)은 빠진다.
    assert [r[0] for r in rows] == ["TD", "TB", "TC", "TA"]
