"""CORE 순수 로직 회귀 (WP-186). 네트워크·DB 없음.

`data/core_snapshots.json` 은 실제 replay 스냅샷 5개의 root 와 as-of strict 링크에서
**CORE 계산에 실제로 쓰이는 것만** 뽑아 둔 것이다.

    total_links  as-of 아웃링크 전체 개수 (focus 분모)
    links_to     그 아웃링크 중 **같은 스냅샷 root** 를 가리키는 것만

`build_edges` 와 `vouches` 는 root 제목만 조회하고 focus 는 분모 개수만 쓰므로,
나머지 아웃링크는 개수만 맞춘 더미로 대체해도 결과가 같다(`_linkset` 참조).
덕분에 fixture 가 22 KB 에 머문다 — 원본 링크 캐시는 431 MB 다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cluster import rootgraph

FIXTURES = json.loads(
    (Path(__file__).parent / "data" / "core_snapshots.json").read_text(encoding="utf-8")
)


def _linkset(root: dict) -> set[str]:
    """root 제목을 가리키는 링크 + 개수만 맞춘 더미.

    더미는 `__pad__` 접두라 어떤 root 제목과도 겹치지 않는다 — 겹치면 없던 간선이
    생겨 조용히 다른 결과가 나온다.
    """
    links = set(root["links_to"])
    pad = root["total_links"] - len(links)
    if pad < 0:
        raise AssertionError(f"fixture 손상: {root['title']} links_to > total_links")
    links |= {f"__pad__{root['key']}#{i}" for i in range(pad)}
    return links


def core_of(name: str) -> tuple[rootgraph.CoreResult, list[str]]:
    roots = FIXTURES[name]["roots"]
    keys = [r["key"] for r in roots]
    return (
        rootgraph.core(keys, [_linkset(r) for r in roots], [r["views"] for r in roots]),
        keys,
    )


def sizes(name: str) -> list[int]:
    result, _ = core_of(name)
    return sorted((len(c) for c in result.components), reverse=True)


def component_with(name: str, title: str) -> list[str]:
    result, keys = core_of(name)
    for comp in result.components:
        members = [keys[i] for i in comp]
        if title in members:
            return sorted(members)
    raise AssertionError(f"{title} 이 {name} 에 없다")


# --- 사건별 회귀 --------------------------------------------------------------

def test_dolly_forms_one_component_of_16():
    """Dolly [16]. 여기가 CORE 가 가장 크게 묶는 자리라 회귀가 먼저 드러난다."""
    members = component_with("dolly", "Stella Parton")
    assert len(members) == 16
    for expected in ("Dollywood", "Randy Parton", "Rachel Parton George",
                     "Coat of Many Colors (song)", "Straight Talk",
                     "Nashville, Tennessee", "Reba McEntire"):
        assert expected in members
    # 🔴 아웃링크 0 인 정상 멤버가 살아 있어야 한다 — focus 분모 0 을 "집중도 낮음" 으로
    #    읽으면 이 문서들이 hub 로 몰려 잘려 나간다.
    assert sizes("dolly")[0] == 16


def test_mangione_and_brian_thompson_pair():
    """한 방향 링크만 있어도 묶인다(무방향 membership)."""
    assert component_with("mangione", "Luigi Mangione") == sorted(
        ["Luigi Mangione", "Killing of Brian Thompson"])


def test_summerslam_and_wwe():
    assert component_with("summerslam", "SummerSlam") == sorted(
        ["Nick Aldis", "SummerSlam", "Gunther (wrestler)"])
    wwe = component_with("wwe_0803", "Trick Williams")
    assert len(wwe) == 6
    assert "WWE United States Championship" in wwe
    assert "Chelsea Green" in wwe


def test_quiet_snapshot_stays_all_singleton():
    """조용한 시간대는 묶이지 않는다 — 없는 사건을 만들어 내지 않는다."""
    assert sizes("quiet") == [1] * 20


# --- 구조 불변식 --------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_root_appears_exactly_once(name):
    result, keys = core_of(name)
    flat = [i for comp in result.components for i in comp]
    assert sorted(flat) == list(range(len(keys)))       # 노드 삭제도 중복도 없다


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_giant_component(name):
    """20+ giant 가 다시 생기면 안 된다. 전체 1,104 실측도 giant 0 이다."""
    assert max(len(c) for c in core_of(name)[0].components) < 20


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_deterministic(name):
    """같은 입력이면 같은 결과 — 재계산 호환의 근거."""
    assert core_of(name)[0] == core_of(name)[0]


# --- 규칙 단위 ---------------------------------------------------------------

def test_edge_needs_only_one_direction():
    edges = rootgraph.build_edges(["A", "B", "C"], [{"B"}, set(), set()])
    assert edges == [(0, 1)]


def test_focus_ratio_is_none_when_no_outlinks():
    """아웃링크 0 → None. hub 후보에서 빠진다(자료 없음 ≠ 집중도 낮음)."""
    keys = ["A", "B"]
    ratios = rootgraph.focus_ratios(keys, [{"B"}, set()], [(0, 1)])
    assert ratios[0] == pytest.approx(1.0)
    assert ratios[1] is None


def test_focus_suppression_cuts_weak_bridge_but_keeps_node():
    """generic hub 억제 — 간선만 끊고 노드는 남긴다."""
    # H(2) 가 A·B 와 C·D 를 잇는다. H 는 아웃링크가 많아 집중도가 낮다.
    keys = ["A", "B", "C", "D", "H"]
    hub_links = {"A", "C"} | {f"x{i}" for i in range(2000)}
    linksets = [{"B", "H"}, {"A"}, {"D", "H"}, {"C"}, hub_links]
    views = [10, 10, 5, 5, 1]
    result = rootgraph.core(keys, linksets, views)
    assert len(result.removed_focus) >= 1
    # 노드는 하나도 사라지지 않는다.
    assert sorted(i for c in result.components for i in c) == [0, 1, 2, 3, 4]
    # A·B 와 C·D 가 H 하나로 한 사건이 되지 않는다.
    comps = {frozenset(c) for c in result.components}
    assert not any({0, 1, 2, 3} <= c for c in comps)


def test_directional_needs_two_detachable_pieces():
    """D2 — 떼어 낼 조각이 하나뿐이면 발동하지 않는다."""
    keys = ["A", "B", "H"]
    linksets = [{"H"}, {"H"}, set()]          # incoming-only hub, 조각 2개지만 1개만 detach
    n = len(keys)
    edges = rootgraph.build_edges(keys, linksets)
    _, removed_d2, _ = rootgraph.suppress_directional(
        n, edges, keys, linksets, [1, 1, 1], min_detach=2)
    _, removed_d1, _ = rootgraph.suppress_directional(
        n, edges, keys, linksets, [1, 1, 1], min_detach=1)
    assert removed_d2 == []
    assert removed_d1 != []


def test_empty_linkset_root_becomes_singleton():
    """링크를 못 구한 root 는 singleton. 현재 판으로 폴백하지 않는다."""
    result = rootgraph.core(["A", "B"], [set(), set()], [1, 1])
    assert sorted(len(c) for c in result.components) == [1, 1]


def test_length_mismatch_is_rejected():
    with pytest.raises(ValueError):
        rootgraph.core(["A"], [set(), set()], [1, 1])
