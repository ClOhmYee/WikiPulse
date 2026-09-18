"""mediawiki_history → 생성 시각(UTC) 인덱스 (WP-115).

덤프 행은 78컬럼이라 전부 적지 않고 `COLUMN_INDEX` 로 필요한 자리만 채운다 —
컬럼이 하나 늘어도 이 테스트가 깨지지 않게 하려는 것이다(`test_normalize_dump.py` 와
같은 이유). 네트워크·실덤프 없이 돈다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta, timezone

import pytest

UTC = timezone.utc

from batch.page_creation import (
    creation_dates_for,
    creation_entry,
    read_index,
    scan,
    write_index,
)
from batch.ingest import Counts
from batch.schema import COLUMNS, COLUMN_INDEX
from producer.normalize import SkipEvent


def _row(**values) -> list[str]:
    row = [""] * len(COLUMNS)
    row[COLUMN_INDEX["page_namespace_historical"]] = "0"
    # 충돌을 가르는 근거라 기본값을 둔다. 개별 테스트가 덮어쓴다.
    row[COLUMN_INDEX["event_timestamp"]] = values.pop(
        "event_timestamp", "2024-10-01 00:00:00.0")
    for name, value in values.items():
        row[COLUMN_INDEX[name]] = value
    return row


def _line(**values) -> str:
    return "\t".join(_row(**values)) + "\n"


# --- 추출 -------------------------------------------------------------------

def test_제목과_생성_시각을_뽑는다():
    row = _row(page_title_historical="Hurricane_Milton",
               page_creation_timestamp="2024-10-05 14:55:15.0")
    title, created, _event_at = creation_entry(row)
    # 덤프는 밑줄형, wiki_page·Clickstream 은 공백형이다 (WP-79).
    assert title == "Hurricane Milton"
    # 🔴 날짜로 뭉개지 않는다 — 덤프 정밀도를 그대로 남긴다 (-115, 2026-09-18).
    assert created == datetime(2024, 10, 5, 14, 55, 15, tzinfo=UTC)


def test_생성_시각은_timezone_aware_UTC_다():
    """naive 로 두면 소비하는 쪽이 로컬 시간대로 읽어 날짜가 하루 밀린다."""
    row = _row(page_title_historical="Hurricane_Milton",
               page_creation_timestamp="2024-10-05 14:55:15.0")
    _title, created, event_at = creation_entry(row)
    assert created.tzinfo is not None and created.utcoffset().total_seconds() == 0
    assert event_at.tzinfo is not None and event_at.utcoffset().total_seconds() == 0


def test_ns0_이_아니면_건너뛴다():
    row = _row(page_title_historical="Talk", page_creation_timestamp="2024-10-05 00:00:00.0")
    row[COLUMN_INDEX["page_namespace_historical"]] = "1"
    with pytest.raises(SkipEvent):
        creation_entry(row)


def test_현재_namespace_가_아니라_historical_을_본다():
    """삭제된 문서는 현재 값이 비어 ns0 집계가 반토막 난다 (normalize_dump 실측)."""
    row = _row(page_title_historical="Deleted_Thing",
               page_creation_timestamp="2024-09-30 01:02:03.0")
    row[COLUMN_INDEX["page_namespace"]] = ""        # 현재 값은 비어 있다
    assert creation_entry(row)[0] == "Deleted Thing"


def test_생성일이_없으면_건너뛴다():
    with pytest.raises(SkipEvent):
        creation_entry(_row(page_title_historical="No Creation"))


def test_이벤트_시각이_없으면_건너뛴다():
    """충돌을 가를 근거가 없는 행이다. 없는 순서를 지어내지 않는다."""
    with pytest.raises(SkipEvent):
        creation_entry(_row(page_title_historical="No Event",
                            page_creation_timestamp="2024-10-05 00:00:00.0",
                            event_timestamp=""))


def test_깨진_타임스탬프는_지어내지_않고_버린다():
    with pytest.raises(SkipEvent):
        creation_entry(_row(page_title_historical="Broken",
                            page_creation_timestamp="2024-13-99 not a time"))


def test_제목이_없으면_건너뛴다():
    with pytest.raises(SkipEvent):
        creation_entry(_row(page_creation_timestamp="2024-10-05 00:00:00.0"))


# --- 순회 -------------------------------------------------------------------

def _dump(tmp_path, *lines):
    import bz2
    path = tmp_path / "dump.tsv.bz2"
    with bz2.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(lines)
    return path


def test_revision_행에서도_생성일을_얻는다(tmp_path):
    """`page` 행만 보면 그 달에 생긴 문서만 잡힌다. revision 행에 실린 값을 써야
    2005년 문서도 인덱스에 들어온다 — 모듈 docstring 의 ✅ 항목."""
    source = _dump(tmp_path,
                   _line(event_entity="revision", page_title_historical="Old_Article",
                         page_creation_timestamp="2005-07-07 15:31:37.0"))
    index, counts = {}, Counts()
    scan(source, index, counts)
    assert index["Old Article"][0] == datetime(2005, 7, 7, 15, 31, 37, tzinfo=UTC)


def test_제목_충돌은_마지막_주인을_남기고_센다(tmp_path):
    """🔴 이른 값을 고르면 이동해 온 신규 사건 문서가 "옛 문서" 로 보여 창에서 탈락한다.

    실측(2026-09-17): 이른 값 규칙에서 `Hurricane Helene` 이 2006-01-07, `Typhoon Yagi`
    가 2023-06-06 으로 나왔다 — 실제 값은 2024-09-23·2024-09-01 이다.
    """
    source = _dump(tmp_path,
                   _line(page_title_historical="Hurricane_Helene",
                         page_creation_timestamp="2006-01-07 10:18:44.0",
                         event_timestamp="2024-09-10 00:00:00.0"),
                   _line(page_title_historical="Hurricane_Helene",
                         page_creation_timestamp="2024-09-23 15:15:38.0",
                         event_timestamp="2024-09-28 00:00:00.0"))
    index, counts = {}, Counts()
    conflicts = scan(source, index, counts)
    assert index["Hurricane Helene"][0] == datetime(2024, 9, 23, 15, 15, 38, tzinfo=UTC)
    assert conflicts == 1


def test_충돌_판정은_행_순서와_무관하다(tmp_path):
    """덤프를 어느 월부터 훑든 같은 값이 남아야 한다 — event_timestamp 로 비교한다."""
    late = _line(page_title_historical="Reused",
                 page_creation_timestamp="2024-09-23 00:00:00.0",
                 event_timestamp="2024-10-05 00:00:00.0")
    early = _line(page_title_historical="Reused",
                  page_creation_timestamp="2006-01-07 00:00:00.0",
                  event_timestamp="2024-09-01 00:00:00.0")
    for order in ((late, early), (early, late)):
        index, counts = {}, Counts()
        scan(_dump(tmp_path, *order), index, counts)
        assert index["Reused"][0] == datetime(2024, 9, 23, tzinfo=UTC)


def test_같은_값이_반복되면_충돌이_아니다(tmp_path):
    source = _dump(tmp_path,
                   _line(page_title_historical="Same",
                         page_creation_timestamp="2024-09-01 00:00:00.0"),
                   _line(page_title_historical="Same",
                         page_creation_timestamp="2024-09-01 12:00:00.0"))
    index, counts = {}, Counts()
    # 같은 날짜면 충돌이 아니다 — 시각이 달라도 날짜로 내려 비교한다.
    # 저장은 시각까지 하지만(-115) 이 카운터는 "제목 주인이 바뀌었나" 만 센다.
    assert scan(source, index, counts) == 0
    assert counts.written == 1


# --- 적재본 왕복 -------------------------------------------------------------

def test_인덱스를_쓰고_되읽는다(tmp_path):
    index = {"Hurricane Milton": datetime(2024, 10, 5, 14, 55, 15, tzinfo=UTC),
             "Iran": datetime(2001, 10, 1, 3, 4, 5, tzinfo=UTC)}
    write_index(index, tmp_path / "out", shard_records=1)
    assert dict(read_index(tmp_path / "out")) == index


def test_찾는_제목만_돌려준다(tmp_path):
    """인덱스가 수백만 행이라 통째로 올리지 않는다."""
    write_index({"A": datetime(2024, 9, 1, tzinfo=UTC),
                 "B": datetime(2024, 9, 2, tzinfo=UTC),
                 "C": datetime(2024, 9, 3, tzinfo=UTC)},
                tmp_path / "out", shard_records=500)
    assert creation_dates_for(tmp_path / "out", ["A", "C", "Missing"]) == {
        "A": datetime(2024, 9, 1, tzinfo=UTC), "C": datetime(2024, 9, 3, tzinfo=UTC)}


def test_없는_제목은_키_자체가_없다(tmp_path):
    """🔴 None 을 넣으면 "미상" 과 "창 밖" 이 구분되지 않는다 — 모듈 docstring ⚠️."""
    write_index({"A": datetime(2024, 9, 1, tzinfo=UTC)}, tmp_path / "out", shard_records=500)
    found = creation_dates_for(tmp_path / "out", ["A", "Missing"])
    assert "Missing" not in found


# --- 타입 계약 (WP-115, 2026-09-18) ---------------------------------

def test_naive_생성_시각은_적재를_거부한다(tmp_path):
    """🔴 naive 를 UTC 로 "고쳐" 주면 로컬 시각이 UTC 로 둔갑해 조용히 어긋난다."""
    with pytest.raises(ValueError, match="timezone-aware"):
        write_index({"A": datetime(2024, 9, 1)}, tmp_path / "out", shard_records=500)


def test_시간대_없는_옛_적재본은_읽기를_거부한다(tmp_path):
    """자정으로 보정하면 실제보다 이른 시각이 되어 시점 상한을 잘못 통과시킨다.

    ⚠️ 조용히 넘기면 안 되는 자리라 예외로 세운다 — 옛 적재본은 다시 만든다.
    """
    out = tmp_path / "out"
    out.mkdir()
    with gzip.open(out / "part-00000.jsonl.gz", "wt", encoding="utf-8") as handle:
        print(json.dumps({"title": "A", "created": "2024-09-01"}), file=handle)
    with pytest.raises(ValueError, match="옛 적재본"):
        list(read_index(out))


def test_다른_시간대로_줘도_UTC_로_저장된다(tmp_path):
    kst = timezone(timedelta(hours=9))
    # KST 2024-10-06 08:00 = UTC 2024-10-05 23:00
    write_index({"A": datetime(2024, 10, 6, 8, tzinfo=kst)}, tmp_path / "out",
                shard_records=500)
    assert dict(read_index(tmp_path / "out")) == {
        "A": datetime(2024, 10, 5, 23, tzinfo=UTC)}
