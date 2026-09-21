"""요약 대상 선택 SQL 을 진짜 PostgreSQL 로 검증한다 (WP-165).

`IssueSummaryRepository.clustersNeedingSummary` 는 window function 을 쓰는 raw JDBC 라
`ddl-auto=validate` 로도 백엔드 단위 테스트로도 안 잡힌다 — 실 DB 검증이 여기 몫이다
(`test_summary_writer_sql.py` 와 같은 관습). 아래 SQL 은 그 문장을 그대로 옮겼다.

🔴 **이게 비용 상한이다.** `batchSize` 는 한 폴의 크기일 뿐이라 폴을 반복하면 미처리
클러스터 전체를 훑는다. 운영 4,474건 전수 요약이 약 277,000 크레딧이라
켜는 순간 넘긴다.

못 박는 것:
    - 스냅샷별 `pulse_score` 상위 N 만 고른다 (화면 정렬과 같은 축)
    - 순위는 **그 스냅샷의 전체 클러스터** 위에서 매긴다 — DETECTED·VERIFYING 만으로
      매기면 상위가 CONFIRMED 로 빠질 때 하위가 올라와 상한이 새어 나간다
    - 같은 issue_key·같은 model 요약이 이미 있으면 상한과 무관하게 고른다 (LLM 0)
    - model 이 다르면 면제가 걸리지 않는다 (프롬프트 버전을 올리면 재생성이라 비용이 든다)
    - 0 이면 무제한 (옛 동작)
"""

from __future__ import annotations

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

MODEL = "claude-x (summary_v1)"

# IssueSummaryRepository.clustersNeedingSummary 의 SQL. 이름 파라미터만 %s 로 바꿨다.
_SELECT = """
WITH ranked AS (
    SELECT id, status, issue_key,
           row_number() OVER (PARTITION BY snapshot_ts
                              ORDER BY pulse_score DESC, id ASC) AS rnk
      FROM issue_cluster
)
SELECT id
  FROM ranked
 WHERE status IN ('DETECTED', 'VERIFYING')
   AND (%(top)s <= 0
        OR rnk <= %(top)s
        OR EXISTS (SELECT 1
                     FROM issue_report r
                     JOIN issue_cluster c2 ON c2.id = r.cluster_id
                    WHERE c2.issue_key IS NOT NULL
                      AND c2.issue_key = ranked.issue_key
                      AND r.model = %(model)s))
 ORDER BY id DESC
 LIMIT %(limit)s
"""


def _select(conn, top: int, limit: int = 100, model: str = MODEL) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(_SELECT, {"top": top, "limit": limit, "model": model})
        return [row[0] for row in cur.fetchall()]


def _cluster(conn, *, score: float, status: str = "DETECTED",
             snapshot: str = "2026-09-01T00:00:00+00:00", issue_key=None) -> int:
    rows = q(
        conn,
        "INSERT INTO issue_cluster (snapshot_ts, pulse_score, status, issue_key) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        snapshot, score, status, issue_key,
    )
    return rows[0][0]


def _report(conn, cluster_id: int, model: str = MODEL) -> None:
    x(
        conn,
        "INSERT INTO issue_report (cluster_id, summary, model, generated_at) "
        "VALUES (%s, '요약', %s, now())",
        cluster_id, model,
    )


def test_스냅샷별_상위_N_만_고른다(conn):
    high = _cluster(conn, score=9.0)
    mid = _cluster(conn, score=5.0)
    low = _cluster(conn, score=1.0)

    assert set(_select(conn, top=2)) == {high, mid}
    assert low not in _select(conn, top=2)


def test_상한_0_은_무제한이다(conn):
    ids = {_cluster(conn, score=s) for s in (9.0, 5.0, 1.0)}

    assert set(_select(conn, top=0)) == ids


def test_스냅샷마다_따로_센다(conn):
    """상한은 스냅샷별이다 — 시점이 늘면 대상도 그만큼 늘어난다(비용 = 스냅샷 수 × N)."""
    a1 = _cluster(conn, score=9.0, snapshot="2026-09-01T00:00:00+00:00")
    a2 = _cluster(conn, score=1.0, snapshot="2026-09-01T00:00:00+00:00")
    b1 = _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")
    b2 = _cluster(conn, score=1.0, snapshot="2026-09-02T00:00:00+00:00")

    picked = set(_select(conn, top=1))

    assert picked == {a1, b1}
    assert a2 not in picked and b2 not in picked


def test_순위는_스냅샷_전체로_매긴다(conn):
    """🔴 상위가 CONFIRMED 로 빠져도 하위가 승격되지 않는다.

    DETECTED·VERIFYING 만으로 순위를 매기면 확정이 늘어날수록 대상이 아래로 번져
    상한이 조용히 새어 나간다. 이 테스트가 그 회귀를 잡는다.
    """
    _cluster(conn, score=9.0, status="CONFIRMED")   # 1위, 이미 종착
    second = _cluster(conn, score=5.0)              # 2위
    third = _cluster(conn, score=1.0)               # 3위

    picked = _select(conn, top=2)

    assert picked == [second]                        # 3위는 올라오지 않는다
    assert third not in picked


def test_DISCARDED_와_CONFIRMED_는_대상이_아니다(conn):
    live = _cluster(conn, score=9.0, status="VERIFYING")
    _cluster(conn, score=8.0, status="CONFIRMED")
    _cluster(conn, score=7.0, status="DISCARDED")

    assert _select(conn, top=0) == [live]


def test_같은_issue_key_요약이_있으면_상한_밖이어도_고른다(conn):
    """재사용은 LLM 0 이라 면제한다 — 과거 스냅샷의 빈 요약이 이것 때문에 사라진다."""
    top_one = _cluster(conn, score=9.0, issue_key="k-1")
    reusable = _cluster(conn, score=0.1, issue_key="k-1",
                        snapshot="2026-09-02T00:00:00+00:00")
    _report(conn, top_one)
    # 같은 스냅샷에서 reusable 보다 높은 클러스터를 둬 상한 밖으로 민다.
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")

    picked = _select(conn, top=1)

    assert reusable in picked


def test_model_이_다르면_면제되지_않는다(conn):
    """프롬프트 버전을 올리면 재생성이라 비용이 든다 — 면제가 걸리면 안 된다."""
    other = _cluster(conn, score=9.0, issue_key="k-2")
    low = _cluster(conn, score=0.1, issue_key="k-2",
                   snapshot="2026-09-02T00:00:00+00:00")
    _report(conn, other, model="claude-x (summary_v0)")
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")

    assert low not in _select(conn, top=1)


def test_issue_key_가_없으면_면제되지_않는다(conn):
    """⚠️ V1 옛 클러스터는 issue_key 가 NULL 이다. NULL = NULL 로 서로 묶이면 안 된다."""
    reported = _cluster(conn, score=9.0, issue_key=None)
    low = _cluster(conn, score=0.1, issue_key=None,
                   snapshot="2026-09-02T00:00:00+00:00")
    _report(conn, reported)
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")

    assert low not in _select(conn, top=1)


def test_limit_은_한_폴의_크기일_뿐이다(conn):
    """batchSize 를 비용 상한으로 읽지 않게 못 박는다. 대상 자체는 상한이 정한다."""
    ids = sorted({_cluster(conn, score=float(9 - i)) for i in range(5)}, reverse=True)

    assert _select(conn, top=0, limit=2) == ids[:2]
