"""이슈 술어 + lift 집계·랭킹 검증.

lift 산식과 §11 이 관찰한 방향(이슈 종목 lift>1, 무관 종목 lift<1)을 합성
코퍼스로 재현한다. 실 데이터 §11 수치 재현은 driver 를 실 HDFS 에 돌려 확인한다.
"""

from __future__ import annotations

import pytest

from gkg.lift import Aggregate, IssuePredicate, aggregate, compute_lift, rank
from gkg.parse import Record


def rec(orgs, themes=(), locations=()) -> Record:
    return Record(doc_id="d", orgs=frozenset(orgs), themes=tuple(themes),
                  locations=tuple(locations))


# --- 술어 -----------------------------------------------------------------


def test_predicate_needs_a_dimension():
    with pytest.raises(ValueError):
        IssuePredicate()


def test_theme_matches_as_substring_of_code():
    p = IssuePredicate(themes=("HURRICANE",))
    assert p.matches(rec([], themes=["NATURAL_DISASTER_HURRICANE"]))
    assert not p.matches(rec([], themes=["ECON_STOCKMARKET"]))


def test_theme_and_location_are_anded():
    p = IssuePredicate(themes=("HURRICANE",), locations=("florida",))
    assert p.matches(rec([], ["NATURAL_DISASTER_HURRICANE"], ["florida, united states"]))
    # 테마만 맞고 지역이 다르면 이슈 아님.
    assert not p.matches(rec([], ["NATURAL_DISASTER_HURRICANE"], ["texas"]))
    # 지역만 맞고 테마가 다르면 이슈 아님.
    assert not p.matches(rec([], ["ECON_STOCKMARKET"], ["florida"]))


def test_location_matches_case_insensitive_substring():
    p = IssuePredicate(locations=("florida",))
    assert p.matches(rec([], locations=["west palm beach, florida, united states"]))


# --- 집계·산식 -------------------------------------------------------------


def test_compute_lift_formula():
    # 이슈 40% 노출, 코퍼스 10% 노출 → lift 4.0
    assert compute_lift(4, 10, 10, 100) == pytest.approx(4.0)


def test_lift_direction_matches_spec_signal():
    """이슈 기사에 몰린 기관은 lift>1, 전체에 고루 퍼진 기관은 lift<1 (§11)."""
    p = IssuePredicate(themes=("HURRICANE",))
    records = []
    # 이슈 기사 10건: 전부 fpl, 절반 nvidia.
    for i in range(10):
        orgs = ["fpl"] + (["nvidia"] if i % 2 == 0 else [])
        records.append(rec(orgs, themes=["NATURAL_DISASTER_HURRICANE"]))
    # 비이슈 기사 90건: nvidia 가 대부분, fpl 없음.
    for i in range(90):
        records.append(rec(["nvidia"] if i % 3 else [], themes=["ECON_STOCKMARKET"]))

    agg = aggregate(records, p)
    assert agg.n_issue == 10
    assert agg.n_corpus == 100
    lifts = {o.org_name: o for o in rank(agg, min_issue_count=1)}
    # fpl: 이슈 10/10, 코퍼스 10/100 → lift 10
    assert lifts["fpl"].lift == pytest.approx(10.0)
    # nvidia 는 코퍼스 전반에 퍼져 lift < 1
    assert lifts["nvidia"].lift < 1.0
    # 랭킹은 lift 내림차순 — fpl 이 맨 위
    assert rank(agg, min_issue_count=1)[0].org_name == "fpl"


def test_min_issue_count_filters_thin_orgs():
    p = IssuePredicate(themes=("X",))
    records = [rec(["solid"], ["X"]) for _ in range(5)]
    records += [rec(["solid", "thin"], ["X"])]  # thin 은 이슈 기사 1건뿐
    agg = aggregate(records, p)
    names = {o.org_name for o in rank(agg, min_issue_count=3)}
    assert "solid" in names and "thin" not in names


def test_rank_empty_when_no_issue_articles():
    p = IssuePredicate(themes=("HURRICANE",))
    agg = aggregate([rec(["x"], ["ECON"])], p)  # 이슈 술어 통과 0건
    assert rank(agg) == []


def test_top_n_caps_results():
    p = IssuePredicate(themes=("X",))
    records = [rec([f"org{i}" for i in range(j)], ["X"]) for j in range(1, 6)]
    agg = aggregate(records, p)
    assert len(rank(agg, min_issue_count=1, top=2)) == 2


# --- 병합(Spark reduce) ----------------------------------------------------


def test_merge_equals_single_pass():
    p = IssuePredicate(themes=("X",))
    left = [rec(["a", "b"], ["X"]), rec(["a"], ["Y"])]
    right = [rec(["a"], ["X"]), rec(["c"], ["X"])]

    whole = aggregate(left + right, p)
    merged = aggregate(left, p).merge(aggregate(right, p))

    assert merged.n_issue == whole.n_issue
    assert merged.n_corpus == whole.n_corpus
    assert merged.org_issue == whole.org_issue
    assert merged.org_corpus == whole.org_corpus
