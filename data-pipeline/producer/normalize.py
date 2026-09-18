"""EventStreams recentchange 이벤트를 내부 edit_event 형태로 정규화한다.

이 모듈에 Kafka·네트워크 의존이 없다 — 순수 함수라 테스트가 쉽다.

왜 정규화 레이어를 따로 두나
    실시간 경로(EventStreams JSON)와 리플레이 경로(mediawiki_history TSV)는
    필드명·타입·봇 표시 방식이 서로 다르다. 둘을 같은 edit_event 형태로 맞춰
    두지 않으면 급증 탐지 로직을 두 벌 짜게 된다. 리플레이는 아직 구현 전이지만
    `source` 필드를 지금 넣어 자리를 잡아둔다.
    근거: docs/requirements-v0.3.md §3.2, §10

실측으로 확인한 스키마 (2026-09-08, stream.wikimedia.org/v2/stream/recentchange)
    - page_id 필드가 없다. 페이지 식별자는 (wiki, title) 뿐이다.
    - type 분포(enwiki ns0 12초 표본): edit 28 · new 7 · categorize 25 · log 1
      categorize는 문서 편집이 아니라 분류 자동 갱신이라 반드시 걸러야 한다.
    - meta.dt 는 ms 정밀도 ISO8601, 최상위 timestamp 는 초 단위. dt 를 쓴다.
    - type=new 는 length.old / revision.old 가 없다.
    - **title 이 공백형이다.** 75초 표본 2,496건에 밑줄 제목이 0건이었다
      (2026-09-13 재측정). 덤프는 밑줄형이라 canonical_title 로 맞춘다 — §5.1.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# 문서 본문 편집으로 볼 이벤트 종류.
# categorize(분류 자동 갱신)·log(이동·삭제 등)는 편집량 신호가 아니라 제외한다.
EDIT_TYPES = frozenset({"edit", "new"})

# 주 문서 네임스페이스. 0 = (Main/Article)
ARTICLE_NAMESPACE = 0

#: 제목에서 공백과 같은 뜻으로 쓰이는 문자. MediaWiki 는 밑줄과 공백을 구분하지 않는다.
_TITLE_SEPARATORS = re.compile(r"[ _]+")


def canonical_title(raw: str) -> str:
    """문서 제목을 파이프라인 내부 canonical 형태(공백형)로 맞춘다. (WP-79)

    같은 문서가 경로마다 다른 키로 들어가면 `(wiki, title)` 자연키가 갈라진다.
    LIVE 는 `Hurricane Milton`, 덤프는 `Hurricane_Milton` 을 주는데 둘은 같은
    문서다 — 같은 pageid 로 해석된다(78046814, 2026-09-13 실측).

    공백형을 고른 이유
        MediaWiki 가 밑줄로 주든 공백으로 주든 **공백형으로 정규화해 돌려준다**.
        밑줄은 URL 표기이지 제목이 아니다. edit_event 계약(data-pipeline/README.md)
        과 API 명세도 이미 공백형이라, 밑줄을 내는 곳만 맞추면 된다.
        명세 §5.1.

    적용하는 규칙 (2026-09-13 MediaWiki API `normalized` 응답으로 실측)
        밑줄 -> 공백              Hurricane_Milton   -> Hurricane Milton
        연속 구분자 -> 공백 하나   Hurricane__Milton  -> Hurricane Milton
        앞뒤 구분자 제거           _Hurricane Milton_ -> Hurricane Milton
    뒤 둘은 방어용이다. LIVE 표본 2,496건에 연속 공백이 0건이라 실제로는 값이
    바뀌지 않는 게 정상이다. 적용해도 MediaWiki canonical 에서 멀어질 수 없다.

    ⚠️ 적용하지 않는 규칙 — 추측으로 넣지 않는다
        **첫 글자 대문자.** 소스가 주는 건 이미 대문자화된 MediaWiki 저장 제목이다
        (`eBay` 를 조회하면 저장 제목이 `EBay`, pageid 130495). 우리는 사용자가 친
        제목을 받지 않는다. 게다가 이 규칙은 위키별 `$wgCapitalLinks` 설정에 달렸고
        enwiki 밖에서는 확인하지 않았다.
        **Unicode NFC.** MediaWiki 가 NFC 로 저장·요구하고(API 경고 확인), LIVE
        표본 2,496건 전부 NFC 였다. 소스가 이미 NFC 라 no-op 이다.
    둘 다 필요해지면 근거 수치를 먼저 만든 뒤 넣는다.

    구분자를 ` ` 와 `_` 로만 한정한 것도 같은 이유다. `str.split()` 은 NBSP 까지
    공백으로 보는데, MediaWiki 가 NBSP 를 제목에서 어떻게 다루는지는 확인하지 않았다.
    """
    return _TITLE_SEPARATORS.sub(" ", raw).strip(" ")


class SkipEvent(Exception):
    """이 이벤트는 파이프라인에 넣지 않는다. 오류가 아니라 정상적인 필터링이다."""


def _iso_to_epoch_ms(dt_str: str) -> int:
    """meta.dt('2026-09-08T00:24:20.990Z') -> epoch millis."""
    # fromisoformat 은 파이썬 3.11 미만에서 'Z' 를 못 읽는다.
    normalized = dt_str.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).timestamp() * 1000)


def normalize(raw: dict[str, Any], *, wikis: frozenset[str] | None = None) -> dict[str, Any]:
    """recentchange 이벤트 하나를 edit_event 로 바꾼다.

    Args:
        raw: EventStreams 가 준 JSON 을 파싱한 dict
        wikis: 통과시킬 wiki 코드 집합 (예: {"enwiki"}). None 이면 전부 통과.

    Returns:
        edit_event dict

    Raises:
        SkipEvent: 대상이 아닌 이벤트 (다른 wiki, 다른 네임스페이스, categorize 등)
        KeyError, ValueError: 스키마가 예상과 다를 때. 호출자가 로그로 남긴다.
    """
    wiki = raw.get("wiki")
    if wikis is not None and wiki not in wikis:
        raise SkipEvent(f"wiki={wiki}")

    if raw.get("namespace") != ARTICLE_NAMESPACE:
        raise SkipEvent(f"namespace={raw.get('namespace')}")

    event_type = raw.get("type")
    if event_type not in EDIT_TYPES:
        raise SkipEvent(f"type={event_type}")

    length = raw.get("length") or {}
    revision = raw.get("revision") or {}

    # 새 문서는 old 가 없다. 그 경우 증분 = 새 길이 전체.
    new_len = length.get("new")
    old_len = length.get("old")
    if new_len is None:
        byte_delta = None
    else:
        byte_delta = new_len - (old_len or 0)

    meta = raw["meta"]

    return {
        # 식별
        "wiki": wiki,
        "domain": meta.get("domain"),
        # canonical 형태로 맞춰 내보낸다 — 덤프 경로와 같은 키가 되게 (WP-79)
        "title": canonical_title(raw["title"]),
        # 편집 내용
        "event_type": event_type,
        "rev_id": revision.get("new"),
        "rev_parent_id": revision.get("old"),
        "byte_delta": byte_delta,
        "new_length": new_len,
        # 편집자 — 봇은 여기서 거르지 않는다. 플래그만 실어 보내고
        # 필터링은 Spark 쪽에서 한다 (노이즈 정의가 바뀔 수 있어서).
        "user": raw.get("user"),
        "is_bot": bool(raw.get("bot", False)),
        "is_minor": bool(raw.get("minor", False)),
        # 시각
        "event_ts": meta["dt"],
        "event_ts_ms": _iso_to_epoch_ms(meta["dt"]),
        # 출처 — 리플레이 경로가 붙으면 "dump" 가 들어온다
        "source": "eventstreams",
        # 추적용. 같은 이벤트가 두 번 들어왔는지 확인할 때 쓴다.
        "meta_id": meta.get("id"),
    }


def partition_key(event: dict[str, Any]) -> bytes:
    """같은 문서는 같은 파티션으로 보낸다.

    Spark 윈도우 집계가 문서 단위라, 한 문서의 이벤트가 여러 파티션에 흩어지면
    순서 보장이 깨진다. page_id 가 스트림에 없어서 (wiki, title) 을 키로 쓴다.
    문서 이동(rename)이 일어나면 키가 바뀌지만 MVP 범위에서는 감수한다.

    title 은 normalize() 가 이미 canonical 로 맞춰 놓은 값이다. 덤프 경로도 같은
    함수를 쓰므로 같은 문서는 실시간·리플레이가 같은 파티션으로 간다.
    """
    return f"{event['wiki']}:{event['title']}".encode("utf-8")
