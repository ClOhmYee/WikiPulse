"""CORE 기본 경로 — root grouping 이 Cluster/Member 로 옮겨지는지 (WP-161).

`test_rootgraph.py` 가 그래프 규칙을, 여기는 **계약 변환**을 본다:
멤버는 root 뿐인가 · lead/label/issue_key 는 무엇인가 · pulse/hot 은 어떻게 합쳐지는가 ·
expansion 이 정말 꺼져 있는가.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from cluster.snapshot import Neighbor, Seed, build_snapshot, issue_key_of, lead_of

UTC = timezone.utc


def _dt(h=0):
    return datetime(2026, 8, 25, h, tzinfo=UTC)


def _seed(page_id, title, spike=5.0, views=100):
    return Seed(page_id=page_id, wiki="enwiki", title=title,
                event_date=date(2026, 8, 25), spike_score=spike,
                window_start=_dt(19), window_end=_dt(20), views=views,
                max_rev_id=1_000_000 + page_id)


def _snapshot(seeds, links, **kw):
    return build_snapshot(_dt(20), "replay", seeds, root_links=links, **kw)


# --- grouping ----------------------------------------------------------------

def test_linked_roots_become_one_cluster():
    seeds = [_seed(1, "Dolly Parton", spike=9.0), _seed(2, "Dollywood", spike=4.0),
             _seed(3, "Unrelated Person", spike=3.0)]
    snap = _snapshot(seeds, {1: {"Dollywood"}, 2: set(), 3: set()})

    assert snap.cluster_count == 2
    big = next(c for c in snap.clusters if len(c.members) == 2)
    assert {m.page_id for m in big.members} == {1, 2}


def test_every_root_lands_in_exactly_one_cluster():
    seeds = [_seed(i, f"Page {i}") for i in range(1, 6)]
    snap = _snapshot(seeds, {1: {"Page 2"}, 2: set(), 3: {"Page 4"}, 4: set(), 5: set()})
    landed = [m.page_id for c in snap.clusters for m in c.members]
    assert sorted(landed) == [1, 2, 3, 4, 5]


def test_root_without_rev_id_stays_singleton():
    """🔴 `max_rev_id` 가 없으면 현재 판으로 폴백하지 않는다 — 링크 없이 singleton."""
    anchored = _seed(1, "Dolly Parton", spike=9.0)
    unanchored = Seed(page_id=2, wiki="enwiki", title="Dollywood",
                      event_date=date(2026, 8, 25), spike_score=4.0,
                      window_start=_dt(19), window_end=_dt(20), views=10,
                      max_rev_id=None)
    # 링크 맵에 2 번이 아예 없다 — driver.load_root_links 가 그렇게 돌려준다.
    snap = _snapshot([anchored, unanchored], {1: set()})
    assert snap.cluster_count == 2
    assert all(len(c.members) == 1 for c in snap.clusters)


def test_root_links_none_disables_grouping():
    """비상 스위치(`--no-root-grouping`). root 1개 = 클러스터 1개."""
    seeds = [_seed(1, "Dolly Parton"), _seed(2, "Dollywood")]
    snap = build_snapshot(_dt(20), "replay", seeds, root_links=None)
    assert snap.cluster_count == 2


# --- lead / 라벨 / 키 ---------------------------------------------------------

def test_lead_is_max_spike_then_title_desc():
    low = _seed(1, "Aaa", spike=3.0)
    high = _seed(2, "Bbb", spike=9.0)
    tie = _seed(3, "Zzz", spike=9.0)
    assert lead_of([low, high]) is high
    assert lead_of([low, high, tie]) is tie          # 동점이면 제목 내림차순
    assert lead_of([tie, high, low]) is tie          # 입력 순서에 안 흔들린다


def test_label_and_issue_key_come_from_lead():
    seeds = [_seed(1, "Dolly Parton", spike=9.0), _seed(2, "Dollywood", spike=4.0)]
    snap = _snapshot(seeds, {1: {"Dollywood"}, 2: set()})
    cluster = snap.clusters[0]
    assert cluster.label == "Dolly Parton"
    assert cluster.seed_page_id == 1
    assert cluster.issue_key == issue_key_of("replay", seeds[0])
    assert cluster.issue_key == "replay:enwiki:Dolly Parton"


def test_pulse_is_max_and_hot_is_any():
    seeds = [_seed(1, "A", spike=9.0), _seed(2, "B", spike=1.0)]
    snap = _snapshot(seeds, {1: {"B"}, 2: set()}, hot_spike_threshold=5.0)
    assert snap.clusters[0].pulse_score == pytest.approx(9.0)
    assert snap.clusters[0].hot is True

    cool = _snapshot([_seed(1, "A", spike=1.0), _seed(2, "B", spike=2.0)],
                     {1: {"B"}, 2: set()}, hot_spike_threshold=5.0)
    assert cool.clusters[0].hot is False


def test_members_keep_their_own_fixed_metrics():
    """멤버 지표는 판정 당시 값 그대로다 — lead 값으로 덮지 않는다."""
    seeds = [_seed(1, "A", spike=9.0, views=5000), _seed(2, "B", spike=4.0, views=7)]
    snap = _snapshot(seeds, {1: {"B"}, 2: set()})
    by_id = {m.page_id: m for m in snap.clusters[0].members}
    assert by_id[1].views == 5000 and by_id[1].spike_score == pytest.approx(9.0)
    assert by_id[2].views == 7 and by_id[2].spike_score == pytest.approx(4.0)
    # 🔴 전부 root 라 metric window 가 반드시 있다 — 프론트 계약(metric window)의 근거.
    assert all(m.window_start and m.window_end for m in snap.clusters[0].members)


def test_member_order_is_deterministic():
    seeds = [_seed(1, "A", spike=1.0), _seed(2, "B", spike=9.0), _seed(3, "C", spike=5.0)]
    links = {1: {"B", "C"}, 2: set(), 3: set()}
    first = _snapshot(seeds, links).clusters[0]
    second = _snapshot(list(reversed(seeds)), links).clusters[0]
    assert [m.page_id for m in first.members] == [m.page_id for m in second.members]


# --- expansion OFF -----------------------------------------------------------

def _neighbor(page_id):
    return Neighbor(page_id=page_id, wiki="enwiki", title=f"N{page_id}",
                    clickstream_n=4200, clickstream_month="2026-07",
                    created_at=datetime(2026, 8, 24, tzinfo=UTC))


def test_expansion_is_off_by_default():
    """🔴 이웃을 넘겨도 무시한다. 멤버는 root 뿐이고 간선은 없다."""
    seeds = [_seed(1, "A")]
    snap = build_snapshot(_dt(20), "replay", seeds, {1: [_neighbor(99)]},
                          root_links={1: set()})
    assert [m.page_id for m in snap.clusters[0].members] == [1]
    assert snap.clusters[0].edges == ()


def test_expansion_true_still_works_on_top_of_core():
    """레이어는 보존돼 있다 — 켜면 CORE component 의 각 root 에 붙는다."""
    seeds = [_seed(1, "A", spike=9.0), _seed(2, "B", spike=4.0)]
    snap = build_snapshot(_dt(20), "replay", seeds, {2: [_neighbor(99)]},
                          root_links={1: {"B"}, 2: set()}, expansion=True)
    assert snap.cluster_count == 1
    assert {m.page_id for m in snap.clusters[0].members} == {1, 2, 99}
    # 간선은 이웃을 데려온 root(2) 에 달린다 — lead(1) 가 아니다.
    assert [(e.source_page_id, e.target_page_id) for e in snap.clusters[0].edges] == [(2, 99)]


def test_core_members_never_lack_metric_window():
    """expansion OFF 인 한 metric window 가 없는 노드는 나올 수 없다.

    2026-09-22 preview 에서 baseline 5,120 클러스터가 이 값이 없어 펄스맵 렌더에서
    탈락했다. CORE 정본이 root 만 쓰는 이유 중 하나다.
    """
    seeds = [_seed(i, f"P{i}") for i in range(1, 4)]
    snap = build_snapshot(_dt(20), "replay", seeds,
                          {1: [_neighbor(98)], 2: [_neighbor(99)]},
                          root_links={1: {"P2"}, 2: set(), 3: set()})
    for cluster in snap.clusters:
        for member in cluster.members:
            assert member.window_start is not None
            assert member.window_end is not None
            assert member.spike_score is not None
