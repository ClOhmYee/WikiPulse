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

from datetime import datetime

from .snapshot import Neighbor, Seed


def load_seeds_from_spike(conn, snapshot_ts: datetime, source: str) -> list[Seed]:
    """spike + wiki_page 를 조인해 이 시점의 씨드를 만든다. (미구현 — 골격)"""
    raise NotImplementedError("spike 조회 어댑터는 소스 배선 시 구현한다")


def load_clickstream_neighbors(seed: Seed, month: str) -> list[Neighbor]:
    """Clickstream 월별 덤프에서 씨드의 이웃을 읽는다. (미구현 — 인제스트 선행)"""
    raise NotImplementedError("Clickstream 인제스트가 선행되어야 한다")


def load_creation_dates(page_ids: list[int]) -> dict[int, object]:
    """mediawiki_history page_creation_timestamp 로 생성일을 채운다. (미구현 — 골격)"""
    raise NotImplementedError("mediawiki_history 생성일 어댑터는 소스 배선 시 구현한다")
