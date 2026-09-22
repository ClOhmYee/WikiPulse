import { useCallback, useState } from "react";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import { metricLabel } from "../event/presentation.js";

export default function IssueRankings() {
  const [period, setPeriod] = useState("monthly");
  const load = useCallback(
    (signal) => dataClient.getIssueRankings({}, { signal }),
    [],
  );
  const { data, loading, error, reload } = useAsyncResource(
    load,
    "issue-rankings",
  );
  const entries = data?.data[period] || [];
  return (
    <aside
      className="explore-rankings"
      aria-label="기간별 이슈 Top 10"
      aria-busy={loading}
    >
      <section className="explore-ranking" aria-labelledby="ranking-title">
        <div className="explore-ranking-heading">
          <h2 id="ranking-title">TOP 10</h2>
          <div className="wp-segment" role="group" aria-label="순위 기간">
            {[
              { key: "monthly", label: "30일" },
              { key: "yearly", label: "1년" },
            ].map(({ key, label }) => (
              <button
                key={key}
                aria-pressed={period === key}
                onClick={() => setPeriod(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {error ? (
          <div className="explore-ranking-error" role="status">
            <p>이슈 순위를 불러오지 못했습니다.</p>
            <button className="wp-text-button" onClick={reload}>
              순위 다시 불러오기
            </button>
          </div>
        ) : loading ? (
          <p className="explore-ranking-state" role="status">
            순위를 불러오는 중입니다.
          </p>
        ) : !entries.length ? (
          <p className="explore-ranking-state" role="status">
            이 기간에 포착된 이슈가 없습니다.
          </p>
        ) : (
          <ol
            className="explore-ranking-list"
            aria-label={`최근 ${period === "monthly" ? "30일" : "1년"} 급증점수 순위`}
          >
            {entries.map((issue) => (
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
    </aside>
  );
}
