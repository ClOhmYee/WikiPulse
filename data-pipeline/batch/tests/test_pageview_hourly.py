"""`other/pageviews` 시간별 덤프 파싱 검증 (WP-127). 네트워크 없이 돈다.

실제 줄은 2026-09-18 04:00Z 파일에서 가져왔다.
"""

from __future__ import annotations

import pytest

from batch.pageview import SchemaMismatch, UnsupportedWiki
from batch.pageview_hourly import (
    safe_row_floor,
    scan_titles,
    PageviewHourly,
    aggregate,
    filename_hour,
    parse_row,
    projects_for,
    ts_hour_from_filename,
)

TS_HOUR = "2026-09-21T14:00:00"
EN = projects_for("enwiki")


# ---------------------------------------------------------------- 시각

def test_파일명_시각은_윈도우_끝이라_한_시간을_뺀다():
    """🔴 `-090000` 은 09시가 아니라 **08:00~09:00** 이다 (2026-09-18 실측).

    근거 — `Air India Flight 171` (2025-06-12, 문서 생성 08:58:02 UTC):
      일별 pageview_complete 프로파일  08시 3회 · 09시 24,669회 · 22시 26,757회
      시간별 `-090000` = 3회      -> 일별 08시(생성 후 2분치)와 일치
      시간별 `-230000` = 26,757회 -> 일별 22시와 일치
    ~~파일명 시각을 그대로 썼다~~ → 모든 조회수가 한 시간 늦게 붙었다. 값이 그럴듯해서
    화면만 봐서는 모른다 — 2단계 관문이 엉뚱한 시간의 조회수로 판정하게 된다.
    """
    assert ts_hour_from_filename("pageviews-20260918-040000.gz") == "2026-09-18T03:00:00"
    assert ts_hour_from_filename("/tmp/cache/pageviews-20250612-230000.gz") == "2025-06-12T22:00:00"


def test_자정_파일은_전날_23시다():
    """⚠️ 날짜가 넘어간다. 하루 경계에서 하루치가 통째로 어긋나는 자리다."""
    assert ts_hour_from_filename("pageviews-20250612-000000.gz") == "2025-06-11T23:00:00"


def test_파일명_변환이_왕복한다():
    """한쪽만 고치면 조용히 어긋난다 — 두 함수를 같은 파일에 둔 이유다."""
    for name in ("pageviews-20250612-000000.gz", "pageviews-20250612-090000.gz",
                 "pageviews-20261231-230000.gz"):
        start = ts_hour_from_filename(name)
        date, hour = filename_hour(start)
        assert f"pageviews-{date}-{hour}0000.gz" == name.split("/")[-1]


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
    assert parse_row("en !!!_(album) 1 0", EN) == ("!!! (album)", 1, False)
    assert parse_row("en.m Air_India_Flight_171 268 0", EN) == ("Air India Flight 171", 268, True)


def test_제목은_canonical_공백형으로_나온다():
    """편집 덤프·LIVE 와 같은 키여야 조인이 된다 (WP-79)."""
    assert parse_row("en Hurricane_Milton 500 0", EN) == ("Hurricane Milton", 500, False)


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
    assert parse_row("en 1%_rule 2 0", EN) == ("1% rule", 2, False)
    assert parse_row("en %s 21 0", EN) == ("%s", 21, False)


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
                                   "2025-06-12T09:00:00", 1_000, 732)]


def test_표기가_다른_같은_문서도_한_키다():
    rows = list(aggregate(["en Hurricane_Milton 3 0", "en.m Hurricane__Milton 4 0"],
                          "enwiki", "2024-10-06T19:00:00"))
    assert rows == [PageviewHourly("enwiki", "Hurricane Milton",
                                   "2024-10-06T19:00:00", 7, 4)]


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
                                   "2025-06-12T09:00:00", 268, 0)]


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


# ------------------------------------------------ 모바일 몫 (WP-210)

def test_모바일_몫을_따로_남긴다():
    """🔴 봇은 데스크톱 단일 채널로 온다. 합산만 하고 버리면 다시 못 얻는다.

    `Roblox` 2026-08-10 은 478만 조회(674배)인데 모바일이 0.1% 였다(평소 60%).
    같은 파일 안에 있는 값이라 적재 때 남기면 공짜다 — 버리면 문서마다 AQS 를
    때려야 하고 거기서 429 가 난다. 근거: ai/spec-evidence/gate-review/RESULT.md.
    """
    rows = list(aggregate(
        ["en Roblox 4777498 0", "en.m Roblox 3746 0"],
        "enwiki", "2026-08-10T12:00:00"))
    assert rows == [PageviewHourly("enwiki", "Roblox", "2026-08-10T12:00:00",
                                   4_781_244, 3_746)]
    assert rows[0].mobile_ratio < 0.01


def test_모바일_몫은_views_에_포함된_부분집합이다():
    """⚠️ 빼는 값이 아니다. 빼는 쪽으로 오해하면 조회수가 조용히 절반이 된다."""
    rows = list(aggregate(
        ["en Air_India_Flight_171 268 0", "en.m Air_India_Flight_171 732 0"],
        "enwiki", "2025-06-12T09:00:00"))
    row = rows[0]
    assert row.views == 1_000                 # 합
    assert row.mobile_views == 732            # 그중 모바일
    assert row.mobile_views <= row.views
    assert row.mobile_ratio == pytest.approx(0.732)


def test_모바일_행이_없으면_0_이다():
    rows = list(aggregate(["en Water 5 0"], "enwiki", "2025-06-12T09:00:00"))
    assert rows[0].mobile_views == 0
    assert rows[0].mobile_ratio == 0.0


def test_조회수가_0_이면_비율은_None_이다():
    """0 으로 두면 '봇' 과 구분되지 않는다 — 판정하는 쪽이 갈라 봐야 한다."""
    assert PageviewHourly("enwiki", "Water", "2025-06-12T09:00:00", 0, 0).mobile_ratio is None


def test_m_접미사만_모바일로_센다():
    """⚠️ `en` 에 붙는 다른 변종이 생겨도 데스크톱으로 오분류되지 않게 `.m` 만 본다."""
    assert parse_row("en.m Water 5 0", EN)[2] is True
    assert parse_row("en Water 5 0", EN)[2] is False


# ------------------------------- 기준선용 하한 (WP-212)

def test_하한을_주면_후보가_아니어도_남는다():
    """🔴 후보 문서만 남기면 page_baseline 을 만들 이력이 안 쌓인다."""
    lines = ["en Popular_Doc 400 0", "en.m Popular_Doc 300 0", "en Tail_Doc 3 0"]
    rows = list(aggregate(lines, "enwiki", TS_HOUR, titles=None, min_views=100))
    assert [r.title for r in rows] == ["Popular Doc"]
    assert rows[0].views == 700


def test_하한과_후보는_OR_이다():
    """🔴 대체가 아니다. 후보는 하한을 못 넘어도 남겨야 재판정이 된다 —
    빠지면 그 대기가 영영 안 풀린다."""
    lines = ["en Popular_Doc 400 0", "en Waiting_Doc 3 0", "en Other 5 0"]
    waiting = frozenset({"Waiting Doc"})
    scan = scan_titles(lines, "enwiki", min_views=100) | waiting
    rows = list(aggregate(lines, "enwiki", TS_HOUR,
                          titles=scan, min_views=100, candidates=waiting))
    assert sorted(r.title for r in rows) == ["Popular Doc", "Waiting Doc"]


def test_candidates_없이는_하한이_무력화되지_않는다():
    """🔴 `titles` 로 후보 판정을 하면 합산된 제목이 전부 그 안이라 아무것도 안 걸러진다.

    이 함정을 테스트가 실제로 잡았다 — `candidates` 를 따로 둔 이유다.
    """
    lines = ["en Tail_A 60 0", "en Tail_B 55 0"]
    scan = scan_titles(lines, "enwiki", min_views=100)      # 둘 다 행 60·55 >= 50
    assert scan == frozenset({"Tail A", "Tail B"})
    rows = list(aggregate(lines, "enwiki", TS_HOUR, titles=scan, min_views=100))
    assert rows == []                                       # 합계는 둘 다 100 미만


def test_하한은_행이_아니라_합계로_본다():
    """⚠️ 데스크톱 60 · 모바일 70 은 합 130 이라 통과해야 한다.
    행 단위로 보면 둘 다 100 미만이라 빠진다."""
    lines = ["en Split_Doc 60 0", "en.m Split_Doc 70 0"]
    rows = list(aggregate(lines, "enwiki", TS_HOUR, titles=None, min_views=100))
    assert [(r.title, r.views) for r in rows] == [("Split Doc", 130)]


def test_하한이_없으면_기존_동작_그대로():
    lines = ["en A 3 0", "en B 5 0"]
    assert len(list(aggregate(lines, "enwiki", TS_HOUR))) == 2


# --- 1패스 문턱 ---

def test_1패스_문턱은_project_수로_나눈_올림이다():
    """🔴 추측이 아니라 비둘기집 원리다. enwiki 는 `en`·`en.m` 둘이라 합이 100
    이상이면 둘 중 하나가 반드시 50 이상이다."""
    assert safe_row_floor("enwiki", 100) == 50
    assert safe_row_floor("enwiki", 101) == 51


def test_1패스는_문턱_넘는_행이_있는_제목만_남긴다():
    lines = ["en Big 60 0", "en.m Small 8 0", "en Small 10 0", "en.m Only_Mobile 55 0"]
    assert scan_titles(lines, "enwiki", min_views=100) == frozenset({"Big", "Only Mobile"})


def test_1패스가_버린_문서는_합쳐도_하한에_못_미친다():
    """문턱의 안전성을 값으로 고정한다 — 경계에서 새면 조용히 문서를 잃는다."""
    floor = safe_row_floor("enwiki", 100)
    lines = [f"en Edge {floor - 1} 0", f"en.m Edge {floor - 1} 0"]
    assert scan_titles(lines, "enwiki", min_views=100) == frozenset()
    assert (floor - 1) * 2 < 100
