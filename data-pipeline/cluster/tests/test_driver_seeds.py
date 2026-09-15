"""spike → 씨드 어댑터·런타임 (WP-99). DB 없이 가짜 커넥션으로 계약만 고정한다.

`test_driver.py` 는 Clickstream 이웃 변환(-81)을 본다. 여기는 씨드 경로다.
실 PostgreSQL 왕복(적재·멱등)은 `test_driver_pg.py` 가 본다 — 나눈 이유는
`test_writer.py` 와 같다. 한 파일에 두면 DB 없는 환경에서 계약 검사까지 함께
skip 되어 깨져도 아무도 모른다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from cluster.driver import (
    SELECT_SNAPSHOT_TIMES_SQL,
    SPIKE_SOURCE,
    _completeness,
    build_snapshot_at,
    load_prior_first_detected,
    load_seeds_from_spike,
    load_snapshot_times,
    require_spike_source,
    run,
)
from cluster.score import size_score
from cluster.snapshot import DEFAULT_STATUS

UTC = timezone.utc
WINDOW_START = datetime(2024, 10, 6, 19, tzinfo=UTC)
DETECTED_AT = datetime(2024, 10, 6, 20, tzinfo=UTC)


class FakeCursor:
    """질의 문자열로 어떤 조회인지 가르고 미리 정한 행을 준다."""

    def __init__(self, conn):
        self._conn = conn
        self._rows: list[tuple] = []

    def execute(self, sql, params=None):
        self._conn.calls.append((sql, params))
        if "DISTINCT" in sql:
            self._rows = [(ts,) for ts in self._conn.snapshot_times]
        elif "FROM spike" in sql:
            self._rows = list(self._conn.spikes)
        elif "FROM issue_cluster" in sql:
            self._rows = list(self._conn.prior.items())
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, spikes=(), snapshot_times=(), prior=None):
        self.spikes = spikes
        self.snapshot_times = snapshot_times
        self.prior = prior or {}
        self.calls: list = []

    def cursor(self):
        return FakeCursor(self)


def spike_row(page_id=398, wiki="enwiki", title="Hurricane Milton",
              window_start=WINDOW_START, detected_at=DETECTED_AT,
              edit_count=10, view_ratio=None, spike_score=26.4575, row_id=1):
    """SELECT_SEEDS_SQL 의 컬럼 순서 그대로."""
    return (row_id, page_id, wiki, title, window_start, detected_at,
            edit_count, view_ratio, spike_score)


# ---------------------------------------------------------------- 씨드 매핑

def test_spike_행이_Seed로_매핑된다():
    seeds = load_seeds_from_spike(FakeConn(spikes=[spike_row()]), DETECTED_AT)
    assert len(seeds) == 1
    seed = seeds[0]
    assert (seed.page_id, seed.wiki, seed.title) == (398, "enwiki", "Hurricane Milton")
    assert seed.spike_score == pytest.approx(26.4575)
    assert seed.edit_count == 10
    assert seed.window_start == WINDOW_START
    assert seed.window_end == DETECTED_AT       # spike 에 window_end 컬럼이 없다


def test_event_date는_window_start의_UTC_날짜다():
    seeds = load_seeds_from_spike(
        FakeConn(spikes=[spike_row(window_start=datetime(2024, 10, 6, 23, tzinfo=UTC),
                                   detected_at=datetime(2024, 10, 7, 0, tzinfo=UTC))]),
        DETECTED_AT)
    assert seeds[0].event_date == date(2024, 10, 6)


def test_없는_값은_지어내지_않는다():
    """spike 는 조회수 원값·기준선을 저장하지 않는다 — None 이 맞다."""
    seed = load_seeds_from_spike(FakeConn(spikes=[spike_row()]), DETECTED_AT)[0]
    assert seed.views is None
    assert seed.edit_baseline is None
    assert seed.view_baseline is None


def test_조회수_미판정은_pending_판정됐으면_complete():
    assert _completeness(None) == "pending"
    assert _completeness(3.2) == "complete"

    seed = load_seeds_from_spike(
        FakeConn(spikes=[spike_row(view_ratio=3.2)]), DETECTED_AT)[0]
    assert seed.completeness == "complete"


def test_빈_결과는_빈_리스트():
    assert load_seeds_from_spike(FakeConn(spikes=[]), DETECTED_AT) == []


def test_detected_at이_window_start보다_앞이면_막는다():
    """WP-94 는 detected_at=윈도우 끝이다. 처리 시각이 들어오면 구간이 뒤집힌다."""
    with pytest.raises(ValueError, match="detected_at"):
        load_seeds_from_spike(
            FakeConn(spikes=[spike_row(detected_at=WINDOW_START)]), DETECTED_AT)


def test_조회_함수는_source를_아예_받지_않는다():
    """spike 에 출처 컬럼이 없다 — 인자로 두면 '이 source 로 거른다'로 오해된다."""
    import inspect

    assert "source" not in inspect.signature(load_seeds_from_spike).parameters

    conn = FakeConn(spikes=[spike_row()])
    load_seeds_from_spike(conn, DETECTED_AT)
    sql, params = conn.calls[0]
    assert params == (DETECTED_AT,)
    assert "source" not in sql


# ------------------------------------------- source provenance 가드 (WP-99)

def test_replay는_통과한다():
    assert require_spike_source(SPIKE_SOURCE) == "replay"


@pytest.mark.parametrize("bad", ["live", "LIVE", "", "Replay"])
def test_replay가_아니면_거부한다(bad):
    """spike 에 provenance 컬럼이 없어 리플레이 행을 live 로 저장할 수 있었다."""
    with pytest.raises(ValueError, match="provenance|replay"):
        require_spike_source(bad)


def test_build_snapshot_at은_live를_거부한다():
    with pytest.raises(ValueError, match="provenance|replay"):
        build_snapshot_at(FakeConn(spikes=[spike_row()]), DETECTED_AT, "live")


def test_run은_시점을_돌기_전에_live를_거부한다():
    """시점이 0개여도 막는다 — 늦게 막으면 빈 목록일 때만 통과해 나중에 갑자기 깨진다."""
    with pytest.raises(ValueError, match="provenance|replay"):
        run(FakeConn(spikes=[spike_row()]), "live", snapshot_times=[])


def test_replay_spike는_live_라벨로_생산되지_않는다():
    """거짓 라벨링 차단 — 같은 입력이 replay 로만 나온다."""
    conn = FakeConn(spikes=[spike_row()])
    assert build_snapshot_at(conn, DETECTED_AT, "replay").source == "replay"
    with pytest.raises(ValueError):
        build_snapshot_at(conn, DETECTED_AT, "live")


def test_CLI는_live를_받지_않는다():
    """argparse choices 가 먼저 거절한다."""
    from cluster.driver import build_arg_parser

    parser = build_arg_parser()
    assert parser.parse_args(["--dsn", "x"]).source == SPIKE_SOURCE
    with pytest.raises(SystemExit):
        parser.parse_args(["--dsn", "x", "--source", "live"])


# ---------------------------------------------------------------- 시점·이전 감지

def test_시점_조회는_오름차순이다():
    """first_detected_at 멱등성이 이 순서에 달렸다 — SQL 정렬을 고정한다."""
    assert "ORDER BY s.detected_at" in SELECT_SNAPSHOT_TIMES_SQL
    times = [datetime(2024, 10, 6, h, tzinfo=UTC) for h in (20, 21, 22)]
    assert load_snapshot_times(FakeConn(snapshot_times=times)) == times


def test_이전_최초감지를_issue_key별로_읽는다():
    prior = {"replay:enwiki:Hurricane Milton": datetime(2024, 10, 6, 20, tzinfo=UTC)}
    assert load_prior_first_detected(FakeConn(prior=prior), "replay") == prior


# ---------------------------------------------------------------- 씨드 단독 스냅샷

def test_씨드_단독_스냅샷이_생산된다():
    """이웃이 없어도 멤버 1개·간선 0개로 정상 생산된다(-75 계약)."""
    snapshot = build_snapshot_at(FakeConn(spikes=[spike_row()]), DETECTED_AT, "replay")

    assert snapshot.snapshot_ts == DETECTED_AT
    assert snapshot.source == "replay"
    assert snapshot.cluster_count == 1

    cluster = snapshot.clusters[0]
    assert cluster.issue_key == "replay:enwiki:Hurricane Milton"
    assert cluster.status == DEFAULT_STATUS
    assert cluster.pulse_score == pytest.approx(26.458, abs=1e-3)
    assert len(cluster.edges) == 0                      # 간선 없음이 정상
    assert [m.is_seed for m in cluster.members] == [True]

    member = cluster.members[0]
    assert member.page_id == 398
    assert member.size_score == size_score(26.4575)     # 점수는 -75 score.py 가 정한다
    assert member.window_start == WINDOW_START
    assert member.window_end == DETECTED_AT


def test_비씨드_생성일_어댑터는_호출되지_않는다():
    """씨드 단독 경로는 생성일(이웃 게이트 입력)을 안 쓴다 — 골격인 채로 둬도 된다."""
    import cluster.driver as driver

    called: list = []
    original = driver.load_creation_dates
    driver.load_creation_dates = lambda *a, **k: called.append(a) or {}
    try:
        build_snapshot_at(FakeConn(spikes=[spike_row()]), DETECTED_AT, "replay")
    finally:
        driver.load_creation_dates = original
    assert called == []


def test_이전_최초감지가_있으면_그_시각을_쓴다():
    """같은 issue_key 가 여러 시점에 걸쳐도 first_detected_at 은 가장 이른 시각."""
    first = datetime(2024, 10, 6, 20, tzinfo=UTC)
    later = datetime(2024, 10, 7, 14, tzinfo=UTC)
    conn = FakeConn(spikes=[spike_row(window_start=datetime(2024, 10, 7, 13, tzinfo=UTC),
                                      detected_at=later)],
                    prior={"replay:enwiki:Hurricane Milton": first})
    assert build_snapshot_at(conn, later, "replay").clusters[0].first_detected_at == first


def test_씨드가_없으면_빈_스냅샷():
    """클러스터 0개 스냅샷도 유효하다 — 미저장 시점과 구분된다(cluster_snapshot)."""
    snapshot = build_snapshot_at(FakeConn(spikes=[]), DETECTED_AT, "replay")
    assert snapshot.cluster_count == 0
    assert snapshot.clusters == ()
