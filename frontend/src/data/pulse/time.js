const HOUR = 3_600_000;
export const kstDate = (ts) =>
  new Date(Date.parse(ts) + 9 * HOUR).toISOString().slice(0, 10);
export const kstTime = (ts) =>
  new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(ts));
export const kstTimestamp = (ts) => `${kstDate(ts)} ${kstTime(ts)} KST`;
export function isNewIssue(firstDetectedAt, snapshotTs, hours = 24) {
  if (!firstDetectedAt) return false;
  const age = Date.parse(snapshotTs) - Date.parse(firstDetectedAt);
  return Number.isFinite(age) && age >= 0 && age < hours * HOUR;
}
export const snapshotKey = (item) => `${item.source}:${item.snapshotTs}`;
export function closestSnapshot(items, timestamp) {
  return items.reduce(
    (best, item) =>
      !best ||
      Math.abs(Date.parse(item.snapshotTs) - timestamp) <
        Math.abs(Date.parse(best.snapshotTs) - timestamp)
        ? item
        : best,
    null,
  );
}
export function calendarDays(items) {
  if (!items.length) return [];
  const days = new Set(items.map((item) => kstDate(item.snapshotTs)));
  const sorted = [...days].sort();
  const first = Date.parse(sorted[0]);
  const last = Date.parse(sorted.at(-1));
  return Array.from(
    { length: Math.floor((last - first) / (24 * HOUR)) + 1 },
    (_, index) => {
      const value = new Date(first + index * 24 * HOUR)
        .toISOString()
        .slice(0, 10);
      return { value, available: days.has(value) };
    },
  );
}
