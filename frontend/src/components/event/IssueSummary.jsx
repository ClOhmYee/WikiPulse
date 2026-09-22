import { useId } from "react";
import "./issueSummary.css";

export function IssueSummary({ summary, compact = false }) {
  const titleId = useId();
  return (
    <section
      className={`issue-summary${compact ? " issue-summary--compact" : ""}`}
      aria-labelledby={titleId}
    >
      <h3 id={titleId}>한눈에 보는 이슈</h3>
      <p>{summary?.trim() || "이 시점의 요약이 제공되지 않았습니다."}</p>
    </section>
  );
}
