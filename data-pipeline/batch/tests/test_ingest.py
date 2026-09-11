"""적재 CLI 테스트 — 재실행 안전성·이어받기·shard·dry-run.

네트워크 없이 돈다. 덤프를 캐시 경로에 미리 놓아 download() 가 그대로 쓰게 한다
(그래서 CONTACT_EMAIL 없이도 돈다 — 캐시가 있으면 요청을 안 하기 때문이다).

여기서 잡으려는 실패
    - 두 번 돌렸을 때 이벤트가 두 배가 되는 것
    - 중간에 죽었을 때 반쪽 출력이 완료본처럼 남는 것
    - dry-run 이 파일을 만드는 것
"""

from __future__ import annotations

import bz2
import gzip
import json

import pytest

from batch import ingest as ingest_module
from batch.ingest import MANIFEST_NAME, Counts, ShardWriter, dump_url, ingest
from batch.schema import COLUMNS

SNAPSHOT = "2026-08"
WIKI = "aawiki"
TIME_RANGE = "all-time"

BASE = {
    "wiki_db": WIKI,
    "event_entity": "revision",
    "event_timestamp": "2005-07-07 15:31:37.0",
    "event_user_text_historical": "Arde",
    "page_title_historical": "Main_Page",
    "page_namespace_historical": "0",
    "page_first_edit_timestamp": "2005-07-07 15:31:37.0",
    "revision_id": "1269",
    "revision_text_bytes": "8211",
    "revision_text_bytes_diff": "8211",
    "revision_minor_edit": "false",
}


def tsv_line(**overrides) -> str:
    values = {**BASE, **overrides}
    return "\t".join(values.get(name, "") for name in COLUMNS)


def make_dump(cache_dir, lines) -> None:
    """캐시 경로에 덤프를 미리 놓는다 — download() 가 네트워크를 안 탄다."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{SNAPSHOT}.{WIKI}.{TIME_RANGE}.tsv.bz2"
    with bz2.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run(tmp_path, *, lines=None, **kwargs):
    if lines is not None:
        make_dump(tmp_path / "dumps", lines)
    options = dict(
        wiki=WIKI,
        time_range=TIME_RANGE,
        snapshot=SNAPSHOT,
        out=tmp_path / "out",
        cache=tmp_path / "dumps",
        shard_records=1000,
        dry_run=False,
        force=False,
    )
    options.update(kwargs)
    return ingest(**options)


def events_in(directory) -> list[dict]:
    out = []
    for shard in sorted(directory.glob("part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            out += [json.loads(line) for line in handle if line.strip()]
    return out


# --- URL ------------------------------------------------------------------


def test_덤프_URL_규칙():
    """readme.html 의 /{version}/{wiki}/{version}.{wiki}.{range}.tsv.bz2"""
    assert dump_url("2026-08", "enwiki", "2025-06").endswith(
        "/2026-08/enwiki/2026-08.enwiki.2025-06.tsv.bz2"
    )


# --- 적재 기본 ------------------------------------------------------------


def test_적재하면_JSONL_gz_와_매니페스트가_생긴다(tmp_path):
    counts = run(tmp_path, lines=[tsv_line(revision_id=str(i)) for i in range(5)])
    destination = tmp_path / "out" / WIKI / TIME_RANGE

    assert counts.written == 5
    assert (destination / MANIFEST_NAME).exists()

    events = events_in(destination)
    assert len(events) == 5
    assert {e["source"] for e in events} == {"dump"}
    assert {e["meta_id"] for e in events} == {f"dump:{WIKI}:{i}" for i in range(5)}


def test_매니페스트에_근거가_남는다(tmp_path):
    run(tmp_path, lines=[tsv_line()])
    manifest = json.loads(
        (tmp_path / "out" / WIKI / TIME_RANGE / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["issue"] == "WP-56"
    assert manifest["events_written"] == 1
    assert manifest["source_url"].endswith(f"{SNAPSHOT}.{WIKI}.{TIME_RANGE}.tsv.bz2")
    assert manifest["shards"] == ["part-00000.jsonl.gz"]


def test_대상이_아닌_행은_스킵으로_집계된다(tmp_path):
    counts = run(
        tmp_path,
        lines=[
            tsv_line(),
            tsv_line(event_entity="user"),
            tsv_line(page_namespace_historical="2"),
        ],
    )
    assert counts.read == 3
    assert counts.written == 1
    assert counts.skipped == {"event_entity": 1, "namespace": 1}


# --- 재실행 안전성 --------------------------------------------------------


def test_두_번_돌려도_이벤트가_늘지_않는다(tmp_path):
    """같은 명령을 두 번 돌리는 건 흔하다. 두 배가 되면 baseline 이 통째로 틀어진다."""
    lines = [tsv_line(revision_id=str(i)) for i in range(3)]
    first = run(tmp_path, lines=lines)
    second = run(tmp_path)  # 캐시·매니페스트 그대로 재실행

    assert first.written == 3
    assert second is None, "완료된 단위는 건너뛰어야 한다"
    assert len(events_in(tmp_path / "out" / WIKI / TIME_RANGE)) == 3


def test_force_는_다시_적재하되_중복을_남기지_않는다(tmp_path):
    lines = [tsv_line(revision_id=str(i)) for i in range(3)]
    run(tmp_path, lines=lines)
    again = run(tmp_path, force=True)

    assert again.written == 3
    assert len(events_in(tmp_path / "out" / WIKI / TIME_RANGE)) == 3


def test_반쪽_출력이_완료본으로_보이지_않는다(tmp_path):
    """정규화 도중 죽으면 .partial 만 남고 매니페스트는 없어야 한다."""
    make_dump(tmp_path / "dumps", [tsv_line(revision_id=str(i)) for i in range(3)])
    destination = tmp_path / "out" / WIKI / TIME_RANGE
    boom = RuntimeError("중단")

    def explode(*args, **kwargs):
        raise boom

    original = ingest_module.convert
    ingest_module.convert = explode
    try:
        with pytest.raises(RuntimeError):
            run(tmp_path)
    finally:
        ingest_module.convert = original

    assert not (destination / MANIFEST_NAME).exists()
    assert not list(destination.glob("part-*.jsonl.gz"))

    # 다시 돌리면 정상 완료된다 (남은 .partial 이 방해하지 않는다).
    assert run(tmp_path).written == 3
    assert len(events_in(destination)) == 3


def test_캐시된_덤프는_다시_받지_않는다(tmp_path):
    """download() 가 네트워크를 타면 이 테스트가 실패한다 (CONTACT_EMAIL 미설정)."""
    monkey = tmp_path / "dumps"
    make_dump(monkey, [tsv_line()])
    assert run(tmp_path, force=True).written == 1


# --- shard ----------------------------------------------------------------


def test_shard_크기를_넘으면_파일이_나뉜다(tmp_path):
    """한 달치를 gzip 하나로 만들면 Spark 가 분할해 읽지 못한다."""
    counts = run(
        tmp_path,
        lines=[tsv_line(revision_id=str(i)) for i in range(10)],
        shard_records=4,
    )
    destination = tmp_path / "out" / WIKI / TIME_RANGE
    shards = sorted(p.name for p in destination.glob("part-*.jsonl.gz"))

    assert counts.written == 10
    assert shards == ["part-00000.jsonl.gz", "part-00001.jsonl.gz", "part-00002.jsonl.gz"]
    assert len(events_in(destination)) == 10


def test_shard_는_이벤트를_잃지_않는다(tmp_path):
    run(tmp_path, lines=[tsv_line(revision_id=str(i)) for i in range(7)], shard_records=2)
    ids = [e["rev_id"] for e in events_in(tmp_path / "out" / WIKI / TIME_RANGE)]
    assert sorted(ids) == list(range(7))


def test_빈_입력은_shard_를_만들지_않는다(tmp_path):
    counts = run(tmp_path, lines=[tsv_line(event_entity="user")])
    assert counts.written == 0
    manifest = json.loads(
        (tmp_path / "out" / WIKI / TIME_RANGE / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["shards"] == []


def test_ShardWriter_는_같은_입력에_같은_바이트를_낸다(tmp_path):
    """gzip mtime 을 0 으로 고정했다. 재실행 결과를 바이트로 비교할 수 있어야 한다."""
    payload = {"wiki": "aawiki", "rev_id": 1}
    outputs = []
    for name in ("a", "b"):
        directory = tmp_path / name
        with ShardWriter(directory, 10) as writer:
            writer.write(payload)
        outputs.append((directory / "part-00000.jsonl.gz").read_bytes())
    assert outputs[0] == outputs[1]


# --- dry-run --------------------------------------------------------------


def test_dry_run_은_세기만_하고_아무것도_안_쓴다(tmp_path):
    counts = run(
        tmp_path,
        lines=[tsv_line(revision_id=str(i)) for i in range(4)],
        dry_run=True,
    )
    assert counts.written == 4
    assert not (tmp_path / "out").exists()


def test_dry_run_뒤에도_정상_적재가_된다(tmp_path):
    lines = [tsv_line(revision_id=str(i)) for i in range(4)]
    run(tmp_path, lines=lines, dry_run=True)
    assert run(tmp_path).written == 4


# --- 집계 -----------------------------------------------------------------


def test_스킵_사유는_앞부분으로_묶인다():
    counts = Counts()
    counts.skip("namespace=2")
    counts.skip("namespace=14")
    counts.skip("event_entity=user")
    assert counts.skipped == {"namespace": 2, "event_entity": 1}
