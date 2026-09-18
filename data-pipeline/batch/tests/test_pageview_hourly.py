"""`other/pageviews` 시간별 덤프 파싱 검증 (WP-127). 네트워크 없이 돈다.

실제 줄은 2026-09-18 04:00Z 파일에서 가져왔다.
"""

from __future__ import annotations

import pytest

from batch.pageview import SchemaMismatch, UnsupportedWiki
from batch.pageview_hourly import (
    PageviewHourly,
    aggregate,
    parse_row,
    projects_for,
    ts_hour_from_filename,
)

EN = projects_for("enwiki")


# ---------------------------------------------------------------- 시각

def test_시각은_파일명에서_온다():
    """🔴 행에는 시각 컬럼이 없다. 파일과 시각을 잘못 짝지으면 전부 밀리고 에러도 안 난다."""
    assert ts_hour_from_filename("pageviews-20260918-040000.gz") == "2026-09-18T04:00:00"
    assert ts_hour_from_filename("/tmp/cache/pageviews-20250612-230000.gz") == "2025-06-12T23:00:00"


def test_시각을_못_읽으면_막는다():
    with pytest.raises(SchemaMismatch):
        ts_hour_from_filename("pageviews-2026-09-18.gz")


# ---------------------------------------------------------------- project

def test_데스크톱과_모바일을_둘_다_받는다():
    assert projects_for("enwiki") == frozenset({"en", "en.m"})


def test_미등록_위키는_막는다():
    with pytest.raises(UnsupportedWiki):
        projects_for("kowiki")


def test_자매_프로젝트는_안_받는다():
    """🔴 `en.d`(wiktionary)·`en.b`(wikibooks)는 같은 `en` 으로 시작하지만 다른 위키다.

    받으면 조회수가 부풀고 에러는 안 난다. 2026-09-18 한 시간 파일에 en 계열이 16종
    있었고 en.d 만 92,769행이었다.
    """
    assert parse_row("en.d Water 40 0", EN) is None
    assert parse_row("en.b Cookbook 10 0", EN) is None
    assert parse_row("en.m.d Water 5 0", EN) is None


def test_다른_언어_위키는_안_받는다():
    assert parse_row("ja Water 100 0", EN) is None


# ---------------------------------------------------------------- 행 파싱

def test_실제_줄을_읽는다():
    assert parse_row("en !!!_(album) 1 0", EN) == ("!!! (album)", 1)
    assert parse_row("en.m Air_India_Flight_171 268 0", EN) == ("Air India Flight 171", 268)


def test_제목은_canonical_공백형으로_나온다():
    """편집 덤프·LIVE 와 같은 키여야 조인이 된다 (WP-79)."""
    assert parse_row("en Hurricane_Milton 500 0", EN) == ("Hurricane Milton", 500)


def test_ns0가_아니면_뺀다():
    for title in ("Category:Indexed_pages", "User_talk:Someone", "Special:Search",
                  "Talk:Water", "File:A.png"):
        assert parse_row(f"en {title} 9 0", EN) is None


def test_canonical이_빈_문자열이_되는_행은_뺀다():
    """`_` 같은 행이 실제로 있다 (2026-09-18 04:00Z 파일에 5회).

    두면 제목이 빈 wiki_page 행이 생기고, 그 행은 어느 편집과도 조인되지 않는다.
    """
    assert parse_row("en _ 5 0", EN) is None
    assert parse_row("en __ 5 0", EN) is None


def test_퍼센트가_든_제목을_디코드하지_않는다():
    """⚠️ `%` 는 percent-encoding 이 아니라 문자 그대로인 경우가 대부분이다.

    한 시간 파일에 85행(조회수 264, 0.00%)이 있었고 전부 `1%_rule`·`%s` 꼴이었다
    (2026-09-18 실측). 디코드하면 그런 제목이 깨진다.
    """
    assert parse_row("en 1%_rule 2 0", EN) == ("1% rule", 2)
    assert parse_row("en %s 21 0", EN) == ("%s", 21)


def test_제목_없음_행은_뺀다():
    """`-` 는 무관 문서가 뭉친 값이다 (일별 덤프와 같은 규칙)."""
    assert parse_row('en - 3 0', EN) is None


def test_컬럼_수가_다르면_막는다():
    """형식이 바뀌면 조용히 다른 값을 읽는다 — 멈추는 쪽이 맞다."""
    with pytest.raises(SchemaMismatch):
        parse_row("en Water 40", EN)
    with pytest.raises(SchemaMismatch):
        parse_row("en Water 40 0 extra", EN)


def test_조회수가_정수가_아니면_막는다():
    with pytest.raises(SchemaMismatch):
        parse_row("en Water four 0", EN)


# ---------------------------------------------------------------- 합산

def test_데스크톱과_모바일이_한_행으로_합쳐진다():
    """한 문서가 `en` 과 `en.m` 두 행으로 온다. 안 합치면 조회수가 절반씩 갈린다."""
    rows = list(aggregate(
        ["en Air_India_Flight_171 268 0", "en.m Air_India_Flight_171 732 0"],
        "enwiki", "2025-06-12T09:00:00"))
    assert rows == [PageviewHourly("enwiki", "Air India Flight 171",
                                   "2025-06-12T09:00:00", 1_000)]


def test_표기가_다른_같은_문서도_한_키다():
    rows = list(aggregate(["en Hurricane_Milton 3 0", "en.m Hurricane__Milton 4 0"],
                          "enwiki", "2024-10-06T19:00:00"))
    assert rows == [PageviewHourly("enwiki", "Hurricane Milton",
                                   "2024-10-06T19:00:00", 7)]


def test_빈_줄은_건너뛴다():
    rows = list(aggregate(["en Water 5 0", "", "   "], "enwiki", "2025-06-12T09:00:00"))
    assert [r.views for r in rows] == [5]


def test_후보_문서만_남길_수_있다():
    """⚠️ enwiki ns0 만 시간당 약 190만 행이다. 2단계 계약에서 조회수를 봐야 하는 건
    1단계를 통과한 문서뿐이라, 그 집합으로 거르는 게 정상 경로다."""
    lines = ["en Water 10 0", "en Air_India_Flight_171 268 0", "en Cat 7 0"]
    rows = list(aggregate(lines, "enwiki", "2025-06-12T09:00:00",
                          titles=frozenset({"Air India Flight 171"})))
    assert rows == [PageviewHourly("enwiki", "Air India Flight 171",
                                   "2025-06-12T09:00:00", 268)]


def test_필터_제목도_canonical로_비교한다():
    """호출자가 밑줄형 집합을 주면 한 건도 안 걸리는데, 그게 "조회수 0" 으로 읽힌다.

    ⚠️ 그래서 필터는 canonical 공백형으로 준다는 계약이다 — 여기서 그 계약을 고정한다.
    """
    lines = ["en Hurricane_Milton 500 0"]
    assert list(aggregate(lines, "enwiki", "2024-10-06T19:00:00",
                          titles=frozenset({"Hurricane Milton"})))
    assert not list(aggregate(lines, "enwiki", "2024-10-06T19:00:00",
                              titles=frozenset({"Hurricane_Milton"})))


def test_필터가_없으면_전부_나온다():
    lines = ["en Water 10 0", "en Cat 7 0"]
    assert len(list(aggregate(lines, "enwiki", "2025-06-12T09:00:00"))) == 2
