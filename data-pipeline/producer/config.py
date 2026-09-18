"""환경 변수 설정. 개인 경로·키는 코드에 박지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Config:
    stream_url: str
    user_agent: str
    cursor_file: str | None
    bootstrap_servers: str
    topic: str
    wikis: frozenset[str] | None
    log_every: int

    @classmethod
    def from_env(cls) -> "Config":
        wikis_raw = _env("WIKIS", "enwiki").strip()
        # WIKIS=* 이면 전 위키. 기본은 enwiki 만.
        wikis = None if wikis_raw == "*" else frozenset(
            w.strip() for w in wikis_raw.split(",") if w.strip()
        )

        contact = _env("CONTACT_EMAIL", "").strip()
        if not contact:
            raise SystemExit(
                "CONTACT_EMAIL 이 필요하다. Wikimedia 는 연락처 없는 User-Agent 를 차단한다.\n"
                "  data-pipeline/.env.example 을 .env 로 복사해 채운다."
            )

        cursor_raw = _env("SSE_CURSOR_FILE", "").strip()

        return cls(
            stream_url=_env(
                "STREAM_URL", "https://stream.wikimedia.org/v2/stream/recentchange"
            ),
            user_agent=f"WikiPulse/0.1 (WikiPulse; {contact})",
            cursor_file=cursor_raw or None,
            bootstrap_servers=_env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            topic=_env("KAFKA_TOPIC", "wiki.edits"),
            wikis=wikis,
            log_every=int(_env("LOG_EVERY_SECONDS", "30")),
        )
