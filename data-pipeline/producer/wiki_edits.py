"""EventStreams recentchange -> Kafka `wiki.edits`

    python -m producer.wiki_edits

Kafka 가 필요한 게 처리량 때문은 아니다 (enwiki 초당 2건, 1건 1.5 KB).
    1. EventStreams 는 SSE(HTTP)라 Spark Structured Streaming 이 직접 못 읽는다.
       이 프로듀서가 SSE 를 Kafka 토픽으로 옮겨야 Spark 가 붙는다.
    2. Spark 가 재시작하는 동안 이벤트가 사라지지 않는다. 토픽 보존 기간 안에서는
       오프셋을 되감아 재처리할 수 있다.
    근거: docs/requirements-v0.3.md §3.1
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from types import FrameType

from confluent_kafka import KafkaException, Producer

from .config import Config
from .normalize import SkipEvent, normalize, partition_key

log = logging.getLogger("producer")


class Stats:
    """처리량을 주기적으로 찍는다. 실측값(enwiki 약 2/s)과 맞는지 보려는 것."""

    def __init__(self, interval: int) -> None:
        self.interval = interval
        self.started = time.monotonic()
        self.window_start = self.started
        self.received = 0
        self.produced = 0
        self.skipped = 0
        self.malformed = 0
        self._last_produced = 0

    def maybe_log(self) -> None:
        now = time.monotonic()
        elapsed = now - self.window_start
        if elapsed < self.interval:
            return
        rate = (self.produced - self._last_produced) / elapsed
        log.info(
            "수신 %d · 발행 %d (%.1f/s) · 건너뜀 %d · 파싱실패 %d",
            self.received,
            self.produced,
            rate,
            self.skipped,
            self.malformed,
        )
        self.window_start = now
        self._last_produced = self.produced


def _on_delivery(err: KafkaException | None, msg: object) -> None:
    if err is not None:
        # 여기서 죽이지 않는다. 개별 실패는 로그로 남기고 스트림은 계속 간다.
        log.error("발행 실패: %s", err)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    config = Config.from_env()

    producer = Producer(
        {
            "bootstrap.servers": config.bootstrap_servers,
            # 중복은 Spark 가 meta_id 로 걸러낼 수 있지만 유실은 못 되돌린다.
            # 그래서 at-least-once 쪽으로 맞춘다.
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "lz4",
            "linger.ms": 100,
            "client.id": "wikipulse-producer",
        }
    )

    # 지연 로딩을 피하려고 SSE 는 나중에 import 하지 않는다.
    from .sse import SSEClient

    client = SSEClient(config.stream_url, user_agent=config.user_agent)
    stats = Stats(config.log_every)

    stopping = False

    def _handle_signal(signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        stopping = True
        log.info("신호 %d 수신 — 버퍼를 비우고 종료한다", signum)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    target = ",".join(sorted(config.wikis)) if config.wikis else "전체 위키"
    log.info("대상 %s -> %s (토픽 %s)", target, config.bootstrap_servers, config.topic)

    try:
        for payload in client.events():
            if stopping:
                break

            stats.received += 1
            try:
                raw = json.loads(payload)
                event = normalize(raw, wikis=config.wikis)
            except SkipEvent:
                stats.skipped += 1
                continue
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                # 스키마가 예상과 다르면 조용히 지나가지 않는다. 세어서 드러낸다.
                stats.malformed += 1
                if stats.malformed <= 5:
                    log.warning("이벤트 파싱 실패(%s): %.200s", exc, payload)
                continue

            try:
                producer.produce(
                    config.topic,
                    key=partition_key(event),
                    value=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                    on_delivery=_on_delivery,
                )
            except BufferError:
                # 로컬 큐가 찼다 = 브로커가 못 따라오고 있다. 비우고 다시 시도.
                log.warning("로컬 큐 포화 — 비우는 중")
                producer.flush(10)
                producer.produce(
                    config.topic,
                    key=partition_key(event),
                    value=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                    on_delivery=_on_delivery,
                )

            stats.produced += 1
            producer.poll(0)  # 배달 콜백 처리
            stats.maybe_log()
    finally:
        remaining = producer.flush(30)
        if remaining:
            log.error("발행하지 못한 메시지 %d건", remaining)
        log.info(
            "종료. 수신 %d · 발행 %d · 건너뜀 %d · 파싱실패 %d",
            stats.received,
            stats.produced,
            stats.skipped,
            stats.malformed,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
