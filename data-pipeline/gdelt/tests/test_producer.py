"""producer 테스트. 네트워크·HDFS·실시간 없이, 주입한 가짜로 돈다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests

from gdelt import catalog, fetch, gaps
from gdelt.config import Config
from gdelt.producer import Producer, store_file


def _cfg(tmp_path, **over):
    base = dict(
        lastupdate_url="http://gdelt/lastupdate.txt",
        masterlist_url="http://gdelt/masterfilelist.txt",
        file_base_url="http://gdelt/gdeltv2",
        user_agent="test",
        request_timeout=5.0,
        sink_kind="local",
        local_dir=str(tmp_path / "data"),
        webhdfs_url="http://hdfs-namenode:9870",
        webhdfs_user="hadoop",
        hdfs_base_path="/gdelt/gkg",
        gaps_path=str(tmp_path / "gaps.json"),
        poll_seconds=900,
        selfheal_hours=0,
    )
    base.update(over)
    return Config(**base)


class FakeSink:
    def __init__(self, existing=()):
        self.store = {rel: b"" for rel in existing}

    def exists(self, rel):
        return rel in self.store

    def write(self, rel, data):
        self.store[rel] = data


class FakeResp:
    def __init__(self, text="", lines=None):
        self.text = text
        self._lines = lines or []

    def raise_for_status(self):
        pass

    def iter_lines(self, decode_unicode=False):
        yield from self._lines


class FakeSession:
    def __init__(self, text_by_url=None, lines_by_url=None):
        self.text_by_url = text_by_url or {}
        self.lines_by_url = lines_by_url or {}

    def get(self, url, **kwargs):
        if kwargs.get("stream"):
            return FakeResp(lines=self.lines_by_url.get(url, []))
        return FakeResp(text=self.text_by_url.get(url, ""))


def _download_from(available):
    """available: {timestamp: bytes}. 없는 ts 는 404."""

    def _dl(gkg):
        if gkg.timestamp in available:
            return available[gkg.timestamp]
        raise fetch.GdeltNotFound(gkg.url)

    return _dl


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


LU = (
    "1 a http://gdelt/gdeltv2/20260909041500.export.CSV.zip\n"
    "1 b http://gdelt/gdeltv2/20260909041500.gkg.csv.zip\n"
)


# --- store_file ---

def test_store_file_세_상태():
    sink = FakeSink()
    gkg = catalog.GkgFile(timestamp="20260909041500", url="http://x/20260909041500.gkg.csv.zip")

    assert store_file(gkg, sink=sink, download=_download_from({gkg.timestamp: b"PK"})) == "written"
    assert store_file(gkg, sink=sink, download=_download_from({})) == "skipped"  # 이제 존재

    gkg2 = catalog.GkgFile(timestamp="20260909043000", url="http://x/20260909043000.gkg.csv.zip")
    assert store_file(gkg2, sink=sink, download=_download_from({})) == "gap"  # 404


# --- poll_once ---

def test_poll_once_최신을_받는다(tmp_path):
    cfg = _cfg(tmp_path, selfheal_hours=0)
    sink = FakeSink()
    prod = Producer(
        cfg,
        sink=sink,
        session=FakeSession(text_by_url={cfg.lastupdate_url: LU}),
        download=_download_from({"20260909041500": b"PKdata"}),
    )
    status = prod.poll_once(now=_utc(2026, 9, 9, 4, 15))
    assert status == "written"
    assert sink.exists("2026/09/09/20260909041500.gkg.csv.zip")


def test_poll_once_최신_404는_즉시_결손기록_안함(tmp_path):
    # 방금 발행된 파일이 CDN 지연으로 잠깐 404 일 수 있다. poll 은 즉시 기록하지 않고
    # self_heal 의 확인 유예에 맡긴다(최근 슬롯이라 여기서도 기록 안 됨).
    cfg = _cfg(tmp_path, selfheal_hours=0)
    prod = Producer(
        cfg,
        sink=FakeSink(),
        session=FakeSession(text_by_url={cfg.lastupdate_url: LU}),
        download=_download_from({}),  # 최신도 404
    )
    status = prod.poll_once(now=_utc(2026, 9, 9, 4, 15))
    assert status == "gap"
    assert gaps.load(cfg.gaps_path) == []  # 결손 기록 안 됨


# --- self_heal ---

def test_self_heal_옛_404만_결손_확정(tmp_path):
    # now 로부터 4시간 창. 마진(2h)보다 옛 슬롯의 404 만 기록된다.
    cfg = _cfg(tmp_path, selfheal_hours=4)
    prod = Producer(
        cfg,
        sink=FakeSink(),
        session=FakeSession(),
        download=_download_from({}),  # 전부 404
    )
    prod.self_heal(now=_utc(2025, 6, 14, 12, 0))

    recorded = gaps.load(cfg.gaps_path)
    assert recorded, "옛 구간 결손이 기록돼야 한다"
    # 마진 안(10:00 이후)은 기록 안 됨 — 확정된 마지막 슬롯은 09:45
    assert all(g["reason"] == "404" for g in recorded)
    ends = [g["to"] for g in recorded]
    assert max(ends) == "20250614094500"


def test_self_heal_최근_404는_기록안함(tmp_path):
    cfg = _cfg(tmp_path, selfheal_hours=1)  # 1시간 < 마진 2시간
    prod = Producer(cfg, sink=FakeSink(), session=FakeSession(), download=_download_from({}))
    prod.self_heal(now=_utc(2026, 9, 9, 4, 15))
    assert gaps.load(cfg.gaps_path) == []


def test_self_heal_있는건_건너뛰고_없는것만_채움(tmp_path):
    cfg = _cfg(tmp_path, selfheal_hours=1)
    # 04:00 은 이미 있음, 나머지는 받을 수 있음
    sink = FakeSink(existing=["2026/09/09/20260909040000.gkg.csv.zip"])
    avail = {ts: b"PK" for ts in ["20260909031500", "20260909033000", "20260909034500", "20260909041500"]}
    prod = Producer(cfg, sink=sink, session=FakeSession(), download=_download_from(avail))
    prod.self_heal(now=_utc(2026, 9, 9, 4, 15))
    # 04:00 은 그대로, 04:15 은 새로 채워짐
    assert sink.store["2026/09/09/20260909040000.gkg.csv.zip"] == b""  # 안 덮음
    assert sink.exists("2026/09/09/20260909041500.gkg.csv.zip")


# --- backfill ---

def test_backfill_목록에_없는_슬롯은_결손_missing(tmp_path):
    cfg = _cfg(tmp_path)
    master = [
        "1 a http://gdelt/gdeltv2/20241010000000.export.CSV.zip",
        "1 b http://gdelt/gdeltv2/20241010000000.gkg.csv.zip",
        "1 c http://gdelt/gdeltv2/20241010001500.gkg.csv.zip",
        # 20241010003000 (T3) 은 목록에 없음 -> missing
    ]
    prod = Producer(
        cfg,
        sink=FakeSink(),
        session=FakeSession(lines_by_url={cfg.masterlist_url: master}),
        download=_download_from({"20241010000000": b"PK", "20241010001500": b"PK"}),
    )
    result = prod.backfill(_utc(2024, 10, 10, 0, 0), _utc(2024, 10, 10, 0, 30))

    assert result == {"written": 2, "skipped": 0, "gap": 0, "missing": 1}
    recorded = gaps.load(cfg.gaps_path)
    assert recorded == [
        {
            "from": "20241010003000",
            "to": "20241010003000",
            "reason": "missing",
            "recorded_at": recorded[0]["recorded_at"],
        }
    ]
