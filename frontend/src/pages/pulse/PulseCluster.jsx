import { memo, useMemo } from "react";
import { isNewIssue } from "../../data/pulse/time.js";
import { NEON_COLORS, neonColor } from "./neonTheme.js";
import { MAP_SCALE, DEFAULT_ZOOM } from "./useMapCamera.js";
import DocumentLabels from "./DocumentLabels.jsx";

function activate(action) {
  return (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      action();
    }
  };
}

export default memo(function PulseCluster({
  cluster,
  active,
  nodeId,
  emphasized,
  camera,
  compact,
  viewport,
  marker,
  meta,
  onSelect,
  onNodeSelect,
  onEmphasize,
  trackClusterOrbit,
}) {
  const titleUnit = (camera.zoom / DEFAULT_ZOOM) ** 0.35 / camera.zoom;
  const titleSize = compact ? 23 : 20;
  const labelSize = (compact ? 14 : 13) / camera.zoom ** 0.8;
  const color = neonColor(cluster.category);
  const category = Object.hasOwn(NEON_COLORS, cluster.category)
    ? cluster.category
    : "other";
  const nodes = useMemo(
    () => new Map(cluster.nodes.map((node) => [node.pageId, node])),
    [cluster],
  );
  const connected = useMemo(
    () =>
      new Set(
        cluster.edges
          .filter(
            (edge) =>
              edge.sourcePageId === nodeId || edge.targetPageId === nodeId,
          )
          .flatMap((edge) => [edge.sourcePageId, edge.targetPageId]),
      ),
    [cluster, nodeId],
  );
  const { titleLines, lineHeight, titleBoxWidth, titleBoxHeight, titleBoxY } =
    useMemo(() => {
      const lineLimit = compact ? 14 : 20;
      const titleLines = cluster.label
        .split(/\s+/)
        .flatMap(
          (word) => word.match(new RegExp(`.{1,${lineLimit}}`, "gu")) || [],
        )
        .reduce((lines, word) => {
          if (!lines.length || `${lines.at(-1)} ${word}`.length > lineLimit)
            lines.push(word);
          else lines[lines.length - 1] += ` ${word}`;
          return lines;
        }, []);
      if (titleLines.length > 3) {
        titleLines.splice(3);
        titleLines[2] = `${titleLines[2].slice(0, lineLimit - 1)}…`;
      }
      const lineHeight = titleSize * 1.3;
      const titleBoxWidth =
        Math.max(
          ...titleLines.map(
            (line) =>
              [...line].reduce(
                (width, char) =>
                  width + (/[^\u0000-\u00ff]/u.test(char) ? 1 : 0.62),
                0,
              ) * titleSize,
          ),
        ) + 24;
      const titleBoxHeight = titleLines.length * lineHeight + 16;
      const titleBoxY = -12 - titleBoxHeight;

      return {
        titleLines,
        lineHeight,
        titleBoxWidth,
        titleBoxHeight,
        titleBoxY,
      };
    }, [cluster.label, compact, titleSize]);
  return (
    <g
      key={cluster.issueKey}
      transform={`translate(${cluster.x} ${cluster.y})`}
      className="document-cluster"
      data-issue-key={cluster.issueKey}
      data-rank={cluster.rank}
      data-selected={active}
      style={{ "--cluster-color": color }}
      onPointerMove={trackClusterOrbit}
    >
      <g
        role="button"
        tabIndex="0"
        aria-label={`${cluster.label}, ${cluster.memberCount}개 문서`}
        aria-pressed={active}
        onClick={() => onSelect(cluster.issueKey)}
        onKeyDown={activate(() => onSelect(cluster.issueKey))}
      >
        <circle className="document-cluster__boundary" r={cluster.radius} />
        <circle
          className="document-cluster__field"
          r={cluster.radius}
          fill={`url(#${marker}-${category}-field)`}
          aria-hidden="true"
        />
        <circle
          className="document-cluster__orbit"
          r={cluster.radius}
          pathLength="360"
          strokeDasharray="38 142"
          aria-hidden="true"
        />
        <g
          className="document-cluster__heading"
          data-scan-x={cluster.x}
          data-scan-y={
            cluster.y - cluster.radius - (12 + titleBoxHeight / 2) * titleUnit
          }
          data-title-offset={12 + titleBoxHeight / 2}
          data-title-width={titleBoxWidth}
          data-title-height={titleBoxHeight}
          transform={`translate(0 ${-cluster.radius}) scale(${titleUnit})`}
          data-scan-dynamic="true"
          style={{ "--title-unit": 1 }}
        >
          <rect
            className="document-cluster__title-glow"
            x={-titleBoxWidth / 2 + 3}
            y={titleBoxY + 4}
            width={titleBoxWidth}
            height={titleBoxHeight}
            rx={6}
            fill={`url(#${marker}-${category}-title-light)`}
            aria-hidden="true"
          />
          <rect
            className="document-cluster__title-box"
            x={-titleBoxWidth / 2}
            y={titleBoxY}
            width={titleBoxWidth}
            height={titleBoxHeight}
            rx={4}
            vectorEffect="non-scaling-stroke"
            aria-hidden="true"
          />
          <rect
            className="document-cluster__title-shine"
            x={-titleBoxWidth / 2}
            y={titleBoxY}
            width={titleBoxWidth}
            height={titleBoxHeight}
            rx={4}
            fill={`url(#${marker}-${category}-title-light)`}
            aria-hidden="true"
          />
          <text
            className="document-cluster__title"
            style={{
              fontSize: titleSize,
              strokeWidth: 4,
            }}
            textAnchor="middle"
            dominantBaseline="central"
            y={
              titleBoxY +
              titleBoxHeight / 2 -
              ((titleLines.length - 1) * lineHeight) / 2
            }
          >
            {titleLines.map((line, i) => (
              <tspan key={i} x="0" dy={i ? lineHeight : 0}>
                {line}
              </tspan>
            ))}
          </text>
        </g>
        {isNewIssue(
          cluster.firstDetectedAt,
          meta.snapshotTs,
          meta.newWindowHours,
        ) && (
          <text
            className="document-cluster__badge"
            textAnchor="middle"
            y={cluster.radius + 24}
          >
            NEW
          </text>
        )}
      </g>
      <g className="document-edges" aria-hidden="true">
        {cluster.edges.map((edge) => {
          const a = nodes.get(edge.sourcePageId),
            b = nodes.get(edge.targetPageId);
          const distance = Math.hypot(b.x - a.x, b.y - a.y) || 1;
          const dx = (b.x - a.x) / distance,
            dy = (b.y - a.y) / distance;
          return (
            <line
              key={edge.id}
              data-edge-id={edge.id}
              data-kind={edge.kind}
              data-scan-x={cluster.x + (a.x + b.x) / 2}
              data-scan-y={cluster.y + (a.y + b.y) / 2}
              data-highlighted={
                active &&
                (edge.sourcePageId === nodeId || edge.targetPageId === nodeId)
              }
              x1={a.x + dx * (a.radius + 2)}
              y1={a.y + dy * (a.radius + 2)}
              x2={b.x - dx * (b.radius + 4)}
              y2={b.y - dy * (b.radius + 4)}
              strokeWidth={
                edge.kind === "clickstream"
                  ? 1 + Math.min(2, Math.log1p(edge.weight) / 6)
                  : 1.6
              }
              strokeDasharray={edge.kind === "wikidata" ? "5 5" : undefined}
              markerEnd={edge.directed ? `url(#${marker}-arrow)` : undefined}
            />
          );
        })}
      </g>
      {cluster.nodes.map((node) => {
        return (
          <g
            key={node.pageId}
            className="document-node"
            data-page-id={node.pageId}
            data-selected={active && nodeId === node.pageId}
            data-related={active && connected.has(node.pageId)}
            data-label-visible="true"
            data-pending={node.sizeScore === null}
            data-scan-x={cluster.x + node.x}
            data-scan-y={cluster.y + node.y}
            onPointerEnter={() =>
              onEmphasize({ issueKey: cluster.issueKey, pageId: node.pageId })
            }
            onPointerLeave={() => onEmphasize(null)}
            onFocus={() =>
              onEmphasize({ issueKey: cluster.issueKey, pageId: node.pageId })
            }
            onBlur={() => onEmphasize(null)}
            role="button"
            tabIndex="0"
            aria-pressed={active && nodeId === node.pageId}
            aria-label={`${node.title}, ${node.isSeed ? "급증 감지 문서" : "연관 문서"}`}
            transform={`translate(${node.x} ${node.y})`}
            onClick={() => onNodeSelect(cluster.issueKey, node.pageId)}
            onKeyDown={activate(() =>
              onNodeSelect(cluster.issueKey, node.pageId),
            )}
          >
            <circle
              className="document-node__hit"
              r={Math.max(26, node.radius)}
            />
            <circle
              className="document-node__halo"
              r={node.radius + 7}
              fill={`url(#${marker}-${category}-halo)`}
              aria-hidden="true"
            />
            <circle
              className="document-node__body"
              r={node.radius}
              fill={`url(#${marker}-${category}-body)`}
              data-size-score={node.sizeScore ?? "missing"}
            />
            <circle
              className="document-node__echo"
              r={node.radius + 4}
              aria-hidden="true"
            />
            {node.isSeed && (
              <circle
                className="document-node__seed"
                cy={-node.radius + 5}
                r={2.5}
              />
            )}
            <title>
              {node.title} ·{" "}
              {node.sizeScore === null
                ? "급증 지표 미제공"
                : `급증 점수 ${node.spikeScore ?? "미제공"}`}
            </title>
          </g>
        );
      })}
      <DocumentLabels
        nodes={cluster.nodes}
        fontSize={labelSize}
        bounds={{
          left:
            (8 - viewport.width / 2 - camera.x * MAP_SCALE) /
              (camera.zoom * MAP_SCALE) -
            cluster.x,
          right:
            (viewport.width / 2 - 8 - camera.x * MAP_SCALE) /
              (camera.zoom * MAP_SCALE) -
            cluster.x,
          top:
            (8 - viewport.height / 2 - camera.y * MAP_SCALE) /
              (camera.zoom * MAP_SCALE) -
            cluster.y,
          bottom:
            (viewport.height / 2 - 8 - camera.y * MAP_SCALE) /
              (camera.zoom * MAP_SCALE) -
            cluster.y,
        }}
        emphasized={emphasized}
        selected={active ? nodeId : null}
      />
    </g>
  );
});
