"""후보 생성 대상 선택 SQL 을 진짜 PostgreSQL 로 검증한다 (WP-176).

`CandidateRepository.pendingClusterIds` 는 window function 을 쓰는 raw JDBC 라
`ddl-auto=validate` 로도 백엔드 단위 테스트로도 안 잡힌다 — 실 DB 검증이 여기 몫이다
(`test_summary_scope_sql.py` 와 같은 관습). 아래 SQL 은 그 문장을 그대로 옮겼다.

🔴 **이게 비용 상한이다.** 옛 조건은 `NOT EXISTS cluster_stock` 뿐이라 상한이 batchSize
하나였는데, 폴마다 대상을 새로 고르므로 반복하면 운영 4,474개를 전부 훑는다. 후보마다
LLM 검증이 따라붙어 310k~620k 크레딧이다.

⚠️ 후보 생성 자체는 임베딩이라 싸다(0.04/건). 이 상한이 묶는 것은 **그 뒤의 검증**이다.

못 박는 것:
    - 스냅샷별 `pulse_score` 상위 N 만 고른다 (요약과 같은 축)
    - 순위는 **그 스냅샷의 전체 클러스터** 위에서 매긴다 — 처리된 것을 뺀 나머지로 매기면
      처리할수록 하위가 올라와 상한이 조용히 번진다
    - 이미 후보가 있는 클러스터는 제외한다 (폴러는 신규만 집는다)
    - 같은 issue_key 에 DONE 판정이 있으면 상한과 무관하게 고른다 (검증 재사용 → LLM 0)
    - PENDING·FAILED 만 있으면 면제되지 않는다 (재사용할 판정이 아직 없다)
    - 0 이면 무제한 (옛 동작)
    - source 로 대상을 한 출처로 좁힌다 (WP-168). NULL 이면 전체
    - 순위는 좁힌 출처 **안에서** 매긴다 — 화면도 source 로 거르므로 축을 맞춰야 한다
"""

from __future__ import annotations

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

# CandidateRepository.pendingClusterIds 의 SQL. 이름 파라미터만 %(...)s 로 바꿨다.
_SELECT = """
WITH ranked AS (
    SELECT id, status, issue_key, snapshot_ts,
           row_number() OVER (PARTITION BY snapshot_ts
                              ORDER BY pulse_score DESC, id ASC) AS rnk
      FROM issue_cluster
     WHERE (%(source)s::text IS NULL
            OR source = %(source)s::text)
       AND (%(days)s::date[] IS NULL
            OR (snapshot_ts AT TIME ZONE 'UTC')::date = ANY (%(days)s::date[]))
)
SELECT r.id
  FROM ranked r
 WHERE r.status <> 'DISCARDED'
   AND NOT EXISTS (SELECT 1 FROM cluster_stock cs WHERE cs.cluster_id = r.id)
   AND (%(top)s <= 0
        OR r.rnk <= %(top)s
        OR EXISTS (SELECT 1
                     FROM cluster_stock cs2
                     JOIN issue_cluster c2 ON c2.id = cs2.cluster_id
                    WHERE cs2.issue_key IS NOT NULL
                      AND cs2.issue_key = r.issue_key
                      AND cs2.check_state = 'DONE'
                      AND c2.snapshot_ts <= r.snapshot_ts))
 ORDER BY r.snapshot_ts DESC
 LIMIT %(limit)s
"""


def _select(conn, top: int, limit: int = 100, source=None, days=None) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(_SELECT, {"top": top, "limit": limit, "source": source, "days": days})
        return [row[0] for row in cur.fetchall()]


def _cluster(conn, *, score: float, status: str = "DETECTED",
             snapshot: str = "2026-09-01T00:00:00+00:00", issue_key=None,
             source: str = "live") -> int:
    rows = q(
        conn,
        "INSERT INTO issue_cluster (snapshot_ts, pulse_score, status, issue_key, source) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        snapshot, score, status, issue_key, source,
    )
    return rows[0][0]


def _stock(conn, ticker: str) -> None:
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES (%s, %s, 'NASDAQ') "
            "ON CONFLICT (ticker) DO NOTHING", ticker, ticker + " Inc")


def _candidate(conn, cluster_id: int, ticker: str, *, state: str = "DONE",
               issue_key=None) -> None:
    _stock(conn, ticker)
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, verified, check_state, issue_key) "
        "VALUES (%s, %s, 'BOTH', false, %s, %s)",
        cluster_id, ticker, state, issue_key,
    )


def test_스냅샷별_상위_N_만_고른다(conn):
    high = _cluster(conn, score=9.0)
    mid = _cluster(conn, score=5.0)
    low = _cluster(conn, score=1.0)

    picked = set(_select(conn, top=2))

    assert picked == {high, mid}
    assert low not in picked


def test_상한_0_은_무제한이다(conn):
    ids = {_cluster(conn, score=s) for s in (9.0, 5.0, 1.0)}

    assert set(_select(conn, top=0)) == ids


def test_이미_후보가_있으면_제외한다(conn):
    done = _cluster(conn, score=9.0)
    fresh = _cluster(conn, score=8.0)
    _candidate(conn, done, "AAA")

    assert _select(conn, top=0) == [fresh]


def test_순위는_스냅샷_전체로_매긴다(conn):
    """🔴 처리된 것을 빼고 매기면 처리할수록 하위가 올라와 상한이 번진다.

    1위에 이미 후보가 있어도 3위가 승격되면 안 된다. 폴을 반복할수록 대상이 아래로
    번지는 회귀를 이 테스트가 잡는다.
    """
    first = _cluster(conn, score=9.0)
    second = _cluster(conn, score=5.0)
    third = _cluster(conn, score=1.0)
    _candidate(conn, first, "AAA")   # 1위는 이미 처리됨

    picked = _select(conn, top=2)

    assert picked == [second]
    assert third not in picked


def test_DISCARDED_는_대상이_아니다(conn):
    live = _cluster(conn, score=9.0)
    _cluster(conn, score=8.0, status="DISCARDED")

    assert _select(conn, top=0) == [live]


def test_같은_issue_key_에_DONE_판정이_있으면_상한_밖이어도_고른다(conn):
    """검증이 (issue_key, ticker, prompt_version) 으로 재사용하므로 LLM 0 이다."""
    top_one = _cluster(conn, score=9.0, issue_key="k-1")
    _candidate(conn, top_one, "AAA", state="DONE", issue_key="k-1")

    # 다른 스냅샷의 하위 클러스터 — 같은 issue_key
    low = _cluster(conn, score=0.1, issue_key="k-1",
                   snapshot="2026-09-02T00:00:00+00:00")
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")  # 상한을 채운다

    assert low in _select(conn, top=1)


def test_PENDING_만_있으면_면제되지_않는다(conn):
    """⚠️ 아직 판정이 없다 — 재사용할 게 없으므로 LLM 이 실제로 돈다."""
    other = _cluster(conn, score=9.0, issue_key="k-2")
    _candidate(conn, other, "AAA", state="PENDING", issue_key="k-2")

    low = _cluster(conn, score=0.1, issue_key="k-2",
                   snapshot="2026-09-02T00:00:00+00:00")
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")

    assert low not in _select(conn, top=1)


def test_미래_DONE_판정은_과거_클러스터를_상한에서_면제하지_않는다(conn):
    """재사용 불가능한 미래 판정을 공짜 캐시로 세면 실제 LLM 비용이 상한 밖으로 샌다."""
    snap = "2026-09-01T00:00:00+00:00"
    _cluster(conn, score=9.0, snapshot=snap)  # 과거 스냅샷 상한 1을 채운다.
    low = _cluster(conn, score=0.1, issue_key="future-only", snapshot=snap)
    future = _cluster(conn, score=9.0, issue_key="future-only",
                      snapshot="2026-09-02T00:00:00+00:00")
    _candidate(conn, future, "FUT", state="DONE", issue_key="future-only")

    assert low not in _select(conn, top=1)


def test_issue_key_가_없으면_면제되지_않는다(conn):
    """⚠️ V1 옛 클러스터는 issue_key 가 NULL 이다. NULL 끼리 묶이면 안 된다."""
    other = _cluster(conn, score=9.0, issue_key=None)
    _candidate(conn, other, "AAA", state="DONE", issue_key=None)

    low = _cluster(conn, score=0.1, issue_key=None,
                   snapshot="2026-09-02T00:00:00+00:00")
    _cluster(conn, score=9.0, snapshot="2026-09-02T00:00:00+00:00")

    assert low not in _select(conn, top=1)


def test_limit_은_한_폴의_크기일_뿐이다(conn):
    """batchSize 를 비용 상한으로 읽지 않게 못 박는다."""
    ids = sorted({_cluster(conn, score=float(9 - i)) for i in range(5)})

    picked = _select(conn, top=0, limit=2)

    assert len(picked) == 2
    assert set(picked) <= set(ids)


def test_source_로_대상을_좁힌다(conn):
    """🔴 정렬이 snapshot_ts DESC 라 LIVE 가 쌓이면 과거 replay 에 영원히 못 닿는다."""
    live = _cluster(conn, score=9.0, source="live",
                    snapshot="2026-09-21T00:00:00+00:00")
    replay = _cluster(conn, score=9.0, source="replay",
                      snapshot="2025-06-12T00:00:00+00:00")

    assert _select(conn, top=0, source="replay") == [replay]
    assert _select(conn, top=0, source="live") == [live]
    assert set(_select(conn, top=0)) == {live, replay}


def test_순위는_좁힌_출처_안에서_매긴다(conn):
    """밖에서 매기면 다른 출처가 순위 자리를 먹어 상한보다 적게 뽑힌다.

    같은 snapshot_ts 에 두 출처가 섞인 경우다. 화면도 source 로 거르므로
    "보여주는 상위 N" 과 대상이 어긋나면 안 된다.
    """
    snap = "2026-09-21T00:00:00+00:00"
    _cluster(conn, score=9.0, source="live", snapshot=snap)
    _cluster(conn, score=8.0, source="live", snapshot=snap)
    first = _cluster(conn, score=5.0, source="replay", snapshot=snap)
    second = _cluster(conn, score=1.0, source="replay", snapshot=snap)

    assert set(_select(conn, top=2, source="replay")) == {first, second}


# ------------------------------------------------ 스냅샷 날짜 한정 (WP-215)

def test_날짜를_주면_그_UTC_날짜_스냅샷만_고른다(conn):
    demo = _cluster(conn, score=1.0, snapshot="2026-07-25T04:00:00+00:00")
    kst_only = _cluster(conn, score=9.0, snapshot="2026-07-24T20:00:00+00:00")  # KST 07-25
    other = _cluster(conn, score=9.0, snapshot="2026-09-01T00:00:00+00:00")

    picked = _select(conn, top=0, days="{2026-07-17,2026-07-25}")

    assert picked == [demo]
    assert kst_only not in picked and other not in picked


def test_날짜는_스냅샷을_통째로_골라_순위를_안_바꾼다(conn):
    """상위 N 은 그 스냅샷 안에서 매긴다 — 날짜 한정이 순위 축을 흔들면 안 된다."""
    snap = "2026-07-17T01:00:00+00:00"
    high = _cluster(conn, score=9.0, snapshot=snap)
    _cluster(conn, score=1.0, snapshot=snap)

    assert _select(conn, top=1, days="{2026-07-17}") == [high]


def test_날짜가_없으면_전체다(conn):
    a = _cluster(conn, score=1.0, snapshot="2026-07-17T01:00:00+00:00")
    b = _cluster(conn, score=1.0, snapshot="2026-09-01T00:00:00+00:00")

    assert set(_select(conn, top=0, days=None)) == {a, b}
