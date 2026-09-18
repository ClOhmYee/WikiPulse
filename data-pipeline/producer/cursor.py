from __future__ import annotations

import json
import os
from pathlib import Path


class CursorStore:
    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def load(self) -> str | None:
        if self.path is None or not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cursor 파일을 읽을 수 없다: {self.path}") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or not isinstance(payload.get("event_id"), str)
            or not payload["event_id"]
        ):
            raise ValueError(f"cursor 파일 형식이 잘못됐다: {self.path}")
        return payload["event_id"]

    def save(self, event_id: str) -> None:
        if self.path is None:
            return
        if not event_id:
            raise ValueError("빈 SSE event id는 저장할 수 없다")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump({"version": 1, "event_id": event_id}, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
