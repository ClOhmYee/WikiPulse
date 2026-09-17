"""클러스터 생산 순수 로직 검증 (WP-75). Spark·DB 없이 돈다.

§11 실측 사건을 축약해 게이트가 실제로 사건 문서만 묶고 배경 문서를 거르는지,
issue_key·first_detected·HOT·sizeScore·간선이 계약대로 나오는지 본다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from cluster.score import SCORE_VERSION, size_score
from cluster.snapshot import (
    DEFAULT_HOT_SPIKE_THRESHOLD,
    Neighbor,
    Seed,
    WikidataRelation,
    build_snapshot,
    issue_key_of,
)

UTC = timezone.utc


def _dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def _seed(page_id=1, wiki="enwiki", title="Strait of Hormuz",
          event=date(2025, 6, 12), spike=9.7, **kw):
    return Seed(
        page_id=page_id, wiki=wiki, title=title, event_date=event, spike_score=spike,
        window_start=_dt(2025, 6, 12), window_end=_dt(2025, 6, 12, 4), **kw,
    )


# ---------------------------------------------------------------- 게이트

def test_생성일_창_안의_이웃만_묶인다():
    """§11 Hormuz: 사건 문서(+11일)는 들어오고 배경 지리 문서는 창 밖이라 빠진다."""
    seed = _seed()
    neighbors = {1: [
        # 진짜 사건 문서 — 사건일 +11일 생성, 창(±30) 안
        Neighbor(page_id=2, wiki="enwiki",
                 title="2025 Iran threat of Strait of Hormuz closure",
                 clickstream_n=383, clickstream_month="2025-06", created_at=_dt(2025, 6, 23)),
        # 배경 지리 문서 — 이동량은 30배 크지만(11,778) 2009년 생성, 창 밖
        Neighbor(page_id=3, wiki="enwiki", title="Choke point",
                 clickstream_n=11778, clickstream_month="2025-06", created_at=_dt(2009, 1, 1)),
    ]}
    snap = build_snapshot(_dt(2025, 7, 1), "live", [seed], neighbors)

    cluster = snap.clusters[0]
    member_ids = {m.page_id for m in cluster.members}
    assert member_ids == {1, 2}, "사건 문서만 씨드와 함께 묶여야 한다"
    assert 3 not in member_ids, "이동량이 커도 창 밖 배경 문서는 빠진다"


def test_스냅샷_이후_생성된_이웃은_소급_포함하지_않는다():
    """과거 스냅샷 재계산에 나중에 생긴 문서가 섞이면 시점 지도가 바뀌는 버그를 막는다."""
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Future article",
                 clickstream_n=383, clickstream_month="2025-05", created_at=_dt(2025, 6, 23)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1}


def test_같은날_스냅샷_이후_생성된_이웃도_제외한다():
    """날짜만 비교하면 같은 UTC 날짜의 미래 생성 문서가 과거 시간대에 섞인다."""
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Later today",
                 clickstream_n=383, clickstream_month="2025-05",
                 created_at=_dt(2025, 6, 12, 6)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1}


def test_같은날_스냅샷_이전에_생성된_이웃은_포함한다():
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Earlier today",
                 clickstream_n=383, clickstream_month="2025-05",
                 created_at=_dt(2025, 6, 12, 4)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1, 2}


def test_스냅샷_당월_clickstream은_과거_근거로_쓰지_않는다():
    """월이 끝나기 전에는 완성되지 않은 당월 Clickstream을 사용할 수 없다."""
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Same-month article",
                 clickstream_n=383, clickstream_month="2025-06", created_at=_dt(2025, 6, 12)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 30, 23), "live", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1}


@pytest.mark.parametrize("evidence_month", ["2025-07", "invalid", "2025-13"])
def test_미래이거나_잘못된_clickstream_월은_제외한다(evidence_month):
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Invalid evidence",
                 clickstream_n=383, clickstream_month=evidence_month,
                 created_at=_dt(2025, 6, 12)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 30, 23), "live", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1}


def test_다음달_스냅샷은_완료된_전월_clickstream을_쓴다():
    """6월 덤프가 완성된 뒤의 7월 스냅샷에는 6월 이웃을 편입할 수 있다."""
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="June article",
                 clickstream_n=383, clickstream_month="2025-06", created_at=_dt(2025, 6, 23)),
    ]}

    cluster = build_snapshot(_dt(2025, 7, 1), "live", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1, 2}


def test_clickstream_월_경계는_UTC로_판정한다():
    """KST 7월이어도 UTC가 아직 6월이면 6월 덤프는 당월 근거다."""
    kst = timezone(timedelta(hours=9))
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="June article",
                 clickstream_n=383, clickstream_month="2025-06",
                 created_at=_dt(2025, 6, 12)),
    ]}
    snapshot_ts = datetime(2025, 7, 1, 0, 30, tzinfo=kst)

    cluster = build_snapshot(snapshot_ts, "live", [seed], neighbors).clusters[0]

    assert {m.page_id for m in cluster.members} == {1}


def test_스냅샷_시각은_timezone_aware여야_한다():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_snapshot(datetime(2025, 6, 12, 5), "live", [_seed()], {})


def test_이동량은_문턱이_아니라_weight로만_쓴다():
    """작은 이동량(n=10)도 생성일 창 안이면 들어온다. 포함은 창이 정한다."""
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Low traffic sibling",
                 clickstream_n=10, clickstream_month="2025-05", created_at=_dt(2025, 6, 15)),
    ]}
    cluster = build_snapshot(_dt(2025, 6, 16), "live", [seed], neighbors).clusters[0]
    nb = next(m for m in cluster.members if m.page_id == 2)
    assert nb.weight == 10.0
    assert nb.is_seed is False


def test_생성일_미상_이웃은_포함하지_않는다():
    seed = _seed()
    neighbors = {1: [
        Neighbor(page_id=2, wiki="enwiki", title="Unknown creation",
                 clickstream_n=500, clickstream_month="2025-05", created_at=None),
    ]}
    cluster = build_snapshot(_dt(2025, 6, 16), "live", [seed], neighbors).clusters[0]
    assert {m.page_id for m in cluster.members} == {1}


# ---------------------------------------------------------------- 멤버·점수

def test_씨드는_지표와_sizeScore를_고정한다():
    seed = _seed(spike=9.7, edit_count=47, views=91000, completeness="complete")
    cluster = build_snapshot(_dt(2025, 6, 12, 5), "live", [seed], {}).clusters[0]
    m = cluster.members[0]
    assert m.is_seed is True
    assert m.edit_count == 47
    assert m.spike_score == 9.7
    assert m.size_score == size_score(9.7)          # 0~1 절대 척도
    assert 0 < m.size_score < 1


def test_비씨드_멤버는_sizeScore가_None이다():
    """원시 급증 점수가 없으니 None. 화면은 작은 점선 노드로 그린다(0과 구분)."""
    seed = _seed()
    neighbors = {1: [Neighbor(page_id=2, wiki="enwiki", title="Sibling",
                              clickstream_n=200, clickstream_month="2025-05",
                              created_at=_dt(2025, 6, 20))]}
    cluster = build_snapshot(_dt(2025, 6, 21), "live", [seed], neighbors).clusters[0]
    nb = next(m for m in cluster.members if m.page_id == 2)
    assert nb.size_score is None
    assert nb.spike_score is None
    assert nb.completeness == "unavailable"


def test_pulse_score는_씨드_급등도다():
    cluster = build_snapshot(_dt(2025, 6, 12, 5), "live", [_seed(spike=9.7)], {}).clusters[0]
    assert cluster.pulse_score == 9.7


# ---------------------------------------------------------------- HOT / issue_key

def test_HOT은_급등도_임계로_정해진다():
    hot = build_snapshot(_dt(2025, 6, 12, 5), "live",
                         [_seed(spike=DEFAULT_HOT_SPIKE_THRESHOLD + 1)], {}).clusters[0]
    cold = build_snapshot(_dt(2025, 6, 12, 5), "live",
                          [_seed(spike=DEFAULT_HOT_SPIKE_THRESHOLD - 1)], {}).clusters[0]
    assert hot.hot is True
    assert cold.hot is False


def test_issue_key는_씨드_자연키로_시점간_안정():
    seed = _seed()
    key = issue_key_of("live", seed)
    assert key == "live:enwiki:Strait of Hormuz"
    # 다른 시각의 같은 씨드는 같은 key
    a = build_snapshot(_dt(2025, 6, 12), "live", [seed], {}).clusters[0]
    b = build_snapshot(_dt(2025, 6, 13), "live", [seed], {}).clusters[0]
    assert a.issue_key == b.issue_key == key


def test_first_detected는_과거값을_잇는다():
    seed = _seed()
    key = issue_key_of("live", seed)
    first = _dt(2025, 6, 10)
    cluster = build_snapshot(
        _dt(2025, 6, 13), "live", [seed], {},
        prior_first_detected={key: first},
    ).clusters[0]
    assert cluster.first_detected_at == first


def test_first_detected_없으면_이번_스냅샷():
    ts = _dt(2025, 6, 13)
    cluster = build_snapshot(ts, "live", [_seed()], {}).clusters[0]
    assert cluster.first_detected_at == ts


# ---------------------------------------------------------------- 간선

def test_clickstream_간선은_방향과_월근거를_갖는다():
    seed = _seed()
    neighbors = {1: [Neighbor(page_id=2, wiki="enwiki", title="Sibling",
                              clickstream_n=383, clickstream_month="2025-05",
                              created_at=_dt(2025, 6, 20), directed=True)]}
    cluster = build_snapshot(_dt(2025, 6, 21), "live", [seed], neighbors).clusters[0]
    e = next(e for e in cluster.edges if e.kind == "clickstream")
    assert (e.source_page_id, e.target_page_id) == (1, 2)
    assert e.directed is True
    assert e.weight == 383.0
    assert e.evidence_month == "2025-05"
    assert e.evidence_observed_at is None


def test_wikidata_간선은_멤버_사이에만_점선으로():
    seed = _seed()
    neighbors = {1: [Neighbor(page_id=2, wiki="enwiki", title="Member",
                              clickstream_n=383, clickstream_month="2025-05",
                              created_at=_dt(2025, 6, 20))]}
    wikidata = {1: [
        WikidataRelation(target_page_id=2, label="P361 부분", observed_at=_dt(2025, 6, 20)),
        # page 9 는 멤버가 아니다 — 간선을 만들면 안 된다
        WikidataRelation(target_page_id=9, label="P17 국가", observed_at=_dt(2025, 6, 20)),
    ]}
    cluster = build_snapshot(_dt(2025, 6, 21), "live", [seed], neighbors, wikidata).clusters[0]
    wd = [e for e in cluster.edges if e.kind == "wikidata"]
    assert len(wd) == 1
    assert wd[0].target_page_id == 2
    assert wd[0].directed is False
    assert wd[0].evidence_observed_at == _dt(2025, 6, 20)
    assert wd[0].evidence_month is None


def test_스냅샷_이후_관측한_wikidata_간선은_소급_포함하지_않는다():
    seed = _seed()
    neighbors = {1: [Neighbor(page_id=2, wiki="enwiki", title="Member",
                              clickstream_n=383, clickstream_month="2025-05",
                              created_at=_dt(2025, 6, 20))]}
    wikidata = {1: [
        WikidataRelation(target_page_id=2, label="Future relation",
                         observed_at=_dt(2026, 9, 11)),
    ]}

    cluster = build_snapshot(_dt(2025, 6, 21), "replay", [seed], neighbors, wikidata).clusters[0]

    assert [e for e in cluster.edges if e.kind == "wikidata"] == []


# ---------------------------------------------------------------- 스냅샷

def test_같은_문서가_두_클러스터에_한_번씩():
    """서로 다른 씨드의 공통 이웃은 각 클러스터에 한 번씩 들어간다(계약)."""
    s1 = _seed(page_id=1, title="Seed A", event=date(2025, 6, 12))
    s2 = _seed(page_id=5, title="Seed B", event=date(2025, 6, 12))
    shared = Neighbor(page_id=2, wiki="enwiki", title="Shared", clickstream_n=100,
                      clickstream_month="2025-05", created_at=_dt(2025, 6, 15))
    snap = build_snapshot(_dt(2025, 6, 16), "live", [s1, s2],
                          {1: [shared], 5: [shared]})
    assert snap.cluster_count == 2
    for c in snap.clusters:
        assert 2 in {m.page_id for m in c.members}


def test_빈_스냅샷도_유효하다():
    snap = build_snapshot(_dt(2025, 6, 16), "live", [], {})
    assert snap.cluster_count == 0
    assert snap.score_version == SCORE_VERSION


def test_source는_live_replay만():
    with pytest.raises(ValueError):
        build_snapshot(_dt(2025, 6, 16), "prod", [], {})
