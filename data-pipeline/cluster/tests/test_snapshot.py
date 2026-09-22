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
    EditResurgence,
    Neighbor,
    Seed,
    WikidataRelation,
    issue_key_of,
)
from cluster.snapshot import build_snapshot as _build_snapshot

UTC = timezone.utc


def build_snapshot(*args, **kwargs):
    """이 파일은 **legacy expansion 레이어**의 테스트다 (WP-161).

    -161 에서 CORE 가 정본이 되며 `expansion` 기본값이 False 로 바뀌었다. 여기 검증은
    전부 Clickstream 이웃 게이트(-51·-77·-115)에 대한 것이라 레이어를 켜고 돈다.
    CORE 기본 경로는 `test_rootgraph.py`·`test_snapshot_core.py` 가 본다.

    ⚠️ `root_links` 를 주지 않으므로 grouping 은 꺼진 채다 — root 1개 = 클러스터 1개인
    -161 이전 구조 그대로이고, 그래서 아래 기대값이 그대로 유효하다.
    """
    kwargs.setdefault("expansion", True)
    return _build_snapshot(*args, **kwargs)


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
    # 🔴 생성일 창을 통과한 이웃은 **추가 씨드**다 (명세 v0.3 §3.2 4번, -115).
    #    `is_seed=false` 자리는 -77 재급증 문서 몫이고 이 모듈은 그 경로를 안 만든다.
    assert nb.is_seed is True


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


def test_추가_씨드_멤버는_sizeScore가_None이다():
    """원시 급증 점수가 없으니 None. 화면은 작은 점선 노드로 그린다(0과 구분).

    추가 씨드는 detector 를 직접 통과한 문서가 아니라 급증 수치 자체가 없다 —
    `is_seed=true` 라고 해서 루트 씨드와 같은 지표를 갖는 것이 아니다.
    """
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


# ---------------------------------------------------------------- 비-씨드 재급증 (WP-144)

def _resurgence(event_edits, baseline_edits,
                event_start=_dt(2026, 3, 1), days=16):
    """사건기간과 그 **직전 같은 길이** 기준기간. POC 표본의 Iran 구간을 본뜬다."""
    span = timedelta(days=days)
    return EditResurgence(
        event_edits=event_edits,
        baseline_edits=baseline_edits,
        event_start=event_start,
        event_end=event_start + span,
        baseline_start=event_start - span,
        baseline_end=event_start,
    )


def _old_neighbor(page_id, title, resurgence, n=500):
    """2009년 생성 — 생성일 창은 확실히 떨어지는 배경 문서."""
    return Neighbor(
        page_id=page_id, wiki="enwiki", title=title,
        clickstream_n=n, clickstream_month="2026-03",
        created_at=_dt(2009, 1, 1), resurgence=resurgence,
    )


def _iran_snapshot(neighbors):
    seed = _seed(title="2026 Iran war", event=date(2026, 3, 8))
    return build_snapshot(_dt(2026, 4, 1), "live", [seed], {1: neighbors})


def test_재조명_문서는_창밖이어도_비씨드로_편입된다():
    """§11/-77 Mojtaba_Khamenei: 2009 생성이라 창 밖인데 사건기간 19.5배·1,053건."""
    snap = _iran_snapshot([
        _old_neighbor(2, "Mojtaba Khamenei", _resurgence(1053, 54)),
    ])
    members = {m.page_id: m for m in snap.clusters[0].members}

    assert 2 in members, "재급증 게이트를 통과한 배경 문서는 편입돼야 한다"
    assert members[2].is_seed is False, "사건 이전부터 있던 문서는 추가 씨드가 아니다"
    assert members[1].is_seed is True, "루트 씨드는 그대로"


def test_재조명_멤버는_판정_당시_편집수를_복사한다():
    """시점 정합성 — 나중에 최신값으로 보충하면 미래 수치가 과거에 섞인다."""
    r = _resurgence(1053, 54)
    snap = _iran_snapshot([_old_neighbor(2, "Mojtaba Khamenei", r)])
    member = next(m for m in snap.clusters[0].members if m.page_id == 2)

    assert member.edit_count == 1053
    assert member.edit_baseline == 54.0
    assert member.window_start == r.event_start
    assert member.window_end == r.event_end
    assert member.completeness == "unavailable", "조회수 판정을 거친 문서가 아니다"


def test_비율만_높고_절대량이_작으면_탈락한다():
    """-77: Tampa(5.0배·10건)와 Ali_Khamenei(5.0배·700건)가 비율은 동률이다."""
    snap = _iran_snapshot([
        _old_neighbor(2, "Tampa, Florida", _resurgence(10, 2)),      # 5.0배지만 10건
        _old_neighbor(3, "Ali Khamenei", _resurgence(700, 140)),     # 5.0배·700건
    ])
    member_ids = {m.page_id for m in snap.clusters[0].members}

    assert 2 not in member_ids, "절대 편집 20건 미만은 비율이 통과해도 탈락"
    assert 3 in member_ids


def test_절대량이_커도_비율이_낮으면_배경이다():
    """-77: 2024_Atlantic_hurricane_season 828건이지만 1.1배 — 계절성 배경."""
    snap = _iran_snapshot([
        _old_neighbor(2, "2024 Atlantic hurricane season", _resurgence(828, 753)),
        _old_neighbor(3, "Hurricane Helene", _resurgence(459, 1530)),   # 0.3배
    ])
    member_ids = {m.page_id for m in snap.clusters[0].members}

    assert member_ids == {1}, "비율이 5 미만이면 절대량과 무관하게 배경이다"


def test_재급증_입력이_없으면_판정하지_않는다():
    """측정 실패와 '측정했는데 미달'은 다르다 — 근거 없이 편입하지 않는다."""
    snap = _iran_snapshot([_old_neighbor(2, "Choke point", None)])
    assert {m.page_id for m in snap.clusters[0].members} == {1}


def test_기준기간_편집이_적으면_비율을_믿지_않는다():
    """🔴 2026-09-20 실측으로 추가된 기준 하한 (WP-145).

    ~~기준 0 이면 절대 하한만으로 통과~~ 는 폐기됐다 — 기준 0 의 67.5% 가 그 이전에도
    편집 0 이라 **애초에 없던 문서**였다. 기준 1~2 도 비율이 편집 한두 건에 흔들려
    쓸 수 없다(`British philosophy` 867/1 = 867배, 기준이 5 였으면 173배).
    """
    snap = _iran_snapshot([
        _old_neighbor(2, "Rationale for the 2026 Iran war", _resurgence(25, 0)),
        _old_neighbor(3, "British philosophy", _resurgence(867, 1)),
        _old_neighbor(4, "Islamic Revolutionary Guard Corps", _resurgence(47, 7)),
    ])
    member_ids = {m.page_id for m in snap.clusters[0].members}

    assert 2 not in member_ids, "기준 0 은 '조용했다' 가 아니라 '없었다' 다"
    assert 3 not in member_ids, "기준 1 짜리 867배는 믿을 수 없다"
    assert 4 in member_ids, "-77 정답 IRGC(기준 7)는 살아야 한다 — 하한 10 은 이걸 죽인다"


def test_생성일_창을_통과하면_재급증을_보지_않고_추가씨드다():
    """게이트 순서 — 뒤집히면 사건 때문에 새로 생긴 문서가 배경으로 기록된다."""
    seed = _seed(title="2026 Iran war", event=date(2026, 3, 8))
    new_doc = Neighbor(
        page_id=2, wiki="enwiki", title="Kuwait in the 2026 Iran war",
        clickstream_n=12, clickstream_month="2026-03",
        created_at=_dt(2026, 3, 10),                 # 창 안
        resurgence=_resurgence(1, 900),              # 재급증으론 확실히 탈락할 값
    )
    snap = build_snapshot(_dt(2026, 4, 1), "live", [seed], {1: [new_doc]})
    member = next(m for m in snap.clusters[0].members if m.page_id == 2)

    assert member.is_seed is True, "창을 통과했으면 재급증 값과 무관하게 추가 씨드다"
    assert member.edit_count is None, "추가 씨드 경로는 지표를 재지 않는다"


def test_스냅샷_이후_편집은_재급증_근거로_쓰지_않는다():
    """사건기간이 스냅샷을 넘으면 과거 지도에 미래 편집이 섞인다."""
    snap = _iran_snapshot([
        _old_neighbor(2, "Mojtaba Khamenei",
                      _resurgence(1053, 54, event_start=_dt(2026, 4, 1))),
    ])
    assert {m.page_id for m in snap.clusters[0].members} == {1}


def test_기준기간이_사건기간과_겹치면_탈락한다():
    """겹치면 기준선이 사건 자체로 오염돼 비율이 실제보다 낮게 나온다."""
    overlapping = EditResurgence(
        event_edits=1053, baseline_edits=54,
        event_start=_dt(2026, 3, 1), event_end=_dt(2026, 3, 17),
        baseline_start=_dt(2026, 2, 20), baseline_end=_dt(2026, 3, 8),  # 겹침
    )
    snap = _iran_snapshot([_old_neighbor(2, "Mojtaba Khamenei", overlapping)])
    assert {m.page_id for m in snap.clusters[0].members} == {1}


def test_두_구간_길이가_다르면_탈락한다():
    """길이가 다르면 비율이 재급증이 아니라 길이 비를 재는 값이 된다."""
    mismatched = EditResurgence(
        event_edits=1053, baseline_edits=54,
        event_start=_dt(2026, 3, 1), event_end=_dt(2026, 3, 17),   # 16일
        baseline_start=_dt(2026, 2, 27), baseline_end=_dt(2026, 3, 1),  # 2일
    )
    snap = _iran_snapshot([_old_neighbor(2, "Mojtaba Khamenei", mismatched)])
    assert {m.page_id for m in snap.clusters[0].members} == {1}


def test_재조명_멤버도_clickstream_간선을_받는다():
    snap = _iran_snapshot([
        _old_neighbor(2, "Mojtaba Khamenei", _resurgence(1053, 54), n=777),
    ])
    edge = next(e for e in snap.clusters[0].edges if e.target_page_id == 2)

    assert edge.kind == "clickstream"
    assert edge.weight == 777.0
    assert edge.evidence_month == "2026-03"


def test_cluster_label_is_the_seed_title():
    """🔴 회귀 고정 — 루트 씨드 제목이 이슈 이름이다.

    ~~`label=None`~~ 이라 계속 NULL 이었고, 파이프라인 어디에도 채우는 UPDATE 가
    없는데 프론트 `PulseCluster.jsx` 는 `cluster.label` 로 제목을 그린다. 운영에
    4,474 클러스터를 적재하고 나서야 **제목 없는 버블**로 드러났다
    (2026-09-20, WP-149).
    """
    seed = _seed(title="Air India Flight 171")
    snapshot = build_snapshot(_dt(2025, 6, 12, 13), "replay", [seed], {})
    assert snapshot.clusters
    assert snapshot.clusters[0].label == "Air India Flight 171"
