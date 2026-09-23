"""조회수만으로 기준선을 만드는 경로 (WP-212). DB 는 대역이다.

여기서 고정하는 것은 **무엇을 읽어 무엇을 만드는지**다. 수식 자체는
`test_baseline_rows.py` 가 고정하고 여기서 다시 검증하지 않는다 — 두 곳에서
같은 것을 검증하면 한쪽만 고쳐졌을 때 갈린다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from spike.baseline_from_views import read_views, run, window_bounds

UTC = timezone.utc


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.params = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.params = params
        self.executed.append(sql)

    def fetchall(self):
        return self.rows

    def executemany(self, sql, seq):
        self.executed.append((sql, list(seq)))


class FakeConn:
    def __init__(self, rows=()):
        self.cur = FakeCursor(list(rows))
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def view_row(day: int, hour: int, views: int, title="Moderna"):
    return ("enwiki", title, datetime(2026, 9, day, hour, tzinfo=UTC), hour, views)


# ---------------------------------------------------------------- 창 경계

def test_as_of_그날_전체가_창에_들어간다():
    """⚠️ 끝을 as_of 0시로 자르면 그날 하루가 통째로 빠진다 — 행 수만 줄어 안 보인다."""
    start, end = window_bounds(date(2026, 9, 22), window_days=28)
    assert start == datetime(2026, 8, 25, tzinfo=UTC)
    assert end == datetime(2026, 9, 23, tzinfo=UTC)          # as_of 다음 날 0시
    assert end - start == timedelta(days=29)


def test_창_길이는_인자로_바뀐다():
    start, end = window_bounds(date(2026, 9, 22), window_days=7)
    assert start == datetime(2026, 9, 15, tzinfo=UTC)


# ---------------------------------------------------------------- 읽기

def test_edit_count_를_0_으로_준다():
    """🔴 이 경로에는 편집 정보가 없다. 지어내지 않고 0 을 준다 —
    edit_z 는 관문이 아니라 진단값이라 판정에는 영향이 없다."""
    conn = FakeConn([view_row(20, 14, 6893)])
    rows = list(read_views(conn, "enwiki", date(2026, 9, 22)))
    assert rows == [{
        "wiki": "enwiki", "title": "Moderna",
        "window_start": datetime(2026, 9, 20, 14, tzinfo=UTC),
        "hour_of_day": 14, "edit_count": 0, "views": 6893,
    }]


def test_창과_위키를_질의에_넘긴다():
    conn = FakeConn([])
    list(read_views(conn, "enwiki", date(2026, 9, 22), window_days=28))
    start, end, wiki = conn.cur.params
    assert (start, end) == window_bounds(date(2026, 9, 22))
    assert wiki == "enwiki"


# ---------------------------------------------------------------- 한 번 돌리기

def test_얇은_기준선을_센다():
    """28일이 차기 전에는 sample_days < 7 이라 detector 가 fallback 을 쓴다.

    깨지는 게 아니라 **아직 안 좋아진** 상태라, 그 개수를 세어 진행도를 본다.
    """
    conn = FakeConn([view_row(20, 14, 100), view_row(21, 14, 120)])
    s = run(conn, as_of=date(2026, 9, 22), dry_run=True)
    assert s["observations"] == 2
    assert s["rows"] == 1                  # (Moderna, 14시) 슬롯 하나
    assert s["thin"] == 1                  # 관측 이틀 -> 얇다
    assert s["written"] == 0               # dry-run 은 안 쓴다
    assert conn.commits == 0


def test_같은_문서의_다른_시간대는_다른_슬롯이다():
    """🔴 기준선 키가 (문서, 시간대) 다. 하나로 뭉치면 낮 트래픽이 새벽 기준으로는
    급증처럼 보인다 — baseline.py 독스트링의 근거."""
    conn = FakeConn([view_row(20, 14, 100), view_row(20, 3, 10)])
    s = run(conn, as_of=date(2026, 9, 22), dry_run=True)
    assert s["rows"] == 2


def test_관측이_없으면_아무것도_안_쓴다():
    """⚠️ 기준선 없음과 기준선 0 은 다른 뜻이다 — detector 가 None 을 신규 문서로 본다."""
    conn = FakeConn([])
    s = run(conn, as_of=date(2026, 9, 22))
    assert (s["rows"], s["written"]) == (0, 0)
    assert conn.commits == 0
