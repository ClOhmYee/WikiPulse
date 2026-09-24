import test from "node:test";
import assert from "node:assert/strict";
import {
  groupIssueSnapshots,
  parseJsonLines,
  searchIssueGroups,
  snapshotsForGroup,
} from "../src/data/historyPreview.js";

const snapshots = [
  { id: 1, source: "replay", issue_key: "replay:enwiki:A", label: "A", snapshot_ts: "2026-07-17T01:00:00+00:00", status: "CONFIRMED", pulse_score: 10 },
  { id: 2, source: "replay", issue_key: "replay:enwiki:A", label: "A", snapshot_ts: "2026-07-18T01:00:00+00:00", status: "DETECTED", pulse_score: 8 },
  { id: 3, source: "replay", issue_key: "replay:enwiki:B", label: "A", snapshot_ts: "2026-07-19T01:00:00+00:00", status: "DETECTED", pulse_score: 9 },
  { id: 4, source: "live", issue_key: "live:enwiki:A", label: "A", snapshot_ts: "2026-09-20T01:00:00+00:00", status: "DETECTED", pulse_score: 7 },
  { id: 5, source: "replay", issue_key: null, label: "옛 A", snapshot_ts: "2026-07-20T01:00:00+00:00", status: "DETECTED", pulse_score: 6 },
  { id: 6, source: "replay", issue_key: null, label: "옛 A", snapshot_ts: "2026-07-21T01:00:00+00:00", status: "DETECTED", pulse_score: 5 },
  { id: 7, source: "replay", issue_key: "replay:enwiki:A", label: "A", snapshot_ts: "2026-07-22T01:00:00+00:00", status: "DISCARDED", pulse_score: 20 },
];

test("JSONL 추출본의 한국어와 시각을 그대로 읽는다", () => {
  assert.deepEqual(parseJsonLines('{"label":"옛 A"}\r\n{"snapshot_ts":"2026-07-17T01:00:00+00:00"}\r\n'), [
    { label: "옛 A" },
    { snapshot_ts: "2026-07-17T01:00:00+00:00" },
  ]);
});

test("동일 키만 묶고 다른 출처·NULL 키·폐기 행은 잘못 합치지 않는다", () => {
  const groups = groupIssueSnapshots(snapshots);
  assert.equal(groups.length, 5);
  const a = groups.find((group) => group.key === "replay:enwiki:A");
  assert.equal(a.count, 2);
  assert.equal(a.latestId, 2);
  assert.equal(a.firstSeen, snapshots[0].snapshot_ts);
  assert.equal(a.lastSeen, snapshots[1].snapshot_ts);
  assert.equal(groups.filter((group) => group.label === "옛 A").length, 2);
  assert.equal(groups.find((group) => group.key === "live:enwiki:A").count, 1);
  assert.equal(snapshotsForGroup(snapshots, a.key).map((row) => row.id).join(","), "2,1");
});

test("대표 제목 검색 결과를 최신순으로 페이지네이션한다", () => {
  const groups = groupIssueSnapshots(snapshots);
  const first = searchIssueGroups(groups, " a ", 0, 2);
  assert.equal(first.total, 5);
  assert.equal(first.items.length, 2);
  assert.equal(first.items[0].source, "live");
  assert.equal(searchIssueGroups(groups, "A", 2, 2).items.length, 2);
  assert.equal(searchIssueGroups(groups, "A", 4, 2).items.length, 1);
  assert.equal(searchIssueGroups(groups, "없는 제목", 0, 20).total, 0);
});
