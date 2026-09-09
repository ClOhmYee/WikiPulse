"""mediawiki_history TSV 컬럼 정의. WP-56.

컬럼 순서 근거 (2026-09-08 실측)
    덤프 파일에는 **헤더 행이 없다.** 이름과 순서는 wikitech 스키마 문서에서
    받아 실제 파일(`2026-08.aawiki.all-time`, 12,075행)로 정렬을 검증했다 —
    모든 행이 78컬럼이었고 각 값의 형태가 이름과 맞았다.
    문서: https://wikitech.wikimedia.org/wiki/Data_Platform/Data_Lake/Edits/MediaWiki_history_dumps

⚠️ 컬럼 수가 78이 아니면 스냅샷 스키마가 바뀐 것이다. 위치가 하나만 밀려도
   모든 필드가 조용히 틀린 값이 되므로 SchemaMismatch 로 멈춘다.
"""

from __future__ import annotations

from collections.abc import Sequence


class SchemaMismatch(Exception):
    """행의 컬럼 수가 기대와 다르다. 스냅샷 스키마 변경 신호다."""


#: 덤프 TSV 의 컬럼 순서. 이 순서 자체가 파일 포맷이다 — 재정렬 금지.
COLUMNS: tuple[str, ...] = (
    "wiki_db",
    "event_log_id",
    "event_entity",
    "event_type",
    "event_timestamp",
    "event_comment",
    "event_user_id",
    "event_user_central_id",
    "event_user_text_historical",
    "event_user_text",
    "event_user_blocks_historical",
    "event_user_blocks",
    "event_user_groups_historical",
    "event_user_groups",
    "event_user_is_bot_by_historical",
    "event_user_is_bot_by",
    "event_user_is_created_by_self",
    "event_user_is_created_by_system",
    "event_user_is_created_by_peer",
    "event_user_is_anonymous",
    "event_user_is_temporary",
    "event_user_is_permanent",
    "event_user_is_cross_wiki",
    "event_user_registration_timestamp",
    "event_user_creation_timestamp",
    "event_user_first_edit_timestamp",
    "event_user_revision_count",
    "event_user_seconds_since_previous_revision",
    "page_id",
    "page_title_historical",
    "page_title",
    "page_namespace_historical",
    "page_namespace_is_content_historical",
    "page_namespace",
    "page_namespace_is_content",
    "page_is_redirect",
    "page_is_deleted",
    "page_creation_timestamp",
    "page_first_edit_timestamp",
    "page_revision_count",
    "page_seconds_since_previous_revision",
    "user_id",
    "user_central_id",
    "user_text_historical",
    "user_text",
    "user_blocks_historical",
    "user_blocks",
    "user_groups_historical",
    "user_groups",
    "user_is_bot_by_historical",
    "user_is_bot_by",
    "user_is_created_by_self",
    "user_is_created_by_system",
    "user_is_created_by_peer",
    "user_is_anonymous",
    "user_is_temporary",
    "user_is_permanent",
    "user_registration_timestamp",
    "user_creation_timestamp",
    "user_first_edit_timestamp",
    "revision_id",
    "revision_parent_id",
    "revision_minor_edit",
    "revision_deleted_parts",
    "revision_deleted_parts_are_suppressed",
    "revision_text_bytes",
    "revision_text_bytes_diff",
    "revision_text_sha1",
    "revision_content_model",
    "revision_content_format",
    "revision_is_deleted_by_page_deletion",
    "revision_deleted_by_page_deletion_timestamp",
    "revision_is_identity_reverted",
    "revision_first_identity_reverting_revision_id",
    "revision_seconds_to_identity_revert",
    "revision_is_identity_revert",
    "revision_is_from_before_page_creation",
    "revision_tags",
)

COLUMN_COUNT = len(COLUMNS)

#: 이름 -> 위치. 행마다 dict 를 만들면 5억 행에서 비싸므로 인덱스만 쓴다.
COLUMN_INDEX: dict[str, int] = {name: i for i, name in enumerate(COLUMNS)}


def split_row(line: str) -> Sequence[str]:
    """TSV 한 줄을 컬럼 배열로. 개행만 벗기고 값은 손대지 않는다.

    Raises:
        SchemaMismatch: 컬럼 수가 COLUMN_COUNT 와 다를 때
    """
    row = line.rstrip("\n").split("\t")
    if len(row) != COLUMN_COUNT:
        raise SchemaMismatch(f"컬럼 {len(row)}개 (기대 {COLUMN_COUNT}개)")
    return row


def field(row: Sequence[str], name: str) -> str:
    """이름으로 값을 꺼낸다. 없는 값은 빈 문자열이다 (덤프에 NULL 표기가 없다)."""
    return row[COLUMN_INDEX[name]]
