"""시간별 조회수 적재 CLI 검증 (WP-127). 네트워크 없이 돈다 — download 는 대역이다."""

from __future__ import annotations

import gzip
import json
import os
import urllib.error
from pathlib import Path

import pytest

from batch import pageview_hourly_ingest as ingest
from batch.ingest import MANIFEST_NAME
from batch.pageview import SchemaMismatch


def write_dump(path: Path, lines: list[str]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def fake_download(dump: Path):
    return lambda url, cache: dump


# ---------------------------------------------------------------- URL·시각

def test_dump_url은_윈도우_끝_이름의_파일을_가리킨다():
    """🔴 08~09시 구간은 `-090000` 파일에 들어 있다 (2026-09-18 실측)."""
    assert ingest.dump_url("2025-06-12T08:00:00") == (
        "https://dumps.wikimedia.org/other/pageviews/"
        "2025/2025-06/pageviews-20250612-090000.gz")


def test_dump_url_날짜가_넘어간다():
    """23시 구간은 **다음 날** `-000000` 파일이다."""
    assert ingest.dump_url("2025-06-12T23:00:00") == (
        "https://dumps.wikimedia.org/other/pageviews/"
        "2025/2025-06/pageviews-20250613-000000.gz")


def test_하루는_24시간이다():
    hours = ingest.hours_of_day("2025-06-12")
    assert len(hours) == 24
    assert hours[0] == "2025-06-12T00:00:00" and hours[-1] == "2025-06-12T23:00:00"


@pytest.mark.parametrize("given", ["2025-06-12T09", "2025-06-12T09:00",
                                   "2025-06-12 09:00:00", "2025-06-12T09:34:12"])
def test_hour_입력_표기를_흡수한다(given):
    assert ingest.normalize_hour(given) == "2025-06-12T09:00:00"


# ---------------------------------------------------------------- 적재

def test_받아서_합산해_샤드와_매니페스트를_쓴다(tmp_path, monkeypatch):
    dump = write_dump(tmp_path / "pageviews-20250612-100000.gz", [
        "en Air_India_Flight_171 268 0",
        "en.m Air_India_Flight_171 732 0",       # 데스크톱+모바일 합산
        "ja Air_India_Flight_171 50 0",          # 다른 위키
        "en Category:Aviation 9 0",              # ns0 아님
    ])
    monkeypatch.setattr(ingest, "download", fake_download(dump))

    status = ingest.ingest_hour("2025-06-12T09:00:00", "enwiki", tmp_path, tmp_path / "out",
                                titles=None, shard_records=1000, dry_run=False)

    assert status == "ok"
    out_dir = tmp_path / "out" / "enwiki" / "2025-06-12" / "09"
    manifest = json.loads((out_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["records"] == 1 and manifest["views_total"] == 1_000
    assert manifest["source"] == "other/pageviews" and manifest["filtered"] is False


def test_이미_적재된_시간은_건너뛴다(tmp_path, monkeypatch):
    out_dir = tmp_path / "out" / "enwiki" / "2025-06-12" / "09"
    out_dir.mkdir(parents=True)
    (out_dir / MANIFEST_NAME).write_text("{}", encoding="utf-8")

    def explode(url, cache):
        raise AssertionError("이미 적재된 시간은 받지 않는다")

    monkeypatch.setattr(ingest, "download", explode)
    assert ingest.ingest_hour("2025-06-12T09:00:00", "enwiki", tmp_path, tmp_path / "out",
                              titles=None, shard_records=1000, dry_run=False) == "skip"


def test_404는_실패가_아니라_대기다(tmp_path, monkeypatch):
    """🔴 아직 안 나온 시간이다 (윈도우 끝 기준 약 2시간 지연, 실측 125~153분).

    결손으로 세면 LIVE 스케줄러가 다시 안 받는다 — 그 시간 조회수가 영영 안 들어온다.
    """
    def raise_404(url, cache):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(ingest, "download", raise_404)
    assert ingest.ingest_hour("2026-09-18T05:00:00", "enwiki", tmp_path, tmp_path / "out",
                              titles=None, shard_records=1000, dry_run=False) == "pending"


def test_파일명_시각이_요청과_다르면_막는다(tmp_path, monkeypatch):
    """🔴 행에 시각 컬럼이 없어서, 엉뚱한 파일을 받으면 조회수가 통째로 다른 시간에 붙는다."""
    dump = write_dump(tmp_path / "pageviews-20250612-120000.gz", ["en Water 5 0"])
    monkeypatch.setattr(ingest, "download", fake_download(dump))

    with pytest.raises(SchemaMismatch, match="파일명 시각"):
        ingest.ingest_hour("2025-06-12T09:00:00", "enwiki", tmp_path, tmp_path / "out",
                           titles=None, shard_records=1000, dry_run=False)


def test_후보_제목으로_거른다(tmp_path, monkeypatch):
    dump = write_dump(tmp_path / "pageviews-20250612-100000.gz", [
        "en Air_India_Flight_171 268 0",
        "en Water 10 0",
    ])
    monkeypatch.setattr(ingest, "download", fake_download(dump))

    ingest.ingest_hour("2025-06-12T09:00:00", "enwiki", tmp_path, tmp_path / "out",
                       titles=frozenset({"Air India Flight 171"}),
                       shard_records=1000, dry_run=False)

    out_dir = tmp_path / "out" / "enwiki" / "2025-06-12" / "09"
    manifest = json.loads((out_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["records"] == 1 and manifest["filtered"] is True


def test_dry_run은_아무것도_안_쓴다(tmp_path, monkeypatch):
    dump = write_dump(tmp_path / "pageviews-20250612-100000.gz", ["en Water 10 0"])
    monkeypatch.setattr(ingest, "download", fake_download(dump))

    assert ingest.ingest_hour("2025-06-12T09:00:00", "enwiki", tmp_path, tmp_path / "out",
                              titles=None, shard_records=1000, dry_run=True) == "ok"
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------- 후보 파일

def test_후보_제목_파일을_읽는다(tmp_path):
    path = tmp_path / "cand.txt"
    path.write_text("Air India Flight 171\n\nHurricane Milton\n", encoding="utf-8")
    assert ingest.load_titles(path) == frozenset({"Air India Flight 171", "Hurricane Milton"})


def test_후보_파일이_비면_막는다(tmp_path):
    """빈 집합으로 돌면 한 건도 안 걸리고 그게 "조회수 0" 으로 읽힌다 — 멈추는 쪽이 맞다."""
    path = tmp_path / "empty.txt"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ingest.load_titles(path)


def test_후보_파일을_안_주면_전부다(tmp_path):
    assert ingest.load_titles(None) is None


# ---------------------------------------------------------------- main 루프

def test_main_하루는_24시간_순회(monkeypatch):
    seen = []

    def fake_hour(ts_hour, *a, **k):
        seen.append(ts_hour)
        return "ok"

    monkeypatch.setattr(ingest, "ingest_hour", fake_hour)
    assert ingest.main(["--date", "2025-06-12", "--dry-run"]) == 0
    assert len(seen) == 24 and seen[0].endswith("T00:00:00")


def test_main_전부_대기면_3(monkeypatch):
    """받은 게 하나도 없으면 실패 코드를 낸다 — 스케줄러가 조용히 성공으로 넘기지 않게."""
    monkeypatch.setattr(ingest, "ingest_hour", lambda *a, **k: "pending")
    assert ingest.main(["--hour", "2026-09-18T05", "--dry-run"]) == 3


def test_main_latest는_과거_시간을_오름차순으로_준다(monkeypatch):
    seen = []
    monkeypatch.setattr(ingest, "ingest_hour",
                        lambda ts, *a, **k: seen.append(ts) or "ok")
    assert ingest.main(["--latest", "3", "--dry-run"]) == 0
    assert len(seen) == 3 and seen == sorted(seen)


# ---------------------------------------------------------------- 캐시 정리

def test_prune_cache_오래된_것만_지운다(tmp_path):
    old = tmp_path / "pageviews-20250601-000000.gz"
    fresh = tmp_path / "pageviews-20250601-010000.gz"
    old.write_bytes(b"old")
    fresh.write_bytes(b"fresh")

    now = 1_000_000.0
    old_mtime = now - 49 * 3600  # 49시간 전 — 보존기한(48시간) 초과
    fresh_mtime = now - 1 * 3600  # 1시간 전 — 보존기한 이내
    os.utime(old, (old_mtime, old_mtime))
    os.utime(fresh, (fresh_mtime, fresh_mtime))

    removed = ingest.prune_cache(tmp_path, max_age_hours=48, now=now)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_prune_cache_partial_다운로드는_안_지운다(tmp_path):
    partial = tmp_path / "pageviews-20250601-000000.gz.part"
    partial.write_bytes(b"in-progress")
    old_mtime = 1_000_000.0 - 49 * 3600
    os.utime(partial, (old_mtime, old_mtime))

    removed = ingest.prune_cache(tmp_path, max_age_hours=48, now=1_000_000.0)

    assert removed == 0
    assert partial.exists()


def test_prune_cache_빈_디렉터리는_0(tmp_path):
    assert ingest.prune_cache(tmp_path) == 0
