"""덤프 정규화 테스트. 실시간 경로와 계약이 어긋나는 것을 잡는다.

여기서 잡으려는 실패 둘.

1. **필드 집합이 실시간과 갈라지는 것.** 갈라지면 Spark 가 from_json 으로 읽을 때
   조용히 null 이 채워져 집계가 0이 되는데 에러는 안 난다.
2. **`_historical` 대신 현재 컬럼을 쓰는 것.** 삭제된 문서에서 현재 컬럼이 비어
   있어 편집 수만 줄고 에러는 안 난다 (표본에서 ns0 677 -> 335).

숫자·컬럼 배치는 2026-09-08 에 2026-08.aawiki.all-time 을 직접 받아 확인한 것이다.
네트워크 없이 돈다.
"""

from __future__ import annotations

import copy
import json

import pytest

from batch.normalize_dump import (
    DUMP_SOURCE,
    UnsupportedWiki,
    derive_event_type,
    domain_for,
    meta_id_for,
    normalize_dump,
)
from batch.schema import COLUMN_COUNT, COLUMNS, SchemaMismatch, split_row
from producer.normalize import SkipEvent, normalize

# --- 표본 행 만들기 -----------------------------------------------------

#: aawiki 실제 행에서 가져온 revision/create · ns0 값 (2026-09-08)
SAMPLE = {
    "wiki_db": "aawiki",
    "event_entity": "revision",
    "event_type": "create",
    "event_timestamp": "2005-07-07 15:31:37.0",
    "event_user_text_historical": "Arde",
    "event_user_text": "Arde~aawiki",
    "page_id": "1269",
    "page_title_historical": "Main_Page",
    "page_title": "Main_Page",
    "page_namespace_historical": "0",
    "page_namespace": "0",
    "page_creation_timestamp": "2005-07-07 15:31:37.0",
    "page_first_edit_timestamp": "2005-07-07 15:31:37.0",
    "revision_id": "1269",
    "revision_parent_id": "0",
    "revision_minor_edit": "false",
    "revision_text_bytes": "8211",
    "revision_text_bytes_diff": "8211",
}


def row(**overrides) -> list[str]:
    """78컬럼 행을 만든다. 지정 안 한 컬럼은 빈 문자열(덤프의 NULL 표기)."""
    values = copy.deepcopy(SAMPLE)
    values.update(overrides)
    unknown = set(values) - set(COLUMNS)
    assert not unknown, f"덤프에 없는 컬럼: {unknown}"
    return [values.get(name, "") for name in COLUMNS]


# --- 스키마 -------------------------------------------------------------


def test_컬럼은_78개다():
    """스냅샷 스키마가 바뀌면 여기서 먼저 걸린다."""
    assert COLUMN_COUNT == 78
    assert len(set(COLUMNS)) == 78, "컬럼 이름 중복"


def test_컬럼_수가_다르면_멈춘다():
    """위치가 하나만 밀려도 모든 필드가 조용히 틀린 값이 된다."""
    with pytest.raises(SchemaMismatch):
        split_row("a\tb\tc\n")


def test_정상_행은_78컬럼으로_쪼개진다():
    assert len(split_row("\t".join(row()) + "\n")) == 78


# --- 계약: 실시간과 같은 필드 -------------------------------------------


def live_event() -> dict:
    """실시간 경로가 내는 edit_event. 필드 집합 비교용."""
    return normalize(
        {
            "meta": {
                "domain": "en.wikipedia.org",
                "id": "b18aa477-0c22-4475-9416-23367a447b2b",
                "dt": "2026-09-08T00:24:20.990Z",
            },
            "type": "edit",
            "namespace": 0,
            "title": "Hurricane Milton",
            "timestamp": 1788827059,
            "user": "Alice",
            "bot": False,
            "minor": False,
            "length": {"old": 1000, "new": 1100},
            "revision": {"old": 10, "new": 11},
            "wiki": "enwiki",
        }
    )


def test_덤프_출력_키가_실시간_출력_키와_정확히_같다():
    """pyspark 없이도 도는 계약 검사. 한쪽에 필드를 더하고 다른 쪽을 잊는 걸 막는다."""
    dump_keys = set(normalize_dump(row()).keys())
    live_keys = set(live_event().keys())
    assert dump_keys == live_keys, (
        f"덤프에만 있음: {dump_keys - live_keys} / 실시간에만 있음: {live_keys - dump_keys}"
    )


def test_출력이_JSON_직렬화된다():
    """Kafka·JSONL 로 나가는 형태라 직렬화가 안 되면 적재 단계에서 터진다."""
    assert json.loads(json.dumps(normalize_dump(row()), ensure_ascii=False))


# --- 필터 ---------------------------------------------------------------


@pytest.mark.parametrize("entity", ["user", "page"])
def test_revision_이_아닌_행은_거른다(entity):
    """표본에서 편집이 아닌 행이 61%다. 실시간에는 없는 필터 축이다."""
    with pytest.raises(SkipEvent):
        normalize_dump(row(event_entity=entity))


def test_다른_네임스페이스는_거른다():
    with pytest.raises(SkipEvent):
        normalize_dump(row(page_namespace_historical="2"))


def test_네임스페이스는_현재값이_아니라_과거값으로_판정한다():
    """삭제된 문서는 page_namespace 가 비어 있다. 현재값을 보면 절반이 사라진다."""
    event = normalize_dump(row(page_namespace_historical="0", page_namespace=""))
    # 덤프 입력은 `Main_Page`(밑줄), 출력은 canonical 공백형이다 — WP-79.
    assert event["title"] == "Main Page"


def test_제목도_과거값을_쓴다():
    """표본에서 ns0 677행 중 342행의 page_title 이 비어 있었다."""
    event = normalize_dump(row(page_title_historical="Test", page_title=""))
    assert event["title"] == "Test"


def test_다른_위키는_거른다():
    with pytest.raises(SkipEvent):
        normalize_dump(row(), wikis=frozenset({"enwiki"}))


def test_지정한_위키는_통과한다():
    assert normalize_dump(row(), wikis=frozenset({"aawiki"}))["wiki"] == "aawiki"


def test_식별자가_없으면_거른다():
    with pytest.raises(SkipEvent):
        normalize_dump(row(revision_id=""))
    with pytest.raises(SkipEvent):
        normalize_dump(row(event_timestamp=""))


# --- 봇 -----------------------------------------------------------------


def test_봇은_거르지_않고_플래그만_싣는다():
    """노이즈 정의가 바뀔 수 있어 필터링은 Spark 쪽 책임이다 (실시간과 같은 규칙)."""
    event = normalize_dump(row(event_user_is_bot_by_historical="group"))
    assert event["is_bot"] is True
    assert event["user"] == "Arde"


def test_봇_표시가_없으면_False():
    assert normalize_dump(row())["is_bot"] is False


def test_봇_판정도_과거값을_쓴다():
    """현재 봇이어도 편집 당시 봇이 아니었으면 봇 편집이 아니다."""
    event = normalize_dump(
        row(event_user_is_bot_by_historical="", event_user_is_bot_by="group")
    )
    assert event["is_bot"] is False


# --- event_type 파생 -----------------------------------------------------


def test_첫_편집이면_new():
    assert derive_event_type(row()) == "new"


def test_첫_편집이_아니면_edit():
    assert (
        derive_event_type(
            row(
                event_timestamp="2010-01-01 00:00:00.0",
                page_first_edit_timestamp="2005-07-07 15:31:37.0",
            )
        )
        == "edit"
    )


def test_첫_편집_시각이_결측이면_edit():
    """표본에서 결측이 흔했다. 추측하지 않고 edit 로 둔다."""
    assert derive_event_type(row(page_first_edit_timestamp="")) == "edit"


# --- 값 매핑 -------------------------------------------------------------


def test_증분은_덤프_값을_그대로_쓴다():
    """실시간은 new-old 를 계산하지만 덤프는 diff 를 직접 준다. 음수 정상."""
    event = normalize_dump(row(revision_text_bytes_diff="-21436"))
    assert event["byte_delta"] == -21436


def test_새_문서의_parent_는_None():
    """실시간 type=new 가 rev_parent_id=None 을 내는 것과 맞춘다."""
    assert normalize_dump(row(revision_parent_id="0"))["rev_parent_id"] is None
    assert normalize_dump(row(revision_parent_id=""))["rev_parent_id"] is None


def test_parent_가_있으면_숫자로_싣는다():
    assert normalize_dump(row(revision_parent_id="4504"))["rev_parent_id"] == 4504


def test_source_는_dump_다():
    """실시간과 리플레이를 구분하는 필드다. 명세 §3.2."""
    assert normalize_dump(row())["source"] == DUMP_SOURCE == "dump"


def test_시각은_실시간과_같은_모양으로_변환된다():
    """덤프는 '2005-07-07 15:31:37.0', 실시간 meta.dt 는 ISO8601 Z 다."""
    event = normalize_dump(row())
    assert event["event_ts"] == "2005-07-07T15:31:37.000Z"
    assert event["event_ts_ms"] == 1120750297000


def test_시각_두_필드가_같은_순간을_가리킨다():
    event = normalize_dump(row(event_timestamp="2024-10-10 12:34:56.0"))
    assert event["event_ts"] == "2024-10-10T12:34:56.000Z"
    assert event["event_ts_ms"] == 1728563696000


def test_나머지_필드가_원본과_맞는다():
    event = normalize_dump(row())
    assert event["wiki"] == "aawiki"
    assert event["rev_id"] == 1269
    assert event["new_length"] == 8211
    assert event["is_minor"] is False


def test_사소한_편집_플래그():
    assert normalize_dump(row(revision_minor_edit="true"))["is_minor"] is True


# --- 파생 필드: domain · meta_id -----------------------------------------


def test_도메인은_위키에서_파생된다():
    """덤프 78컬럼에 domain 이 없다 (2026-09-08 확인)."""
    assert domain_for("enwiki") == "en.wikipedia.org"
    assert domain_for("aawiki") == "aa.wikipedia.org"


def test_언더바_언어코드는_하이픈_도메인이_된다():
    """DB 이름은 _, 도메인은 - 를 쓴다."""
    assert domain_for("zh_min_nanwiki") == "zh-min-nan.wikipedia.org"


@pytest.mark.parametrize("wiki", ["commonswiki", "wikidatawiki", "enwiktionary"])
def test_규칙이_다른_위키는_추측하지_않고_멈춘다(wiki):
    """조용히 틀린 도메인을 만드는 것보다 멈추는 게 낫다."""
    with pytest.raises(UnsupportedWiki):
        domain_for(wiki)


def test_meta_id_는_같은_revision_이면_항상_같다():
    """덤프에 EventStreams 의 meta.id 가 없어 생성한다. 재실행해도 값이 같아야 한다."""
    assert meta_id_for("enwiki", 123) == "dump:enwiki:123"
    assert normalize_dump(row())["meta_id"] == "dump:aawiki:1269"
    assert normalize_dump(row())["meta_id"] == normalize_dump(row())["meta_id"]


def test_파생_필드에_None_을_넣지_않는다():
    """domain·meta_id 는 기본값 None 을 쓰지 않기로 했다 (2026-09-08 결정)."""
    event = normalize_dump(row())
    assert event["domain"] and event["meta_id"]
