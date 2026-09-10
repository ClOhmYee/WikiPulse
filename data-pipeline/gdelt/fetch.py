"""GDELT 파일 다운로드 — 리다이렉트 추적·무결성 검증·재시도.

무결성을 두 겹으로 본다
    1. zip 매직 바이트(PK\\x03\\x04) — 404 대신 200 으로 HTML 오류 페이지가 오거나
       응답이 잘렸을 때 잡는다. md5 를 모를 때(자가치유 경로)도 최소한 이건 본다.
    2. size·md5 — lastupdate/masterlist 가 알려줄 때 정확히 대조한다.

404 는 재시도하지 않는다 — GDELT 쪽에 원래 없는 파일이다(결손). GdeltNotFound 로
올려 producer 가 결손으로 기록하게 한다. 그 외 실패(네트워크·5xx·무결성)는 재시도한다.

⚠️ URL 은 http:// 지만 GDELT 가 https 로 301 한다 (2026-09-09 실측). requests 는
   기본으로 리다이렉트를 따라가므로 그대로 둔다.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable

import requests

log = logging.getLogger("gdelt.fetch")

ZIP_MAGIC = b"PK\x03\x04"


class GdeltNotFound(Exception):
    """404 — GDELT 쪽에 없는 파일. 결손으로 기록하고 재시도하지 않는다."""


class IntegrityError(Exception):
    """크기·md5·매직이 안 맞음. 잘린 다운로드일 수 있어 재시도 대상이다."""


def verify(data: bytes, *, expected_size: int | None, expected_md5: str | None) -> None:
    if not data:
        raise IntegrityError("빈 응답")
    if not data.startswith(ZIP_MAGIC):
        raise IntegrityError("zip 매직이 아님 — HTML 오류 페이지이거나 잘렸다")
    if expected_size is not None and len(data) != expected_size:
        raise IntegrityError(f"크기 불일치: {len(data)} != {expected_size}")
    if expected_md5 is not None:
        got = hashlib.md5(data).hexdigest()
        if got != expected_md5:
            raise IntegrityError(f"md5 불일치: {got} != {expected_md5}")


def download(
    url: str,
    *,
    expected_size: int | None = None,
    expected_md5: str | None = None,
    session: requests.Session,
    user_agent: str | None = None,
    timeout: float = 120.0,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """파일 바이트를 받아 검증해 돌려준다.

    Raises:
        GdeltNotFound: 404 (재시도 안 함)
        IntegrityError / requests.RequestException: 재시도 소진 후 마지막 예외
    """
    headers = {"User-Agent": user_agent} if user_agent else {}
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 404:
                raise GdeltNotFound(url)
            resp.raise_for_status()
            data = resp.content
            verify(data, expected_size=expected_size, expected_md5=expected_md5)
            return data
        except GdeltNotFound:
            raise  # 결손 — 재시도 무의미
        except (requests.RequestException, IntegrityError) as exc:
            last_exc = exc
            log.warning("다운로드 실패(%d/%d) %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                sleep(backoff * attempt)

    assert last_exc is not None
    raise last_exc
