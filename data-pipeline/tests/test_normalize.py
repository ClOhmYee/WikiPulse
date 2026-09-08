"""normalize() 테스트.

표본은 2026-09-08 stream.wikimedia.org 에서 실제로 받은 이벤트다.
필드를 상상해서 쓰지 않았다.
"""

from __future__ import annotations

import copy

import pytest

from producer.normalize import SkipEvent, normalize, partition_key

# 2026-09-08 00:24:20Z 실제 수신 이벤트 (parsedcomment 만 길어서 줄임)
REAL_EDIT = {
    "$schema": "/mediawiki/recentchange/1.0.0",
    "meta": {
        "uri": "https://en.wikipedia.org/wiki/Raghvi_Bist",
        "request_id": "c8eedcd0-749b-4b3d-98d4-2d6a8d07dbeb",
        "id": "b18aa477-0c22-4475-9416-23367a447b2b",
        "domain": "en.wikipedia.org",
        "stream": "mediawiki.recentchange",
        "dt": "2026-09-08T00:24:20.990Z",
        "topic": "eqiad.mediawiki.recentchange",
        "partition": 0,
        "offset": 6496589447,
    },
    "id": 2066604043,
    "type": "edit",
    "namespace": 0,
    "title": "Raghvi Bist",
    "comment": "/* top */ Task 30",
    "timestamp": 1788827059,
    "user": "PrimeBOT",
    "bot": True,
    "minor": True,
    "length": {"old": 10971, "new": 10972},
    "revision": {"old": 1332171990, "new": 1373796840},
    "server_name": "en.wikipedia.org",
    "wiki": "enwiki",
}


def make(**overrides):
    event = copy.deepcopy(REAL_EDIT)
    event.update(overrides)
    return event


def test_실제_이벤트를_정규화한다():
    result = normalize(REAL_EDIT, wikis=frozenset({"enwiki"}))

    assert result["wiki"] == "enwiki"
    assert result["title"] == "Raghvi Bist"
    assert result["event_type"] == "edit"
    assert result["rev_id"] == 1373796840
    assert result["rev_parent_id"] == 1332171990
    assert result["byte_delta"] == 1
    assert result["user"] == "PrimeBOT"
    assert result["source"] == "eventstreams"


def test_봇은_거르지_않고_플래그만_실어_보낸다():
    """노이즈 정의가 바뀔 수 있어 필터링은 Spark 쪽 몫이다."""
    result = normalize(REAL_EDIT)
    assert result["is_bot"] is True


def test_event_ts_는_밀리초까지_보존한다():
    result = normalize(REAL_EDIT)
    # 2026-09-08T00:24:20.990Z
    assert result["event_ts_ms"] % 1000 == 990
    assert result["event_ts"] == "2026-09-08T00:24:20.990Z"


def test_초단위_timestamp_가_아니라_meta_dt_를_쓴다():
    """최상위 timestamp 는 초 단위라 같은 초의 편집을 구분하지 못한다."""
    result = normalize(REAL_EDIT)
    assert result["event_ts_ms"] != REAL_EDIT["timestamp"] * 1000


def test_새_문서는_old_길이가_없어도_증분을_낸다():
    """type=new 는 length.old·revision.old 가 비어 있다."""
    result = normalize(
        make(type="new", length={"new": 2500}, revision={"new": 999})
    )
    assert result["byte_delta"] == 2500
    assert result["rev_parent_id"] is None
    assert result["event_type"] == "new"


@pytest.mark.parametrize("event_type", ["categorize", "log", "external"])
def test_편집이_아닌_이벤트는_건너뛴다(event_type):
    """categorize 가 enwiki ns0 표본의 40%였다. 안 거르면 편집 수가 부풀려진다."""
    with pytest.raises(SkipEvent):
        normalize(make(type=event_type))


def test_본문_외_네임스페이스는_건너뛴다():
    with pytest.raises(SkipEvent):
        normalize(make(namespace=14))  # Category


def test_대상_외_위키는_건너뛴다():
    with pytest.raises(SkipEvent):
        normalize(make(wiki="kowiki"), wikis=frozenset({"enwiki"}))


def test_wikis_가_None_이면_전부_통과():
    assert normalize(make(wiki="kowiki"), wikis=None)["wiki"] == "kowiki"


def test_같은_문서는_같은_키를_받는다():
    """문서 단위 윈도우 집계라 같은 문서가 여러 파티션에 흩어지면 안 된다."""
    first = partition_key(normalize(REAL_EDIT))
    second = partition_key(normalize(make(id=999, revision={"old": 1, "new": 2})))
    assert first == second == b"enwiki:Raghvi Bist"


def test_다른_위키의_같은_제목은_다른_키다():
    a = partition_key(normalize(make(wiki="enwiki")))
    b = partition_key(normalize(make(wiki="kowiki")))
    assert a != b
