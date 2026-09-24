/** 로컬 개발용 추출본을 읽는다. 운영 API 응답 형식에는 관여하지 않는다. */
export function parseJsonLines(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
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
    if (row.snapshot_ts < current.firstSeen)
      current.firstSeen = row.snapshot_ts;
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
  return {
    total: matching.length,
    items: matching.slice(offset, offset + limit),
  };
}

export function snapshotsForGroup(rows, key) {
  return rows
    .filter(
      (row) =>
        row.status !== "DISCARDED" &&
        (row.issue_key || `legacy:${row.source}:${row.id}`) === key,
    )
    .sort((a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts) || b.id - a.id);
}

const kstDayFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function kstDateKey(timestamp) {
  const parts = Object.fromEntries(
    kstDayFormat
      .formatToParts(new Date(timestamp))
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function snapshotsByKstDay(rows) {
  const byDay = new Map();
  for (const row of [...rows].sort(
    (a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts) || b.id - a.id,
  )) {
    const date = kstDateKey(row.snapshot_ts);
    if (!byDay.has(date)) byDay.set(date, []);
    byDay.get(date).push(row);
  }
  return byDay;
}

export function calendarDays(month, byDay) {
  const [year, monthNumber] = month.split("-").map(Number);
  const firstWeekday = new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay();
  const length = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  return [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length }, (_, index) => {
      const day = index + 1;
      const date = `${month}-${String(day).padStart(2, "0")}`;
      return {
        day,
        date,
        enabled: byDay.has(date),
        count: byDay.get(date)?.length || 0,
      };
    }),
  ];
}

export function preferredSnapshot(rows, reports) {
  const sorted = [...rows].sort(
    (a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts) || b.id - a.id,
  );
  const reportById = new Map(reports.map((report) => [report.id, report]));
  return (
    sorted.find((row) => reportById.get(row.id)?.sections?.length) ||
    sorted.find((row) => reportById.get(row.id)?.summary) ||
    sorted[0] ||
    null
  );
}
