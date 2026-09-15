import { ArrowLeft, ArrowRight } from "lucide-react";
import { ISSUE_STATUS_LABELS } from "../../pages/event/presentation.js";
import "./dataPresentation.css";
export function IssueState({ status }) {
  return (
    <span className="issue-state" data-status={status}>
      {ISSUE_STATUS_LABELS[status] || "AI 검증 상태 미제공"}
    </span>
  );
}
export function Pagination({ pagination, onChange, loading = false }) {
  if (!pagination) return null;
  const { offset, limit, total, hasMore } = pagination;
  return (
    <nav className="data-pagination" aria-label="목록 페이지">
      <p aria-live="polite">
        전체 {total.toLocaleString()}개 · {total ? offset + 1 : 0}–
        {Math.min(offset + limit, total)}번째
      </p>
      <div>
        <button
          className="wp-button"
          disabled={loading || offset === 0}
          onClick={() => onChange({ offset: Math.max(0, offset - limit) })}
        >
          <ArrowLeft size={15} />
          이전 페이지
        </button>
        <button
          className="wp-button"
          disabled={loading || !hasMore}
          onClick={() => onChange({ offset: offset + limit })}
        >
          다음 페이지
          <ArrowRight size={15} />
        </button>
      </div>
    </nav>
  );
}
