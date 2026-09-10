import { ArrowRight, Bookmark, ExternalLink } from "lucide-react";
import { CategoryTag } from "../../components/ui/CategoryTag";
import { getIssueCategory } from "../../data/categories.js";
import { isNewIssue, kstTimestamp } from "../../data/pulse/time.js";
export function SignalBadges({ cluster, meta }) {
  return (
    <span className="pulse-badges">
      {cluster.hot && (
        <span
          className="pulse-badge pulse-badge--hot"
          title="이 시점에 급증 판정을 통과했습니다"
        >
          HOT
        </span>
      )}
      {isNewIssue(
        cluster.firstDetectedAt,
        meta.snapshotTs,
        meta.newWindowHours,
      ) && (
        <span
          className="pulse-badge pulse-badge--new"
          title={`이 시점 기준 ${meta.newWindowHours}시간 내 처음 감지되었습니다`}
        >
          NEW
        </span>
      )}
    </span>
  );
}
const metric = (v, completeness) =>
  v === null
    ? completeness === "pending"
      ? "집계 중"
      : "미제공"
    : new Intl.NumberFormat("ko-KR").format(v);
export default function PulsePreview({
  cluster,
  meta,
  nodeId,
  onNodeSelect,
  savedEvents,
  onToggleEvent,
}) {
  const node = cluster?.nodes.find((v) => v.pageId === nodeId);
  const links =
    cluster?.edges.filter(
      (v) => v.sourcePageId === nodeId || v.targetPageId === nodeId,
    ) || [];
  return (
    <aside
      className="signal-preview pulse-preview"
      aria-label="선택한 사건"
      data-snapshot={meta.snapshotTs}
    >
      {!cluster ? (
        <div className="pulse-preview__empty">
          <h2>이슈의 맥락을 따라가세요</h2>
          <p>
            지도에서 클러스터를 선택하면 이 시점의 요약과 구성 문서를 확인할 수
            있습니다.
          </p>
        </div>
      ) : (
        <>
          <div className="signal-preview__top">
            <CategoryTag category={getIssueCategory(cluster.category)} />
            <button
              className="wp-icon-button"
              onClick={() => onToggleEvent(cluster.id)}
              aria-pressed={savedEvents.includes(cluster.id)}
              aria-label={
                savedEvents.includes(cluster.id)
                  ? "선택한 사건 저장 해제"
                  : "선택한 사건 저장"
              }
            >
              <Bookmark
                size={18}
                fill={
                  savedEvents.includes(cluster.id) ? "currentColor" : "none"
                }
              />
            </button>
          </div>
          <SignalBadges cluster={cluster} meta={meta} />
          <h2>{cluster.label}</h2>
          <p>{cluster.summary || "이 시점의 요약이 아직 없습니다."}</p>
          <dl className="pulse-metrics">
            <div>
              <dt>이슈 급증 점수</dt>
              <dd>{cluster.pulseScore.toFixed(1)}</dd>
            </div>
            <div>
              <dt>구성 문서</dt>
              <dd>{cluster.memberCount}개</dd>
            </div>
          </dl>
          <p className="wp-small wp-muted">
            최초 감지{" "}
            {cluster.firstDetectedAt
              ? kstTimestamp(cluster.firstDetectedAt)
              : "미제공"}
          </p>
          <h3>구성 문서</h3>
          <div className="pulse-document-list" aria-label="구성 문서 선택">
            {cluster.nodes.map((v) => (
              <button
                key={v.pageId}
                className="pulse-document"
                aria-pressed={nodeId === v.pageId}
                onClick={() => onNodeSelect(v.pageId)}
              >
                <span>{v.title}</span>
                <small>{v.isSeed ? "급증 감지" : "연관 문서"}</small>
              </button>
            ))}
          </div>
          {node && (
            <section className="pulse-node-detail" aria-label="선택한 문서">
              <h3>{node.title}</h3>
              <dl className="pulse-metrics">
                <div>
                  <dt>편집 수 / 기준선</dt>
                  <dd>
                    {metric(node.editCount, node.completeness)} /{" "}
                    {metric(node.editBaseline, node.completeness)}
                  </dd>
                </div>
                <div>
                  <dt>조회 수 / 기준선</dt>
                  <dd>
                    {metric(node.views, node.completeness)} /{" "}
                    {metric(node.viewBaseline, node.completeness)}
                  </dd>
                </div>
                <div>
                  <dt>급증 점수</dt>
                  <dd>{metric(node.spikeScore, node.completeness)}</dd>
                </div>
              </dl>
              <p className="wp-small wp-muted">
                집계 구간
                <br />
                {kstTimestamp(node.windowStart)}
                <br />~ {kstTimestamp(node.windowEnd)}
              </p>
              <a
                className="wp-text-button"
                href={`https://${node.wiki.replace(/wiki$/, "")}.wikipedia.org/wiki/${encodeURIComponent(node.title.replaceAll(" ", "_"))}`}
                target="_blank"
                rel="noreferrer"
              >
                위키백과 원문
                <ExternalLink size={13} />
              </a>
              <h4>연결 근거</h4>
              {links.length ? (
                <ul className="pulse-evidence">
                  {links.map((edge) => (
                    <li key={edge.id}>
                      <strong>
                        {
                          cluster.nodes.find(
                            (v) =>
                              v.pageId ===
                              (edge.sourcePageId === nodeId
                                ? edge.targetPageId
                                : edge.sourcePageId),
                          )?.title
                        }
                      </strong>
                      <span>
                        {edge.kind === "clickstream"
                          ? `Clickstream · ${edge.evidence.month} · ${metric(edge.weight)}회 이동`
                          : `Wikidata · ${kstTimestamp(edge.evidence.observedAt)}`}
                      </span>
                      <span>
                        {edge.directed
                          ? `${edge.sourcePageId === nodeId ? "선택 문서에서 이동" : "선택 문서로 이동"}`
                          : "방향 없는 관계"}{" "}
                        · {edge.evidence.label}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="wp-small wp-muted">
                  제공된 연결 근거가 없습니다.
                </p>
              )}
            </section>
          )}
          <a
            className="wp-button"
            data-variant="primary"
            href={`#/issues/${encodeURIComponent(cluster.id)}`}
          >
            사건 자세히 보기
            <ArrowRight size={16} />
          </a>
        </>
      )}
      <p className="pulse-preview__timestamp">
        {kstTimestamp(meta.snapshotTs)} 기준
      </p>
    </aside>
  );
}
