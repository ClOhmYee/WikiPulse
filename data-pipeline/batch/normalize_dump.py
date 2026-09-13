"""mediawiki_history 행을 실시간과 같은 edit_event 형태로 정규화한다.

WP-56. `producer/normalize.py` 의 실시간 경로와 **같은 15필드**를 낸다.
필드가 어긋나면 급증 탐지 로직을 두 벌 짜게 된다 — 명세 §3.2, §5.

이 모듈에 네트워크·파일 의존이 없다. 순수 함수라 표본 행만으로 테스트된다.

실측으로 확인한 것 (2026-09-08, 2026-08.aawiki.all-time 12,075행)
    - **`event_entity` 가 revision·user·page 3종이다.** 편집이 아닌 행이 61%다.
      실시간 경로(recentchange)에는 없는 필터 축이라 가장 먼저 거른다.
    - **`_historical` 변종을 써야 한다.** 현재 값(`page_namespace`·`page_title`)은
      삭제된 문서에서 비어 있어, 그대로 쓰면 ns0 집계가 677 → 335 로 반토막 난다.
      에러 없이 편집 수만 줄어드는 유형이라 특히 위험하다.
    - **타임스탬프가 초 정밀도다.** 표본 전부 `.0` 으로 끝난다. 실시간 경로는
      `meta.dt`(ms)를 쓰는데 덤프에는 그 정밀도가 아예 없다 — 리플레이 데이터는
      시간 해상도가 구조적으로 낮다. 윈도우 집계에는 영향 없다.
    - **제목이 밑줄형이다.** `page_title_historical` 은 `Hurricane_Milton` 처럼 온다.
      실시간(EventStreams)은 공백형이라 그대로 두면 같은 문서가 두 키로 갈라진다.
      `canonical_title` 로 공백형에 맞춘다 — 규칙과 근거는 그 함수, 명세 §5.1.
    - **증분을 덤프가 직접 준다.** `revision_text_bytes_diff` 는 결측 0, 음수 정상.
      실시간처럼 new - old 를 계산하지 않는다.

⚠️ event_type(edit/new)은 파생값이다
    덤프의 `event_type` 은 revision 행에서 **전부 `create`** 라 실시간의 edit/new
    구분을 주지 않는다. 아래 규칙은 EventStreams 값을 복원한 것이 아니라
    **live edit_event 계약에 맞추기 위한 파생 규칙**이다 (2026-09-08 팀 결정).
    `revision_parent_id` 는 표본에서 결측·0 비율이 86%로 지나치게 높아 주 신호로
    쓰지 않는다. enwiki 실적재 때 new/edit 비율을 재실측하고, 비정상이면
    이 로직을 바로 고치지 말고 별도 이슈로 올린다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from producer.normalize import (
    ARTICLE_NAMESPACE,
    EDIT_TYPES,
    SkipEvent,
    canonical_title,
)

from .schema import field

#: edit_event.source. 실시간은 "eventstreams", 리플레이는 "dump" 다.
DUMP_SOURCE = "dump"

#: 편집 이벤트를 담은 event_entity. user·page 행은 편집량 신호가 아니다.
REVISION_ENTITY = "revision"

#: 덤프 타임스탬프 형식. 예: 2004-02-24 11:54:14.0 (UTC, 초 정밀도)
DUMP_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

#: 언어 위키 DB 이름 -> 도메인. enwiki -> en.wikipedia.org
_LANGUAGE_WIKI = re.compile(r"^([a-z][a-z0-9_-]*)wiki$")

#: 언어 접두가 아닌 위키. 도메인 규칙이 달라 파생하지 않는다.
NON_LANGUAGE_WIKIS = frozenset(
    {
        "commonswiki",
        "wikidatawiki",
        "metawiki",
        "specieswiki",
        "incubatorwiki",
        "loginwiki",
        "mediawikiwiki",
        "sourceswiki",
        "outreachwiki",
        "testwiki",
    }
)


class UnsupportedWiki(ValueError):
    """도메인을 파생할 수 없는 위키. 조용히 틀린 도메인을 만드는 대신 멈춘다."""


def domain_for(wiki: str) -> str:
    """위키 DB 이름에서 도메인을 파생한다.

    덤프에 `domain` 컬럼이 없어서(78컬럼 확인, 2026-09-08) 파생한다.
    같은 입력이면 항상 같은 값이다.

        enwiki        -> en.wikipedia.org
        zh_min_nanwiki -> zh-min-nan.wikipedia.org   (DB 는 _, 도메인은 -)

    Raises:
        UnsupportedWiki: 언어 위키가 아니거나(commonswiki 등) 패턴이 안 맞을 때.
            MVP 대상은 enwiki 라, 규칙이 다른 위키를 추측해서 넣지 않는다.
    """
    if wiki in NON_LANGUAGE_WIKIS:
        raise UnsupportedWiki(f"언어 위키가 아니다: {wiki}")
    matched = _LANGUAGE_WIKI.match(wiki)
    if not matched:
        raise UnsupportedWiki(f"도메인 파생 규칙이 없다: {wiki}")
    return f"{matched.group(1).replace('_', '-')}.wikipedia.org"


def meta_id_for(wiki: str, revision_id: int) -> str:
    """추적용 식별자. 덤프에는 EventStreams 의 meta.id 가 없어 생성한다.

    같은 revision 이면 항상 같은 값이다. edit_event 스키마에서 이 필드가
    문자열이라 UUID 로 감쌀 이유가 없다.
    """
    return f"{DUMP_SOURCE}:{wiki}:{revision_id}"


def _text(row: Sequence[str], name: str) -> str | None:
    """빈 문자열을 None 으로. 덤프에는 NULL 표기가 따로 없다."""
    value = field(row, name)
    return value if value else None


def _int(row: Sequence[str], name: str) -> int | None:
    value = field(row, name)
    if not value:
        return None
    return int(value)


def _flag(row: Sequence[str], name: str) -> bool:
    """'true'/'false'/'' -> bool. 빈 값은 False."""
    return field(row, name) == "true"


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, DUMP_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def _iso_z(moment: datetime) -> str:
    """실시간 meta.dt 와 같은 모양으로. 예: 2004-02-24T11:54:14.000Z"""
    millis = moment.microsecond // 1000
    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{millis:03d}Z"


def derive_event_type(row: Sequence[str]) -> str:
    """edit / new 파생. 모듈 docstring 의 ⚠️ 를 함께 볼 것.

    page_first_edit_timestamp 가 있고 이벤트 시각과 같으면 그 문서의 첫 편집이라
    new, 그 외에는 edit. 결측이면 edit 로 둔다.
    """
    first_edit = field(row, "page_first_edit_timestamp")
    if first_edit and first_edit == field(row, "event_timestamp"):
        return "new"
    return "edit"


def normalize_dump(
    row: Sequence[str], *, wikis: frozenset[str] | None = None
) -> dict[str, Any]:
    """mediawiki_history 행 하나를 edit_event 로 바꾼다.

    Args:
        row: `schema.split_row()` 가 낸 78컬럼 배열
        wikis: 통과시킬 wiki 코드 집합 (예: {"enwiki"}). None 이면 전부 통과.

    Returns:
        edit_event dict. 키 집합이 producer.normalize.normalize() 와 같다.

    Raises:
        SkipEvent: 대상이 아닌 행 (다른 wiki, revision 이 아닌 entity,
            다른 네임스페이스, 식별자 결측). 오류가 아니라 정상적인 필터링이다.
        UnsupportedWiki: 도메인을 파생할 수 없는 위키
    """
    wiki = field(row, "wiki_db")
    if wikis is not None and wiki not in wikis:
        raise SkipEvent(f"wiki={wiki}")

    entity = field(row, "event_entity")
    if entity != REVISION_ENTITY:
        raise SkipEvent(f"event_entity={entity}")

    # 현재 값이 아니라 과거 시점 값을 쓴다 — 모듈 docstring 참고.
    namespace = field(row, "page_namespace_historical")
    if namespace != str(ARTICLE_NAMESPACE):
        raise SkipEvent(f"namespace={namespace}")

    event_type = derive_event_type(row)
    if event_type not in EDIT_TYPES:
        raise SkipEvent(f"type={event_type}")

    revision_id = _int(row, "revision_id")
    if revision_id is None:
        raise SkipEvent("revision_id 결측")

    timestamp = field(row, "event_timestamp")
    if not timestamp:
        raise SkipEvent("event_timestamp 결측")
    moment = _parse_timestamp(timestamp)

    # 문서 생성 revision 은 parent 가 0 이거나 비어 있다. 실시간 경로가
    # type=new 에서 None 을 내므로 여기서도 None 으로 맞춘다.
    parent_id = _int(row, "revision_parent_id")
    if parent_id == 0:
        parent_id = None

    return {
        # 식별
        "wiki": wiki,
        "domain": domain_for(wiki),
        # 덤프는 밑줄형(`Hurricane_Milton`), 실시간은 공백형이다. 같은 문서가
        # 다른 (wiki, title) 키로 갈라지지 않게 여기서 맞춘다 (WP-79).
        "title": canonical_title(field(row, "page_title_historical")),
        # 편집 내용
        "event_type": event_type,
        "rev_id": revision_id,
        "rev_parent_id": parent_id,
        # 실시간은 new-old 를 계산하지만 덤프는 증분을 직접 준다.
        "byte_delta": _int(row, "revision_text_bytes_diff"),
        "new_length": _int(row, "revision_text_bytes"),
        # 편집자 — 봇은 여기서 거르지 않는다. 플래그만 실어 보내고
        # 필터링은 Spark 쪽에서 한다 (실시간 경로와 같은 규칙).
        "user": _text(row, "event_user_text_historical"),
        "is_bot": bool(field(row, "event_user_is_bot_by_historical")),
        "is_minor": _flag(row, "revision_minor_edit"),
        # 시각 — 한 번 파싱한 datetime 에서 둘 다 뽑는다.
        "event_ts": _iso_z(moment),
        "event_ts_ms": int(moment.timestamp() * 1000),
        # 출처 — 실시간은 "eventstreams"
        "source": DUMP_SOURCE,
        # 추적용. 덤프에 meta.id 가 없어 생성한다.
        "meta_id": meta_id_for(wiki, revision_id),
    }
