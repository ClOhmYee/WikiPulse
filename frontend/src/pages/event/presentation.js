export const ISSUE_STATUS_LABELS = {
  DETECTED: "분석 준비",
  VERIFYING: "분석 진행 중",
  CONFIRMED: "분석 완료",
};
export const COMPLETENESS_LABELS = {
  complete: "판정 완료",
  pending: "입력 대기",
  unavailable: "원본 없음",
};
export function completenessDescription(value) {
  if (value === "complete") return "이 스냅샷의 판정에 사용된 고정값입니다.";
  if (value === "pending")
    return "이 스냅샷은 판정 입력을 기다리는 중이라 일부 값이 비어 있을 수 있습니다.";
  return "이 스냅샷에는 원본이 없어 일부 값이 비어 있을 수 있습니다.";
}
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
