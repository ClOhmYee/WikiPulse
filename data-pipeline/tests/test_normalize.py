"""normalize() 테스트.

표본은 2026-09-08 stream.wikimedia.org 에서 실제로 받은 이벤트다.
필드를 상상해서 쓰지 않았다.
"""

from __future__ import annotations

import copy
import unicodedata

import pytest

from producer.normalize import SkipEvent, canonical_title, normalize, partition_key

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


@pytest.mark.parametrize("meta_id", [None, "", " \t"])
def test_meta_id_가_비어_있으면_거부한다(meta_id):
    raw = copy.deepcopy(REAL_EDIT)
    raw["meta"]["id"] = meta_id

    with pytest.raises(ValueError, match="meta.id"):
        normalize(raw)


def test_같은_문서는_같은_키를_받는다():
    """문서 단위 윈도우 집계라 같은 문서가 여러 파티션에 흩어지면 안 된다."""
    first = partition_key(normalize(REAL_EDIT))
    second = partition_key(normalize(make(id=999, revision={"old": 1, "new": 2})))
    assert first == second == b"enwiki:Raghvi Bist"


def test_다른_위키의_같은_제목은_다른_키다():
    a = partition_key(normalize(make(wiki="enwiki")))
    b = partition_key(normalize(make(wiki="kowiki")))
    assert a != b


# --- canonical_title (WP-79) ------------------------------------
#
# 적용/비적용 규칙의 근거는 canonical_title docstring 에 있다.
# 여기서는 "적용한다"뿐 아니라 **"적용하지 않는다"도 고정**한다 — 나중에 누가
# 좋은 뜻으로 대문자화·NFC 를 끼워 넣으면 조용히 키가 갈라지기 때문이다.


def test_밑줄을_공백으로_바꾼다():
    """덤프(Hurricane_Milton)와 LIVE(Hurricane Milton)가 같은 문서다."""
    assert canonical_title("Hurricane_Milton") == "Hurricane Milton"
    assert canonical_title("Strait_of_Hormuz") == "Strait of Hormuz"


def test_이미_공백형인_제목은_그대로다():
    """LIVE 경로가 주는 형태. 여기서 값이 바뀌면 안 된다."""
    assert canonical_title("Hurricane Milton") == "Hurricane Milton"
    assert canonical_title("Iran") == "Iran"


def test_연속_구분자는_공백_하나로_줄인다():
    """MediaWiki 실측: Hurricane__Milton -> Hurricane Milton (2026-09-13)."""
    assert canonical_title("Hurricane__Milton") == "Hurricane Milton"
    assert canonical_title("Hurricane _ Milton") == "Hurricane Milton"


def test_앞뒤_구분자를_제거한다():
    assert canonical_title("_Hurricane Milton_") == "Hurricane Milton"
    assert canonical_title("  Hurricane Milton  ") == "Hurricane Milton"


def test_두_번_적용해도_같다():
    """적재본을 다시 읽어 또 정규화해도 값이 흔들리면 안 된다."""
    once = canonical_title("_Hurricane__Milton_")
    assert canonical_title(once) == once == "Hurricane Milton"


def test_첫_글자를_대문자로_바꾸지_않는다():
    """비적용 규칙 고정. 소스가 주는 건 이미 대문자화된 MediaWiki 저장 제목이라
    (`eBay` -> 저장 제목 `EBay`) 우리가 또 할 이유가 없다. 위키별 $wgCapitalLinks
    설정에 달린 규칙이고 enwiki 밖에서는 확인하지 않았다."""
    assert canonical_title("eBay") == "eBay"
    assert canonical_title("iPhone") == "iPhone"


def test_유니코드_정규화를_하지_않는다():
    """비적용 규칙 고정. MediaWiki 가 NFC 로 저장·요구하고 LIVE 표본 2,496건이
    전부 NFC 였다 — 소스가 이미 NFC 라 no-op 이다. 여기서 NFC 를 돌리면 확인하지
    않은 변환이 파이프라인에 들어온다."""
    # 결합문자를 소스에 그대로 두면 편집기·도구가 NFC 로 합쳐버릴 수 있다.
    # 파일 바이트에 기대지 않고 실행 시점에 만든다.
    nfd = unicodedata.normalize("NFD", "Zürich")
    assert nfd != "Zürich", "전제: NFD 와 NFC 가 달라야 이 테스트가 의미 있다"
    assert canonical_title(nfd) == nfd


def test_한글_제목도_그대로_통과한다():
    """kowiki 를 켰을 때 제목이 망가지지 않는지. 구분자만 건드려야 한다."""
    assert canonical_title("호르무즈_해협") == "호르무즈 해협"
