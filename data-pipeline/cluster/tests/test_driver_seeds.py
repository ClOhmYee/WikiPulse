"""spike → 씨드 어댑터·런타임 (WP-99 · -102). DB 없이 가짜 커넥션으로 계약만 고정한다.

`test_driver.py` 는 Clickstream 이웃 변환(-81)을 본다. 여기는 씨드 경로다.
실 PostgreSQL 왕복(적재·멱등·출처 격리)은 `test_driver_pg.py`·
`test_driver_source_pg.py` 가 본다 — 나눈 이유는 `test_writer.py` 와 같다. 한 파일에
두면 DB 없는 환경에서 계약 검사까지 함께 skip 되어 깨져도 아무도 모른다.

가짜 커넥션이 `source` 를 **실제로 건다**
    -102 의 계약이 "조회에 source 를 건다" 라, 대역이 그 파라미터를 무시하면 이 파일은
    필터가 빠진 것을 못 잡는다. `FakeCursor` 가 파라미터의 source 로 행을 거른다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from cluster.driver import (
    SELECT_SEEDS_SQL,
    SELECT_SNAPSHOT_TIMES_SQL,
    SPIKE_SOURCES,
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
    """질의 문자열로 어떤 조회인지 가르고, `source` 파라미터로 행을 거른다."""

    def __init__(self, conn):
        self._conn = conn
        self._rows: list[tuple] = []

    def execute(self, sql, params=None):
        self._conn.calls.append((sql, params))
        if "DISTINCT" in sql:
            # SELECT_SNAPSHOT_TIMES_SQL 파라미터: (source, since, since, until, until)
            self._rows = [(ts,) for ts in self._conn.times_for(params[0])]
        elif "FROM spike" in sql:
            # SELECT_SEEDS_SQL 파라미터: (source, detected_at).
            # 시각은 거르지 않는다 — 대역의 `spikes` 가 곧 "이 질의가 낼 행" 이다.
            source = params[0]
            self._rows = [row[:12] for row in self._conn.spikes if row[12] == source]
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
    """`snapshot_times` 는 시퀀스(모든 출처 공통) 또는 {source: [ts,...]} 매핑."""

    def __init__(self, spikes=(), snapshot_times=(), prior=None):
        self.spikes = spikes
        self.snapshot_times = snapshot_times
        self.prior = prior or {}
        self.calls: list = []

    def times_for(self, source):
        if isinstance(self.snapshot_times, dict):
            return self.snapshot_times.get(source, ())
        return self.snapshot_times

    def cursor(self):
        return FakeCursor(self)


def spike_row(page_id=398, wiki="enwiki", title="Hurricane Milton",
              window_start=WINDOW_START, detected_at=DETECTED_AT,
              edit_count=10, views=24_669, view_baseline=None, view_ratio=None,
              spike_score=26.4575, row_id=1, max_rev_id=1_250_000_001,
              source="replay"):
    """SELECT_SEEDS_SQL 의 컬럼 순서 그대로 + 맨 뒤에 출처 태그.

    `source` 는 조회 컬럼이 아니라 대역 테이블의 태그다 — `FakeCursor` 가 그걸로 거르고
    드라이버에는 앞 12개만 넘긴다(실 질의가 내는 컬럼 수와 같다).

    `max_rev_id` 는 V9 증거 컬럼이자 CORE 의 as-of 링크 앵커다 (WP-186).

    기본값은 canary 실측(2025-06-12 `Air India Flight 171`)을 따랐다 — 신규 문서라
    기준선 표본이 없어 `view_baseline`·`view_ratio` 가 NULL 이고 조회수 원값만 있다.
    **그 조합이 바로 이번 결함이 났던 자리다** (WP-129).
    """
    return (row_id, page_id, wiki, title, window_start, detected_at,
            edit_count, views, view_baseline, view_ratio, spike_score,
            max_rev_id, source)


# ---------------------------------------------------------------- 씨드 매핑

def test_spike_행이_Seed로_매핑된다():
    seeds = load_seeds_from_spike(FakeConn(spikes=[spike_row()]), DETECTED_AT, "replay")
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
        DETECTED_AT, "replay")
    assert seeds[0].event_date == date(2024, 10, 6)


def test_조회수_원값과_기준선은_spike_에서_그대로_온다():
    """~~spike 는 조회수 원값·기준선을 저장하지 않는다~~ → V7 부터 저장한다
    (2026-09-18, WP-129).

    canary 에서 실제 판정 조회수 25,426 이 있는데도 `cluster_member.views` 가 null 로
    나갔다. driver 가 `views=None` 을 하드코딩했기 때문인데, 읽을 컬럼이 없어서였다.
    """
    seed = load_seeds_from_spike(FakeConn(spikes=[spike_row()]), DETECTED_AT, "replay")[0]
    assert seed.views == 24_669
    assert seed.view_baseline is None      # 신규 문서 — 기준선 표본이 없다
    assert seed.edit_baseline is None      # 편집 기준선은 아직 spike 에 없다(지어내지 않는다)


def test_표본_없는_신규문서가_complete_로_나온다():
    """🔴 이 이슈의 발단 (canary §5, WP-129).

    신규 문서는 기준선 표본이 없어 절대 하한(>=100)으로 확정된다 — 명세 §3.2 3번
    "0 에서의 급등". 그 경로는 배수를 낼 분모가 없어 `view_ratio` 가 NULL 인데,
    ~~그걸 판정 미완료로 읽어 pending 으로 저장했다~~. 판정은 끝났으니 complete 다.
    """
    seed = load_seeds_from_spike(
        FakeConn(spikes=[spike_row(views=25_426, view_baseline=None, view_ratio=None)]),
        DETECTED_AT, "replay")[0]
    assert seed.completeness == "complete"
    assert seed.views == 25_426


def test_조회수가_없는_옛_행은_여전히_None_이다():
    """V7 이전에 저장된 행. 지어내지 않고 그대로 통과시킨다."""
    seed = load_seeds_from_spike(
        FakeConn(spikes=[spike_row(views=None)]), DETECTED_AT, "replay")[0]
    assert seed.views is None
    assert seed.completeness == "pending"


def test_조회수_미판정은_pending_판정됐으면_complete():
    """🔴 판단 근거가 `view_ratio` -> `views` 로 바뀌었다 (WP-129).

    표본 없는 문서는 배수가 정당하게 NULL 이다(분모가 없다). 그걸 "판정 미완료" 로
    읽어서 확정 건이 전부 pending 으로 저장됐다 — canary §5.
    """
    assert _completeness(None) == "pending"
    assert _completeness(24_669) == "complete"

    seed = load_seeds_from_spike(
        FakeConn(spikes=[spike_row(view_ratio=3.2)]), DETECTED_AT, "replay")[0]
    assert seed.completeness == "complete"


def test_빈_결과는_빈_리스트():
    assert load_seeds_from_spike(FakeConn(spikes=[]), DETECTED_AT, "replay") == []


def test_detected_at이_window_start보다_앞이면_막는다():
    """WP-94 는 detected_at=윈도우 끝이다. 처리 시각이 들어오면 구간이 뒤집힌다."""
    with pytest.raises(ValueError, match="detected_at"):
        load_seeds_from_spike(
            FakeConn(spikes=[spike_row(detected_at=WINDOW_START)]), DETECTED_AT, "replay")


# ------------------------------- source 가 입력 필터다 (WP-102)

def test_조회_함수는_source를_필수로_받는다():
    """~~아예 받지 않는다(-99)~~ → 필수 (-102). V5 가 spike.source 를 만들었다.

    기본값이 없어야 한다 — 있으면 새 호출자가 빠뜨려도 통과하고, 그 순간 라벨과
    입력이 갈린다.
    """
    import inspect

    param = inspect.signature(load_seeds_from_spike).parameters.get("source")
    assert param is not None
    assert param.default is inspect.Parameter.empty, "기본값을 두지 않는다"


def test_씨드_질의에_source_조건이_걸린다():
    """🔴 이게 빠지면 LIVE 스냅샷에 리플레이 씨드가 섞이는데 에러가 안 난다."""
    assert "s.source = %s" in SELECT_SEEDS_SQL

    conn = FakeConn(spikes=[spike_row()])
    load_seeds_from_spike(conn, DETECTED_AT, "replay")
    _, params = conn.calls[0]
    assert params == ("replay", DETECTED_AT)


def test_같은_시점의_다른_출처_행은_안_섞인다():
    """같은 문서·윈도우를 두 출처가 각각 갖는다(V5 UNIQUE 키에 source).

    시각만으로 고르면 두 행이 한 스냅샷에 같이 들어간다.
    """
    both = [spike_row(row_id=1, source="replay", spike_score=26.4575),
            spike_row(row_id=2, source="live", spike_score=31.0)]

    replay = load_seeds_from_spike(FakeConn(spikes=both), DETECTED_AT, "replay")
    live = load_seeds_from_spike(FakeConn(spikes=both), DETECTED_AT, "live")

    assert [s.spike_score for s in replay] == [pytest.approx(26.4575)]
    assert [s.spike_score for s in live] == [pytest.approx(31.0)]


def test_시점_질의에도_source_조건이_걸린다():
    """출처별 시점만 돈다 — 합치면 한쪽에만 있는 시점에 빈 스냅샷이 남는다."""
    assert "s.source = %s" in SELECT_SNAPSHOT_TIMES_SQL

    t_replay = datetime(2024, 10, 6, 20, tzinfo=UTC)
    t_live = datetime(2026, 9, 16, 5, tzinfo=UTC)
    conn = FakeConn(snapshot_times={"replay": [t_replay], "live": [t_live]})

    assert load_snapshot_times(conn, "replay") == [t_replay]
    assert load_snapshot_times(conn, "live") == [t_live]
    assert conn.calls[0][1][0] == "replay"


# ------------------------------------------- source 검증 가드 (-99 → -102)

@pytest.mark.parametrize("good", ["replay", "live"])
def test_허용_source는_통과한다(good):
    """~~replay 만(-99)~~ → 둘 다 (-102). spike.source 가 생겨 조회로 가를 수 있다."""
    assert require_spike_source(good) == good
    assert good in SPIKE_SOURCES


@pytest.mark.parametrize("bad", ["LIVE", "Replay", "", "gdelt", None])
def test_없는_source는_거부한다(bad):
    """🔴 대소문자만 어긋나도 조회가 0행이 되어 '빈 스냅샷' 으로 조용히 저장된다."""
    with pytest.raises(ValueError, match="source"):
        require_spike_source(bad)


def test_live도_replay도_각자_라벨로_생산된다():
    """입력 필터와 출력 라벨이 같은 값이다 — 거짓 라벨링이 성립하지 않는다."""
    both = [spike_row(row_id=1, source="replay"),
            spike_row(row_id=2, source="live")]

    replay = build_snapshot_at(FakeConn(spikes=both), DETECTED_AT, "replay")
    live = build_snapshot_at(FakeConn(spikes=both), DETECTED_AT, "live")

    assert replay.source == "replay"
    assert live.source == "live"
    assert replay.clusters[0].issue_key == "replay:enwiki:Hurricane Milton"
    assert live.clusters[0].issue_key == "live:enwiki:Hurricane Milton"


def test_한쪽_출처만_있으면_다른_쪽은_빈_스냅샷이다():
    """리플레이 행만 있는 DB 에 live 를 돌려도 그 행을 씨드로 쓰지 않는다."""
    conn = FakeConn(spikes=[spike_row(source="replay")])
    assert build_snapshot_at(conn, DETECTED_AT, "live").cluster_count == 0
    assert build_snapshot_at(conn, DETECTED_AT, "replay").cluster_count == 1


def test_run은_시점을_돌기_전에_없는_source를_거부한다():
    """시점이 0개여도 막는다 — 늦게 막으면 빈 목록일 때만 통과해 나중에 갑자기 깨진다."""
    with pytest.raises(ValueError, match="source"):
        run(FakeConn(spikes=[spike_row()]), "LIVE", snapshot_times=[])


def test_CLI는_source를_필수로_받고_둘_다_허용한다():
    """🔴 기본값이 있으면 --source 를 빠뜨린 LIVE 운영이 리플레이를 다시 만든다."""
    from cluster.driver import build_arg_parser

    parser = build_arg_parser()
    assert parser.parse_args(["--dsn", "x", "--source", "live"]).source == "live"
    assert parser.parse_args(["--dsn", "x", "--source", "replay"]).source == "replay"

    with pytest.raises(SystemExit):
        parser.parse_args(["--dsn", "x"])                       # 빠뜨리면 거절
    with pytest.raises(SystemExit):
        parser.parse_args(["--dsn", "x", "--source", "LIVE"])   # 오타도 거절


# ---------------------------------------------------------------- 시점·이전 감지

def test_시점_조회는_오름차순이다():
    """first_detected_at 멱등성이 이 순서에 달렸다 — SQL 정렬을 고정한다."""
    assert "ORDER BY s.detected_at" in SELECT_SNAPSHOT_TIMES_SQL
    times = [datetime(2024, 10, 6, h, tzinfo=UTC) for h in (20, 21, 22)]
    assert load_snapshot_times(FakeConn(snapshot_times=times), "replay") == times


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
