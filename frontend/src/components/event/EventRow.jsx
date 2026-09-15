import { ArrowRight, Bookmark } from "lucide-react";
import { CategoryTag } from "../ui/CategoryTag";
import { IssueState } from "./IssueState";
import {
  metricLabel,
  sourceLabel,
  timestampLabel,
} from "../../pages/event/presentation.js";
export function EventRow({ event, saved, onToggle, category }) {
  return (
    <article className="event-row">
      <div className="event-row__main">
        {category && <CategoryTag category={category} />}
        <a
          href={`#/issues/${encodeURIComponent(event.id)}`}
          className="event-row__title"
        >
          {event.title}
          <ArrowRight size={17} />
        </a>
        {event.summary && <p>{event.summary}</p>}
        <div className="event-row__meta">
          <span>{metricLabel(event.memberCount, 0)}개 문서</span>
          <time dateTime={event.snapshotTs || undefined}>
            {timestampLabel(event.snapshotTs)}
          </time>
          <span>{sourceLabel(event.source)}</span>
          <IssueState status={event.status} />
        </div>
      </div>
      <div className="event-row__signal">
        <strong>{metricLabel(event.pulseScore)}</strong>
        <span>급증 점수</span>
      </div>
      <div className="event-row__edits">
        <strong>{metricLabel(event.stockCount, 0)}</strong>
        <span>관련 종목</span>
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
