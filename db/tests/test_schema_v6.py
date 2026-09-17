"""cluster_stock 재사용·재시도 컬럼 검증 — V6 (WP-44 재오픈·-49·-50).

conftest 픽스처(conn)가 V1~V6 를 순서대로 적재한다.
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

    UNIQUE 로 묶었으면 두 번째 INSERT 가 깨졌어야 한다(V6 마이그레이션 설명 참고).
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


# VerificationRepository.findPriorVerdict 와 동일 SQL — 재사용 캐시 조회(-69).
# %s 순서: issue_key, ticker, prompt_version, cluster_id(<>). 부분 인덱스
# (issue_key, ticker, prompt_version) WHERE check_state='DONE' 를 탄다.
_FIND_PRIOR_VERDICT = (
    "SELECT verified, match_path, confidence, rationale "
    "  FROM cluster_stock "
    " WHERE issue_key = %s AND ticker = %s "
    "   AND prompt_version = %s "
    "   AND check_state = 'DONE' "
    "   AND cluster_id <> %s "
    " ORDER BY verified_at DESC NULLS LAST "
    " LIMIT 1"
)

# VerificationRepository.recordReused 와 동일 SQL — 이전 판정 복사 기록(-69).
_RECORD_REUSED = (
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


def test_findPriorVerdict_다른_스냅샷의_최근_DONE을_준다(conn):
    """-69: 진행 중 이슈가 새 cluster_id 로 재감지될 때, 다른 스냅샷의 최근 DONE 판정을 찾는다."""
    _stock(conn, "RUS11")
    c_old = _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-09T12:00Z'")
    c_new = _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-09T13:00Z'")
    # 이전 스냅샷의 확정 판정.
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified, match_path, confidence, rationale, verified_at) "
        "VALUES (%s, 'RUS11', 'BOTH', 'milton-2024', 'v1', 'DONE', true, "
        " 'REGION', 'strong', '복사될 근거', '2024-10-09T12:30Z')",
        c_old,
    )
    # 새 스냅샷의 미검증 후보(자기 행) — DONE 이 아니라 조회에서 빠진다.
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'RUS11', 'BOTH')",
        c_new,
    )

    row = q(conn, _FIND_PRIOR_VERDICT, "milton-2024", "RUS11", "v1", c_new)[0]
    assert row == (True, "REGION", "strong", "복사될 근거")


def test_findPriorVerdict_자기_클러스터_행은_제외한다(conn):
    """🔴 -69: cluster_id <> :cid — 현재 처리 중인 클러스터의 판정은 재사용원으로 세지 않는다.

    유일한 DONE 이 조회 대상 cluster_id 자신이면 결과가 없어야 한다.
    """
    _stock(conn, "RUS12")
    cid = _cluster(conn, issue_key="'iran-2026'")
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, issue_key, prompt_version, "
        " check_state, verified, match_path, confidence, rationale, verified_at) "
        "VALUES (%s, 'RUS12', 'BOTH', 'iran-2026', 'v1', 'DONE', true, "
        " 'REGION', 'strong', '근거', now())",
        cid,
    )
    assert q(conn, _FIND_PRIOR_VERDICT, "iran-2026", "RUS12", "v1", cid) == []


def test_recordReused_이전판정을_복사해_DONE으로_전이한다(conn):
    """-69: LLM 없이 이전 판정 값을 그대로 써 DONE 으로 전이. verified_at 갱신·재사용 키 채움."""
    ticker = "RUS13"
    cid = _pending_candidate(conn, ticker)

    x(conn, _RECORD_REUSED, True, "SUPPLY_CHAIN", "weak", "재사용 근거", "milton-2024", "v1", cid, ticker)

    row = q(
        conn,
        "SELECT check_state, verified, match_path, confidence, rationale, issue_key, prompt_version, "
        "       verified_at IS NOT NULL "
        "FROM cluster_stock WHERE ticker = %s",
        ticker,
    )[0]
    assert row == ("DONE", True, "SUPPLY_CHAIN", "weak", "재사용 근거", "milton-2024", "v1", True)


# VerificationRepository.verifiedPassCountTier12 와 동일 SQL — 3등급(EMBEDDING_ONLY) 발동 게이트.
# 재사용(-69) verified 행이 tier=BOTH/GDELT_ONLY 를 유지한 채 DONE 으로 남아 이 카운트에
# 잡히는지가 서비스 게이트 정확성의 전제다. Java 단위 테스트는 이 카운트를 목으로 스텁하므로,
# "재사용 write → 카운트 증가" 인과는 여기 실 DB 에서만 실측된다.
_VERIFIED_PASS_COUNT_TIER12 = (
    "SELECT count(*) "
    "  FROM cluster_stock "
    " WHERE cluster_id = %s AND check_state = 'DONE' AND verified = true "
    "   AND tier IN ('BOTH', 'GDELT_ONLY')"
)


def test_재사용된_verified행이_tier12_게이트_카운트에_잡힌다(conn):
    """-69 인과 실측: recordReused 로 쓴 DONE+verified+BOTH 행이 게이트 카운트를 0→1 로 올린다.

    recordReused 는 tier 를 건드리지 않아 -67 이 심은 tier(BOTH)가 유지되고, verified=true·
    check_state='DONE' 을 갱신하므로 카운트 조건을 그대로 만족한다.
    """
    _stock(conn, "RUS14")
    cid = _cluster(conn, issue_key="'milton-2024'")
    x(conn, "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'RUS14', 'BOTH')", cid)

    assert q(conn, _VERIFIED_PASS_COUNT_TIER12, cid)[0][0] == 0  # PENDING 은 안 잡힘

    x(conn, _RECORD_REUSED, True, "REGION", "strong", "근거", "milton-2024", "v1", cid, "RUS14")

    assert q(conn, _VERIFIED_PASS_COUNT_TIER12, cid)[0][0] == 1  # 재사용 verified 가 카운트에 잡힘


def test_재사용된_EMBEDDING_ONLY_verified는_tier12_카운트에서_빠진다(conn):
    """-69: EMBEDDING_ONLY 는 캐시 히트로 재사용돼 DONE+verified 가 돼도 tier12 게이트엔 안 잡힌다."""
    _stock(conn, "RUS15")
    cid = _cluster(conn, issue_key="'milton-2024'")
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'RUS15', 'EMBEDDING_ONLY')",
        cid,
    )

    x(conn, _RECORD_REUSED, True, "REGION", "strong", "근거", "milton-2024", "v1", cid, "RUS15")

    assert q(conn, _VERIFIED_PASS_COUNT_TIER12, cid)[0][0] == 0  # tier3 는 게이트 카운트 밖


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
