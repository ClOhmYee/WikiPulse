"""Clickstream 이웃 배선 — 순수 로직 (WP-115).

`test_driver.py` 가 보던 변환 계약 위에, 이번에 배선된 **월 선택·생성일 해석·
게이트 통과 집계**를 본다. DB 가 필요한 부분은 `test_driver_neighbors_pg.py`.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from batch.clickstream import NeighborRef
from batch.page_creation import write_index
from batch.page_edit_daily import edit_days_for
from batch.page_edit_daily import write_index as write_edit_index
from cluster.driver import (
    MonthlyNeighborSource,
    NeighborStats,
    load_creation_dates,
    neighbors_for_snapshot,
    resurgence_for,
)
from cluster.snapshot import DEFAULT_CREATION_WINDOW_DAYS, Seed

UTC = timezone.utc


def _seed(title, page_id=1, event_date=date(2024, 10, 7)):
    return Seed(page_id=page_id, wiki="enwiki", title=title, event_date=event_date,
                spike_score=9.7, window_start=datetime(2024, 10, 7, tzinfo=UTC),
                window_end=datetime(2024, 10, 7, 4, tzinfo=UTC))


# --- 근거 월 선택 (select_completed_month 위임) --------------------------------
#
# 🔴 월 선택 규칙은 `batch.clickstream.select_completed_month` 한 곳이다
#    (2026-09-18, develop 머지). ~~`clickstream_month_for(previous|event)`~~ 는
#    -115 가 머지 전까지 쓰던 로컬 스위치였고 규칙이 두 벌이 되므로 제거했다.
#    여기서는 "driver 가 그 함수에 위임하는가" 만 본다 — 규칙 자체의 단위 테스트는
#    `batch/tests/test_clickstream.py` 가 갖고 있다.

def _dump(root, wiki, month, rows=(("Seed", "Neighbor", 5000),)):
    """`clickstream_ingest` 출력 모양 그대로 — manifest 까지 있어야 완료본이다."""
    directory = root / wiki / month
    directory.mkdir(parents=True)
    with gzip.open(directory / "part-00000.jsonl.gz", "wt", encoding="utf-8") as handle:
        for prev, curr, n in rows:
            print(json.dumps({"prev": prev, "curr": curr, "n": n}), file=handle)
    (directory / "_manifest.json").write_text(
        json.dumps({"wiki": wiki, "month": month, "shards": ["part-00000.jsonl.gz"]}),
        encoding="utf-8")
    return directory


def test_근거_월은_직전_완료_월이다(tmp_path):
    root = tmp_path / "cs"
    _dump(root, "enwiki", "2024-09")
    source = MonthlyNeighborSource(root, tmp_path / "ci")
    assert source.month_for("enwiki", datetime(2024, 10, 7, 14, tzinfo=UTC)) == "2024-09"


def test_직전_월이_없으면_더_오래된_완료본으로_폴백한다(tmp_path):
    """직전 월 덤프가 아직 공개·적재되지 않은 경우. 당월로 넘어가지 않는다."""
    root = tmp_path / "cs"
    _dump(root, "enwiki", "2024-08")
    source = MonthlyNeighborSource(root, tmp_path / "ci")
    assert source.month_for("enwiki", datetime(2024, 10, 7, tzinfo=UTC)) == "2024-08"


def test_스냅샷_당월_덤프는_고르지_않는다(tmp_path):
    """월이 끝나야 나오는 덤프다 — 운영 당시에는 존재하지 않던 근거다(명세 v0.3 §3.2 4번)."""
    root = tmp_path / "cs"
    _dump(root, "enwiki", "2024-10")
    source = MonthlyNeighborSource(root, tmp_path / "ci")
    with pytest.raises(FileNotFoundError):
        source.month_for("enwiki", datetime(2024, 10, 7, tzinfo=UTC))


def test_월은_UTC_로_읽는다(tmp_path):
    """로컬 시각으로 읽으면 월말 스냅샷이 옆 달 덤프를 집는다 — 에러 없이 이웃만 달라진다."""
    kst = timezone(timedelta(hours=9))
    root = tmp_path / "cs"
    _dump(root, "enwiki", "2024-09")
    source = MonthlyNeighborSource(root, tmp_path / "ci")
    # KST 2024-11-01 05:00 = UTC 2024-10-31 20:00 -> 직전 완료 월은 2024-09 여야 한다.
    assert source.month_for("enwiki", datetime(2024, 11, 1, 5, tzinfo=kst)) == "2024-09"


def test_완료본이_하나도_없으면_막는다(tmp_path):
    """조용히 빈 이웃을 돌려주면 "이웃이 없는 시점" 과 구분되지 않는다."""
    source = MonthlyNeighborSource(tmp_path / "cs", tmp_path / "ci")
    with pytest.raises(FileNotFoundError):
        source.month_for("enwiki", datetime(2024, 10, 7, tzinfo=UTC))


def test_이웃_인자는_짝으로_준다():
    """생성일 없이 Clickstream 만 주면 창 게이트가 이웃을 전부 탈락시켜 씨드 단독이 된다."""
    from cluster.driver import main
    assert main(["--source", "replay", "--dsn", "x", "--clickstream-root", "./cs"]) == 2
    assert main(["--source", "replay", "--dsn", "x", "--creation-index", "./ci"]) == 2


def test_월_규칙_인자는_사라졌다():
    """~~--clickstream-month-rule~~ -> select_completed_month 로 통합 (develop 머지)."""
    from cluster.driver import build_arg_parser
    args = build_arg_parser().parse_args(
        ["--source", "replay", "--dsn", "x",
         "--clickstream-root", "./cs", "--creation-index", "./ci"])
    assert not hasattr(args, "clickstream_month_rule")


# --- 게이트·집계 -------------------------------------------------------------

def test_생성일_창을_통과한_이웃만_남는다(fake_conn):
    refs = {"Hurricane Milton": [
        NeighborRef(title="Hurricane Milton tornado outbreak", n=5000, directed=True),
        NeighborRef(title="Choke point", n=11778, directed=True),      # 오래된 배경 문서
    ]}
    created = {"Hurricane Milton tornado outbreak": datetime(2024, 10, 9, tzinfo=UTC),
               "Choke point": datetime(2009, 1, 1, tzinfo=UTC)}
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
        fake_conn, [_seed("Hurricane Milton")], refs, {"Old Page": datetime(2009, 1, 1, tzinfo=UTC)},
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
    created = {"New": datetime(2024, 10, 9, tzinfo=UTC),
               "Old": datetime(2001, 1, 1, tzinfo=UTC)}
    neighbors_for_snapshot(
        fake_conn, [_seed("Hurricane Milton")], refs, created, "2024-10",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=NeighborStats())
    assert fake_conn.asked == [["New"]]


# --- 적재본 연결 -------------------------------------------------------------

def test_적재본이_없는_월은_막는다(tmp_path, fake_conn):
    """조용히 빈 이웃을 내면 "이웃 없음" 과 "덤프 미적재" 가 구분되지 않는다.

    🔴 스캔 **전에** 막아야 한다. 뒤에서 막으면 앞 월을 수천만 행 다 읽고 나서 죽는다.
    """
    source = MonthlyNeighborSource(tmp_path / "clickstream", tmp_path / "creation")
    fake_conn.seed_titles = {"enwiki": {"Hurricane Milton"}}
    with pytest.raises(FileNotFoundError):
        source.prepare(fake_conn, "replay", [datetime(2024, 10, 7, tzinfo=UTC)])


def test_manifest_없는_적재본은_완료본이_아니다(tmp_path, fake_conn):
    """shard 파일만 있고 `_manifest.json` 이 없으면 검증을 통과하지 않은 적재본이다."""
    directory = tmp_path / "clickstream" / "enwiki" / "2024-09"
    directory.mkdir(parents=True)
    with gzip.open(directory / "part-00000.jsonl.gz", "wt", encoding="utf-8") as h:
        print(json.dumps({"prev": "Hurricane Milton", "curr": "X", "n": 500}), file=h)
    source = MonthlyNeighborSource(tmp_path / "clickstream", tmp_path / "creation")
    fake_conn.seed_titles = {"enwiki": {"Hurricane Milton"}}
    with pytest.raises(FileNotFoundError):
        source.prepare(fake_conn, "replay", [datetime(2024, 10, 7, tzinfo=UTC)])


def test_완료_월_적재본을_읽어_간선_라벨까지_싣는다(tmp_path, fake_conn):
    """스냅샷 당월(2024-10)이 아니라 직전 완료 월(2024-09) 이웃이 붙어야 한다."""
    root = tmp_path / "clickstream"
    _dump(root, "enwiki", "2024-09",
          rows=(("Hurricane Milton", "September Thing", 500),))
    _dump(root, "enwiki", "2024-10",
          rows=(("Hurricane Milton", "October Thing", 500),))
    write_index({"September Thing": datetime(2024, 10, 1, tzinfo=UTC),
                 "October Thing": datetime(2024, 10, 9, tzinfo=UTC)},
                tmp_path / "creation", shard_records=100)

    fake_conn.seed_titles = {"enwiki": {"Hurricane Milton"}}
    ts = datetime(2024, 10, 7, tzinfo=UTC)

    source = MonthlyNeighborSource(root, tmp_path / "creation")
    source.prepare(fake_conn, "replay", [ts])
    neighbors = source(fake_conn, ts, [_seed("Hurricane Milton")])
    assert [nb.title for nb in neighbors[1]] == ["September Thing"]
    # 근거 월이 그대로 간선 라벨이 된다.
    assert neighbors[1][0].clickstream_month == "2024-09"


def test_생성일은_인덱스에서_온다(tmp_path):
    write_index({"Iran": datetime(2001, 10, 1, tzinfo=UTC)}, tmp_path / "creation",
                shard_records=100)
    assert load_creation_dates(tmp_path / "creation", ["Iran", "Nope"]) == {
        "Iran": datetime(2001, 10, 1, tzinfo=UTC)}


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


# ------------------------------------------------ 비-씨드 재급증 배선 (WP-145)

def _resurgence_index(tmp_path, days_by_title):
    """`batch/page_edit_daily` 적재본을 만든다."""
    out = tmp_path / "edits"
    write_edit_index(days_by_title, out, shard_records=1000)
    return out


def _days(start: date, n: int, per_day: int) -> dict:
    return {start + timedelta(days=i): per_day for i in range(n)}


def test_사건기간은_생성일_창과_같은_폭이다():
    """폭이 다르면 창을 떨어진 문서를 다른 자로 재게 돼 두 게이트가 비교 불가다."""
    spike = resurgence_for({date(2026, 3, 8): 1}, date(2026, 3, 8), window_days=30)

    assert spike.event_start == datetime(2026, 2, 6, tzinfo=UTC)   # -30일
    assert spike.event_end == datetime(2026, 4, 8, tzinfo=UTC)     # +30일 다음날(끝 제외)
    # 기준기간은 직전 같은 길이, 겹치지 않는다.
    assert spike.baseline_end == spike.event_start
    assert (spike.event_end - spike.event_start) == (
        spike.baseline_end - spike.baseline_start)


def test_편집_인덱스에_없으면_수치를_지어내지_않는다():
    """0 으로 채우면 기준기간이 0 이 되어 덤프 구멍이 재급증으로 위장된다."""
    assert resurgence_for(None, date(2026, 3, 8), window_days=30) is None


def test_재조명_문서가_창밖이어도_이웃으로_살아남는다(tmp_path):
    """Mojtaba_Khamenei 형 — 2009 생성이라 창 밖인데 사건기간 편집이 급증했다."""
    seed = _seed("2026 Iran war", event_date=date(2026, 3, 8))
    refs = {"2026 Iran war": [NeighborRef(title="Mojtaba Khamenei", n=500, directed=True)]}
    created = {"Mojtaba Khamenei": datetime(2009, 1, 1, tzinfo=UTC)}
    # 사건기간(2/6~4/7) 61일에 매일 20건, 직전 61일은 매일 1건 → 20배·1,220건
    edits = _resurgence_index(tmp_path, {"Mojtaba Khamenei": {
        **_days(date(2025, 12, 7), 61, 1),
        **_days(date(2026, 2, 6), 61, 20),
    }})

    stats = NeighborStats()
    out = neighbors_for_snapshot(
        _FakeConn(), [seed], refs, created, "2026-02",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats,
        snapshot_ts=datetime(2026, 5, 1, tzinfo=UTC),
        edit_days_of_title=edit_days_for(edits, ["Mojtaba Khamenei"]),
    )

    assert stats.window_rejected == 1, "창은 떨어져야 한다 (2009 생성)"
    assert stats.resurgence_passed == 1
    neighbor = out[seed.page_id][0]
    assert neighbor.title == "Mojtaba Khamenei"
    assert neighbor.resurgence is not None
    assert neighbor.resurgence.event_edits == 61 * 20


def test_배경_문서는_재급증에서도_탈락한다(tmp_path):
    """Hurricane_Helene 형 — 절대량은 큰데 비율이 1 근처다."""
    seed = _seed("2026 Iran war", event_date=date(2026, 3, 8))
    refs = {"2026 Iran war": [NeighborRef(title="Choke point", n=11778, directed=True)]}
    created = {"Choke point": datetime(2009, 1, 1, tzinfo=UTC)}
    edits = _resurgence_index(tmp_path, {"Choke point": {
        **_days(date(2025, 12, 7), 61, 10),
        **_days(date(2026, 2, 6), 61, 11),   # 1.1배
    }})

    stats = NeighborStats()
    out = neighbors_for_snapshot(
        _FakeConn(), [seed], refs, created, "2026-02",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats,
        snapshot_ts=datetime(2026, 5, 1, tzinfo=UTC),
        edit_days_of_title=edit_days_for(edits, ["Choke point"]),
    )

    assert stats.resurgence_rejected == 1
    assert stats.resurgence_passed == 0
    assert out[seed.page_id] == [], "이동량이 커도 비율이 낮으면 배경이다"


def test_편집_인덱스_구멍은_탈락과_따로_센다(tmp_path):
    """⚠️ 합치면 덤프 구멍이 '규칙대로 걸렀다' 로 읽힌다."""
    seed = _seed("2026 Iran war", event_date=date(2026, 3, 8))
    refs = {"2026 Iran war": [NeighborRef(title="없는문서", n=100, directed=True)]}
    created = {"없는문서": datetime(2009, 1, 1, tzinfo=UTC)}

    stats = NeighborStats()
    neighbors_for_snapshot(
        _FakeConn(), [seed], refs, created, "2026-02",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats,
        snapshot_ts=datetime(2026, 5, 1, tzinfo=UTC),
        edit_days_of_title={},
    )

    assert stats.resurgence_missing == 1
    assert stats.resurgence_rejected == 0


def test_편집_인덱스를_안_주면_옛_동작_그대로다(tmp_path):
    """LIVE 처럼 월 덤프가 없는 구간은 씨드 전용으로 돈다 — 조용히 깨지지 않는다."""
    seed = _seed("2026 Iran war", event_date=date(2026, 3, 8))
    refs = {"2026 Iran war": [NeighborRef(title="Mojtaba Khamenei", n=500, directed=True)]}
    created = {"Mojtaba Khamenei": datetime(2009, 1, 1, tzinfo=UTC)}

    stats = NeighborStats()
    out = neighbors_for_snapshot(
        _FakeConn(), [seed], refs, created, "2026-02",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats)

    assert stats.window_rejected == 1
    assert stats.resurgence_missing == 0, "재급증 경로 자체를 안 돈다"
    assert out[seed.page_id] == []


def test_사건기간이_데이터_끝을_넘으면_판정하지_않는다():
    """🔴 2026-09-20 실측 — 스냅샷의 마지막 달은 잘려 있다.

    `2026-08` 스냅샷의 `2026-09` 파일은 09-01 하루치뿐이었다(24,378건, 다른 달의
    0.5%). 잘린 구간을 0 으로 세면 진짜 재조명 문서가 "미달" 로 탈락한다 —
    놓치는 쪽으로, 에러 없이 틀린다.
    """
    days = {date(2026, 8, 20): 500}

    # 사건일 +30일 = 09-19 로 데이터 끝(09-01)을 넘는다 → 판정 보류
    assert resurgence_for(days, date(2026, 8, 20), 30,
                          coverage_until=date(2026, 9, 1)) is None
    # 끝을 안 넘으면 평소대로 판정한다
    assert resurgence_for(days, date(2026, 7, 1), 30,
                          coverage_until=date(2026, 9, 1)) is not None
    # 경계를 모르면(옛 적재본) 판정한다 — 날짜를 지어내지 않는다
    assert resurgence_for(days, date(2026, 8, 20), 30) is not None


def test_잘린_구간은_탈락이_아니라_미상으로_센다(tmp_path):
    """탈락으로 세면 덤프 경계가 '규칙대로 걸렀다' 로 읽힌다."""
    seed = _seed("2026 Iran war", event_date=date(2026, 8, 20))
    refs = {"2026 Iran war": [NeighborRef(title="Mojtaba Khamenei", n=500, directed=True)]}
    created = {"Mojtaba Khamenei": datetime(2009, 1, 1, tzinfo=UTC)}
    edits = _resurgence_index(tmp_path, {"Mojtaba Khamenei": _days(date(2026, 7, 1), 40, 50)})

    stats = NeighborStats()
    neighbors_for_snapshot(
        _FakeConn(), [seed], refs, created, "2026-07",
        creation_window_days=DEFAULT_CREATION_WINDOW_DAYS, stats=stats,
        snapshot_ts=datetime(2026, 10, 1, tzinfo=UTC),
        edit_days_of_title=edit_days_for(edits, ["Mojtaba Khamenei"]),
        edit_coverage_until=date(2026, 9, 1))

    assert stats.resurgence_missing == 1
    assert stats.resurgence_rejected == 0
    assert stats.resurgence_passed == 0
