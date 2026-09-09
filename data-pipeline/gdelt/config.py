"""환경 변수 설정. 개인 경로·키는 코드에 박지 않는다.

producer/config.py 와 같은 방식(dataclass + from_env)이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# GDELT URL 은 http 로 공개되지만 https 로 301 리다이렉트된다(2026-09-09 실측).
# 기본값을 https 로 둬 왕복을 한 번 아낀다. requests 는 리다이렉트를 따라가므로
# http 로 줘도 동작은 한다.
_GDELT_BASE = "https://data.gdeltproject.org/gdeltv2"


@dataclass(frozen=True)
class Config:
    # 소스
    lastupdate_url: str
    masterlist_url: str
    file_base_url: str  # 타임스탬프로 직접 URL 을 만들 때(자가치유)
    user_agent: str
    request_timeout: float

    # 싱크
    sink_kind: str  # "local" | "webhdfs"
    local_dir: str
    webhdfs_url: str
    webhdfs_user: str
    hdfs_base_path: str

    # 운영
    gaps_path: str
    poll_seconds: int
    selfheal_hours: int

    @classmethod
    def from_env(cls) -> "Config":
        sink_kind = _env("GDELT_SINK", "local").strip().lower()
        if sink_kind not in ("local", "webhdfs"):
            raise SystemExit(
                f"GDELT_SINK 는 local 또는 webhdfs 여야 한다 (받은 값: {sink_kind!r}).\n"
                "  data-pipeline/.env.example 참고."
            )

        # GDELT 는 연락처를 강제하지 않지만(위키와 다름) 예의상 붙인다.
        contact = _env("CONTACT_EMAIL", "").strip()
        ua = f"WikiPulse/0.1 (WikiPulse; {contact})" if contact else "WikiPulse/0.1 (WikiPulse)"

        return cls(
            lastupdate_url=_env("GDELT_LASTUPDATE_URL", f"{_GDELT_BASE}/lastupdate.txt"),
            masterlist_url=_env("GDELT_MASTERLIST_URL", f"{_GDELT_BASE}/masterfilelist.txt"),
            file_base_url=_env("GDELT_FILE_BASE_URL", _GDELT_BASE).rstrip("/"),
            user_agent=ua,
            request_timeout=float(_env("GDELT_REQUEST_TIMEOUT", "120")),
            sink_kind=sink_kind,
            local_dir=_env("GDELT_LOCAL_DIR", "gdelt-data"),
            webhdfs_url=_env("WEBHDFS_URL", "http://hdfs-namenode:9870"),
            webhdfs_user=_env("WEBHDFS_USER", "hadoop"),
            hdfs_base_path=_env("HDFS_BASE_PATH", "/gdelt/gkg"),
            gaps_path=_env("GDELT_GAPS_PATH", "gdelt-data/gaps.json"),
            poll_seconds=int(_env("GDELT_POLL_SECONDS", "900")),
            selfheal_hours=int(_env("GDELT_SELFHEAL_HOURS", "6")),
        )
