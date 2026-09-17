import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Maximize, Minimize, RotateCcw, Minus, Plus } from "lucide-react";
import { getIssueCategory } from "../../data/categories.js";
import { isNewIssue } from "../../data/pulse/time.js";
import useMapCamera, {
  MAP_SCALE,
  mapPoint,
  MIN_ZOOM,
  MAX_ZOOM,
  DEFAULT_ZOOM,
} from "./useMapCamera.js";

export default function PulseMap({
  scene,
  cameraState,
  selectedKey,
  nodeId,
  onSelect,
  onNodeSelect,
  meta,
  expanded,
  onToggleExpanded,
}) {
  const svgRef = useRef(null),
    drag = useRef(null);
  const marker = useId().replaceAll(":", "");
  const { camera, move, stop, zoomBy } = useMapCamera(svgRef);
  const [compact, setCompact] = useState(
    () => window.matchMedia("(max-width: 720px)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(max-width: 720px)");
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useLayoutEffect(() => {
    const saved = cameraState.current;
    const canRestore =
      saved && saved.scene === scene && saved.snapshotTs === meta.snapshotTs;
    move(canRestore ? saved.camera : { zoom: DEFAULT_ZOOM, x: 0, y: 0 });
    return () => {
      // Keep the last rendered view across dialog remounts and viewport changes.
      cameraState.current = {
        camera: stop(),
        scene,
        snapshotTs: meta.snapshotTs,
      };
    };
  }, [meta.snapshotTs, scene, cameraState, stop, move]);
  const titleSize = (compact ? 23 : 20) / camera.zoom;
  const labelSize = (compact ? 14 : 13) / camera.zoom ** 0.8;
  const showLabels = camera.zoom >= 0.8;
  const activate = (action) => (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      action();
    }
  };
  const pointAt = (e) => mapPoint(svgRef.current, e.clientX, e.clientY);
  const clusters = scene.clusters;
  const newCount = clusters.filter((v) =>
    isNewIssue(v.firstDetectedAt, meta.snapshotTs, meta.newWindowHours),
  ).length;
  return (
    <div
      className="pulse-map document-map"
      role="region"
      aria-label="사건 관계 지도"
      data-snapshot={meta.snapshotTs}
      data-zoom={camera.zoom}
    >
      <div className="document-map__caption">
        <strong>
          {clusters.length}개 이슈{newCount ? ` · ${newCount}개 NEW` : ""}
        </strong>
        <span>
          {clusters.reduce((n, v) => n + v.nodes.length, 0)}개 문서 · 문서를
          선택해 연결 근거를 확인하세요 · 휠로 확대·축소 · 드래그로 주변 탐색
        </span>
      </div>
      <svg
        ref={svgRef}
        role="group"
        tabIndex="0"
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          const delta = {
            ArrowLeft: [80, 0],
            ArrowRight: [-80, 0],
            ArrowUp: [0, 80],
            ArrowDown: [0, -80],
          }[e.key];
          if (delta) {
            e.preventDefault();
            const old = stop();
            move({
              ...old,
              x: old.x + delta[0],
              y: old.y + delta[1],
            });
          }
        }}
        aria-label="이슈와 문서 관계 그래프"
        onPointerDown={(e) => {
          if (e.target.closest('[role="button"]')) return;
          const point = pointAt(e);
          drag.current = { x: point.x, y: point.y, camera: stop() };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const point = pointAt(e);
          move({
            ...drag.current.camera,
            x: drag.current.camera.x + point.x - drag.current.x,
            y: drag.current.camera.y + point.y - drag.current.y,
          });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <defs>
          <marker
            id={`${marker}-arrow`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="#83a5b1" />
          </marker>
        </defs>
        <g
          style={{
            transformBox: "view-box",
            transform: `translate(50%, 50%) translate(${camera.x * MAP_SCALE}px, ${camera.y * MAP_SCALE}px) scale(${camera.zoom * MAP_SCALE})`,
          }}
        >
          {clusters.map((cluster) => {
            const active = cluster.issueKey === selectedKey,
              color = getIssueCategory(cluster.category).color;
            const nodes = new Map(
              cluster.nodes.map((node) => [node.pageId, node]),
            );
            const connected = new Set(
              cluster.edges
                .filter(
                  (edge) =>
                    edge.sourcePageId === nodeId ||
                    edge.targetPageId === nodeId,
                )
                .flatMap((edge) => [edge.sourcePageId, edge.targetPageId]),
            );
            const lineLimit = compact ? 14 : 20;
            const titleLines = cluster.label
              .split(/\s+/)
              .flatMap(
                (word) =>
                  word.match(new RegExp(`.{1,${lineLimit}}`, "gu")) || [],
              )
              .reduce((lines, word) => {
                if (
                  !lines.length ||
                  `${lines.at(-1)} ${word}`.length > lineLimit
                )
                  lines.push(word);
                else lines[lines.length - 1] += ` ${word}`;
                return lines;
              }, []);
            if (titleLines.length > 3) {
              titleLines.splice(3);
              titleLines[2] = `${titleLines[2].slice(0, lineLimit - 1)}…`;
            }
            const lineHeight = titleSize * 1.3;
            return (
              <g
                key={cluster.issueKey}
                transform={`translate(${cluster.x} ${cluster.y})`}
                className="document-cluster"
                data-issue-key={cluster.issueKey}
                data-rank={cluster.rank}
                data-selected={active}
                style={{ "--cluster-color": color }}
              >
                <g
                  role="button"
                  tabIndex="0"
                  aria-label={`${cluster.label}, ${cluster.memberCount}개 문서`}
                  aria-pressed={active}
                  onClick={() => onSelect(cluster.issueKey)}
                  onKeyDown={activate(() => onSelect(cluster.issueKey))}
                >
                  <circle
                    className="document-cluster__boundary"
                    r={cluster.radius}
                  />
                  <text
                    className="document-cluster__title"
                    style={{
                      fontSize: titleSize,
                      strokeWidth: 4 / camera.zoom,
                    }}
                    textAnchor="middle"
                    y={
                      -cluster.radius -
                      18 / camera.zoom -
                      (titleLines.length - 1) * lineHeight
                    }
                  >
                    {titleLines.map((line, i) => (
                      <tspan key={i} x="0" dy={i ? lineHeight : 0}>
                        {line}
                      </tspan>
                    ))}
                  </text>
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
                        data-highlighted={
                          active &&
                          (edge.sourcePageId === nodeId ||
                            edge.targetPageId === nodeId)
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
                        strokeDasharray={
                          edge.kind === "wikidata" ? "5 5" : undefined
                        }
                        markerEnd={
                          edge.directed ? `url(#${marker}-arrow)` : undefined
                        }
                      />
                    );
                  })}
                </g>
                {cluster.nodes.map((node) => (
                  <g
                    key={node.pageId}
                    className="document-node"
                    data-page-id={node.pageId}
                    data-selected={active && nodeId === node.pageId}
                    data-related={active && connected.has(node.pageId)}
                    data-label-visible={showLabels}
                    data-pending={node.sizeScore === null}
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
                      className="document-node__body"
                      r={node.radius}
                      data-size-score={node.sizeScore ?? "missing"}
                    />
                    {node.isSeed && (
                      <circle className="document-node__seed" r={3} />
                    )}
                    <text
                      textAnchor="middle"
                      y={node.radius + 18 / camera.zoom}
                      style={{
                        fontSize: labelSize,
                        strokeWidth: 4 / camera.zoom,
                      }}
                    >
                      {node.title.length > 25
                        ? `${node.title.slice(0, 24)}…`
                        : node.title}
                    </text>
                    <title>
                      {node.title} ·{" "}
                      {node.sizeScore === null
                        ? "급증 지표 미제공"
                        : `급증 점수 ${node.spikeScore ?? "미제공"}`}
                    </title>
                  </g>
                ))}
              </g>
            );
          })}
        </g>
      </svg>
      <div className="document-map__footer">
        <div className="document-map__legend">
          <span>
            <i />
            Clickstream 이동
          </span>
          <span>
            <i className="is-dashed" />
            Wikidata 관계
          </span>
          <span>
            <b />
            급증 감지 문서
          </span>
        </div>
        <div className="document-map__controls">
          <button
            className="wp-icon-button"
            aria-label="지도 축소"
            disabled={camera.zoom <= MIN_ZOOM}
            onClick={() => zoomBy(1 / 1.2, { x: 0, y: 0 })}
          >
            <Minus size={17} />
          </button>
          <button
            className="wp-icon-button"
            aria-label="지도 확대"
            disabled={camera.zoom >= MAX_ZOOM}
            onClick={() => zoomBy(1.2, { x: 0, y: 0 })}
          >
            <Plus size={17} />
          </button>
          <button
            className="wp-icon-button"
            aria-label="지도 위치 초기화"
            onClick={() => move({ zoom: DEFAULT_ZOOM, x: 0, y: 0 })}
          >
            <RotateCcw size={16} />
          </button>
          <button
            className="wp-icon-button"
            aria-label={expanded ? "전체화면 닫기" : "펄스맵 전체화면"}
            aria-expanded={expanded}
            onClick={onToggleExpanded}
          >
            {expanded ? <Minimize size={17} /> : <Maximize size={17} />}
          </button>
        </div>
      </div>
    </div>
  );
}
