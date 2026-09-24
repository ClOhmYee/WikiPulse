import {
  Activity,
  AlertCircle,
  Clock3,
  FileText,
  Landmark,
  Network,
  Sparkles,
} from "lucide-react";
import { wikipediaUrl } from "../../lib/wiki";
import { IssueSummary } from "./IssueSummary";
import { timestampLabel } from "../../pages/event/presentation.js";
import { reportView } from "./reportView.js";

const SECTION_ICON = {
  overview: FileText,
  documents: Network,
  signal: Activity,
  stocks: Landmark,
};

// 카드 안 근거 칩은 이 개수까지만 — 나머지는 아래 "참고 문서" 전체 목록에 있다.
const CARD_EVIDENCE_LIMIT = 4;

function EvidenceChip({ article }) {
  return (
    <a
      className="dt-evidence-chip"
      href={wikipediaUrl(article)}
      target="_blank"
      rel="noreferrer"
    >
      <FileText size={13} aria-hidden="true" />
      {article.name || article.title}
      <span className="dt-sr-only"> 원문 열기 (새 탭)</span>
    </a>
  );
}

function ReportCard({ card, stocks }) {
  const Icon = SECTION_ICON[card.id] || Sparkles;
  const shown = card.evidence.slice(0, CARD_EVIDENCE_LIMIT);
  const hidden = card.evidence.length - shown.length;
  const tickers = card.id === "stocks" ? stocks : [];
  return (
    <section className="dt-report-card" aria-label={card.title}>
      <h3>
        <Icon size={17} aria-hidden="true" />
        {card.title}
      </h3>
      <div className="dt-report-card-body">
        {card.paragraphs.map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      </div>
      {(tickers.length > 0 || shown.length > 0) && (
        <div className="dt-report-card-chips">
          {tickers.map((stock) => (
            <a
              key={stock.symbol}
              className="dt-report-ticker"
              href={`#/stocks/${encodeURIComponent(stock.symbol)}`}
              title={stock.name}
            >
              {stock.symbol}
            </a>
          ))}
          {shown.map((article) => (
            <EvidenceChip key={article.id} article={article} />
          ))}
          {hidden > 0 && (
            <span className="dt-report-card-more">+{hidden}</span>
          )}
        </div>
      )}
    </section>
  );
}

const STATUS_COPY = {
  generating: {
    title: "리포트를 생성하고 있습니다",
    body: "관측된 신호와 근거 문서를 정리한 뒤 리포트를 표시합니다. 그동안 아래 지표와 근거 문서를 확인할 수 있습니다.",
    icon: Clock3,
  },
  insufficient_evidence: {
    title: "리포트를 만들 근거가 충분하지 않습니다",
    body: "현재 수집된 문서와 관측 정보만으로는 해석을 제공하지 않습니다. 근거 문서와 신호를 직접 확인해 주세요.",
    icon: FileText,
  },
  failed: {
    title: "리포트를 불러오지 못했습니다",
    body: "잠시 후 다시 확인해 주세요. 이슈 지표와 근거 문서 탐색은 계속 사용할 수 있습니다.",
    icon: AlertCircle,
  },
};

export function IssueReport({
  report,
  summary,
  articles = [],
  stocks = [],
  isExample = false,
}) {
  const view = reportView(report, articles);
  const { paragraphs, evidence } = view;
  const status =
    report?.status === "ready" && !paragraphs.length
      ? "insufficient_evidence"
      : report?.status || "insufficient_evidence";
  const isReady = status === "ready";
  const summaryOnly =
    !isExample &&
    status === "insufficient_evidence" &&
    typeof summary === "string" &&
    summary.trim();
  const state = summaryOnly
    ? {
        title: "본문 리포트는 저장되지 않았습니다",
        body: "DB에 저장된 요약만 표시합니다.",
        icon: FileText,
      }
    : STATUS_COPY[status] || STATUS_COPY.insufficient_evidence;
  const StateIcon = state.icon;
  return (
    <section className="dt-report" aria-labelledby="issue-report-title">
      <div className="dt-report-heading">
        <div>
          <h2 id="issue-report-title">
            <Sparkles size={20} aria-hidden="true" />
            리포트
          </h2>
          <p>
            {isExample
              ? "이슈의 배경과 주요 쟁점 · 예시 리포트"
              : "이슈의 배경과 주요 쟁점"}
          </p>
        </div>
      </div>
      <IssueSummary summary={summary} />
      {isReady ? (
        <article className="dt-report-article" aria-label="리포트 본문">
          {view.layout === "cards" ? (
            <div className="dt-report-cards">
              {view.cards.map((card) => (
                <ReportCard key={card.id} card={card} stocks={stocks} />
              ))}
            </div>
          ) : (
            <div className="dt-report-prose">
              {paragraphs.map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
            </div>
          )}
          {evidence.length > 0 && (
            <footer className="dt-report-sources">
              <h3>참고 문서</h3>
              <div className="dt-report-evidence">
                {evidence.map((article) => (
                  <EvidenceChip key={article.id} article={article} />
                ))}
              </div>
            </footer>
          )}
        </article>
      ) : (
        <div
          className="dt-report-state"
          role={status === "failed" ? "alert" : "status"}
        >
          <StateIcon size={20} aria-hidden="true" />
          <div>
            <h3>{state.title}</h3>
            <p>{state.body}</p>
          </div>
        </div>
      )}
      <dl className="dt-report-meta" aria-label="리포트 정보">
        <div>
          <dt>기준 시각</dt>
          <dd>{timestampLabel(report?.snapshotTs)}</dd>
        </div>
        <div>
          <dt>생성 시각</dt>
          <dd>{timestampLabel(report?.generatedAt)}</dd>
        </div>
        <div>
          <dt>생성 정보</dt>
          <dd>{report?.model || "미제공"}</dd>
        </div>
      </dl>
    </section>
  );
}
