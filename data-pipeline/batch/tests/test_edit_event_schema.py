"""덤프 출력이 Spark 가 읽는 EDIT_EVENT_SCHEMA 와 맞는지.

`test_normalize_dump.py` 의 계약 검사(실시간 출력 키와 비교)가 1차이고, 이 파일은
Spark 쪽 스키마를 직접 보는 2차다. pyspark 가 있어야 돌아서 따로 뒀다 —
1차를 같은 파일에 두면 pyspark 없는 환경에서 함께 skip 되어, 정작 계약이 깨져도
아무도 모르게 된다.
"""

from __future__ import annotations

import pytest

from batch.normalize_dump import normalize_dump
from batch.schema import COLUMNS

pytest.importorskip("pyspark", reason="pyspark 미설치 — 이 파일은 건너뛴다")

from streaming.edit_windows import EDIT_EVENT_SCHEMA  # noqa: E402

SAMPLE = {
    "wiki_db": "aawiki",
    "event_entity": "revision",
    "event_timestamp": "2005-07-07 15:31:37.0",
    "event_user_text_historical": "Arde",
    "page_title_historical": "Main_Page",
    "page_namespace_historical": "0",
    "page_first_edit_timestamp": "2005-07-07 15:31:37.0",
    "revision_id": "1269",
    "revision_text_bytes": "8211",
    "revision_text_bytes_diff": "8211",
    "revision_minor_edit": "false",
}


def sample_row() -> list[str]:
    return [SAMPLE.get(name, "") for name in COLUMNS]


def test_덤프_출력_필드가_EDIT_EVENT_SCHEMA_와_정확히_같다():
    produced = set(normalize_dump(sample_row()).keys())
    declared = {f.name for f in EDIT_EVENT_SCHEMA.fields}
    assert produced == declared, (
        f"덤프에만 있음: {produced - declared} / 스키마에만 있음: {declared - produced}"
    )
