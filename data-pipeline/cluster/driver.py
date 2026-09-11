"""스냅샷 생산 드라이버 — 실 데이터 소스 배선 (WP-75).

이 파일은 골격이다. 순수 로직(snapshot.py)과 저장(writer.py)은 완성돼 테스트되지만,
아래 소스 어댑터는 선행 이슈의 산출물이 붙은 뒤 채운다.

    - 씨드: spike 테이블(WP-38 detector 출력) 조회
    - Clickstream 이웃: 월별 덤프 적재(아직 이슈 없음 — Clickstream 인제스트 선행 필요)
    - 문서 생성일: mediawiki_history page_creation_timestamp(WP-56 적재본)
    - Wikidata 관계: wbgetentities/SPARQL(선택 — 없으면 clickstream 간선만)
    - 이전 first_detected_at: issue_cluster 에서 issue_key 별 min(snapshot_ts)

LIVE 와 리플레이가 같은 build_snapshot 을 쓴다. LIVE 는 현재 시각을 snapshot_ts 로,
리플레이(Spark 배치)는 과거 시점을 넣어 같은 로직을 과거 덤프에 돌린다.

    # LIVE 예시(의사코드)
    seeds = load_seeds_from_spike(conn, snapshot_ts)
    neighbors = {s.page_id: load_clickstream_neighbors(s, month_before(snapshot_ts))
                 for s in seeds}
    created = load_creation_dates([n.page_id for ns in neighbors.values() for n in ns])
    prior = load_prior_first_detected(conn, source="live")
    snap = build_snapshot(snapshot_ts, "live", seeds, neighbors,
                          prior_first_detected=prior)
    persist_snapshot(conn, snap)
    conn.commit()

지금은 어댑터 시그니처만 둔다. 소스가 준비되면 여기서 build_snapshot 입력으로 변환한다.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from batch.clickstream import NeighborRef, neighbors_for, read_shards

from .snapshot import Neighbor, Seed


def load_seeds_from_spike(conn, snapshot_ts: datetime, source: str) -> list[Seed]:
    """spike + wiki_page 를 조인해 이 시점의 씨드를 만든다. (미구현 — 골격)"""
    raise NotImplementedError("spike 조회 어댑터는 소스 배선 시 구현한다")


def load_clickstream_neighbors(
    shards_dir: str | Path, seeds: list[Seed]
) -> dict[str, list[NeighborRef]]:
    """적재본(WP-81)에서 각 씨드의 Clickstream 이웃을 한 번의 순회로 읽는다.

    씨드 제목 → 이웃(title, n, directed) 목록. 반환값의 title/n/directed 를
    build_clusters 가 page_id·생성일과 합쳐 cluster.snapshot.Neighbor 로 만든다
    (아래 build_neighbor_inputs). 덤프가 수백만 행이라 씨드별 재스캔은 하지 않는다.
    """
    seed_titles = {s.title for s in seeds}
    return neighbors_for(read_shards(shards_dir), seed_titles)


def build_neighbor_inputs(
    refs: list[NeighborRef],
    month: str,
    page_of_title: dict[str, tuple[int, str]],
    created_of_page: dict[int, date | None],
) -> list[Neighbor]:
    """NeighborRef 를 cluster.snapshot.Neighbor 로 변환한다.

    page_of_title: 이웃 제목 → (page_id, wiki)   — wiki_page 조회(미배선)
    created_of_page: page_id → 생성일             — mediawiki_history(WP-56, 미배선)
    두 소스가 아직 없으면 그 이웃은 건너뛴다(생성일 미상은 게이트가 어차피 탈락시킨다).
    """
    out: list[Neighbor] = []
    for ref in refs:
        page = page_of_title.get(ref.title)
        if page is None:
            continue
        page_id, wiki = page
        out.append(Neighbor(
            page_id=page_id,
            wiki=wiki,
            title=ref.title,
            clickstream_n=ref.n,
            clickstream_month=month,
            created_at=created_of_page.get(page_id),
            directed=ref.directed,
        ))
    return out


def load_creation_dates(page_ids: list[int]) -> dict[int, object]:
    """mediawiki_history page_creation_timestamp 로 생성일을 채운다. (미구현 — 골격)"""
    raise NotImplementedError("mediawiki_history 생성일 어댑터는 소스 배선 시 구현한다")
