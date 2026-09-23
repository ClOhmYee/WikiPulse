"""클러스터 → GKG 술어 변환 테스트. WP-148.

기준은 명세 §11 의 Milton 실측이다: `I = HURRICANE ∧ florida` 로 이슈 기사를 고르면
FPL 10.5 · Generac 9.3 · Duke 8.4 · Publix 7.0 이 나오고 무관한 Nvidia 는 0.4 다.
여기서는 그 **술어를 사람 없이 뽑아내는지**를 본다.
"""

from __future__ import annotations

import pytest

from gkg.lift import IssuePredicate, aggregate, rank
from gkg.parse import Record
from gkg.predicate import (
    Member,
    Vocabulary,
    _theme_candidates,
    derive,
    describe,
    title_terms,
)


def rec(doc_id: str, orgs=(), themes=(), locations=()) -> Record:
    return Record(
        doc_id=doc_id,
        orgs=frozenset(orgs),
        themes=tuple(themes),
        locations=tuple(locations),
    )


# --- title_terms ------------------------------------------------------------


def test_title_terms_drops_structure_words_and_years():
    assert title_terms("Effects of Hurricane Milton in Florida") == (
        "hurricane", "milton", "florida")
    # 연도·괄호 한정어는 테마 코드에도 지역에도 없다.
    assert title_terms("Hurricane Milton (2024)") == ("hurricane", "milton")


def test_title_terms_drops_short_tokens():
    """3글자는 부분문자열 매칭에서 무관한 코드에 광범위하게 걸린다."""
    assert "oil" not in title_terms("Oil spill")


# --- Vocabulary -------------------------------------------------------------


def test_vocabulary_counts_documents_not_mentions():
    """한 기사가 같은 테마를 두 번 달아도 문서빈도는 1이다."""
    vocab = Vocabulary.from_records([
        rec("a", themes=("NATURAL_DISASTER_HURRICANE", "NATURAL_DISASTER_HURRICANE")),
        rec("b", themes=("NATURAL_DISASTER_HURRICANE",)),
    ])
    assert vocab.n_docs == 2
    assert vocab.themes["NATURAL_DISASTER_HURRICANE"] == 2


def test_vocabulary_merge_is_additive():
    left = Vocabulary.from_records([rec("a", themes=("X",), locations=("florida",))])
    right = Vocabulary.from_records([rec("b", themes=("X",), locations=("texas",))])
    merged = left.merge(right)
    assert merged.n_docs == 2
    assert merged.themes["X"] == 2
    assert merged.locations == {"florida": 1, "texas": 1}


# --- 핵심: Milton 모양을 뽑아내는가 ------------------------------------------


def milton_corpus() -> list[Record]:
    """Milton 코퍼스의 축소 모형. 비율은 §11 의 구조를 따른다.

    - 이슈 기사: HURRICANE 테마 ∧ florida 지역
    - 같은 테마지만 다른 지역(텍사스 허리케인) — 지역 축이 걸러야 한다
    - 같은 지역이지만 다른 테마(플로리다 일반 기사) — 테마 축이 걸러야 한다
    - 무관 기사 — 둘 다 아니다
    """
    records: list[Record] = []
    for i in range(20):
        records.append(rec(
            f"issue-{i}",
            orgs=("florida power & light", "duke energy"),
            themes=("NATURAL_DISASTER_HURRICANE", "MANMADE_DISASTER_IMPLIED"),
            locations=("florida, united states", "tampa, florida, united states"),
        ))
    for i in range(10):
        records.append(rec(
            f"other-hurricane-{i}",
            orgs=("centerpoint energy",),
            themes=("NATURAL_DISASTER_HURRICANE",),
            locations=("texas, united states",),
        ))
    for i in range(10):
        records.append(rec(
            f"other-florida-{i}",
            orgs=("disney",),
            themes=("TAX_FNCACT", "ECON_STOCKMARKET"),
            locations=("florida, united states",),
        ))
    for i in range(60):
        records.append(rec(
            f"noise-{i}",
            orgs=("nvidia",),
            themes=("ECON_STOCKMARKET",),
            locations=("california, united states",),
        ))
    return records


def milton_members() -> list[Member]:
    return [
        Member("Hurricane Milton", is_seed=True),
        Member("Florida", is_seed=True),
        Member("Tampa", is_seed=False),
    ]


def test_derive_reproduces_milton_predicate():
    """§11 의 `HURRICANE ∧ florida` 를 사람 없이 뽑는다."""
    vocab = Vocabulary.from_records(milton_corpus())
    result = derive(milton_members(), vocab)

    assert result.predicate is not None
    assert "HURRICANE" in result.predicate.themes
    assert "florida" in result.predicate.locations
    # `milton` 은 코퍼스 어휘에 없으므로 술어에 들어가면 안 된다 — 들어가면 0건이 된다.
    assert "MILTON" not in result.predicate.themes


def test_derived_predicate_selects_the_issue_articles():
    """뽑은 술어가 실제로 이슈 기사를 고르고, lift 순위가 §11 모양이 된다.

    이게 이 모듈의 존재 이유다 — 술어를 뽑는 것과 그 술어가 집계에서 먹히는 것은
    다른 일이고, 갈리면 조용히 0건이 된다.
    """
    corpus = milton_corpus()
    vocab = Vocabulary.from_records(corpus)
    predicate = derive(milton_members(), vocab).predicate
    assert predicate is not None

    agg = aggregate(corpus, predicate)
    assert agg.n_issue == 20, "이슈 기사만 정확히 골라야 한다"

    ranked = {o.org_name: o.lift for o in rank(agg, min_issue_count=1)}
    assert "florida power & light" in ranked
    assert "duke energy" in ranked
    # 무관 기관은 이슈 기사에 없으므로 순위에 아예 없다.
    assert "nvidia" not in ranked
    # 같은 테마 다른 지역(텍사스)도 걸러졌다.
    assert "centerpoint energy" not in ranked


# --- 실패 모드 두 가지 -------------------------------------------------------


def test_rejects_unobserved_term_so_predicate_never_selects_zero():
    """코퍼스에 없는 용어는 버린다. 남기면 이슈 기사 0건이 되고 조용히 성공한다."""
    vocab = Vocabulary.from_records([
        rec("a", themes=("NATURAL_DISASTER_HURRICANE",), locations=("florida, united states",)),
    ] * 5)
    result = derive([Member("Kryptonite Incident")], vocab)

    # 관측 안 된 테마·지역은 술어에 들어가지 않는다. 그 자리는 키워드 대체가 맡고
    # (WP-221), 0건 여부는 driver 가 집계 뒤에 막는다.
    assert result.predicate.themes == () and result.predicate.locations == ()
    assert result.predicate.keywords == ("kryptonite incident",)
    assert any("관측되지 않음" in why for _, _, why in result.rejected)


def generic_corpus() -> list[Record]:
    """ECON 테마가 코퍼스 100건 중 90건에 붙은, 신호가 없는 코퍼스."""
    corpus = [rec(f"econ-{i}", themes=("ECON_STOCKMARKET",)) for i in range(90)]
    corpus += [rec(f"x-{i}", themes=("NATURAL_DISASTER_HURRICANE",)) for i in range(10)]
    return corpus


def test_rejects_too_generic_term_so_lift_does_not_flatten():
    """코퍼스 대부분에 걸리는 용어는 버린다. 남기면 lift 가 전부 1 로 수렴한다."""
    vocab = Vocabulary.from_records(generic_corpus())
    result = derive([Member("Econ crisis")], vocab)  # 기본 가드 0.5, ECON 은 90%

    assert "ECON" not in result.predicate.themes
    assert result.predicate.keywords == ("econ crisis",)  # 대체 (WP-221)
    assert any("너무 일반적" in why for _, _, why in result.rejected)


def test_generic_guard_is_configurable():
    """가드를 풀면 통과한다 — 값이 정책이지 물리 법칙이 아님을 고정한다."""
    vocab = Vocabulary.from_records(generic_corpus())
    result = derive([Member("Econ crisis")], vocab, max_corpus_ratio=1.0)
    assert result.predicate is not None
    assert result.predicate.themes == ("ECON",)


def test_event_theme_survives_a_large_share_of_a_short_window():
    """🔴 회귀 고정 — 큰 사건은 짧은 창에서 코퍼스의 상당 비율을 정당하게 차지한다.

    가드를 0.25 로 뒀을 때 Milton 의 `hurricane`(코퍼스의 30%)이 거부돼 진짜 사건
    테마가 통째로 탈락했다(2026-09-20). 축이 AND 로 묶인다는 걸 빼먹은 값이었다.
    """
    vocab = Vocabulary.from_records(milton_corpus())
    support, _ = _theme_candidates("hurricane", vocab)
    assert support / vocab.n_docs > 0.25, "이 표본이 그 함정을 실제로 재현해야 한다"

    assert derive(milton_members(), vocab).predicate is not None


# --- 경계 ------------------------------------------------------------------


def test_empty_corpus_returns_none_not_exception():
    """배치가 클러스터 하나 때문에 죽으면 안 된다."""
    result = derive([Member("Hurricane Milton")], Vocabulary(n_docs=0))
    assert result.predicate is None


def test_never_returns_empty_predicate():
    """`IssuePredicate` 는 양축이 비면 생성자에서 막는다 — 그 전에 None 으로 돌린다."""
    vocab = Vocabulary.from_records([rec("a", themes=("X",))] * 5)
    # 키워드 대체(WP-221)도 못 만드는 제목 — 너무 짧다.
    result = derive([Member("Zz")], vocab)
    assert result.predicate is None
    # 예외가 아니라 None 이어야 한다.
    with pytest.raises(ValueError):
        IssuePredicate()


def test_seed_members_win_ties():
    """동점이면 씨드가 먼저 뽑힌다 — 비-seed 는 재급증으로 끌려온 배경 문서다."""
    # 두 용어의 지지도를 같게 두되(동점), 가드에 걸리지 않게 잡음을 충분히 섞는다.
    corpus = [
        rec(f"a-{i}", themes=("ALPHA_CODE",), locations=("alpha, united states",))
        for i in range(5)
    ] + [
        rec(f"b-{i}", themes=("BETA_CODE",), locations=("beta, united states",))
        for i in range(5)
    ] + [
        rec(f"n-{i}", themes=("UNRELATED_CODE",), locations=("nowhere,",))
        for i in range(40)
    ]
    vocab = Vocabulary.from_records(corpus)
    result = derive(
        [Member("Beta", is_seed=False), Member("Alpha", is_seed=True)],
        vocab, max_themes=1)

    assert result.predicate is not None
    assert result.predicate.themes == ("ALPHA",)


def test_describe_explains_rejections():
    """술어가 비었을 때 왜인지 로그에 남아야 한다."""
    vocab = Vocabulary.from_records([rec("a", themes=("X",))] * 5)
    text = describe(derive([Member("Zzzz")], vocab))
    assert "실패" in text
    assert "버림" in text


def test_rejection_records_which_axis_dropped_the_term():
    """🔴 회귀 고정 — 한 용어가 한 축에서만 떨어지는 건 정상이다.

    `florida` 는 테마 코드엔 없어 테마 축에서 거부되지만 지역 축에서는 채택된다.
    축 없이 찍으면 "술어에 florida 가 있는데 버렸다고도 적혀 있다"가 되어 버그로
    오해한다 (2026-09-20 실데이터 로그).
    """
    vocab = Vocabulary.from_records(milton_corpus())
    result = derive(milton_members(), vocab)

    assert result.predicate is not None
    assert "florida" in result.predicate.locations

    dropped = {(axis, term) for axis, term, _ in result.rejected}
    assert ("테마", "florida") in dropped, "테마 축에서 떨어진 것으로 기록돼야 한다"
    assert ("지역", "florida") not in dropped, "지역 축에서는 채택됐다"

    # 같은 (축, 용어) 가 멤버 수만큼 중복되지 않는다.
    assert len(dropped) == len(result.rejected)

    text = describe(result)
    assert "테마:florida" in text


def test_relative_floor_drops_a_thin_term_in_a_large_corpus():
    """🔴 회귀 고정 — 절대 하한만으로는 큰 코퍼스에서 잡음이 술어에 낀다.

    하루치 실측(160,838 기사)에서 `florida` 가 테마 축에도 붙었는데 걸린 코드가
    `TAX_WORLDREPTILES_FLORIDA_KINGSNAKE` 하나(19건) 였다 — 플로리다 왕뱀이다
    (2026-09-20). 테마는 OR 이라 이런 게 끼면 술어가 넓어진다.
    """
    corpus = [
        rec(f"hur-{i}", themes=("NATURAL_DISASTER_HURRICANE",),
            locations=("florida, united states",))
        for i in range(2000)
    ] + [
        rec(f"snake-{i}", themes=("TAX_WORLDREPTILES_FLORIDA_KINGSNAKE",),
            locations=("florida, united states",))
        for i in range(19)
    ] + [
        rec(f"noise-{i}", themes=("ECON_STOCKMARKET",),
            locations=("california, united states",))
        for i in range(18000)
    ]
    vocab = Vocabulary.from_records(corpus)
    # 코퍼스 20,019 → 비례 하한 20. 왕뱀 코드의 19 건이 그 아래로 떨어진다.
    assert vocab.n_docs == 20019

    result = derive([Member("Hurricane Milton"), Member("Florida")], vocab)
    assert result.predicate is not None
    assert result.predicate.themes == ("HURRICANE",), "왕뱀 코드가 끼면 안 된다"

    dropped = {(axis, term): why for axis, term, why in result.rejected}
    assert "지지도 19" in dropped[("테마", "florida")]


def test_absolute_floor_still_applies_to_a_small_corpus():
    """작은 창에서는 비례 하한이 0 이 되므로 절대 하한이 받쳐야 한다."""
    corpus = [rec(f"a-{i}", themes=("NATURAL_DISASTER_HURRICANE",)) for i in range(2)]
    corpus += [rec(f"n-{i}", themes=("OTHER",)) for i in range(20)]
    vocab = Vocabulary.from_records(corpus)

    result = derive([Member("Hurricane Milton")], vocab)  # 지지도 2 < min_support 3
    # 얇은 테마는 술어에 안 들어간다. 남는 건 키워드 대체다(WP-221).
    assert result.predicate.themes == ()
    assert result.predicate.keywords == ("hurricane milton",)


# --- 키워드 대체 (WP-221) ------------------------------------------

from gkg.predicate import title_keyword  # noqa: E402


def test_title_keyword_drops_qualifier_and_article():
    assert title_keyword("The Odyssey (2026 film)") == "odyssey"
    assert title_keyword("SummerSlam (2026)") == "summerslam"
    assert title_keyword("IMAX") == "imax"
    # 너무 짧거나 불용어뿐이면 버린다.
    assert title_keyword("The (2026)") == ""
    assert title_keyword("Air") == ""


def test_falls_back_to_keywords_when_no_theme_or_location_is_observed():
    """🔴 2026-09-23 시연 이슈 3개가 전부 여기서 None 으로 떨어져 GDELT 경로가 0 이었다."""
    vocab = Vocabulary(n_docs=1000, themes={"NATURAL_DISASTER": 10}, locations={"paris": 5})
    d = derive([Member("SummerSlam (2026)")], vocab)
    assert d.predicate is not None
    assert d.predicate.keywords == ("summerslam",)
    assert d.predicate.themes == () and d.predicate.locations == ()
    assert "키워드" in describe(d)


def test_keyword_fallback_is_not_used_when_theme_and_location_work():
    """재난형(§11 Milton) 동작은 그대로다 — 키워드가 끼면 술어가 바뀐다."""
    vocab = Vocabulary(
        n_docs=10000,
        themes={"NATURAL_DISASTER_HURRICANE": 3000},
        locations={"florida, united states": 2000},
    )
    d = derive([Member("Hurricane Milton"), Member("Florida")], vocab)
    assert d.keywords == ()
    assert d.predicate.keywords == ()


def test_keyword_fallback_uses_seed_titles_first():
    vocab = Vocabulary(n_docs=100)
    d = derive([Member("Background Topic", is_seed=False), Member("IMAX", is_seed=True)], vocab)
    assert d.predicate.keywords == ("imax",)
