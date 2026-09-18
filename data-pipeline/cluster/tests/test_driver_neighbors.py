"""Clickstream 이웃 배선 — 순수 로직 (WP-115).

`test_driver.py` 가 보던 변환 계약 위에, 이번에 배선된 **월 선택·생성일 해석·
게이트 통과 집계**를 본다. DB 가 필요한 부분은 `test_driver_neighbors_pg.py`.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone

import pytest

from batch.clickstream import NeighborRef
from batch.page_creation import write_index
from cluster.driver import (
    CLICKSTREAM_MONTH_RULES,
    MonthlyNeighborSource,
    NeighborStats,
    clickstream_month_for,
    load_creation_dates,
    neighbors_for_snapshot,
)
from cluster.snapshot import DEFAULT_CREATION_WINDOW_DAYS, Seed

UTC = timezone.utc


def _seed(title, page_id=1, event_date=date(2024, 10, 7)):
    return Seed(page_id=page_id, wiki="enwiki", title=title, event_date=event_date,
                spike_score=9.7, window_start=datetime(2024, 10, 7, tzinfo=UTC),
                window_end=datetime(2024, 10, 7, 4, tzinfo=UTC))


# --- 근거 월 선택 ------------------------------------------------------------

def test_previous_는_직전_달을_고른다():
    assert clickstream_month_for(datetime(2024, 10, 7, 14, tzinfo=UTC), "previous") == "2024-09"


def test_event_는_스냅샷이_속한_달을_고른다():
    assert clickstream_month_for(datetime(2024, 10, 7, 14, tzinfo=UTC), "event") == "2024-10"


def test_previous_는_연초에_전년_12월로_넘어간다():
    assert clickstream_month_for(datetime(2024, 1, 3, tzinfo=UTC), "previous") == "2023-12"


def test_월은_UTC_로_읽는다():
    """로컬 시각으로 읽으면 월말 스냅샷이 옆 달 덤프를 집는다 — 에러 없이 이웃만 달라진다."""
    kst = timezone(__import__("datetime").timedelta(hours=9))
    # KST 2024-11-01 05:00 = UTC 2024-10-31 20:00 → 근거 월은 10월 기준이어야 한다.
    ts = datetime(2024, 11, 1, 5, tzinfo=kst)
    assert clickstream_month_for(ts, "event") == "2024-10"
    assert clickstream_month_for(ts, "previous") == "2024-09"


def test_근거_월_규칙은_명시해야_한다():
    """🔴 기본값을 두지 않는다 — --source 와 같은 이유. 빠뜨리면 에러 없이 다른
    근거로 산출물이 만들어지고, 틀린 달은 이웃 0 이라 "이웃 없음" 과 구분되지 않는다."""
    from cluster.driver import build_arg_parser, main

    args = build_arg_parser().parse_args(
        ["--source", "replay", "--dsn", "x",
         "--clickstream-root", "./cs", "--creation-index", "./ci"])
    assert args.clickstream_month_rule is None      # 조용한 기본값이 없다
    assert main(["--source", "replay", "--dsn", "x",
                 "--clickstream-root", "./cs", "--creation-index", "./ci"]) == 2


def test_이웃_인자는_짝으로_준다():
    """생성일 없이 Clickstream 만 주면 창 게이트가 이웃을 전부 탈락시켜 씨드 단독이 된다."""
    from cluster.driver import main
    assert main(["--source", "replay", "--dsn", "x", "--clickstream-root", "./cs"]) == 2
    assert main(["--source", "replay", "--dsn", "x", "--creation-index", "./ci"]) == 2


def test_모르는_규칙은_막는다():
    with pytest.raises(ValueError):
        clickstream_month_for(datetime(2024, 10, 7, tzinfo=UTC), "same-day")
    assert CLICKSTREAM_MONTH_RULES == ("previous", "event")


# --- 게이트·집계 -------------------------------------------------------------

def test_생성일_창을_통과한_이웃만_남는다(fake_conn):
    refs = {"Hurricane Milton": [
        NeighborRef(title="Hurricane Milton tornado outbreak", n=5000, directed=True),
        NeighborRef(title="Choke point", n=11778, directed=True),      # 오래된 배경 문서
    ]}
    created = {"Hurricane Milton tornado outbreak": date(2024, 10, 9),
               "Choke point": date(2009, 1, 1)}
    stats = NeighborStats()

    result = neighbors_for_snapshot(
        fake_conn, [_seed("Hurricane Milton")], refs, created, "2024-10",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats)

    titles = [nb.title for nb in result[1]]
    assert titles == ["Hurricane Milton tornado outbreak"]
    # 이동량이 2배 넘게 큰 배경 문서가 탈락한다 — §11 의 "절대값으로는 안 갈린다".
    assert stats.window_rejected == 1
    assert stats.gate_passed == 1


def test_생성일_미상과_창_밖을_따로_센다(fake_conn):
    """🔴 합치면 인덱스 구멍이 게이트 판정으로 위장된다."""
    refs = {"Hurricane Milton": [
        NeighborRef(title="Unknown Page", n=100, directed=True),       # 인덱스에 없음
        NeighborRef(title="Old Page", n=100, directed=True),           # 창 밖
    ]}
    stats = NeighborStats()
    neighbors_for_snapshot(
        fake_conn, [_seed("Hurricane Milton")], refs, {"Old Page": date(2009, 1, 1)},
        "2024-10", creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats)

    assert stats.creation_missing == 1
    assert stats.window_rejected == 1
    assert stats.creation_resolved == 1
    assert stats.gate_passed == 0


def test_덤프에_없는_씨드를_센다(fake_conn):
    """씨드 제목이 덤프에 아예 없으면 이웃이 0 이다 — 근거 월이 틀렸을 때의 증상이다."""
    stats = NeighborStats()
    neighbors_for_snapshot(
        fake_conn, [_seed("Hurricane Milton")], {}, {}, "2024-09",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats)
    assert stats.seeds == 1 and stats.seeds_in_dump == 0 and stats.candidates == 0


def test_게이트를_통과한_이웃만_page_id_를_받는다(fake_conn):
    """뒤집으면 멤버가 될 일 없는 이웃 수십만 건이 wiki_page 에 등록된다."""
    refs = {"Hurricane Milton": [
        NeighborRef(title="New", n=10, directed=True),
        NeighborRef(title="Old", n=99999, directed=True),
    ]}
    created = {"New": date(2024, 10, 9), "Old": date(2001, 1, 1)}
    neighbors_for_snapshot(
        fake_conn, [_seed("Hurricane Milton")], refs, created, "2024-10",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=NeighborStats())
    assert fake_conn.asked == [["New"]]


# --- 적재본 연결 -------------------------------------------------------------

def test_적재본이_없는_월은_막는다(tmp_path, fake_conn):
    """조용히 빈 이웃을 내면 "이웃 없음" 과 "덤프 미적재" 가 구분되지 않는다."""
    source = MonthlyNeighborSource(tmp_path / "clickstream", tmp_path / "creation", "event")
    fake_conn.seed_titles = {"enwiki": {"Hurricane Milton"}}
    with pytest.raises(FileNotFoundError) as caught:
        source.prepare(fake_conn, "replay", [datetime(2024, 10, 7, tzinfo=UTC)])
    assert "clickstream_ingest" in str(caught.value)


def test_월_규칙에_따라_다른_적재본을_읽는다(tmp_path, fake_conn):
    root = tmp_path / "clickstream" / "enwiki"
    for month, neighbor in (("2024-09", "September Thing"), ("2024-10", "October Thing")):
        directory = root / month
        directory.mkdir(parents=True)
        with gzip.open(directory / "part-00000.jsonl.gz", "wt", encoding="utf-8") as h:
            h.write(json.dumps({"prev": "Hurricane Milton", "curr": neighbor, "n": 500}) + "\n")
    write_index({"September Thing": date(2024, 10, 1), "October Thing": date(2024, 10, 9)},
                tmp_path / "creation", shard_records=100)

    fake_conn.seed_titles = {"enwiki": {"Hurricane Milton"}}
    ts = datetime(2024, 10, 7, tzinfo=UTC)

    for rule, expected in (("previous", "September Thing"), ("event", "October Thing")):
        source = MonthlyNeighborSource(
            tmp_path / "clickstream", tmp_path / "creation", rule)
        source.prepare(fake_conn, "replay", [ts])
        neighbors = source(fake_conn, ts, [_seed("Hurricane Milton")])
        assert [nb.title for nb in neighbors[1]] == [expected]
        # 근거 월이 그대로 간선 라벨이 된다.
        assert neighbors[1][0].clickstream_month == clickstream_month_for(ts, rule)


def test_생성일은_인덱스에서_온다(tmp_path):
    write_index({"Iran": date(2001, 10, 1)}, tmp_path / "creation", shard_records=100)
    assert load_creation_dates(tmp_path / "creation", ["Iran", "Nope"]) == {
        "Iran": date(2001, 10, 1)}


# --- 대역 ------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if "FROM wiki_page" in sql:
            self.conn.asked.append(sorted(params[1]))
            self._rows = [(title, 900 + i) for i, title in enumerate(sorted(params[1]))]
        elif "SELECT DISTINCT p.wiki, p.title" in sql:
            self._rows = [(wiki, title)
                          for wiki, titles in self.conn.seed_titles.items()
                          for title in sorted(titles)]
        else:
            self._rows = []

    def executemany(self, sql, params):
        self._rows = []

    def fetchall(self):
        return self._rows


class _FakeConn:
    """page_id 해석만 흉내낸다. 진짜 왕복은 `test_driver_neighbors_pg.py`."""

    def __init__(self):
        self.asked: list[list[str]] = []
        self.seed_titles: dict[str, set[str]] = {}

    def cursor(self):
        return _FakeCursor(self)


@pytest.fixture
def fake_conn():
    return _FakeConn()
