/** 로컬 개발용 추출본을 읽는다. 운영 API 응답 형식에는 관여하지 않는다. */
export function parseJsonLines(text) {
  return text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line));
}

export function groupIssueSnapshots(rows) {
  const groups = new Map();
  for (const row of rows) {
    if (row.status === "DISCARDED") continue;
    const key = row.issue_key || `legacy:${row.source}:${row.id}`;
    const current = groups.get(key);
    if (!current) {
      groups.set(key, {
        key,
        label: row.label || "제목 없음",
        source: row.source,
        firstSeen: row.snapshot_ts,
        lastSeen: row.snapshot_ts,
        latestId: row.id,
        latestStatus: row.status,
        latestScore: row.pulse_score,
        count: 1,
      });
      continue;
    }
    current.count += 1;
    if (row.snapshot_ts < current.firstSeen) current.firstSeen = row.snapshot_ts;
    if (
      row.snapshot_ts > current.lastSeen ||
      (row.snapshot_ts === current.lastSeen && row.id > current.latestId)
    ) {
      current.lastSeen = row.snapshot_ts;
      current.latestId = row.id;
      current.latestStatus = row.status;
      current.latestScore = row.pulse_score;
      current.label = row.label || current.label;
    }
  }
  return [...groups.values()].sort(
    (a, b) => b.lastSeen.localeCompare(a.lastSeen) || a.latestId - b.latestId,
  );
}

export function searchIssueGroups(groups, query, offset = 0, limit = 20) {
  const needle = query.trim().toLocaleLowerCase();
  const matching = needle
    ? groups.filter((group) => group.label.toLocaleLowerCase().includes(needle))
    : groups;
  return { total: matching.length, items: matching.slice(offset, offset + limit) };
}

export function snapshotsForGroup(rows, key) {
  return rows
    .filter((row) => row.status !== "DISCARDED" && (row.issue_key || `legacy:${row.source}:${row.id}`) === key)
    .sort((a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts) || b.id - a.id);
}
