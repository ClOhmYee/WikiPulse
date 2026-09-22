"""CORE — 같은 스냅샷의 급증 root 를 사건 단위 component 로 묶는다 (WP-186).

MVP 정본 규칙. **여기서 끝이다** — 이 모듈이 낸 component 가 곧 issue cluster 이고,
그 안의 root 가 곧 cluster_member 다.

    같은 스냅샷의 spike root
    + strict historical as-of direct Wikipedia link (한 방향이라도)
    → connected component
    → sym focus τ=0.005 로 약한 bridge 억제
    → D2 directional bridge 억제

🔴 **넣지 않는 것** (전부 실측 근거가 있다. 이름만 보고 되살리지 말 것)

    common-neighbor expansion   PoC 7 B1~B4. precision 미달로 불채택.
    Clickstream                 membership 조건 아님. 절대 이동량으로는 사건/배경이
                                안 갈린다 (명세 §11: Hormuz 배경 문서 `Choke_point` 가
                                진짜 사건 문서보다 30배 더 클릭됨).
    resurgence / 생성일 창       CORE 생성 규칙 아님. 보존은 하되 기본 OFF
                                (`snapshot.build_snapshot(expansion=...)`).
    embedding · LLM · 복합 score 쓰지 않는다.
    절대 링크 수 문턱            hub 판정에 쓰지 않는다. PoC 1 에서 p90 절대 기준이
                                Dolly 를 14+2 로 쪼갠 것이 이 결정의 근거다.

이 모듈은 **순수 함수뿐이다.** 네트워크·DB·Spark 의존이 없고 제목 하드코딩이 없다.
링크 수집은 `asof_links.py`, 배선은 `driver.py` 몫이다.

전체 1,104 스냅샷 회귀 기준값은 `tests/test_rootgraph.py` 와 README 에 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: sym focus 문턱. 이 밑이면 "이 문서에게 스냅샷 내 이웃은 곁가지" 로 보고
#: 약한 bridge 만 끊는다. PoC 2~5 에서 고정한 값 — 바꾸면 분포 회귀가 깨진다.
DEFAULT_FOCUS_TAU = 0.005

#: D2 — 실제로 떼어 낼 조각이 이 수 이상일 때만 directional 억제를 발동한다.
#: 1(=D1)은 곁가지 하나만 갈려도 발동해 과하다. 2 는 "H 하나가 셋 이상의 가지를
#: 합치고 있다" 가 분명한 경우로 한정하는 보수 변종이다.
DEFAULT_MIN_DETACH = 2


@dataclass(frozen=True)
class CoreResult:
    """한 스냅샷의 CORE 산출물. 인덱스는 입력 root 리스트의 위치다."""
    components: tuple[tuple[int, ...], ...]
    kept_edges: tuple[tuple[int, int], ...]
    removed_focus: tuple[tuple[int, int], ...]
    removed_directional: tuple[tuple[int, int], ...]


# --- 기본 그래프 -------------------------------------------------------------

def build_edges(keys: list[str], linksets: list[set[str]]) -> list[tuple[int, int]]:
    """A→B 또는 B→A 중 한 방향이라도 direct link 면 무방향 간선.

    🔴 **한 방향으로 충분하다.** 아웃링크가 0 인 정상 멤버가 있다 — Dolly 의
    `Straight Talk`·`Nashville, Tennessee` 가 그렇다. 아웃링크를 멤버 필수조건으로
    만들면 그 문서들이 통째로 빠진다. 방향성은 **bridge 자격에서만** 본다
    (`suppress_directional`).

    `keys` 와 `linksets` 는 **같은 정규화**를 거친 값이어야 한다
    (`asof_links.link_key`). 한쪽만 정규화하면 간선이 에러 없이 사라진다.
    """
    n = len(keys)
    edges: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if keys[j] in linksets[i] or keys[i] in linksets[j]:
                edges.append((i, j))
    return edges


def adjacency(n: int, edges: list[tuple[int, int]]) -> dict[int, set[int]]:
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    return adj


def components(nodes: list[int], adj: dict[int, set[int]]) -> list[list[int]]:
    """연결 요소. 각 요소는 정렬된 인덱스 목록, 요소 순서는 `nodes` 첫 등장 순.

    ⚠️ `adj` 는 `nodes` 전부를 키로 가져야 한다. 부분 그래프를 넘길 때 키를 빠뜨리면
    KeyError 가 아니라 **조용히 다른 결과**가 나오는 자리라 호출부에서 맞춰 만든다.
    """
    seen: set[int] = set()
    out: list[list[int]] = []
    for start in nodes:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        out.append(sorted(comp))
    return out


def _reach(start: int, adj: dict[int, set[int]]) -> list[int]:
    seen, stack = {start}, [start]
    while stack:
        v = stack.pop()
        for w in adj[v]:
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return sorted(seen)


def _views_of(views: list[int | None], nodes: list[int]) -> int:
    """조각의 대표 조회수. None 은 0 으로 본다(값이 없는 것과 0 을 여기선 구분 안 한다)."""
    return max((views[x] or 0) for x in nodes)


# --- focus 억제 --------------------------------------------------------------

def focus_ratios(keys: list[str], linksets: list[set[str]],
                 edges: list[tuple[int, int]]) -> list[float | None]:
    """root 별 link 집중도 = 스냅샷 내 무방향 degree / 전체 아웃링크 수.

    분모 0 이면 `None` — 링크가 아예 없다는 뜻이라 outgoing edge 도 0 이고 남은
    degree 는 전부 incoming 이다. **자료가 없는 것을 "집중도가 낮다" 로 읽으면 안 되므로
    hub 후보에서 뺀다**(보수적). Dolly 의 `Straight Talk` 가 여기 해당한다.

    ⚠️ 분자는 **무방향 degree**(sym)다. PoC 2 의 `out` 변종(나가는 링크만 셈)은
    "남이 나를 가리키기만 하는 문서" 를 전부 focus 0 으로 만들어 대조군으로만 쟀다 —
    정본이 아니라서 포팅하지 않았다. 분모는 어차피 as-of 아웃링크뿐이다
    (as-of backlink 은 API 로 못 얻는다).
    """
    n = len(keys)
    degree = [0] * n
    for u, v in edges:
        degree[u] += 1
        degree[v] += 1
    total = [len(s) for s in linksets]
    return [(degree[i] / total[i]) if total[i] > 0 else None for i in range(n)]


def suppress_focus(n: int, edges: list[tuple[int, int]], ratios: list[float | None],
                   tau: float, views: list[int | None]):
    """집중도가 낮은 노드가 **서로 다른 조각을 잇고 있을 때** 약한 쪽 간선만 끊는다.

    🔴 **노드는 절대 지우지 않는다.** v 는 그대로 한 사건의 멤버로 남고, 다만 v 하나로
    두 사건이 합쳐지지는 못한다. 노드를 지우면 급증 판정을 통과한 문서가 화면에서
    사라진다 — 그건 클러스터링이 아니라 데이터 손실이다.

    ratio 가 낮은 노드부터 하나씩 처리하고 **매번 그래프를 다시 본다.** 한 번에 여러
    노드를 처리하면 앞 처리로 끊긴 그래프를 반영하지 못해 과하게 끊긴다.

    returns (kept_edges, removed_edges)
    """
    adj = adjacency(n, edges)
    removed: list[tuple[int, int]] = []

    while True:
        cands = [v for v in range(n)
                 if ratios[v] is not None and ratios[v] < tau and len(adj[v]) >= 2]
        # 집중도 오름차순 → degree 내림차순 → 인덱스. 인덱스가 마지막 결정자라
        # 같은 입력이면 항상 같은 순서다(재계산 호환).
        cands.sort(key=lambda v: (ratios[v], -len(adj[v]), v))
        fired = False
        for v in cands:
            comp = _reach(v, adj)
            rest = [x for x in comp if x != v]
            sub = {x: (adj[x] & set(rest)) for x in rest}
            pieces = components(rest, sub)
            touched = [p for p in pieces if any(x in adj[v] for x in p)]
            if len(touched) < 2:
                continue                     # v 를 빼도 안 갈린다 — bridge 가 아니다
            best = max(touched, key=lambda p: (sum(1 for x in p if x in adj[v]),
                                               _views_of(views, p)))
            for piece in touched:
                if piece is best:
                    continue                 # v 가 가장 강하게 붙은 조각은 남긴다
                for x in piece:
                    if x in adj[v]:
                        adj[v].discard(x)
                        adj[x].discard(v)
                        removed.append((min(v, x), max(v, x)))
            fired = True
            break
        if not fired:
            break

    kept = sorted({(min(u, v), max(u, v)) for u in adj for v in adj[u]})
    return kept, removed


# --- D2 directional 억제 ------------------------------------------------------

def suppress_directional(n: int, edges: list[tuple[int, int]], keys: list[str],
                         linksets: list[set[str]], views: list[int | None],
                         min_detach: int = DEFAULT_MIN_DETACH):
    """멤버 자격과 bridge 자격의 방향성을 분리한다. **숫자 문턱 없음.**

    멤버 자격은 무방향 그대로다(`build_edges`). 여기서만 방향을 본다 — 노드 H 를 빼서
    component 가 여러 조각으로 갈릴 때, H 가 그 조각을 **한 사건으로 합치는 근거**로
    인정되는 것은 `H → 조각의 어떤 노드` 방향 링크가 있을 때뿐이다. `조각 → H` 만 있는
    incoming-only 관계는 멤버로는 남지만 합치는 데는 못 쓴다.

    H 가 아무 조각에도 근거가 없으면 **가장 직접적으로 붙은 조각 하나**에 멤버로
    남기고 나머지만 떼어 낸다. 여기서도 노드는 지우지 않는다.

    `min_detach=2`(D2) — 실제로 떼어 낼 조각이 둘 이상일 때만 발동한다.

    returns (kept_edges, removed_edges, fired)
    """
    adj = adjacency(n, edges)
    removed: list[tuple[int, int]] = []
    fired: list[tuple[int, list[list[int]]]] = []

    def vouches(h: int, piece: list[int]) -> bool:
        """H 가 이 조각에 **나가는** 링크를 갖고 있는가."""
        return any(keys[x] in linksets[h] for x in piece if x in adj[h])

    while True:
        cands = []
        for h in range(n):
            if len(adj[h]) < 2:
                continue
            comp = _reach(h, adj)
            rest = [x for x in comp if x != h]
            sub = {x: (adj[x] - {h}) for x in rest}
            pieces = components(rest, sub)
            if len(pieces) < 2:
                continue
            # 조각 수 → degree → 인덱스(작은 쪽 우선). `-h, h` 가 유일해서 정렬이
            # `pieces` 까지 내려가지 않는다 — 리스트 비교로 새는 자리를 막아 둔 것이다.
            cands.append((len(pieces), len(adj[h]), -h, h, pieces))
        cands.sort(reverse=True)

        hit = None
        for _n_pieces, _degree, _neg_h, h, pieces in cands:
            vouched = [p for p in pieces if vouches(h, p)]
            unvouched = [p for p in pieces if not vouches(h, p)]
            if not vouched:
                keep = max(unvouched, key=lambda p: (sum(1 for x in p if x in adj[h]),
                                                     _views_of(views, p),
                                                     -min(p)))
                unvouched = [p for p in unvouched if p is not keep]
            if len(unvouched) < min_detach:
                continue
            hit = (h, unvouched)
            break

        if hit is None:
            break
        h, detach = hit
        for piece in detach:
            for x in piece:
                if x in adj[h]:
                    adj[h].discard(x)
                    adj[x].discard(h)
                    removed.append((min(h, x), max(h, x)))
        fired.append((h, detach))

    kept = sorted({(min(u, v), max(u, v)) for u in adj for v in adj[u]})
    return kept, removed, fired


# --- CORE --------------------------------------------------------------------

def core(keys: list[str], linksets: list[set[str]], views: list[int | None],
         *, tau: float = DEFAULT_FOCUS_TAU,
         min_detach: int = DEFAULT_MIN_DETACH) -> CoreResult:
    """한 스냅샷의 root 를 사건 component 로 묶는다. MVP 정본.

    `keys[i]` 는 root i 의 정규화 제목, `linksets[i]` 는 그 root 의 as-of strict
    아웃링크 집합(같은 정규화), `views[i]` 는 판정 당시 조회수(없으면 None).

    링크를 못 구한 root 는 **빈 집합**을 넘긴다 — 간선이 안 생겨 singleton 이 된다.
    🔴 현재 판 링크로 폴백하지 않는다. 그건 미래 정보 누수다.

    같은 입력이면 항상 같은 결과다(재계산 호환). 순서 의존은 전부 인덱스로 결정된다.
    """
    if not (len(keys) == len(linksets) == len(views)):
        raise ValueError("keys·linksets·views 의 길이가 같아야 한다")
    n = len(keys)
    edges = build_edges(keys, linksets)
    ratios = focus_ratios(keys, linksets, edges)
    after_focus, removed_focus = suppress_focus(n, edges, ratios, tau, views)
    kept, removed_directional, _ = suppress_directional(
        n, after_focus, keys, linksets, views, min_detach)
    comps = components(list(range(n)), adjacency(n, kept))
    return CoreResult(
        components=tuple(tuple(c) for c in comps),
        kept_edges=tuple(kept),
        removed_focus=tuple(removed_focus),
        removed_directional=tuple(removed_directional),
    )
