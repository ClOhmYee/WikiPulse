"""GDELT GKG 15분 폴링 -> HDFS 적재 Producer (WP-32).

    python -m gdelt.producer                       # poll (기본): 15분마다 최신 + 자가치유
    python -m gdelt.producer backfill --from 20241010000000 --to 20241010234500

하는 일 (이슈 요구사항)
    1. lastupdate.txt 를 15분마다 읽어 최신 gkg.csv.zip 을 받아 싱크(HDFS)에 저장
    2. 놓친 구간은 masterfilelist.txt 로 백필
    3. GDELT 에 없는 구간(404·미등록)은 결손으로 기록

싱크가 "이미 받은 파일"의 정본이라(sink.exists) 매번 목록을 통째로 안 봐도 되고,
재시작·장애 후에도 빠진 것만 다시 채운다. 근거: docs/requirements-v0.1.md §3.1·§5.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from types import FrameType

import requests

from . import catalog, fetch, gaps
from .config import Config
from .sink import LocalSink, Sink, WebHdfsSink

log = logging.getLogger("gdelt.producer")

# 자가치유에서 404 를 "확실한 결손"으로 굳히기 전에 두는 안전 여유.
# 최신 슬롯은 GDELT 발행이 몇 분 늦으므로, 이보다 최근의 404 는 결손으로 확정하지
# 않고 다음 틱에 다시 시도한다. 옛 구간(2025-06 결손 등)만 기록으로 남는다.
GAP_CONFIRM_MARGIN = timedelta(hours=2)

Downloader = Callable[[catalog.GkgFile], bytes]


def make_downloader(session: requests.Session, cfg: Config) -> Downloader:
    def _download(gkg: catalog.GkgFile) -> bytes:
        return fetch.download(
            gkg.url,
            expected_size=gkg.size,
            expected_md5=gkg.md5,
            session=session,
            user_agent=cfg.user_agent,
            timeout=cfg.request_timeout,
        )

    return _download


def build_sink(cfg: Config) -> Sink:
    if cfg.sink_kind == "webhdfs":
        return WebHdfsSink(
            cfg.webhdfs_url,
            cfg.hdfs_base_path,
            user=cfg.webhdfs_user,
            timeout=cfg.request_timeout,
        )
    return LocalSink(cfg.local_dir)


def store_file(gkg: catalog.GkgFile, *, sink: Sink, download: Downloader) -> str:
    """파일 하나를 받아 싱크에 넣는다.

    Returns: "skipped"(이미 있음) | "written"(새로 받음) | "gap"(404).
    """
    if sink.exists(gkg.relpath):
        return "skipped"
    try:
        data = download(gkg)
    except fetch.GdeltNotFound:
        return "gap"
    sink.write(gkg.relpath, data)
    return "written"


class Producer:
    def __init__(
        self,
        cfg: Config,
        *,
        sink: Sink | None = None,
        session: requests.Session | None = None,
        download: Downloader | None = None,
    ) -> None:
        self.cfg = cfg
        self.session = session or requests.Session()
        self.sink = sink if sink is not None else build_sink(cfg)
        self.download = download or make_downloader(self.session, cfg)

    # --- HTTP 텍스트/스트림 ---

    def _get_text(self, url: str) -> str:
        resp = self.session.get(
            url, headers={"User-Agent": self.cfg.user_agent}, timeout=self.cfg.request_timeout
        )
        resp.raise_for_status()
        return resp.text

    def _iter_lines(self, url: str) -> Iterator[str]:
        resp = self.session.get(
            url,
            headers={"User-Agent": self.cfg.user_agent},
            timeout=self.cfg.request_timeout,
            stream=True,
        )
        resp.raise_for_status()
        yield from resp.iter_lines(decode_unicode=True)

    # --- 동작 ---

    def poll_once(self, *, now: datetime | None = None) -> str:
        """최신 파일 하나를 받고, 이어서 최근 구간을 자가치유한다."""
        now = now or datetime.now(timezone.utc)
        gkg = catalog.parse_lastupdate(self._get_text(self.cfg.lastupdate_url))
        status = store_file(gkg, sink=self.sink, download=self.download)
        log.info("최신 %s -> %s", gkg.timestamp, status)
        if status == "gap":
            # 최신이 404 인 건 이례적이지만, 오면 기록한다.
            gaps.record(
                self.cfg.gaps_path, [catalog.Gap(gkg.timestamp, gkg.timestamp)], reason="404"
            )
        self.self_heal(now=now)
        return status

    def self_heal(self, *, now: datetime) -> None:
        """최근 selfheal_hours 구간에서 싱크에 없는 슬롯을 채운다.

        타임스탬프로 URL 을 직접 만든다(목록 조회 없이). size·md5 를 모르므로
        무결성은 zip 매직으로만 본다. 안전 여유(GAP_CONFIRM_MARGIN)보다 옛 슬롯의
        404 만 확정 결손으로 기록한다 — 최신은 발행 지연일 수 있다.
        """
        start = now - timedelta(hours=self.cfg.selfheal_hours)
        confirm_before = now - GAP_CONFIRM_MARGIN
        healed = 0
        confirmed_missing: list[str] = []

        for ts in catalog.iter_slots(start, now):
            gkg = catalog.GkgFile(
                timestamp=ts, url=f"{self.cfg.file_base_url}/{ts}.gkg.csv.zip"
            )
            if self.sink.exists(gkg.relpath):
                continue
            status = store_file(gkg, sink=self.sink, download=self.download)
            if status == "written":
                healed += 1
            elif status == "gap" and catalog.parse_ts(ts) < confirm_before:
                confirmed_missing.append(ts)

        if healed:
            log.info("자가치유: %d개 채움", healed)
        if confirmed_missing:
            added = gaps.record(
                self.cfg.gaps_path, catalog.coalesce_gaps(confirmed_missing), reason="404"
            )
            log.warning("결손 확정 %d구간 기록", added)

    def backfill(self, from_dt: datetime, to_dt: datetime) -> dict[str, int]:
        """masterfilelist 로 [from, to] 구간을 채운다. 목록에 없는 슬롯은 결손 기록."""
        start = catalog.floor_to_slot(from_dt)
        end = catalog.floor_to_slot(to_dt)
        want = set(catalog.iter_slots(start, end))
        present: set[str] = set()
        counts = {"written": 0, "skipped": 0, "gap": 0}

        for gkg in catalog.parse_masterlist(self._iter_lines(self.cfg.masterlist_url)):
            slot = catalog.parse_ts(gkg.timestamp)
            if not (start <= slot <= end):
                continue
            present.add(gkg.timestamp)
            status = store_file(gkg, sink=self.sink, download=self.download)
            counts[status] += 1
            if status == "gap":
                gaps.record(
                    self.cfg.gaps_path,
                    [catalog.Gap(gkg.timestamp, gkg.timestamp)],
                    reason="404",
                )

        missing = want - present
        if missing:
            added = gaps.record(
                self.cfg.gaps_path, catalog.coalesce_gaps(missing), reason="missing"
            )
            log.warning("목록에 없는 슬롯 %d개 -> 결손 %d구간 기록", len(missing), added)

        log.info(
            "백필 완료 [%s~%s]: 새로 %d · 이미있음 %d · 404 %d · 미등록슬롯 %d",
            start.strftime(catalog.TS_FORMAT),
            end.strftime(catalog.TS_FORMAT),
            counts["written"],
            counts["skipped"],
            counts["gap"],
            len(missing),
        )
        return {**counts, "missing": len(missing)}

    def run_poll(self) -> int:
        """15분 폴링 루프. SIGINT/SIGTERM 으로 깔끔히 멈춘다."""
        stopping = False

        def _handle(signum: int, _frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True
            log.info("신호 %d 수신 — 다음 사이클 전에 멈춘다", signum)

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        target = self.cfg.webhdfs_url if self.cfg.sink_kind == "webhdfs" else self.cfg.local_dir
        log.info(
            "폴링 시작: %s -> %s (%s), 주기 %d초",
            self.cfg.lastupdate_url,
            target,
            self.cfg.sink_kind,
            self.cfg.poll_seconds,
        )

        while not stopping:
            try:
                self.poll_once()
            except Exception as exc:  # 한 사이클 실패로 죽지 않는다. 다음 틱에 재시도.
                log.error("폴링 사이클 실패: %s", exc)
            # 잘게 쪼개 자는 동안에도 신호에 반응한다.
            for _ in range(self.cfg.poll_seconds):
                if stopping:
                    break
                time.sleep(1)

        log.info("폴링 종료")
        return 0


# --- CLI ---

def _parse_arg_ts(value: str) -> datetime:
    """--from/--to 값 파싱: YYYYMMDDHHMMSS 또는 YYYYMMDD."""
    value = value.strip()
    if len(value) == 8:
        value += "000000"
    if len(value) != 14 or not value.isdigit():
        raise argparse.ArgumentTypeError(
            f"타임스탬프는 YYYYMMDD 또는 YYYYMMDDHHMMSS 여야 한다: {value!r}"
        )
    return catalog.parse_ts(value)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="GDELT GKG -> HDFS Producer")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("poll", help="15분 폴링 (기본)")
    bf = sub.add_parser("backfill", help="masterfilelist 로 과거 구간 채우기")
    bf.add_argument("--from", dest="from_ts", required=True, type=_parse_arg_ts)
    bf.add_argument("--to", dest="to_ts", required=True, type=_parse_arg_ts)

    args = parser.parse_args(argv)
    cfg = Config.from_env()
    producer = Producer(cfg)

    if args.command == "backfill":
        producer.backfill(args.from_ts, args.to_ts)
        return 0
    return producer.run_poll()


if __name__ == "__main__":
    sys.exit(main())
