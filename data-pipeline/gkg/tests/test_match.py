"""기관명 → ticker 정규화 매칭 검증."""

from __future__ import annotations

from gkg.match import build_ticker_index, match_ticker, normalize_name


def test_정규화는_법인격_접미어와_구두점을_뗀다():
    assert normalize_name("Duke Energy Corporation") == "duke energy"
    assert normalize_name("Apple Inc.") == "apple"
    assert normalize_name("The Home Depot, Inc.") == "home depot"
    assert normalize_name("Frontline plc") == "frontline"


def test_정규화는_겹친_접미어도_반복해_뗀다():
    # docstring 이 겨냥한 "... co inc" 겹침 — while 루프가 2개 연속을 다 벗겨야 한다.
    assert normalize_name("Toyota Motor Co Ltd") == "toyota motor"
    assert normalize_name("Example Co Inc") == "example"


def test_정규화가_대칭이라_매칭된다():
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    # GKG 기관명(소문자·접미어 없음)이 정식 상호로 매칭된다.
    assert match_ticker("duke energy", index) == "DUK"
    assert match_ticker("Duke Energy", index) == "DUK"


def test_부분문자열_오탐이_없다():
    # 부분문자열 매칭이면 "meta" 가 "meta platforms" 에 걸린다 — 정확일치라 안 걸림.
    index = build_ticker_index([("META", "Meta Platforms Inc")])
    assert match_ticker("meta", index) is None
    assert match_ticker("meta platforms", index) == "META"


def test_미매칭_기관은_None():
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    assert match_ticker("national hurricane center", index) is None


def test_색인은_충돌_시_먼저_온_것을_남긴다():
    # 정규화가 같은 두 티커면 먼저 온(티커 정렬상 앞) 것을 남긴다.
    index = build_ticker_index([("AAA", "Example Group"), ("BBB", "Example Holdings")])
    assert index["example"] == "AAA"


def test_빈_정규화는_색인하지_않는다():
    # 접미어만으로 된 이름은 정규화가 비어 색인에서 빠진다.
    index = build_ticker_index([("X", "The Group"), ("DUK", "Duke Energy")])
    assert "" not in index
    assert match_ticker("The Group", index) is None
