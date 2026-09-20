"""mediawiki_history → 날짜별 편집 수 인덱스 (WP-145).

덤프 행은 78컬럼이라 전부 적지 않고 `COLUMN_INDEX` 로 필요한 자리만 채운다 —
컬럼이 하나 늘어도 이 테스트가 깨지지 않게 하려는 것이다(`test_page_creation.py` 와
같은 이유). 네트워크·실덤프 없이 돈다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date

import pytest

from batch.ingest import Counts
from batch.page_edit_daily import (
    edit_counts_for,
    edit_entry,
    read_index,
    scan,
    write_index,
)
from batch.schema import COLUMNS, COLUMN_INDEX
from producer.normalize import SkipEvent


def _row(**values) -> list[str]:
    row = [""] * len(COLUMNS)
    row[COLUMN_INDEX["page_namespace_historical"]] = "0"
    row[COLUMN_INDEX["event_entity"]] = values.pop("event_entity", "revision")
    row[COLUMN_INDEX["event_timestamp"]] = values.pop(
        "event_timestamp", "2026-03-08 12:00:00.0")
    for name, value in values.items():
        row[COLUMN_INDEX[name]] = value
    return row


def _line(**values) -> str:
    return "\t".join(_row(**values)) + "\n"


def _dump(tmp_path, lines, name="dump") -> "object":
    import bz2
    path = tmp_path / f"{name}.tsv.bz2"
    with bz2.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(lines)
    return path


# --- 추출 -------------------------------------------------------------------

def test_제목과_편집_날짜를_뽑는다():
    row = _row(page_title_historical="Mojtaba_Khamenei",
               event_timestamp="2026-03-08 14:55:15.0")
    title, day = edit_entry(row)
    # 덤프는 밑줄형, Clickstream·page_creation 인덱스는 공백형이다 (WP-79).
    assert title == "Mojtaba Khamenei"
    assert day == date(2026, 3, 8)


def test_revision_이_아닌_행은_건너뛴다():
    """🔴 page·user 행까지 세면 편집 수가 부풀려진다 — 덤프의 61% 가 그것이다."""
    for entity in ("page", "user"):
        row = _row(page_title_historical="Mojtaba_Khamenei", event_entity=entity)
        with pytest.raises(SkipEvent):
            edit_entry(row)


def test_ns0_이_아니면_건너뛴다():
    row = _row(page_title_historical="Talk")
    row[COLUMN_INDEX["page_namespace_historical"]] = "1"
    with pytest.raises(SkipEvent):
        edit_entry(row)


def test_깨진_타임스탬프는_지어내지_않고_버린다():
    row = _row(page_title_historical="Mojtaba_Khamenei", event_timestamp="어제")
    with pytest.raises(SkipEvent):
        edit_entry(row)


# --- 집계 -------------------------------------------------------------------

def test_봇_편집을_거른다면_신호가_사라진다(tmp_path):
    """🔴 이 모듈만 봇을 **포함**한다 (WP-77 POC).

    `user` 단독으로 재면 Mojtaba_Khamenei 가 1,053건에서 5건까지 떨어진다.
    다른 모듈(normalize_dump·historical_windows)과 규칙이 다른 것이 정상이다.
    """
    lines = [
        _line(page_title_historical="Mojtaba_Khamenei",
              event_timestamp="2026-03-08 01:00:00.0",
              event_user_is_bot_by_historical="true"),
        _line(page_title_historical="Mojtaba_Khamenei",
              event_timestamp="2026-03-08 02:00:00.0",
              event_user_is_bot_by_historical=""),
    ]
    index: dict = {}
    scan(_dump(tmp_path, lines), index, Counts())

    assert index["Mojtaba Khamenei"][date(2026, 3, 8)] == 2, "봇 편집도 센다"


def test_같은_날_편집을_합치고_날짜별로_나눈다(tmp_path):
    lines = [
        _line(page_title_historical="Ali_Khamenei", event_timestamp="2026-03-08 01:00:00.0"),
        _line(page_title_historical="Ali_Khamenei", event_timestamp="2026-03-08 23:59:59.0"),
        _line(page_title_historical="Ali_Khamenei", event_timestamp="2026-03-09 00:00:00.0"),
    ]
    index: dict = {}
    scan(_dump(tmp_path, lines), index, Counts())

    assert index["Ali Khamenei"] == {date(2026, 3, 8): 2, date(2026, 3, 9): 1}


def test_여러_덤프를_누적한다(tmp_path):
    """월 경계에서 같은 제목이 다시 나와도 합쳐져야 한다."""
    index: dict = {}
    counts = Counts()
    scan(_dump(tmp_path, [
        _line(page_title_historical="Ali_Khamenei", event_timestamp="2026-02-28 01:00:00.0"),
    ], name="feb"), index, counts)
    scan(_dump(tmp_path, [
        _line(page_title_historical="Ali_Khamenei", event_timestamp="2026-03-01 01:00:00.0"),
    ], name="mar"), index, counts)

    assert index["Ali Khamenei"] == {date(2026, 2, 28): 1, date(2026, 3, 1): 1}


# --- 적재본 왕복 -------------------------------------------------------------

def _written(tmp_path, index) -> "object":
    out = tmp_path / "idx"
    write_index(index, out, shard_records=1000)
    return out


def test_적재본을_그대로_되읽는다(tmp_path):
    index = {"Ali Khamenei": {date(2026, 3, 8): 2, date(2026, 3, 9): 1}}
    assert dict(read_index(_written(tmp_path, index))) == index


def test_같은_입력은_같은_바이트를_낸다(tmp_path):
    """정렬해 쓰므로 재실행 비교가 된다 (ShardWriter 가 gzip mtime 을 고정한 이유)."""
    index = {"B": {date(2026, 3, 9): 1}, "A": {date(2026, 3, 8): 2}}
    first = (_written(tmp_path / "1", index) / "part-00000.jsonl.gz").read_bytes()
    second = (_written(tmp_path / "2", index) / "part-00000.jsonl.gz").read_bytes()
    assert first == second


def test_날짜가_정렬되어_적재된다(tmp_path):
    index = {"A": {date(2026, 3, 9): 1, date(2026, 3, 8): 2}}
    shard = _written(tmp_path, index) / "part-00000.jsonl.gz"
    with gzip.open(shard, "rt", encoding="utf-8") as handle:
        rec = json.loads(handle.readline())
    assert list(rec["days"]) == ["2026-03-08", "2026-03-09"]


# --- 구간 조회 ---------------------------------------------------------------

def test_구간은_시작_포함_끝_제외다(tmp_path):
    """맞물린 두 구간을 부를 때 경계 하루가 양쪽에 들어가면 비율이 조용히 틀어진다."""
    out = _written(tmp_path, {"A": {
        date(2026, 2, 28): 5, date(2026, 3, 1): 7, date(2026, 3, 2): 11,
    }})
    assert edit_counts_for(out, ["A"], date(2026, 3, 1), date(2026, 3, 2)) == {"A": 7}
    assert edit_counts_for(out, ["A"], date(2026, 2, 28), date(2026, 3, 1)) == {"A": 5}


def test_없는_제목은_키를_만들지_않는다(tmp_path):
    """⚠️ '미상' 과 '구간 편집 0건' 은 다른 사실이다 — 0 으로 뭉개면 인덱스 구멍이
    기준선 0 이 되어 비율이 무한대가 되고 재급증으로 위장된다."""
    out = _written(tmp_path, {"A": {date(2026, 3, 8): 2}})
    got = edit_counts_for(out, ["A", "없는문서"], date(2026, 3, 1), date(2026, 4, 1))

    assert "없는문서" not in got
    assert got == {"A": 2}


def test_인덱스에_있지만_구간에_편집이_없으면_0이다(tmp_path):
    out = _written(tmp_path, {"A": {date(2026, 3, 8): 2}})
    got = edit_counts_for(out, ["A"], date(2026, 1, 1), date(2026, 2, 1))

    assert got == {"A": 0}, "미상이 아니라 '세어 보니 0건' 이다"


def test_뒤집힌_구간은_거부한다(tmp_path):
    out = _written(tmp_path, {"A": {date(2026, 3, 8): 2}})
    with pytest.raises(ValueError):
        edit_counts_for(out, ["A"], date(2026, 4, 1), date(2026, 3, 1))
