import { AlertCircle, Clock3, FileText, Sparkles } from "lucide-react";
import { wikipediaUrl } from "../../lib/wiki";
import { timestampLabel } from "../../pages/event/presentation.js";

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

export function IssueReport({ report, articles = [] }) {
  const status = report?.status || "insufficient_evidence";
  const isReady = status === "ready";
  const state = STATUS_COPY[status] || STATUS_COPY.insufficient_evidence;
  const StateIcon = state.icon;
  const articleById = new Map(articles.map((article) => [article.id, article]));
  return (
    <section className="dt-report" aria-labelledby="issue-report-title">
      <div className="dt-report-heading">
        <div>
          <h2 id="issue-report-title">
            <Sparkles size={20} aria-hidden="true" />
            리포트
          </h2>
          <p>관측된 이슈와 출처 문서를 바탕으로 생성한 해석입니다.</p>
        </div>
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
      </div>
      {isReady ? (
        <div className="dt-report-sections">
          {report.sections.map((section) => (
            <article className="dt-report-section" key={section.id}>
              <h3>{section.title}</h3>
              {section.body ? (
                <p>{section.body}</p>
              ) : (
                <p className="dt-report-empty">
                  이 항목에 제공된 해석이 없습니다.
                </p>
              )}
              {section.evidenceIds?.length > 0 && (
                <div
                  className="dt-report-evidence"
                  aria-label={`${section.title} 근거`}
                >
                  {section.evidenceIds.map((id) => {
                    const article = articleById.get(String(id));
                    return article ? (
                      <a
                        key={article.id}
                        className="dt-evidence-chip"
                        href={wikipediaUrl(article)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <FileText size={13} aria-hidden="true" />
                        {article.name || article.title}
                        <span className="dt-sr-only"> 원문 열기</span>
                      </a>
                    ) : null;
                  })}
                </div>
              )}
            </article>
          ))}
        </div>
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
    </section>
  );
}
