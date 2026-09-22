import copy
from datetime import datetime, timezone

import pytest

from tools.production_api_smoke import ContractError, audit_source, validate_map


SNAPSHOT_TS = "2026-09-22T10:00:00Z"


def snapshot_payload(source="live"):
    return {
        "data": [
            {"snapshotTs": SNAPSHOT_TS, "source": source, "clusterCount": 1}
        ]
    }


def map_payload(source="live"):
    return {
        "data": {
            "clusters": [
                {
                    "id": "10",
                    "issueKey": f"{source}:enwiki:Example",
                    "label": "Example",
                    "summary": None,
                    "category": "other",
                    "firstDetectedAt": SNAPSHOT_TS,
                    "hot": True,
                    "pulseScore": 7.2,
                    "status": "DETECTED",
                    "memberCount": 2,
                    "nodes": [
                        {
                            "pageId": "100",
                            "wiki": "enwiki",
                            "title": "Example",
                            "isSeed": True,
                            "editCount": 4,
                            "views": 120,
                            "editBaseline": None,
                            "viewBaseline": None,
                            "spikeScore": 7.2,
                            "sizeScore": 0.8,
                            "completeness": "complete",
                            "windowStart": "2026-09-22T09:00:00Z",
                            "windowEnd": SNAPSHOT_TS,
                        },
                        {
                            "pageId": "101",
                            "wiki": "enwiki",
                            "title": "Related",
                            "isSeed": True,
                            "editCount": 2,
                            "views": 80,
                            "editBaseline": None,
                            "viewBaseline": None,
                            "spikeScore": 5.1,
                            "sizeScore": 0.5,
                            "completeness": "complete",
                            "windowStart": "2026-09-22T09:00:00Z",
                            "windowEnd": SNAPSHOT_TS,
                        },
                    ],
                    "edges": [
                        {
                            "id": "500",
                            "sourcePageId": "100",
                            "targetPageId": "101",
                            "kind": "clickstream",
                            "directed": True,
                            "weight": 3.0,
                            "evidence": {"label": "clickstream", "month": "2026-08"},
                        }
                    ],
                }
            ]
        },
        "meta": {
            "snapshotTs": SNAPSHOT_TS,
            "source": source,
            "scoreVersion": "v1",
            "newWindowHours": 24.0,
            "clusterCount": 1,
            "nodeCount": 2,
            "edgeCount": 1,
            "truncated": False,
        },
    }


def feed_payload(source="live"):
    return {
        "data": [
            {
                "id": 10,
                "label": "Example",
                "pulseScore": 7.2,
                "status": "DETECTED",
                "source": source,
                "snapshotTs": SNAPSHOT_TS,
                "memberCount": 2,
                "stockCount": 0,
            }
        ],
        "meta": {
            "pagination": {"offset": 0, "limit": 1, "total": 1, "hasMore": False},
            "snapshotTs": SNAPSHOT_TS,
        },
    }


class FakeClient:
    def __init__(self, source="live"):
        self.source = source
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params))
        if path == "/issues/snapshots":
            return snapshot_payload(self.source)
        if path == "/issues/map":
            return map_payload(self.source)
        if path == "/issues":
            return feed_payload(self.source)
        if path == "/issues/10":
            return {
                "data": {
                    "id": 10,
                    "source": self.source,
                    "snapshotTs": SNAPSHOT_TS,
                    "members": [],
                    "relatedStocks": [],
                }
            }
        if path == "/issues/10/stocks":
            return {"data": []}
        raise AssertionError(f"unexpected request: {path} {params}")


def test_audit_source_checks_live_endpoints_and_contracts():
    client = FakeClient("live")

    result = audit_source(
        client,
        "live",
        now=datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
        max_live_age_hours=6,
    )

    assert result.snapshot_ts == SNAPSHOT_TS
    assert result.cluster_count == 1
    assert [path for path, _ in client.calls] == [
        "/issues/snapshots",
        "/issues/map",
        "/issues",
        "/issues/10",
        "/issues/10/stocks",
    ]


def test_validate_map_rejects_missing_metric_window():
    payload = map_payload()
    payload["data"]["clusters"][0]["nodes"][0]["windowEnd"] = None

    with pytest.raises(ContractError, match="windowEnd"):
        validate_map(snapshot_payload()["data"][0], payload)


def test_validate_map_rejects_reversed_metric_window():
    payload = map_payload()
    payload["data"]["clusters"][0]["nodes"][0]["windowStart"] = SNAPSHOT_TS
    payload["data"]["clusters"][0]["nodes"][0]["windowEnd"] = "2026-09-22T09:00:00Z"

    with pytest.raises(ContractError, match="windowStart"):
        validate_map(snapshot_payload()["data"][0], payload)


def test_validate_map_rejects_dangling_edge_endpoint():
    payload = map_payload()
    payload["data"]["clusters"][0]["edges"][0]["targetPageId"] = "999"

    with pytest.raises(ContractError, match="targetPageId=999"):
        validate_map(snapshot_payload()["data"][0], payload)


def test_audit_source_rejects_stale_live_snapshot():
    client = FakeClient("live")

    with pytest.raises(ContractError, match="LIVE snapshot is stale"):
        audit_source(
            client,
            "live",
            now=datetime(2026, 9, 23, 0, tzinfo=timezone.utc),
            max_live_age_hours=6,
        )


def test_audit_source_does_not_apply_live_freshness_to_replay():
    client = FakeClient("replay")

    result = audit_source(
        client,
        "replay",
        now=datetime(2027, 1, 1, tzinfo=timezone.utc),
        max_live_age_hours=6,
    )

    assert result.source == "replay"


def test_validate_map_rejects_declared_count_mismatch():
    payload = copy.deepcopy(map_payload())
    payload["meta"]["nodeCount"] = 3

    with pytest.raises(ContractError, match="nodeCount"):
        validate_map(snapshot_payload()["data"][0], payload)
