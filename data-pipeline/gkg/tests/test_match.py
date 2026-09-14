"""기관명 → ticker 정규화 매칭 검증."""

from __future__ import annotations

from gkg.match import build_ticker_index, match_ticker, normalize_name


def test_normalize_strips_legal_suffixes_and_punct():
    assert normalize_name("Duke Energy Corporation") == "duke energy"
    assert normalize_name("Apple Inc.") == "apple"
    assert normalize_name("The Home Depot, Inc.") == "home depot"
    assert normalize_name("Frontline plc") == "frontline"


def test_normalize_is_symmetric_for_matching():
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    # GKG 기관명(소문자·접미어 없음)이 정식 상호로 매칭된다.
    assert match_ticker("duke energy", index) == "DUK"
    assert match_ticker("Duke Energy", index) == "DUK"


def test_no_substring_false_positive():
    # 부분문자열 매칭이면 "meta" 가 "meta platforms" 에 걸린다 — 정확일치라 안 걸림.
    index = build_ticker_index([("META", "Meta Platforms Inc")])
    assert match_ticker("meta", index) is None
    assert match_ticker("meta platforms", index) == "META"


def test_unmatched_org_returns_none():
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    assert match_ticker("national hurricane center", index) is None


def test_index_keeps_first_on_collision():
    # 정규화가 같은 두 티커면 먼저 온(티커 정렬상 앞) 것을 남긴다.
    index = build_ticker_index([("AAA", "Example Group"), ("BBB", "Example Holdings")])
    assert index["example"] == "AAA"


def test_empty_normalization_not_indexed():
    # 접미어만으로 된 이름은 정규화가 비어 색인에서 빠진다.
    index = build_ticker_index([("X", "The Group"), ("DUK", "Duke Energy")])
    assert "" not in index
    assert match_ticker("The Group", index) is None
