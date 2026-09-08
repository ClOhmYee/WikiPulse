"""Server-Sent Events(SSE) 읽기 — 끊기면 Last-Event-ID 로 이어 붙인다.

sseclient 같은 라이브러리를 쓰지 않는 이유
    끊김 처리와 재연결 위치(Last-Event-ID)를 우리가 직접 쥐고 있어야 한다.
    SSE 프레임 파싱 자체는 짧아서 의존성을 늘릴 값어치가 없다.

EventStreams 의 id 필드 (2026-09-08 실측)
    id: [{"topic":"eqiad.mediawiki.recentchange","partition":0,"timestamp":178...},
         {"topic":"codfw.mediawiki.recentchange","partition":0,"offset":-1}]
    이 값을 그대로 Last-Event-ID 헤더에 실으면 그 지점부터 다시 받는다.
    Wikimedia 는 약 7일치를 보관한다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import requests

log = logging.getLogger(__name__)


class SSEClient:
    """끊기면 마지막 이벤트 id 부터 다시 붙는 SSE 리더."""

    def __init__(
        self,
        url: str,
        *,
        user_agent: str,
        timeout: float = 60.0,
        max_backoff: float = 60.0,
    ) -> None:
        self.url = url
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_backoff = max_backoff
        self.last_event_id: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent, "Accept": "text/event-stream"}
        if self.last_event_id:
            headers["Last-Event-ID"] = self.last_event_id
        return headers

    def events(self) -> Iterator[str]:
        """`data:` 본문을 끝없이 내놓는다. 끊기면 알아서 다시 붙는다.

        중단하려면 호출자가 루프를 빠져나가거나 KeyboardInterrupt 를 쓴다.
        """
        backoff = 1.0
        while True:
            try:
                with requests.get(
                    self.url,
                    headers=self._headers(),
                    stream=True,
                    timeout=self.timeout,
                ) as response:
                    response.raise_for_status()
                    resumed = " (이어받기)" if self.last_event_id else ""
                    log.info("EventStreams 연결됨%s", resumed)
                    backoff = 1.0  # 붙었으니 대기 시간 초기화

                    yield from self._parse_frames(response)

                log.warning("스트림이 서버 쪽에서 닫힘. 다시 붙는다.")
            except (requests.RequestException, ConnectionError) as exc:
                log.warning("연결 실패: %s — %.0f초 뒤 재시도", exc, backoff)

            time.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)

    def _parse_frames(self, response: requests.Response) -> Iterator[str]:
        """SSE 프레임을 파싱한다.

        프레임은 빈 줄로 끝난다. 한 프레임 안에서 id: 는 저장하고 data: 만 내놓는다.
        `:ok` 같은 주석 줄은 버린다.
        """
        data_lines: list[str] = []
        pending_id: str | None = None

        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue

            if raw_line == "":  # 프레임 끝
                if data_lines:
                    # id 는 프레임을 다 내보낸 뒤에 갱신한다.
                    # 중간에 죽으면 그 프레임부터 다시 받아야 하므로.
                    payload = "\n".join(data_lines)
                    data_lines = []
                    yield payload
                    if pending_id is not None:
                        self.last_event_id = pending_id
                        pending_id = None
                continue

            if raw_line.startswith(":"):  # 주석 (예: `:ok`)
                continue

            field, _, value = raw_line.partition(":")
            value = value[1:] if value.startswith(" ") else value

            if field == "data":
                data_lines.append(value)
            elif field == "id":
                pending_id = value
            # event: 필드는 recentchange 스트림에서 항상 "message" 라 쓰지 않는다.
