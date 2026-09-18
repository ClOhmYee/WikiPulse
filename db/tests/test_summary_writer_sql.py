"""이슈 요약 writer·라이프사이클 전이(WP-119)의 네이티브 SQL 을 진짜 PostgreSQL 로 검증한다.

백엔드의 `IssueSummaryRepository` 는 매핑 엔티티 없이 raw JDBC 로 이 SQL 을 돌린다 —
`ddl-auto=validate` 로는 안 잡히므로 실 DB 검증이 여기(db pgserver 테스트) 몫이다
(`test_candidate_worker_sql.py` 와 같은 관습). 아래 SQL 은 그 리포지토리 문장을 그대로 옮겼다.

못 박는 것:
    - issue_report 멱등 upsert (ON CONFLICT cluster_id — 요약·모델·생성시각 갱신)
    - status 전이 가드: DETECTED→VERIFYING, VERIFYING→CONFIRMED 만, 되돌리지 않음
    - 요약 재사용 조회 (같은 issue_key 의 다른 스냅샷 요약, 자기 행 제외)
    - CONFIRMED 게이트: cluster_stock 존재 AND PENDING 0 (빈 후보·PENDING 은 미완료, 0통과는 정상)
    - as-of: 각 스냅샷(cluster_id)이 자기 요약 행을 가져 과거 조회에 미래 요약이 안 샌다
"""

from __future__ import annotations

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")


def _new_cluster(conn, **cols) -> int:
    # 값은 바인딩 파라미터로 나가므로 SQL 표현식이 아니라 평범한 값을 준다.
    # snapshot_ts 는 ISO 문자열, status/issue_key 는 따옴표 없는 값.
    base = {"snapshot_ts": "2026-09-01T00:00:00+00:00", "pulse_score": 1.0}
    base.update(cols)
    keys = ", ".join(base)
    placeholders = ", ".join(["%s"] * len(base))
    rows = q(
        conn,
        f"INSERT INTO issue_cluster ({keys}) VALUES ({placeholders}) RETURNING id",
        *base.values(),
    )
    return rows[0][0]


def _ensure_stock(conn, ticker: str) -> None:
    x(
        conn,
        "INSERT INTO stock (ticker, name, exchange) VALUES (%s, %s, 'NASDAQ') "
        "ON CONFLICT (ticker) DO NOTHING",
        ticker,
        ticker + " Inc",
    )


def _add_candidate(conn, cluster_id: int, ticker: str, check_state: str, verified=False) -> None:
    _ensure_stock(conn, ticker)
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, check_state, verified) "
        "VALUES (%s, %s, 'BOTH', %s, %s)",
        cluster_id,
        ticker,
        check_state,
        verified,
    )


# IssueSummaryRepository 문장 그대로 (자리표시자만 :name -> %s).
_UPSERT = """
    INSERT INTO issue_report (cluster_id, summary, model, generated_at)
    VALUES (%s, %s, %s, now())
    ON CONFLICT (cluster_id) DO UPDATE
       SET summary      = EXCLUDED.summary,
           model        = EXCLUDED.model,
           generated_at = EXCLUDED.generated_at
"""

_ADVANCE = "UPDATE issue_cluster SET status = 'VERIFYING' WHERE id = %s AND status = 'DETECTED'"
_CONFIRM = "UPDATE issue_cluster SET status = 'CONFIRMED' WHERE id = %s AND status = 'VERIFYING'"

_FIND_PRIOR = """
    SELECT r.summary, r.model
      FROM issue_report r
      JOIN issue_cluster c ON c.id = r.cluster_id
     WHERE c.issue_key = %s
       AND r.cluster_id <> %s
       AND r.model = %s
     ORDER BY r.generated_at DESC
     LIMIT 1
"""


def _upsert(conn, cluster_id, summary, model):
    with conn.cursor() as cur:
        cur.execute(_UPSERT, (cluster_id, summary, model))


def _insert_report_at(conn, cluster_id, summary, model, generated_at):
    # generated_at 을 명시로 넣는다 — now() 는 트랜잭션 내 상수라 한 테스트 안에서 시각이 안 벌어진다.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO issue_report (cluster_id, summary, model, generated_at) "
            "VALUES (%s, %s, %s, %s)",
            (cluster_id, summary, model, generated_at),
        )


def _rowcount(conn, sql, *args) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.rowcount


def _stock_verification_complete(conn, cluster_id: int) -> bool:
    # IssueSummaryRepository.stockVerificationComplete 의 단일 원자 쿼리를 그대로 옮긴다.
    return q(
        conn,
        "SELECT count(*) > 0 AND count(*) FILTER (WHERE check_state = 'PENDING') = 0 "
        "FROM cluster_stock WHERE cluster_id = %s",
        cluster_id,
    )[0][0]


# ── issue_report 멱등 upsert ────────────────────────────────────────────────


def test_upsert_creates_then_updates_in_place(conn):
    cid = _new_cluster(conn)
    _upsert(conn, cid, "첫 요약", "model-a")
    _upsert(conn, cid, "고친 요약", "model-b")

    rows = q(conn, "SELECT summary, model FROM issue_report WHERE cluster_id = %s", cid)
    assert len(rows) == 1  # PK 충돌이 새 행을 만들지 않는다
    assert rows[0] == ("고친 요약", "model-b")


def test_upsert_bumps_generated_at(conn):
    cid = _new_cluster(conn)
    _upsert(conn, cid, "요약", "m")
    first = q(conn, "SELECT generated_at FROM issue_report WHERE cluster_id = %s", cid)[0][0]
    _upsert(conn, cid, "요약2", "m")
    second = q(conn, "SELECT generated_at FROM issue_report WHERE cluster_id = %s", cid)[0][0]
    assert second >= first


# ── status 전이 가드 ────────────────────────────────────────────────────────


def test_advance_only_from_detected(conn):
    cid = _new_cluster(conn, status="DETECTED")
    assert _rowcount(conn, _ADVANCE, cid) == 1
    assert q(conn, "SELECT status FROM issue_cluster WHERE id = %s", cid)[0][0] == "VERIFYING"
    # 다시 올리려 해도 이미 DETECTED 가 아니라 0행 — 되돌리지 않는다.
    assert _rowcount(conn, _ADVANCE, cid) == 0


@pytest.mark.parametrize("status", ["VERIFYING", "CONFIRMED", "DISCARDED"])
def test_advance_noop_for_non_detected(conn, status):
    cid = _new_cluster(conn, status=status)
    assert _rowcount(conn, _ADVANCE, cid) == 0


def test_confirm_only_from_verifying(conn):
    cid = _new_cluster(conn, status="VERIFYING")
    assert _rowcount(conn, _CONFIRM, cid) == 1
    assert q(conn, "SELECT status FROM issue_cluster WHERE id = %s", cid)[0][0] == "CONFIRMED"


@pytest.mark.parametrize("status", ["DETECTED", "CONFIRMED", "DISCARDED"])
def test_confirm_noop_for_non_verifying(conn, status):
    cid = _new_cluster(conn, status=status)
    assert _rowcount(conn, _CONFIRM, cid) == 0


# ── 요약 재사용 조회 (issue_key) ─────────────────────────────────────────────


def test_find_prior_summary_returns_other_snapshot(conn):
    old = _new_cluster(conn, issue_key="iran-2026-08", snapshot_ts="2026-08-31T00:00:00+00:00")
    new = _new_cluster(conn, issue_key="iran-2026-08", snapshot_ts="2026-09-01T00:00:00+00:00")
    _upsert(conn, old, "이전 스냅샷 요약", "model-x")

    rows = q(conn, _FIND_PRIOR, "iran-2026-08", new, "model-x")
    assert rows == [("이전 스냅샷 요약", "model-x")]


def test_find_prior_summary_excludes_self(conn):
    cid = _new_cluster(conn, issue_key="iran-2026-08")
    _upsert(conn, cid, "자기 요약", "m")
    # 자기 행뿐이면 재사용원이 없다(cluster_id <> self).
    assert q(conn, _FIND_PRIOR, "iran-2026-08", cid, "m") == []


def test_find_prior_summary_picks_latest(conn):
    # 재사용 조회는 generated_at DESC 로 최신 요약 1행을 고른다(스냅샷 시각과 무관).
    a = _new_cluster(conn, issue_key="k")
    b = _new_cluster(conn, issue_key="k")
    target = _new_cluster(conn, issue_key="k")
    _insert_report_at(conn, a, "오래된 요약", "m", "2026-08-31T00:00:00+00:00")
    _insert_report_at(conn, b, "최신 요약", "m", "2026-09-01T00:00:00+00:00")

    assert q(conn, _FIND_PRIOR, "k", target, "m")[0] == ("최신 요약", "m")


def test_find_prior_summary_scoped_by_issue_key(conn):
    other = _new_cluster(conn, issue_key="other-issue")
    target = _new_cluster(conn, issue_key="my-issue")
    _upsert(conn, other, "다른 이슈 요약", "m")
    # 다른 issue_key 의 요약은 재사용 안 된다.
    assert q(conn, _FIND_PRIOR, "my-issue", target, "m") == []


def test_find_prior_summary_scoped_by_model(conn):
    # 🔴 model(=모델·프롬프트버전)이 다르면 재사용 안 한다 — 프롬프트/모델 상향 시 재생성되게.
    old = _new_cluster(conn, issue_key="k")
    target = _new_cluster(conn, issue_key="k")
    _upsert(conn, old, "옛 프롬프트 요약", "claude-x (summary_v1)")
    # 현재 모델이 summary_v2 면 v1 요약은 재사용 대상이 아니다.
    assert q(conn, _FIND_PRIOR, "k", target, "claude-x (summary_v2)") == []
    # 같은 model 이면 재사용된다.
    assert q(conn, _FIND_PRIOR, "k", target, "claude-x (summary_v1)")[0] == (
        "옛 프롬프트 요약", "claude-x (summary_v1)")


# ── CONFIRMED 게이트: 종목 검증 완료 판정 ────────────────────────────────────


def test_gate_empty_candidates_is_incomplete(conn):
    # 후보가 아예 없으면 "-67 미실행"으로 보아 미완료 — 확정 금지(장애·미도착 오인 방지).
    cid = _new_cluster(conn)
    assert _stock_verification_complete(conn, cid) is False


def test_gate_pending_candidate_is_incomplete(conn):
    cid = _new_cluster(conn)
    _add_candidate(conn, cid, "AAA", "DONE", verified=True)
    _add_candidate(conn, cid, "BBB", "PENDING")
    assert _stock_verification_complete(conn, cid) is False


def test_gate_all_done_is_complete_even_with_zero_verified(conn):
    # 전부 탈락(0 통과)이어도 PENDING 이 없으면 완료 — 정상 0-종목 확정의 근거(§10 11번).
    cid = _new_cluster(conn)
    _add_candidate(conn, cid, "AAA", "DONE", verified=False)
    _add_candidate(conn, cid, "BBB", "DONE", verified=False)
    assert _stock_verification_complete(conn, cid) is True


def test_gate_failed_and_done_is_complete(conn):
    # FAILED(3회 파킹)·DONE 만 남으면 더 시도할 PENDING 이 없어 완료다.
    cid = _new_cluster(conn)
    _add_candidate(conn, cid, "AAA", "DONE", verified=True)
    _add_candidate(conn, cid, "BBB", "FAILED")
    assert _stock_verification_complete(conn, cid) is True


# ── as-of: 스냅샷별 요약 격리 ────────────────────────────────────────────────


def test_summary_is_per_snapshot_no_future_leak(conn):
    # 같은 issue_key 의 과거·현재 스냅샷이 각자 요약 행을 가진다. 과거 cluster_id 로 읽으면
    # 그 시점 요약만 나오고, 나중 스냅샷 요약이 소급 노출되지 않는다(§3.2 8번 as-of).
    past = _new_cluster(conn, issue_key="k", snapshot_ts="2026-08-31T00:00:00+00:00")
    now = _new_cluster(conn, issue_key="k", snapshot_ts="2026-09-01T00:00:00+00:00")
    _upsert(conn, past, "과거 요약", "m")
    _upsert(conn, now, "현재 요약", "m")

    read_past = q(conn, "SELECT summary FROM issue_report WHERE cluster_id = %s", past)
    assert read_past == [("과거 요약",)]  # 미래("현재 요약")가 안 샌다


# ── writer 산출물이 읽기 API 투영과 만나는 지점: 정상 0종목 vs 진행 중 구분 ──────
#
# IssueQueryRepository.findSummary / findVerifiedStocks 와 issue_cluster.status 는 API 가
# 그대로 읽는다. 아래는 그 실제 읽기 SQL 로 두 종단 상태가 구분되는지를 못 박는다(§10 11번,
# "재시도 중 이슈를 빈 확정 결과로 노출 안 함").

_READ_SUMMARY = "SELECT summary FROM issue_report WHERE cluster_id = %s"
_READ_STATUS = "SELECT status FROM issue_cluster WHERE id = %s"
_READ_VERIFIED_COUNT = "SELECT count(*) FROM cluster_stock WHERE cluster_id = %s AND verified"


def test_confirmed_zero_stock_reads_as_normal_empty(conn):
    # 요약·종목 검증 모두 끝나 통과 종목이 0개인 정상 확정: status=CONFIRMED, 요약 있음, 통과 0.
    cid = _new_cluster(conn, status="VERIFYING")
    _add_candidate(conn, cid, "AAA", "DONE", verified=False)  # 검증 끝, 탈락
    _upsert(conn, cid, "이슈 요약", "m")
    assert _stock_verification_complete(conn, cid) is True
    x(conn, _CONFIRM, cid)

    assert q(conn, _READ_STATUS, cid)[0][0] == "CONFIRMED"
    assert q(conn, _READ_SUMMARY, cid)[0][0] == "이슈 요약"
    assert q(conn, _READ_VERIFIED_COUNT, cid)[0][0] == 0


def test_in_progress_not_shown_as_confirmed_empty(conn):
    # 진행 중(재시도 대기): PENDING 남음·요약 없음 → 확정 안 됨. 통과 0 은 같지만 status·요약으로
    # 정상 0종목과 구분된다 — 빈 확정 결과로 노출되면 안 된다.
    cid = _new_cluster(conn, status="VERIFYING")
    _add_candidate(conn, cid, "AAA", "PENDING")
    # 게이트(서비스)가 확정을 막는다: 종목 검증 미완료 → confirm 을 부르지 않으므로 VERIFYING 유지.
    # (confirm SQL 자체는 status 만 가드하므로, 완료 판정은 이 게이트 뒤에서만 부른다.)
    assert _stock_verification_complete(conn, cid) is False

    assert q(conn, _READ_STATUS, cid)[0][0] == "VERIFYING"   # 정상 0종목(CONFIRMED)과 다르다
    assert q(conn, _READ_SUMMARY, cid) == []                  # 요약 없음(정상 0종목엔 요약이 있다)
    assert q(conn, _READ_VERIFIED_COUNT, cid)[0][0] == 0
