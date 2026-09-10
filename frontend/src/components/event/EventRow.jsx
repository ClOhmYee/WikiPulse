import { ArrowRight, Bookmark } from "lucide-react";
import { CategoryTag } from "../ui/CategoryTag";
import { formatNumber } from "../../lib/format";
export const statusLabels = {
  rising: "상승 중",
  sustained: "관심 지속",
  cooling: "안정화",
};

export function EventRow({ event, saved, onToggle, category }) {
  return (
    <article className="event-row">
      <div className="event-row__main">
        <CategoryTag category={category} />
        <a href={`#/issues/${event.id}`} className="event-row__title">
          {event.title}
          <ArrowRight size={17} />
        </a>
        <p>{event.summary}</p>
        <div className="event-row__meta">
          <span>{event.articleIds.length}개 문서</span>
          <span>{event.date.replaceAll("-", ".")}</span>
          <span>{statusLabels[event.status]}</span>
        </div>
      </div>
      <div className="event-row__signal">
        <strong>
          {event.pulse.toFixed(1)}
          <small>×</small>
        </strong>
        <span>평소 대비 편집</span>
      </div>
      <div className="event-row__edits">
        <strong>{formatNumber(event.edits)}</strong>
        <span>편집</span>
      </div>
      <button
        className="wp-icon-button"
        data-active={saved}
        aria-label={`${event.title} ${saved ? "저장 해제" : "저장"}`}
        aria-pressed={saved}
        onClick={() => onToggle(event.id)}
      >
        <Bookmark size={18} fill={saved ? "currentColor" : "none"} />
      </button>
    </article>
  );
}
