"""Clickstream 파싱·필터·이웃 조회 검증 (WP-81). 네트워크 없이 돈다."""

from __future__ import annotations

import gzip
import json

import pytest

from batch.clickstream import (
    ClickstreamRow,
    NeighborRef,
    SchemaMismatch,
    canonical_title,
    neighbors_for,
    parse_row,
    parse_rows,
    read_shards,
)


def tsv(prev, curr, kind, n):
    return f"{prev}\t{curr}\t{kind}\t{n}"


# ---------------------------------------------------------------- 파싱·필터

def test_link_행만_남긴다():
    assert parse_row(tsv("Strait_of_Hormuz", "Iran", "link", "383")) == \
        ClickstreamRow("Strait of Hormuz", "Iran", 383)
    assert parse_row(tsv("other_wiki", "Iran", "external", "999")) is None
    assert parse_row(tsv("Iran", "Iran", "other", "50")) is None


def test_제목_밑줄을_공백으로_정규화():
    assert canonical_title("Strait_of_Hormuz") == "Strait of Hormuz"
    row = parse_row(tsv("2025_Iran_war", "Sinking_of_IRIS_Dena", "link", "100"))
    assert row.prev == "2025 Iran war" and row.curr == "Sinking of IRIS Dena"


def test_컬럼_수가_다르면_SchemaMismatch():
    with pytest.raises(SchemaMismatch):
        parse_row("only\ttwo")
    with pytest.raises(SchemaMismatch):
        parse_row("a\tb\tlink\t10\textra")


def test_n이_정수가_아니면_건너뛴다():
    assert parse_row(tsv("A", "B", "link", "NaN")) is None


def test_parse_rows는_빈줄과_비link를_거른다():
    lines = [
        tsv("A", "B", "link", "10"),
        "",
        tsv("A", "C", "external", "20"),
        tsv("A", "D", "link", "15"),
    ]
    rows = list(parse_rows(lines))
    assert [(r.curr, r.n) for r in rows] == [("B", 10), ("D", 15)]


# ---------------------------------------------------------------- 이웃 조회

def test_나가는_이웃과_들어오는_이웃():
    rows = [
        ClickstreamRow("Strait of Hormuz", "Iran", 383),        # 씨드 -> 나감
        ClickstreamRow("Choke point", "Strait of Hormuz", 120),  # 들어옴
    ]
    result = neighbors_for(rows, {"Strait of Hormuz"})
    refs = {r.title: r for r in result["Strait of Hormuz"]}
    assert refs["Iran"].directed is True and refs["Iran"].n == 383
    assert refs["Choke point"].directed is False and refs["Choke point"].n == 120


def test_양방향은_합치고_더_큰_방향을_남긴다():
    rows = [
        ClickstreamRow("A", "B", 100),   # A->B 나감 100
        ClickstreamRow("B", "A", 30),    # B->A 들어옴 30
    ]
    ref = neighbors_for(rows, {"A"})["A"][0]
    assert ref.title == "B"
    assert ref.n == 130               # 합
    assert ref.directed is True       # 나가는 쪽(100)이 더 큼


def test_자기_자신은_이웃이_아니다():
    rows = [ClickstreamRow("A", "A", 999)]
    assert neighbors_for(rows, {"A"})["A"] == []


def test_이웃은_이동량_내림차순():
    rows = [
        ClickstreamRow("A", "Small", 10),
        ClickstreamRow("A", "Big", 500),
        ClickstreamRow("A", "Mid", 100),
    ]
    titles = [r.title for r in neighbors_for(rows, {"A"})["A"]]
    assert titles == ["Big", "Mid", "Small"]


def test_한_순회로_여러_씨드를_동시에():
    rows = [
        ClickstreamRow("Seed1", "X", 10),
        ClickstreamRow("Seed2", "Y", 20),
        ClickstreamRow("X", "Seed2", 5),
    ]
    result = neighbors_for(rows, {"Seed1", "Seed2"})
    assert {r.title for r in result["Seed1"]} == {"X"}
    assert {r.title for r in result["Seed2"]} == {"Y", "X"}


# ---------------------------------------------------------------- shard 왕복

def test_ingest_convert가_link만_쓰고_나머지는_센다():
    from batch.clickstream_ingest import convert
    from batch.ingest import Counts

    lines = [
        tsv("A", "B", "link", "10"),
        tsv("A", "C", "external", "20"),
        tsv("A", "A", "other", "5"),
        "",                                   # 빈 줄은 read 에도 안 센다
        tsv("A", "D", "link", "15"),
    ]
    written = []

    class FakeWriter:
        def write(self, event):
            written.append(event)

    counts = Counts()
    convert(iter(lines), FakeWriter(), counts)
    assert counts.read == 4                   # 빈 줄 제외
    assert counts.written == 2                # link 2개
    assert counts.skipped.get("type") == 2    # external + other
    assert [e["curr"] for e in written] == ["B", "D"]


def test_적재본_shard를_되읽는다(tmp_path):
    shard = tmp_path / "part-00000.jsonl.gz"
    with gzip.open(shard, "wt", encoding="utf-8") as h:
        h.write(json.dumps({"prev": "A", "curr": "B", "n": 42}) + "\n")
        h.write(json.dumps({"prev": "A", "curr": "C", "n": 7}) + "\n")
    rows = list(read_shards(tmp_path))
    assert rows == [ClickstreamRow("A", "B", 42), ClickstreamRow("A", "C", 7)]
