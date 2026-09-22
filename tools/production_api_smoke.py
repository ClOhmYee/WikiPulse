#!/usr/bin/env python3
"""Read-only smoke test for the deployed WikiPulse API.

Usage:
    python tools/production_api_smoke.py https://service.example.com

Only public GET endpoints are called. The script never writes to the service.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DEFAULT_BASE_URL = "https://service.example.com"


class SmokeError(RuntimeError):
    """Base error for a failed smoke check."""


class ContractError(SmokeError):
    """The API responded, but its data violated the service contract."""


class ApiError(SmokeError):
    """The API could not be reached or returned an invalid response."""


@dataclass(frozen=True)
class AuditResult:
    source: str
    snapshot_ts: str
    cluster_count: int
    node_count: int
    edge_count: int


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        root = base_url.rstrip("/")
        self.api_root = root if root.endswith("/api/v1") else f"{root}/api/v1"
        self.timeout = timeout

    def get(self, path: str, **params: object) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{self.api_root}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "wikipulse-production-smoke/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", errors="replace")
            raise ApiError(f"GET {url} returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError(f"GET {url} failed: {exc}") from exc

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(f"GET {url} did not return valid JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError(f"GET {url} returned a non-object JSON root")
        return payload


def parse_instant(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an ISO-8601 UTC string ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid timestamp: {value}") from exc


def require_dict(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    return value


def require_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    return value


def latest_snapshot(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    rows = require_list(payload.get("data"), f"{source} snapshots.data")
    if not rows:
        raise ContractError(f"{source} has no completed snapshots")

    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for index, value in enumerate(rows):
        row = require_dict(value, f"{source} snapshots.data[{index}]")
        if row.get("source") != source:
            raise ContractError(
                f"{source} snapshots.data[{index}].source={row.get('source')!r}"
            )
        count = row.get("clusterCount")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContractError(
                f"{source} snapshots.data[{index}].clusterCount must be a non-negative integer"
            )
        parsed.append(
            (parse_instant(row.get("snapshotTs"), f"{source} snapshotTs"), row)
        )
    return max(parsed, key=lambda item: item[0])[1]


def validate_map(snapshot: dict[str, Any], payload: dict[str, Any]) -> tuple[int, int]:
    source = snapshot["source"]
    snapshot_ts = snapshot["snapshotTs"]
    snapshot_dt = parse_instant(snapshot_ts, f"{source} snapshotTs")
    data = require_dict(payload.get("data"), f"{source} map.data")
    meta = require_dict(payload.get("meta"), f"{source} map.meta")
    clusters = require_list(data.get("clusters"), f"{source} map.data.clusters")

    if meta.get("snapshotTs") != snapshot_ts:
        raise ContractError(
            f"{source} map.meta.snapshotTs={meta.get('snapshotTs')!r}, expected {snapshot_ts}"
        )
    if meta.get("source") != source:
        raise ContractError(
            f"{source} map.meta.source={meta.get('source')!r}, expected {source}"
        )
    if snapshot["clusterCount"] != len(clusters):
        raise ContractError(
            f"{source} snapshot clusterCount={snapshot['clusterCount']}, map has {len(clusters)}"
        )
    if meta.get("clusterCount") != len(clusters):
        raise ContractError(
            f"{source} map.meta.clusterCount={meta.get('clusterCount')}, actual={len(clusters)}"
        )

    total_nodes = 0
    total_edges = 0
    for cluster_index, value in enumerate(clusters):
        prefix = f"{source} cluster[{cluster_index}]"
        cluster = require_dict(value, prefix)
        nodes = require_list(cluster.get("nodes"), f"{prefix}.nodes")
        edges = require_list(cluster.get("edges"), f"{prefix}.edges")
        if cluster.get("memberCount") != len(nodes):
            raise ContractError(
                f"{prefix}.memberCount={cluster.get('memberCount')}, actual={len(nodes)}"
            )

        node_ids: set[str] = set()
        for node_index, node_value in enumerate(nodes):
            node_prefix = f"{prefix}.nodes[{node_index}]"
            node = require_dict(node_value, node_prefix)
            page_id = node.get("pageId")
            if not isinstance(page_id, str) or not page_id:
                raise ContractError(f"{node_prefix}.pageId must be a non-empty string")
            if page_id in node_ids:
                raise ContractError(f"{prefix} has duplicate pageId={page_id}")
            node_ids.add(page_id)

            start = parse_instant(node.get("windowStart"), f"{node_prefix}.windowStart")
            end = parse_instant(node.get("windowEnd"), f"{node_prefix}.windowEnd")
            if start >= end:
                raise ContractError(
                    f"{node_prefix}.windowStart must be earlier than windowEnd"
                )
            if end > snapshot_dt:
                raise ContractError(
                    f"{node_prefix}.windowEnd must not be later than snapshotTs"
                )

        for edge_index, edge_value in enumerate(edges):
            edge_prefix = f"{prefix}.edges[{edge_index}]"
            edge = require_dict(edge_value, edge_prefix)
            source_page = edge.get("sourcePageId")
            target_page = edge.get("targetPageId")
            if source_page not in node_ids:
                raise ContractError(
                    f"{edge_prefix}.sourcePageId={source_page} is not a cluster node"
                )
            if target_page not in node_ids:
                raise ContractError(
                    f"{edge_prefix}.targetPageId={target_page} is not a cluster node"
                )

        total_nodes += len(nodes)
        total_edges += len(edges)

    if meta.get("nodeCount") != total_nodes:
        raise ContractError(
            f"{source} map.meta.nodeCount={meta.get('nodeCount')}, actual={total_nodes}"
        )
    if meta.get("edgeCount") != total_edges:
        raise ContractError(
            f"{source} map.meta.edgeCount={meta.get('edgeCount')}, actual={total_edges}"
        )
    return total_nodes, total_edges


def validate_feed(
    snapshot: dict[str, Any], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    source = snapshot["source"]
    snapshot_ts = snapshot["snapshotTs"]
    rows = require_list(payload.get("data"), f"{source} issues.data")
    meta = require_dict(payload.get("meta"), f"{source} issues.meta")
    if meta.get("snapshotTs") != snapshot_ts:
        raise ContractError(
            f"{source} issues.meta.snapshotTs={meta.get('snapshotTs')!r}, expected {snapshot_ts}"
        )
    if snapshot["clusterCount"] > 0 and not rows:
        raise ContractError(f"{source} snapshot has clusters but issue feed is empty")

    checked: list[dict[str, Any]] = []
    for index, value in enumerate(rows):
        row = require_dict(value, f"{source} issues.data[{index}]")
        if row.get("source") != source or row.get("snapshotTs") != snapshot_ts:
            raise ContractError(
                f"{source} issues.data[{index}] does not match requested source/snapshotTs"
            )
        checked.append(row)
    return checked


def validate_issue_detail(
    source: str, snapshot_ts: str, issue_id: object, payload: dict[str, Any]
) -> None:
    data = require_dict(payload.get("data"), f"{source} issue detail.data")
    if str(data.get("id")) != str(issue_id):
        raise ContractError(
            f"{source} issue detail id={data.get('id')!r}, expected {issue_id}"
        )
    if data.get("source") != source or data.get("snapshotTs") != snapshot_ts:
        raise ContractError(f"{source} issue detail does not match its feed coordinate")


def audit_source(
    client: ApiClient,
    source: str,
    *,
    now: datetime,
    max_live_age_hours: float,
) -> AuditResult:
    snapshot = latest_snapshot(
        source, client.get("/issues/snapshots", source=source)
    )
    snapshot_ts = snapshot["snapshotTs"]
    map_payload = client.get("/issues/map", snapshotTs=snapshot_ts, source=source)
    node_count, edge_count = validate_map(snapshot, map_payload)

    feed = validate_feed(
        snapshot,
        client.get(
            "/issues", snapshotTs=snapshot_ts, source=source, offset=0, limit=1
        ),
    )
    if feed:
        issue_id = feed[0].get("id")
        if issue_id is None:
            raise ContractError(f"{source} issues.data[0].id is missing")
        validate_issue_detail(
            source,
            snapshot_ts,
            issue_id,
            client.get(f"/issues/{issue_id}"),
        )
        stocks = client.get(f"/issues/{issue_id}/stocks")
        require_list(stocks.get("data"), f"{source} issue stocks.data")

    if source == "live":
        snapshot_dt = parse_instant(snapshot_ts, "live snapshotTs")
        age_hours = (now - snapshot_dt).total_seconds() / 3600
        if age_hours > max_live_age_hours:
            raise ContractError(
                "LIVE snapshot is stale: "
                f"age={age_hours:.1f}h, limit={max_live_age_hours:.1f}h, snapshotTs={snapshot_ts}"
            )

    return AuditResult(
        source=source,
        snapshot_ts=snapshot_ts,
        cluster_count=snapshot["clusterCount"],
        node_count=node_count,
        edge_count=edge_count,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only contract and freshness smoke test for the deployed WikiPulse API."
    )
    parser.add_argument(
        "base_url",
        nargs="?",
        default=DEFAULT_BASE_URL,
        help=f"service root or /api/v1 URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--max-live-age-hours",
        type=float,
        default=6.0,
        help="fail when the latest LIVE snapshot is older than this (default: 6)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds (default: 10)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_live_age_hours <= 0:
        print("[FAIL] --max-live-age-hours must be positive", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("[FAIL] --timeout must be positive", file=sys.stderr)
        return 2

    client = ApiClient(args.base_url, timeout=args.timeout)
    now = datetime.now(timezone.utc)
    failures = 0
    for source in ("live", "replay"):
        try:
            result = audit_source(
                client,
                source,
                now=now,
                max_live_age_hours=args.max_live_age_hours,
            )
            print(
                f"[PASS] {source}: snapshot={result.snapshot_ts} "
                f"clusters={result.cluster_count} nodes={result.node_count} edges={result.edge_count}"
            )
        except SmokeError as exc:
            failures += 1
            print(f"[FAIL] {source}: {exc}", file=sys.stderr)

    if failures:
        print(f"[FAIL] production API smoke failed: {failures}/2 source(s)", file=sys.stderr)
        return 1
    print("[PASS] production API smoke passed: 2/2 sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
