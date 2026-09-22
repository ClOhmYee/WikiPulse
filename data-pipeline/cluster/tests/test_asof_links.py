"""as-of 링크 추출·정규화·수집 (WP-161). **네트워크를 타지 않는다.**

HTTP 는 `session_factory` 로 주입한다 — 실 요청을 하는 테스트는 CI 에서 불안정하고,
위키미디어에 대한 예의도 아니다.
"""

from __future__ import annotations

import pytest

from cluster.asof_links import (
    WikipediaLinkFetcher,
    is_ns0,
    link_key,
    wikitext_links,
)


# --- 정규화 ------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Hurricane_Milton", "Hurricane Milton"),
    ("Hurricane__Milton", "Hurricane Milton"),
    ("  Hurricane Milton  ", "Hurricane Milton"),
    ("_Hurricane Milton_", "Hurricane Milton"),
    ("", ""),
])
def test_link_key_normalizes_separators(raw, expected):
    assert link_key(raw) == expected


def test_link_key_uppercases_first_letter():
    """🔴 `canonical_title` 과 다른 지점. 링크 타깃은 사람이 쓴 문자열이고 MediaWiki 가
    첫 글자를 대문자로 해석한다 — `[[eBay]]` 는 `EBay` 문서다.

    비교 양쪽에 같은 함수를 걸어야 맞물린다. 한쪽만 걸면 간선이 **에러 없이** 사라진다.
    """
    assert link_key("eBay") == "EBay"
    assert link_key("dolly Parton") == "Dolly Parton"
    # 이미 대문자인 제목은 그대로 — no-op 이어야 한다.
    assert link_key("Dolly Parton") == "Dolly Parton"
    # 둘째 글자 이후는 건드리지 않는다.
    assert link_key("iPhone") == "IPhone"


@pytest.mark.parametrize("target,ok", [
    ("Hurricane Milton", True),
    ("Apollo 11: The Movie", True),          # 접두가 알려진 ns 가 아니면 ns0 다
    ("File:Foo.png", False),
    ("Category:Hurricanes", False),
    ("Template:Infobox", False),
    ("fr:Ouragan", False),                    # 인터위키 언어코드
    ("commons:Foo", False),
    (":Interwiki", False),
    ("#Section", False),
    ("", False),
])
def test_is_ns0(target, ok):
    assert is_ns0(target) is ok


def test_wikitext_links_extracts_literal_links_only():
    wikitext = (
        "[[Dolly Parton]] recorded [[Jolene|the song]] in [[Nashville, Tennessee]].\n"
        "See also [[File:Dolly.jpg]] and [[Category:Country music]].\n"
        "{{Infobox person|spouse=[[Carl Dean]]}}\n"
        "<ref>[[The Guardian]]</ref>\n"
        "Anchor link [[Dollywood#History]].\n"
    )
    assert wikitext_links(wikitext) == [
        "Carl Dean", "Dolly Parton", "Dollywood", "Jolene",
        "Nashville, Tennessee", "The Guardian",
    ]


def test_wikitext_links_deduplicates_and_sorts():
    assert wikitext_links("[[A]] [[a]] [[B]] [[A|x]]") == ["A", "B"]


def test_wikitext_links_on_empty_input():
    assert wikitext_links("") == []


# --- 수집 --------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    """요청을 기록하고 미리 정해 둔 응답을 돌려준다."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        return self._responses.pop(0)


def _fetcher(responses, **kw):
    session = FakeSession(responses)
    fetcher = WikipediaLinkFetcher(
        user_agent="WikiPulse/test (contact)", session_factory=lambda: session,
        sleep=lambda _s: None, **kw)
    return fetcher, session


def test_fetch_one_uses_oldid_and_wikitext():
    """🔴 `prop=wikitext` 다. `parse.links` 를 쓰면 템플릿이 현재 판이라 미래가 샌다."""
    fetcher, session = _fetcher([
        FakeResponse({"parse": {"title": "Dolly Parton",
                                "wikitext": "[[Dollywood]] [[File:x.png]]"}})])
    title, links, error = fetcher.fetch_one(1234)

    assert (title, links, error) == ("Dolly Parton", ["Dollywood"], None)
    _url, params, headers = session.calls[0]
    assert params["oldid"] == 1234
    assert params["prop"] == "wikitext"
    assert "links" not in params["prop"]
    assert params["maxlag"] == "5"
    assert headers["User-Agent"] == "WikiPulse/test (contact)"


def test_fetch_one_retries_on_503_then_succeeds():
    fetcher, _ = _fetcher([
        FakeResponse({}, status_code=503, headers={"Retry-After": "0"}),
        FakeResponse({"parse": {"title": "A", "wikitext": "[[B]]"}}),
    ])
    assert fetcher.fetch_one(1) == ("A", ["B"], None)


def test_fetch_one_retries_on_maxlag():
    fetcher, _ = _fetcher([
        FakeResponse({"error": {"code": "maxlag"}}),
        FakeResponse({"parse": {"title": "A", "wikitext": ""}}),
    ])
    assert fetcher.fetch_one(1) == ("A", [], None)


def test_fetch_one_reports_permanent_api_error_without_retry():
    fetcher, session = _fetcher([FakeResponse({"error": {"code": "nosuchrevid"}})])
    title, links, error = fetcher.fetch_one(1)
    assert (title, links) == ("", [])
    assert error == "api nosuchrevid"
    assert len(session.calls) == 1          # 영구 오류는 재시도하지 않는다


def test_fetch_one_gives_up_after_max_attempts():
    fetcher, session = _fetcher(
        [FakeResponse({}, status_code=503, headers={"Retry-After": "0"})] * 3,
        max_attempts=3)
    _title, _links, error = fetcher.fetch_one(1)
    assert error.startswith("retries exhausted")
    assert len(session.calls) == 3


def test_fetch_many_deduplicates_revisions():
    fetcher, session = _fetcher(
        [FakeResponse({"parse": {"title": "A", "wikitext": "[[B]]"}})], workers=1)
    got = fetcher.fetch_many([7, 7, 7])
    assert list(got) == [7]
    assert len(session.calls) == 1


def test_fetch_many_on_empty_input_makes_no_request():
    fetcher, session = _fetcher([])
    assert fetcher.fetch_many([]) == {}
    assert session.calls == []
