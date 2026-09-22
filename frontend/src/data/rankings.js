import { DataError } from "./contracts.js";

export function rankingWindow(asOf) {
  const end = new Date(asOf);
  const local = new Date(end.getTime() + 9 * 3_600_000);
  const year = local.getUTCFullYear() - 1;
  const month = local.getUTCMonth();
  const day = Math.min(
    local.getUTCDate(),
    new Date(Date.UTC(year, month + 1, 0)).getUTCDate(),
  );
  const yearFrom = new Date(
    Date.UTC(
      year,
      month,
      day,
      local.getUTCHours(),
      local.getUTCMinutes(),
      local.getUTCSeconds(),
      local.getUTCMilliseconds(),
    ) -
      9 * 3_600_000,
  );
  return {
    asOf: end.toISOString(),
    monthFrom: new Date(end.getTime() - 30 * 86_400_000).toISOString(),
    yearFrom: yearFrom.toISOString(),
  };
}

export function rankIssues(rows, from, asOf) {
  const peaks = new Map();
  const compare = (a, b) =>
    b.pulseScore - a.pulseScore ||
    Date.parse(b.snapshotTs) - Date.parse(a.snapshotTs) ||
    Number(a.id) - Number(b.id);
  for (const row of rows) {
    const time = Date.parse(row.snapshotTs);
    if (
      time < Date.parse(from) ||
      time > Date.parse(asOf) ||
      !["DETECTED", "VERIFYING", "CONFIRMED"].includes(row.status)
    )
      continue;
    const key = row.issueKey || `id:${row.id}`;
    if (!peaks.has(key) || compare(row, peaks.get(key)) < 0)
      peaks.set(key, row);
  }
  return [...peaks.values()]
    .sort(compare)
    .slice(0, 10)
    .map(({ id, label, pulseScore }) => ({ id, label, pulseScore }));
}

export function validateRankings(response) {
  const data = response?.data;
  const timestamp = (value) =>
    typeof value === "string" && Number.isFinite(Date.parse(value));
  const entries = (value) =>
    Array.isArray(value) &&
    value.length <= 10 &&
    value.every(
      (row, i) =>
        row &&
        Number.isSafeInteger(row.id) &&
        row.id > 0 &&
        (row.label == null || typeof row.label === "string") &&
        Number.isFinite(row.pulseScore) &&
        row.pulseScore >= 0 &&
        (!i || value[i - 1].pulseScore >= row.pulseScore),
    ) &&
    new Set(value.map((row) => row.id)).size === value.length;
  if (
    !data ||
    !timestamp(data.asOf) ||
    !timestamp(data.monthFrom) ||
    !timestamp(data.yearFrom) ||
    Date.parse(data.yearFrom) > Date.parse(data.monthFrom) ||
    Date.parse(data.monthFrom) > Date.parse(data.asOf) ||
    !entries(data.monthly) ||
    !entries(data.yearly)
  ) {
    throw new DataError("이슈 순위 응답을 확인할 수 없습니다.", {
      code: "INVALID_RESPONSE",
    });
  }
  return response;
}
