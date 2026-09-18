"""driver 배선 검증 (WP-81 부분). Clickstream 이웃 → Neighbor 변환.

순수 변환만 본다 — spike·생성일 어댑터는 아직 골격이므로 그 부분은 검증 범위 밖.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone

from batch.clickstream import NeighborRef
from cluster.driver import build_neighbor_inputs, load_clickstream_neighbors
from cluster.snapshot import Seed

UTC = timezone.utc


def _seed(title, page_id=1):
    return Seed(page_id=page_id, wiki="enwiki", title=title, event_date=date(2025, 6, 12),
               spike_score=9.7, window_start=datetime(2025, 6, 12, tzinfo=UTC),
               window_end=datetime(2025, 6, 12, 4, tzinfo=UTC))


def test_적재본에서_씨드_이웃을_읽는다(tmp_path):
    shard = tmp_path / "part-00000.jsonl.gz"
    with gzip.open(shard, "wt", encoding="utf-8") as h:
        h.write(json.dumps({"prev": "Strait of Hormuz", "curr": "Iran", "n": 383}) + "\n")
        h.write(json.dumps({"prev": "Unrelated", "curr": "Thing", "n": 50}) + "\n")
    result = load_clickstream_neighbors(tmp_path, [_seed("Strait of Hormuz")])
    assert [r.title for r in result["Strait of Hormuz"]] == ["Iran"]


def test_NeighborRef를_Neighbor로_변환():
    refs = [NeighborRef(title="Iran", n=383, directed=True),
            NeighborRef(title="No Page", n=10, directed=True)]
    page_of_title = {"Iran": (902, "enwiki")}          # No Page 는 매핑 없음 → 건너뜀
    created_of_page = {902: datetime(2025, 6, 20, tzinfo=UTC)}
    neighbors = build_neighbor_inputs(refs, "2025-05", page_of_title, created_of_page)

    assert len(neighbors) == 1
    nb = neighbors[0]
    assert nb.page_id == 902 and nb.wiki == "enwiki" and nb.title == "Iran"
    assert nb.clickstream_n == 383
    assert nb.clickstream_month == "2025-05"
    assert nb.created_at == datetime(2025, 6, 20, tzinfo=UTC)
    assert nb.directed is True
