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


def test_술어는_차원_하나는_있어야():
    with pytest.raises(ValueError):
        IssuePredicate()


def test_테마는_코드의_부분문자열로_매칭():
    p = IssuePredicate(themes=("HURRICANE",))
    assert p.matches(rec([], themes=["NATURAL_DISASTER_HURRICANE"]))
    assert not p.matches(rec([], themes=["ECON_STOCKMARKET"]))


def test_테마항_소문자여도_매칭된다():
    # docstring 이 약속한 대소문자 무시 — 술어 항 입력이 소문자여도 걸려야 한다.
    p = IssuePredicate(themes=("hurricane",))
    assert p.matches(rec([], themes=["NATURAL_DISASTER_HURRICANE"]))


def test_테마와_지역은_AND():
    p = IssuePredicate(themes=("HURRICANE",), locations=("florida",))
    assert p.matches(rec([], ["NATURAL_DISASTER_HURRICANE"], ["florida, united states"]))
    # 테마만 맞고 지역이 다르면 이슈 아님.
    assert not p.matches(rec([], ["NATURAL_DISASTER_HURRICANE"], ["texas"]))
    # 지역만 맞고 테마가 다르면 이슈 아님.
    assert not p.matches(rec([], ["ECON_STOCKMARKET"], ["florida"]))


def test_지역은_단어경계로_매칭_term은_대소문자무시():
    # record.locations 는 parse 가 소문자로 만든다(불변식). term 쪽은 대문자로 줘도
    # 소문자화해 매칭한다.
    p = IssuePredicate(locations=("Florida",))
    assert p.matches(rec([], locations=["west palm beach, florida, united states"]))
    assert p.matches(rec([], locations=["florida"]))


def test_지역_부분문자열_오탐을_막는다():
    # florida 가 실지명 floridablanca(콜롬비아·필리핀)를 통과시키면 안 된다.
    p = IssuePredicate(locations=("florida",))
    assert not p.matches(rec([], locations=["floridablanca, colombia"]))


# --- 집계·산식 -------------------------------------------------------------


def test_lift_산식():
    # 이슈 40% 노출, 코퍼스 10% 노출 → lift 4.0
    assert compute_lift(4, 10, 10, 100) == pytest.approx(4.0)


def test_lift_상한과_1미만():
    # 이슈 기사에만 나오는 기관: lift = n_corpus/n_issue (상한)
    assert compute_lift(10, 10, 10, 100) == pytest.approx(10.0)
    # 코퍼스 전반에 퍼진 기관: lift < 1
    assert compute_lift(2, 80, 10, 100) < 1.0


def test_lift_방향이_명세_신호와_일치():
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


def test_min_issue_count_경계():
    # 컷은 issue_count < min. min=3 이면 정확히 3 은 남고 2 는 빠진다(off-by-one 방어).
    p = IssuePredicate(themes=("X",))
    records = [rec(["keep"], ["X"]) for _ in range(3)]        # keep 이슈 3건
    records += [rec(["drop"], ["X"]) for _ in range(2)]       # drop 이슈 2건
    names = {o.org_name for o in rank(aggregate(records, p), min_issue_count=3)}
    assert "keep" in names and "drop" not in names


def test_동점은_issue_count_그다음_이름순():
    # lift 가 같으면 issue_count 큰 순, 그것도 같으면 이름 오름차순(안정 정렬).
    p = IssuePredicate(themes=("X",))
    records = []
    # a·b 는 이슈 기사에만 나와 lift 상한 동률. a 가 issue_count 더 큼.
    for _ in range(3):
        records.append(rec(["a"], ["X"]))
    records.append(rec(["a", "b"], ["X"]))   # a 이슈 4, b 이슈 1
    records.append(rec(["c"], ["X"]))        # c 이슈 1 (b 와 동률 → 이름순 b<c)
    ranked = [o.org_name for o in rank(aggregate(records, p), min_issue_count=1)]
    assert ranked.index("a") < ranked.index("b")   # issue_count 우선
    assert ranked.index("b") < ranked.index("c")   # 이름 오름차순


def test_이슈_기사가_없으면_랭킹은_빈_리스트():
    p = IssuePredicate(themes=("HURRICANE",))
    agg = aggregate([rec(["x"], ["ECON"])], p)  # 이슈 술어 통과 0건
    assert rank(agg) == []


def test_top_N_으로_자른다():
    p = IssuePredicate(themes=("X",))
    records = [rec([f"org{i}" for i in range(j)], ["X"]) for j in range(1, 6)]
    agg = aggregate(records, p)
    assert len(rank(agg, min_issue_count=1, top=2)) == 2


# --- 병합(Spark reduce) ----------------------------------------------------


def test_병합은_단일패스와_같다():
    p = IssuePredicate(themes=("X",))
    left = [rec(["a", "b"], ["X"]), rec(["a"], ["Y"])]
    right = [rec(["a"], ["X"]), rec(["c"], ["X"])]

    whole = aggregate(left + right, p)
    merged = aggregate(left, p).merge(aggregate(right, p))

    assert merged.n_issue == whole.n_issue
    assert merged.n_corpus == whole.n_corpus
    assert merged.org_issue == whole.org_issue
    assert merged.org_corpus == whole.org_corpus


def test_병합은_결합법칙_N개_순서무관():
    # Spark reduce 는 파티션 N개(>2)를 임의 순서로 접는다 — 결합·순서 불변이어야 한다.
    p = IssuePredicate(themes=("X",))
    a = aggregate([rec(["x", "y"], ["X"])], p)
    b = aggregate([rec(["x"], ["X"]), rec(["z"], ["Y"])], p)
    c = aggregate([rec(["y"], ["X"]), rec(["x"], ["X"])], p)
    whole = aggregate(
        [rec(["x", "y"], ["X"]), rec(["x"], ["X"]), rec(["z"], ["Y"]),
         rec(["y"], ["X"]), rec(["x"], ["X"])], p)

    def fresh():
        return (aggregate([rec(["x", "y"], ["X"])], p),
                aggregate([rec(["x"], ["X"]), rec(["z"], ["Y"])], p),
                aggregate([rec(["y"], ["X"]), rec(["x"], ["X"])], p))

    a1, b1, c1 = fresh()
    left_fold = a1.merge(b1).merge(c1)          # (a·b)·c
    a2, b2, c2 = fresh()
    right_fold = a2.merge(b2.merge(c2))          # a·(b·c)

    for m in (left_fold, right_fold):
        assert m.n_issue == whole.n_issue
        assert m.n_corpus == whole.n_corpus
        assert m.org_issue == whole.org_issue
        assert m.org_corpus == whole.org_corpus


def test_병합은_파일_회계도_합친다():
    left = Aggregate(files=2, empty_files=1)
    right = Aggregate(files=3, empty_files=0)
    merged = left.merge(right)
    assert merged.files == 5
    assert merged.empty_files == 1
