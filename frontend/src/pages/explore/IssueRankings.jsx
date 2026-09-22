import { useCallback } from "react";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import { metricLabel } from "../event/presentation.js";

export default function IssueRankings() {
  const load = useCallback(
    (signal) => dataClient.getIssueRankings({}, { signal }),
    [],
  );
  const { data, loading, error, reload } = useAsyncResource(
    load,
    "issue-rankings",
  );
  return (
    <aside
      className="explore-rankings"
      aria-label="기간별 이슈 Top 10"
      aria-busy={loading}
    >
      {error ? (
        <div className="explore-ranking-error" role="status">
          <p>이슈 순위를 불러오지 못했습니다.</p>
          <button className="wp-text-button" onClick={reload}>
            순위 다시 불러오기
          </button>
        </div>
      ) : (
        [
          { key: "monthly", title: "최근 30일" },
          { key: "yearly", title: "최근 1년" },
        ].map(({ key, title }) => (
          <section
            className="explore-ranking"
            key={key}
            aria-labelledby={`ranking-${key}`}
          >
            <h2 id={`ranking-${key}`}>
              {title}
              <span>TOP 10</span>
            </h2>
            {loading ? (
              <p className="explore-ranking-state" role="status">
                순위를 불러오는 중입니다.
              </p>
            ) : !data?.data[key].length ? (
              <p className="explore-ranking-state">
                이 기간에 포착된 이슈가 없습니다.
              </p>
            ) : (
              <ol
                className="explore-ranking-list"
                aria-label={`${title} 급증점수 순위`}
              >
                {data.data[key].map((issue) => (
                  <li key={issue.id}>
                    <a href={`#/issues/${encodeURIComponent(issue.id)}`}>
                      <span>{issue.label?.trim() || "제목 미제공"}</span>
                      <strong
                        aria-label={`급증점수 ${metricLabel(issue.pulseScore)}`}
                      >
                        {metricLabel(issue.pulseScore)}
                      </strong>
                    </a>
                  </li>
                ))}
              </ol>
            )}
          </section>
        ))
      )}
    </aside>
  );
}
