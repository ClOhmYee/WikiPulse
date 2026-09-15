export const ISSUE_STATUS_LABELS = {
  DETECTED: "AI 검증 전",
  VERIFYING: "AI 검증 중",
  CONFIRMED: "AI 검증 완료",
};
export function metricLabel(value, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(
        value,
      )
    : "미제공";
}
export function timestampLabel(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return "시각 미제공";
  return (
    new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value)) + " KST"
  );
}
export function sourceLabel(source) {
  return source === "live"
    ? "실시간 수집"
    : source === "replay"
      ? "과거 재구성"
      : "출처 미제공";
}
