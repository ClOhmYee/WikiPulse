"""결손 구간 로그 — GDELT 쪽에 없는 시간대를 JSON 파일에 남긴다.

왜 기록하나
    Spark 배치가 나중에 "이 시간대는 원래 데이터가 없음"을 구분해야 한다. 안 그러면
    빠진 구간을 영영 재시도하거나, 데이터 공백을 장애로 오해한다. 이슈 요구사항의
    "결손 구간 기록"이 이것이다. 확인된 예: 2025-06-14 18:00~07-02 02:00 UTC 전체
    404(2026-09-16 경계 재확인, 명세 §11 — 처음 기록은 06-13~07-04로 더 넓었다).

reason
    "404"     — 실제로 받아봤더니 GDELT 가 404. 확실한 결손.
    "missing" — masterfilelist 에 그 15분 슬롯이 아예 없음. 목록에 안 올라온 것.

형식(JSON)
    {"gaps": [{"from": ts, "to": ts, "reason": "404", "recorded_at": iso8601}, ...]}
    from/to 는 15분 격자 타임스탬프(포함). 같은 (from,to,reason)은 한 번만 남는다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone

from .catalog import Gap


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str) -> list[dict]:
    """결손 로그를 읽는다. 없으면 빈 리스트."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc.get("gaps", [])


def record(
    path: str,
    gaps: Iterable[Gap],
    *,
    reason: str,
    now: str | None = None,
) -> int:
    """결손 구간들을 로그에 추가한다. 이미 있는 (from,to,reason)은 건너뛴다.

    Returns: 실제로 새로 추가된 구간 수.
    """
    now = now or _now_iso()
    existing = load(path)
    seen = {(g["from"], g["to"], g["reason"]) for g in existing}

    added = 0
    for gap in gaps:
        key = (gap.start, gap.end, reason)
        if key in seen:
            continue
        existing.append(
            {"from": gap.start, "to": gap.end, "reason": reason, "recorded_at": now}
        )
        seen.add(key)
        added += 1

    if added:
        tmp = f"{path}.part"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"gaps": existing}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return added
