"""`page_baseline` 조회 (WP-94). DB 없이 가짜 커넥션으로 계약만 고정한다.

실 PostgreSQL 왕복은 `test_spike_runtime_pg.py` 가 본다 — 나눈 이유는
`test_baseline_sink_pg.py` 와 같다. 한 파일에 두면 DB 없는 환경에서 계약 검사까지
함께 skip 되어 깨져도 아무도 모른다.
"""

from __future__ import annotations

from spike.baseline_repository import BaselineRepository
from spike.detector import MIN_BASELINE_SAMPLE_DAYS


class FakeCursor:
    """`SELECT` 한 번에 정해진 행을 주고, 받은 파라미터를 기록한다."""

    def __init__(self, store: dict[tuple[str, str], list[tuple]], calls: list):
        self._store = store
        self._calls = calls
        self._rows: list[tuple] = []

    def execute(self, sql, params):
        self._calls.append(params)
        self._rows = list(self._store.get(tuple(params), []))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, store):
        self.store = store
        self.calls: list = []

    def cursor(self):
        return FakeCursor(self.store, self.calls)


def row(hour_of_day, edit_ewma=2.0, edit_stddev=1.0, view_ewma=None, view_stddev=None,
        sample_days=14):
    """SELECT_BASELINE_SQL 의 컬럼 순서 그대로."""
    return (hour_of_day, edit_ewma, edit_stddev, view_ewma, view_stddev, sample_days)


def repo(rows, wiki="enwiki", title="Hurricane Milton"):
    return BaselineRepository(FakeConn({(wiki, title): rows}))


# ---------------------------------------------------------------- 정상 조회

def test_슬롯의_기준선을_detector_Baseline으로_준다():
    baseline = repo([row(19, edit_ewma=3.5, edit_stddev=1.25, sample_days=21)]) \
        .get("enwiki", "Hurricane Milton", 19)
    assert baseline is not None
    assert baseline.edit_ewma == 3.5
    assert baseline.edit_stddev == 1.25
    assert baseline.sample_days == 21
    assert baseline.is_thin is False


def test_조회수_기준선도_그대로_넘어간다():
    baseline = repo([row(0, view_ewma=120.0, view_stddev=30.0)]) \
        .get("enwiki", "Hurricane Milton", 0)
    assert baseline.view_ewma == 120.0
    assert baseline.view_stddev == 30.0


def test_얇은_기준선은_is_thin으로_구분된다():
    thin = MIN_BASELINE_SAMPLE_DAYS - 1
    baseline = repo([row(0, sample_days=thin)]).get("enwiki", "Hurricane Milton", 0)
    assert baseline is not None          # 행은 있다 — '없음' 과 다른 상태다
    assert baseline.is_thin is True


# ---------------------------------------------------------------- 없음

def test_행이_없는_슬롯은_None():
    assert repo([row(0)]).get("enwiki", "Hurricane Milton", 13) is None


def test_문서_자체가_없으면_None():
    assert repo([]).get("enwiki", "No Such Page", 0) is None


# ---------------------------------------------------------------- NULL 보존

def test_NULL_stddev는_None으로_남는다():
    """0 으로 채우면 '분산 0' 과 '표본 없음' 이 구분되지 않는다 (V4 주석)."""
    baseline = repo([row(0, edit_stddev=None, view_ewma=None, view_stddev=None)]) \
        .get("enwiki", "Hurricane Milton", 0)
    assert baseline.edit_stddev is None
    assert baseline.view_ewma is None
    assert baseline.view_stddev is None


# ---------------------------------------------------------------- canonical title

def test_밑줄_제목으로_물어도_공백형으로_조회한다():
    """호출자가 덤프 원형을 넘겨도 SELECT 가 조용히 0행이 되면 안 된다 (WP-92)."""
    conn = FakeConn({("enwiki", "Hurricane Milton"): [row(19)]})
    found = BaselineRepository(conn).get("enwiki", "Hurricane_Milton", 19)
    assert found is not None
    assert conn.calls == [("enwiki", "Hurricane Milton")]


# ---------------------------------------------------------------- 캐시

def test_같은_문서를_여러_슬롯_물어도_왕복은_한_번():
    """문서당 24슬롯뿐이라 한 번에 읽는다 — 리플레이는 문서당 수백 윈도우를 돈다."""
    conn = FakeConn({("enwiki", "Hurricane Milton"): [row(h) for h in range(24)]})
    repository = BaselineRepository(conn)
    for hour in range(24):
        assert repository.get("enwiki", "Hurricane Milton", hour) is not None
    assert len(conn.calls) == 1


def test_없는_문서도_한_번만_묻는다():
    conn = FakeConn({})
    repository = BaselineRepository(conn)
    assert repository.get("enwiki", "Nope", 0) is None
    assert repository.get("enwiki", "Nope", 1) is None
    assert len(conn.calls) == 1


def test_invalidate하면_다시_읽는다():
    conn = FakeConn({("enwiki", "Hurricane Milton"): [row(0)]})
    repository = BaselineRepository(conn)
    repository.get("enwiki", "Hurricane Milton", 0)
    repository.invalidate()
    repository.get("enwiki", "Hurricane Milton", 0)
    assert len(conn.calls) == 2
