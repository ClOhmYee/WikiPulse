"""Historical Window 집계 검증 (WP-58). 네트워크·Spark 없이 돈다."""

from __future__ import annotations

import gzip
import json

from batch.historical_windows import (
    WindowRow,
    aggregate_edits,
    build_windows,
    floor_to_hour,
    hour_of_day,
    is_bot_edit,
    join_windows,
    sum_views,
)


def edit(wiki, title, ts, is_bot=False, user="u1"):
    return {"wiki": wiki, "title": title, "event_ts": ts, "is_bot": is_bot, "user": user}


def view(wiki, title, ts_hour, agent, views):
    return {"wiki": wiki, "title": title, "ts_hour": ts_hour, "agent": agent, "views": views}


# ---------------------------------------------------------------- 시간

def test_정각으로_내린다():
    assert floor_to_hour("2025-06-12T14:37:09") == "2025-06-12T14:00:00"
    assert floor_to_hour("2025-06-12 14:37:09.0") == "2025-06-12T14:00:00"   # 덤프 초정밀
    assert floor_to_hour("2025-06-12T14:00:00Z") == "2025-06-12T14:00:00"


def test_hour_of_day는_요일과_무관하다():
    """0..23 (UTC 시). baseline.py Spark 판(F.hour)과 같은 정의.

    ~~요일×시간 0..167~~ -> 시간 0..23 (2026-09-15, WP-84). 요일 축을 뺐으므로
    **다른 요일의 같은 시각은 같은 슬롯**이다 — 그래야 28일 창에 관측이 28개 쌓인다.
    """
    assert hour_of_day("2025-06-09T00:00:00") == 0      # 월 00시
    assert hour_of_day("2025-06-09T05:00:00") == 5
    assert hour_of_day("2025-06-10T00:00:00") == 0      # 화 00시 — 월요일과 같은 슬롯
    assert hour_of_day("2025-06-15T23:00:00") == 23     # 일 23시 (마지막 슬롯)


# ---------------------------------------------------------------- 편집 집계

def test_봇은_기본_제외():
    assert is_bot_edit(edit("enwiki", "Iran", "t", is_bot=True)) is True
    counts = aggregate_edits([
        edit("enwiki", "Iran", "2025-06-12T14:10:00", user="a"),
        edit("enwiki", "Iran", "2025-06-12T14:50:00", user="b"),
        edit("enwiki", "Iran", "2025-06-12T14:05:00", is_bot=True, user="bot"),  # 봇 제외
    ])
    # (편집 수, 편집자 수) — 봇은 둘 다에서 빠진다
    assert counts[("enwiki", "Iran", "2025-06-12T14:00:00")] == (2, 2)


def test_봇_유지_옵션():
    counts = aggregate_edits(
        [edit("enwiki", "Iran", "2025-06-12T14:05:00", is_bot=True)], keep_bots=True)
    assert counts[("enwiki", "Iran", "2025-06-12T14:00:00")] == (1, 1)


def test_시간별로_나뉜다():
    counts = aggregate_edits([
        edit("enwiki", "Iran", "2025-06-12T14:10:00"),
        edit("enwiki", "Iran", "2025-06-12T15:10:00"),
    ])
    assert counts[("enwiki", "Iran", "2025-06-12T14:00:00")] == (1, 1)
    assert counts[("enwiki", "Iran", "2025-06-12T15:00:00")] == (1, 1)


def test_편집자_수를_따로_센다():
    """같은 사람이 여러 번 고쳐도 편집자는 1명 (WP-85 게이트 입력)."""
    counts = aggregate_edits([
        edit("enwiki", "Iran", "2025-06-12T14:05:00", user="a"),
        edit("enwiki", "Iran", "2025-06-12T14:15:00", user="a"),
        edit("enwiki", "Iran", "2025-06-12T14:25:00", user="a"),
    ])
    assert counts[("enwiki", "Iran", "2025-06-12T14:00:00")] == (3, 1)


# ---------------------------------------------------------------- 조회 집계

def test_agent_가로질러_합산_선택():
    rows = [
        view("enwiki", "Iran", "2025-06-12T14:00:00", "user", 100),
        view("enwiki", "Iran", "2025-06-12T14:00:00", "automated", 20),
        view("enwiki", "Iran", "2025-06-12T14:00:00", "spider", 5),
    ]
    assert sum_views(rows)[("enwiki", "Iran", "2025-06-12T14:00:00")] == 125   # 전부
    assert sum_views(rows, agents={"user", "automated"})[
        ("enwiki", "Iran", "2025-06-12T14:00:00")] == 120                       # spider 제외


# ---------------------------------------------------------------- join

def test_full_outer_한쪽만_있으면_0():
    edits = {("enwiki", "A", "2025-06-09T00:00:00"): (3, 2)}
    views = {("enwiki", "B", "2025-06-09T01:00:00"): 50}
    out = {(r.title, r.window_start): r for r in join_windows(edits, views)}
    assert out[("A", "2025-06-09T00:00:00")].edit_count == 3
    assert out[("A", "2025-06-09T00:00:00")].views == 0        # 조회 없음 → 0
    assert out[("B", "2025-06-09T01:00:00")].edit_count == 0   # 편집 없음 → 0
    assert out[("B", "2025-06-09T01:00:00")].views == 50


def test_build_windows_정렬_결합():
    rows = build_windows(
        [edit("enwiki", "Iran", "2025-06-09T00:10:00")],
        [view("enwiki", "Iran", "2025-06-09T00:00:00", "user", 40)],
    )
    assert rows == [WindowRow(
        "enwiki", "Iran", "2025-06-09T00:00:00", hour_of_day("2025-06-09T00:00:00"),
        edit_count=1, editor_count=1, views=40)]



def test_샤드_세대가_섞여도_한_문서로_join_된다():
    """🔴 WP-92 회귀.

    WP-79 부터 normalize_dump·pageview 가 공백형 제목을 낸다. 그 전에 만든
    -56 편집 샤드는 밑줄형이라 **두 세대가 섞여 돈다.** 읽는 지점에서 canonical 로
    안 맞추면 join_windows 의 (wiki, title, hour) 가 한 건도 안 맞아서, 같은 문서·
    같은 시각이 views=0 행과 edit_count=0 행 **둘**로 쪼개진다. view_ewma 가 전부
    비고 조회수 단독 발동(WP-90)이 통째로 죽는데 **에러는 안 난다.**
    """
    rows = build_windows(
        [edit("enwiki", "Hurricane_Milton", "2024-10-06T19:10:00")],   # 구세대(밑줄)
        [view("enwiki", "Hurricane Milton", "2024-10-06T19:00:00", "user", 500)],
    )
    assert rows == [WindowRow(
        "enwiki", "Hurricane Milton", "2024-10-06T19:00:00",
        hour_of_day("2024-10-06T19:00:00"),
        edit_count=1, editor_count=1, views=500)]


def test_canonical_은_멱등이라_신세대_샤드에_무영향():
    """양쪽 다 공백형이면 값이 하나도 안 바뀐다 — 이 보정이 기존 결과를 흔들지 않는다."""
    rows = build_windows(
        [edit("enwiki", "Hurricane Milton", "2024-10-06T19:10:00")],
        [view("enwiki", "Hurricane Milton", "2024-10-06T19:00:00", "user", 500)],
    )
    assert rows[0].title == "Hurricane Milton"
    assert rows[0].edit_count == 1 and rows[0].views == 500


def test_같은_문서의_두_표기가_한_키로_합쳐진다():
    """세대가 섞인 편집 샤드끼리도 합쳐져야 한다. 안 합치면 편집 수가 쪼개져
    절대 하한(10)에 못 미치고 미탐이 난다."""
    counts = aggregate_edits([
        edit("enwiki", "Hurricane_Milton", "2024-10-06T19:10:00", user="a"),
        edit("enwiki", "Hurricane Milton", "2024-10-06T19:20:00", user="b"),
    ])
    assert counts == {("enwiki", "Hurricane Milton", "2024-10-06T19:00:00"): (2, 2)}

# ---------------------------------------------------------------- CLI 왕복

def test_cli_샤드_읽어_집계(tmp_path):
    from batch.historical_windows_ingest import main

    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    with gzip.open(edits_dir / "part-00000.jsonl.gz", "wt", encoding="utf-8") as h:
        h.write(json.dumps(edit("enwiki", "Iran", "2025-06-09T00:10:00")) + "\n")

    views_dir = tmp_path / "views" / "2025-06-09"       # -57 은 날짜 하위 폴더
    views_dir.mkdir(parents=True)
    with gzip.open(views_dir / "part-00000.jsonl.gz", "wt", encoding="utf-8") as h:
        h.write(json.dumps(view("enwiki", "Iran", "2025-06-09T00:00:00", "user", 40)) + "\n")

    out_dir = tmp_path / "baseline-input"
    rc = main(["--edits", str(edits_dir), "--views", str(tmp_path / "views"),
               "--out", str(out_dir)])
    assert rc == 0
    assert (out_dir / "_manifest.json").exists()

    written = []
    with gzip.open(out_dir / "part-00000.jsonl.gz", "rt", encoding="utf-8") as h:
        for line in h:
            written.append(json.loads(line))
    assert len(written) == 1
    assert written[0]["edit_count"] == 1 and written[0]["views"] == 40
