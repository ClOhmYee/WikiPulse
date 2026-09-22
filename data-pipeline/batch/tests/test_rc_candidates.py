"""RC 수집본 → candidate title (WP-164)."""

from __future__ import annotations

import gzip
import json

from batch.historical_windows import aggregate_edits
from batch.rc_candidates import (
    RC_SOURCE,
    candidate_rows,
    edit_events,
    is_edit_record,
    read_raw,
    to_edit_event,
    write_rows,
)


def _rc(title="Air India Flight 171", *, ns=0, kind="edit", bot=False,
        user="Alice", ts="2026-09-01T02:05:00Z", revid=1, rcid=1):
    return {"ns": ns, "type": kind, "bot": bot, "user": user, "userid": 7,
            "title": title, "timestamp": ts, "revid": revid, "rcid": rcid,
            "pageid": 42, "old_revid": 0, "minor": False}


# ------------------------------------------------------------------ 필터

def test_본문_namespace_밖은_버린다():
    assert is_edit_record(_rc(ns=0)) is True
    assert is_edit_record(_rc(ns=1)) is False
    assert is_edit_record(_rc(ns=14)) is False


def test_편집이_아닌_type은_버린다():
    """수집이 이미 좁혀 받지만 읽는 쪽에서 한 번 더 막는다 — 재수집 시한이 없다."""
    assert is_edit_record(_rc(kind="edit")) is True
    assert is_edit_record(_rc(kind="new")) is True
    for kind in ("log", "categorize", "external"):
        assert is_edit_record(_rc(kind=kind)) is False


def test_봇은_필터에서_거르지_않는다():
    """🔴 거르는 것은 aggregate_edits 책임이다. 여기서 빼면 규칙이 두 벌이 된다."""
    assert is_edit_record(_rc(bot=True)) is True
    assert to_edit_event(_rc(bot=True), "enwiki")["is_bot"] is True


# ------------------------------------------------------------------ 변환

def test_RC_의_bot_플래그를_그대로_is_bot_으로_싣는다():
    """allrevisions + 그룹 조회로 대체하면 정밀도 0.4394 로 떨어진다 (-163 §3)."""
    assert to_edit_event(_rc(bot=True), "enwiki")["is_bot"] is True
    assert to_edit_event(_rc(bot=False), "enwiki")["is_bot"] is False


def test_제목은_canonical_로_통과시킨다():
    event = to_edit_event(_rc(title="Hurricane__Milton "), "enwiki")
    assert event["title"] == "Hurricane Milton"


def test_출처는_덤프_실시간과_구분된다():
    assert to_edit_event(_rc(), "enwiki")["source"] == RC_SOURCE == "recentchanges"


# ------------------------------------------------------- 집계 (덤프와 한 벌)

def test_봇_편집만_있는_문서는_candidate_가_되지_않는다():
    """명세 §3.2 1차 관문 — 봇이 아닌 편집 1건 이상."""
    records = [_rc(title="Bot Only", bot=True, rcid=1, revid=1),
               _rc(title="Bot Only", bot=True, rcid=2, revid=2)]

    rows = candidate_rows(aggregate_edits(edit_events(records, "enwiki")))

    assert rows == []


def test_같은_시간의_편집이_한_윈도우로_집계된다():
    records = [
        _rc(user="Alice", ts="2026-09-01T02:05:00Z", rcid=1, revid=10),
        _rc(user="Bob", ts="2026-09-01T02:59:59Z", rcid=2, revid=20),
        _rc(user="Bot", bot=True, ts="2026-09-01T02:30:00Z", rcid=3, revid=99),
        _rc(user="Alice", ts="2026-09-01T03:00:00Z", rcid=4, revid=30),
    ]

    rows = candidate_rows(aggregate_edits(edit_events(records, "enwiki")))

    assert [(r["window_start"], r["edit_count"], r["editor_count"]) for r in rows] == [
        ("2026-09-01T02:00:00", 2, 2),
        ("2026-09-01T03:00:00", 1, 1),
    ]
    # 봇 편집은 max_rev_id 에도 들어가면 안 된다 — 시점 증거가 오염된다.
    assert rows[0]["max_rev_id"] == 20


def test_행은_시간_제목_순으로_정렬돼_재실행이_같은_결과를_낸다():
    records = [
        _rc(title="Zebra", ts="2026-09-01T03:00:00Z", rcid=1, revid=1),
        _rc(title="Apple", ts="2026-09-01T03:00:00Z", rcid=2, revid=2),
        _rc(title="Mango", ts="2026-09-01T02:00:00Z", rcid=3, revid=3),
    ]

    rows = candidate_rows(aggregate_edits(edit_events(records, "enwiki")))

    assert [(r["window_start"][-8:], r["title"]) for r in rows] == [
        ("02:00:00", "Mango"), ("03:00:00", "Apple"), ("03:00:00", "Zebra"),
    ]


# ------------------------------------------------------------------ 입출력

def test_수집본을_시간_순으로_읽는다(tmp_path):
    for day, hour, title in (("01", "02", "First"), ("01", "03", "Second"),
                             ("02", "00", "Third")):
        directory = tmp_path / "enwiki" / "2026" / "09" / day
        directory.mkdir(parents=True, exist_ok=True)
        with gzip.open(directory / f"{hour}.ndjson.gz", "wt", encoding="utf-8") as fh:
            fh.write(json.dumps(_rc(title=title)) + "\n")

    titles = [rec["title"] for rec in read_raw(tmp_path / "enwiki")]

    assert titles == ["First", "Second", "Third"]


def test_옛_shard_를_남기지_않는다(tmp_path):
    """행이 줄면 옛 part 가 남아 산출물이 실제보다 커 보인다."""
    out = tmp_path / "enwiki"
    write_rows([{"title": f"T{i}"} for i in range(5)], out, shard_records=1)
    assert len(list(out.glob("part-*.jsonl.gz"))) == 5

    write_rows([{"title": "T0"}], out, shard_records=1)

    assert [p.name for p in sorted(out.glob("part-*.jsonl.gz"))] == ["part-00000.jsonl.gz"]
