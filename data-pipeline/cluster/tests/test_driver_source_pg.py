"""LIVE spike → LIVE 클러스터, 그리고 replay/live 격리 (WP-102). 실 PostgreSQL.

`test_driver_pg.py` 는 리플레이 경로의 관통·멱등을 본다. 여기는 **두 출처가 한 DB 에
섞여 있을 때** 각 실행이 자기 출처만 읽는지를 본다 — -102 가 만든 계약이다.

🔴 **spike 를 직접 INSERT 하지 않는다.**
    `SpikeRuntime` + `SpikeSink` (WP-94 · -100 공식 적재 경로)로 만든다.
    손으로 INSERT 하면 "이 컬럼에 이 값이 들어가면" 만 검사하게 되고, 런타임이
    실제로 그 값을 쓰는지는 안 본다 — 라벨이 어긋나도 테스트는 통과한다.
    LIVE 쪽 Spark 어댑터(`streaming.live_spike.process_batch`)는 이 런타임을 감싸기만
    하고 pyspark 를 요구하므로, 여기서는 그 아래층인 런타임을 직접 부른다.
    Spark DataFrame → 런타임 입력 변환은 `spike/tests/test_live_spike_pg.py` 가 본다.

⚠️ **두 출처의 spike 는 `detected_at` 까지 같게 만든다.** 그게 이 파일의 요점이다 —
    시각만으로 고르면 한 스냅샷에 섞이고, 섞여도 에러가 안 난다. V5 가 UNIQUE 키에
    source 를 넣어서 두 행이 공존할 수 있다.

기준선은 일부러 안 넣는다
    `page_baseline` 이 비어 있으면 `detect()` 가 신규 문서 경로로 간다 — 편집 절대량
    (`MIN_ABSOLUTE_EDITS`)·편집자 수(`MIN_DISTINCT_EDITORS`)만 보는 경로다. 판정 규칙을
    검사하는 파일이 아니라(그건 `spike/tests/`), 통제된 급증이 필요할 뿐이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("psycopg")

from cluster.driver import load_snapshot_times, run                 # noqa: E402
from spike.baseline_repository import BaselineRepository            # noqa: E402
from spike.detector import MIN_ABSOLUTE_EDITS, MIN_DISTINCT_EDITORS  # noqa: E402
from spike.runtime import PageWindow, SpikeRuntime                  # noqa: E402
from spike.spike_sink import SpikeSink                              # noqa: E402

UTC = timezone.utc

#: 리플레이가 실제로 다루는 구간(2024년 Milton)과 LIVE 가 다루는 구간(지금)을 갈라 둔다.
REPLAY_WINDOW = datetime(2024, 10, 6, 19, tzinfo=UTC)
LIVE_WINDOW = datetime(2026, 9, 16, 4, tzinfo=UTC)

#: 같은 문서·같은 윈도우를 두 출처가 각각 갖는 경우 — 섞임 검사의 핵심 입력.
SHARED_WINDOW = datetime(2026, 9, 16, 6, tzinfo=UTC)


def save_spike(conn, *, source, title, window_start, edit_count, editor_count=4):
    """공식 런타임으로 spike 한 건. 판정을 통과하지 못하면 그 자리에서 실패시킨다.

    조용히 0건이 저장되면 뒤 단언이 "격리가 잘 됐다" 로 잘못 통과한다 — 입력이
    없어서 안 섞인 것과, 걸러서 안 섞인 것은 다른 사실이다.
    """
    runtime = SpikeRuntime(BaselineRepository(conn), SpikeSink(conn, source=source))
    outcome = runtime.process(PageWindow(
        wiki="enwiki", title=title, window_start=window_start,
        edit_count=edit_count, editor_count=editor_count, views=None,
    ))
    assert outcome.persisted, (
        f"{source} spike 가 저장되지 않았다 — 판정: {outcome.decision.reason}")
    #: detected_at = 윈도우 끝 (spike_sink 계약). 스냅샷 시점이 이 값이다.
    return window_start + timedelta(hours=1)


def _all(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall()


def _one(conn, sql, *args):
    rows = _all(conn, sql, *args)
    return rows[0] if rows else None


def clusters(conn, source=None):
    sql = ("SELECT source, issue_key, snapshot_ts, "
           "(SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id) "
           "FROM issue_cluster c")
    params = ()
    if source is not None:
        sql += " WHERE c.source = %s"
        params = (source,)
    return _all(conn, sql + " ORDER BY c.source, c.snapshot_ts", *params)


@pytest.fixture
def mixed(conn):
    """같은 문서·같은 윈도우·같은 detected_at 을 replay 와 live 가 각각 하나씩.

    편집수를 다르게 줘서 어느 행이 씨드가 됐는지 값으로 구분된다.
    """
    replay_ts = save_spike(conn, source="replay", title="Mixed Page",
                           window_start=SHARED_WINDOW,
                           edit_count=MIN_ABSOLUTE_EDITS + 5)
    live_ts = save_spike(conn, source="live", title="Mixed Page",
                         window_start=SHARED_WINDOW,
                         edit_count=MIN_ABSOLUTE_EDITS + 40)
    assert replay_ts == live_ts, "같은 시점이어야 이 파일이 보려는 함정이 생긴다"

    rows = _all(conn, "SELECT source, edit_count FROM spike s "
                      "JOIN wiki_page p ON p.id = s.page_id WHERE p.title = %s "
                      "ORDER BY s.source", "Mixed Page")
    assert [r[0] for r in rows] == ["live", "replay"], "두 행이 공존해야 한다(V5 UNIQUE 키)"
    return replay_ts


# ------------------------------------------------- 같은 page/window 의 replay/live 분리

def test_replay_실행은_replay_씨드만_읽는다(conn, mixed):
    run(conn, "replay", snapshot_times=[mixed])

    rows = clusters(conn)
    assert len(rows) == 1
    source, issue_key, _, member_count = rows[0]
    assert source == "replay"
    assert issue_key == "replay:enwiki:Mixed Page"
    assert member_count == 1        # live 행이 멤버로 섞이지 않았다

    # 씨드가 리플레이 행이었는지 값으로 확인한다 — 편집수를 다르게 줬다.
    assert _one(conn, "SELECT cm.edit_count FROM cluster_member cm")[0] == \
        MIN_ABSOLUTE_EDITS + 5


def test_live_실행은_live_씨드만_읽는다(conn, mixed):
    run(conn, "live", snapshot_times=[mixed])

    rows = clusters(conn)
    assert len(rows) == 1
    source, issue_key, _, member_count = rows[0]
    assert source == "live"
    assert issue_key == "live:enwiki:Mixed Page"
    assert member_count == 1

    assert _one(conn, "SELECT cm.edit_count FROM cluster_member cm")[0] == \
        MIN_ABSOLUTE_EDITS + 40


def test_둘_다_돌려도_서로_안_섞인다(conn, mixed):
    """같은 시점에 두 출처의 클러스터가 공존한다 — 각자 자기 씨드 하나씩."""
    run(conn, "replay", snapshot_times=[mixed])
    run(conn, "live", snapshot_times=[mixed])

    rows = clusters(conn)
    assert [(r[0], r[1], r[3]) for r in rows] == [
        ("live", "live:enwiki:Mixed Page", 1),
        ("replay", "replay:enwiki:Mixed Page", 1),
    ]
    # 멤버는 출처당 하나. 합쳐서 둘 — 한쪽이 상대 씨드를 끌어왔다면 3~4가 된다.
    assert _one(conn, "SELECT count(*) FROM cluster_member")[0] == 2

    # 🔴 issue_key 가 겹치지 않아 first_detected_at 이 출처 간에 오염되지 않는다.
    keys = {r[1] for r in rows}
    assert len(keys) == 2


def test_한쪽을_다시_돌려도_다른_쪽이_안_지워진다(conn, mixed):
    """writer 의 삭제 단위가 (source, snapshot_ts) 다 — 같은 시각이어도 분리된다."""
    run(conn, "replay", snapshot_times=[mixed])
    run(conn, "live", snapshot_times=[mixed])
    run(conn, "replay", snapshot_times=[mixed])         # replay 만 재실행

    assert len(clusters(conn, "live")) == 1
    assert len(clusters(conn, "replay")) == 1
    assert _one(conn, "SELECT count(*) FROM cluster_snapshot")[0] == 2


# ------------------------------------------------------------- LIVE 클러스터 생산

@pytest.fixture
def live_only(conn):
    """LIVE spike 두 건(다른 문서). 리플레이 행은 다른 구간에 하나 둔다."""
    save_spike(conn, source="replay", title="Hurricane Milton",
               window_start=REPLAY_WINDOW, edit_count=MIN_ABSOLUTE_EDITS + 5)
    ts = save_spike(conn, source="live", title="Live Page A",
                    window_start=LIVE_WINDOW, edit_count=MIN_ABSOLUTE_EDITS + 12)
    save_spike(conn, source="live", title="Live Page B",
               window_start=LIVE_WINDOW, edit_count=MIN_ABSOLUTE_EDITS + 3,
               editor_count=MIN_DISTINCT_EDITORS)
    return ts


def test_live_시점만_골라_LIVE_클러스터를_만든다(conn, live_only):
    times = load_snapshot_times(conn, "live")
    assert times == [live_only], "리플레이 시점(2024)이 섞이면 안 된다"

    run(conn, "live", snapshot_times=times)

    rows = clusters(conn, "live")
    assert {r[1] for r in rows} == {"live:enwiki:Live Page A", "live:enwiki:Live Page B"}
    assert all(r[2] == live_only for r in rows)
    assert all(r[3] == 1 for r in rows)             # 씨드 단독 — 이웃 적재본이 없다

    # 간선 0개는 씨드 단독 계약상 정상이다(-75). 억지로 만들지 않는다.
    assert _one(conn, "SELECT count(*) FROM cluster_edge")[0] == 0

    snapshot = _one(conn, "SELECT cluster_count FROM cluster_snapshot "
                          "WHERE source = 'live' AND snapshot_ts = %s", live_only)
    assert snapshot[0] == 2

    # 리플레이 구간은 건드리지 않았다.
    assert _one(conn, "SELECT count(*) FROM issue_cluster WHERE source='replay'")[0] == 0


def test_live_클러스터_멤버는_씨드다(conn, live_only):
    run(conn, "live", snapshot_times=load_snapshot_times(conn, "live"))

    members = _all(conn, "SELECT cm.is_seed, cm.weight, cm.window_start, cm.window_end "
                         "FROM cluster_member cm")
    assert len(members) == 2
    assert all(m[0] is True and m[1] == 1.0 for m in members)
    assert all(m[2] == LIVE_WINDOW and m[3] == live_only for m in members)


def test_live를_두_번_돌려도_안_늘어난다(conn, live_only):
    times = load_snapshot_times(conn, "live")
    run(conn, "live", snapshot_times=times)
    before = (_one(conn, "SELECT count(*) FROM issue_cluster")[0],
              _one(conn, "SELECT count(*) FROM cluster_member")[0],
              _one(conn, "SELECT count(*) FROM cluster_snapshot")[0])
    keys = _all(conn, "SELECT issue_key, first_detected_at FROM issue_cluster "
                      "ORDER BY issue_key")

    run(conn, "live", snapshot_times=times)

    assert (_one(conn, "SELECT count(*) FROM issue_cluster")[0],
            _one(conn, "SELECT count(*) FROM cluster_member")[0],
            _one(conn, "SELECT count(*) FROM cluster_snapshot")[0]) == before
    assert _all(conn, "SELECT issue_key, first_detected_at FROM issue_cluster "
                      "ORDER BY issue_key") == keys


# ------------------------------------------------------- 리플레이 회귀 (Milton)

def test_Milton_리플레이가_그대로_돈다(conn, live_only):
    """LIVE 행이 같은 DB 에 있어도 리플레이 산출물이 달라지지 않는다."""
    times = load_snapshot_times(conn, "replay")
    assert times == [REPLAY_WINDOW + timedelta(hours=1)]     # LIVE 시점이 안 섞인다

    run(conn, "replay", snapshot_times=times)

    rows = clusters(conn, "replay")
    assert len(rows) == 1
    assert rows[0][1] == "replay:enwiki:Hurricane Milton"
    assert rows[0][3] == 1
    # LIVE 문서가 리플레이 클러스터의 멤버로 들어오지 않았다.
    titles = _all(conn, "SELECT p.title FROM cluster_member cm "
                        "JOIN wiki_page p ON p.id = cm.page_id")
    assert [t[0] for t in titles] == ["Hurricane Milton"]


# --------------------------------------------------- 백엔드가 읽는 형태 (무수정 확인)

def test_백엔드_최신_LIVE_스냅샷_질의가_이_행을_읽는다(conn, live_only):
    """IssueClusterRepository.findLatestLiveSnapshot 과 같은 조건."""
    run(conn, "replay", snapshot_times=load_snapshot_times(conn, "replay"))
    run(conn, "live", snapshot_times=load_snapshot_times(conn, "live"))

    latest = _one(conn, "SELECT max(c.snapshot_ts) FROM issue_cluster c "
                        "WHERE c.source = 'live'")[0]
    assert latest == live_only

    # findCards 무인자(source=NULL) 경로 — 그 시점의 카드가 나온다.
    cards = _all(conn, """
        SELECT c.id, c.source, c.issue_key, c.pulse_score, c.status,
               (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id),
               (SELECT count(*) FROM cluster_stock cs
                 WHERE cs.cluster_id = c.id AND cs.verified)
          FROM issue_cluster c
         WHERE c.snapshot_ts = %s
           AND c.status IN ('DETECTED','VERIFYING','CONFIRMED')
           AND (%s::text IS NULL OR c.source = %s)
         ORDER BY c.pulse_score DESC, c.id ASC
        """, latest, None, None)
    assert len(cards) == 2
    assert {c[1] for c in cards} == {"live"}
    assert all(c[5] == 1 for c in cards)
    assert all(c[6] == 0 for c in cards)    # LLM 검증(-68) 전이라 0이 정상
