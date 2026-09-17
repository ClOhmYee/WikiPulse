import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  Maximize,
  Minimize,
  RotateCcw,
  Minus,
  Plus,
  Radar,
  Pause,
} from "lucide-react";
import { isNewIssue } from "../../data/pulse/time.js";
import { NEON_COLORS } from "./neonTheme.js";
import PulseCluster from "./PulseCluster.jsx";
import useMapView from "./useMapView.js";
import useNeonScan from "./useNeonScan.js";
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
  scanEnabled,
  onToggleScan,
}) {
  const svgRef = useRef(null),
    drag = useRef(null);
  const marker = useId().replaceAll(":", "");
  const { camera, current, subscribe, move, stop, zoomBy } =
    useMapCamera(svgRef);
  const view = useMapView(svgRef, scene, current, subscribe);
  const reducedMotion = useNeonScan(svgRef, scene, scanEnabled, view);
  const [emphasized, setEmphasized] = useState(null);
  const [pointerFocus, setPointerFocus] = useState(false);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const svg = svgRef.current;
    const measure = () =>
      setViewport({ width: svg.clientWidth, height: svg.clientHeight });
    const observer = new ResizeObserver(measure);
    measure();
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);
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
  const pointAt = (e) => mapPoint(svgRef.current, e.clientX, e.clientY);
  const trackClusterOrbit = useCallback(
    (e) => {
      if (drag.current || e.pointerType === "touch" || reducedMotion) return;
      const cluster = e.currentTarget;
      const matrix = cluster.getScreenCTM();
      if (!matrix) return;
      const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(
        matrix.inverse(),
      );
      if (Math.hypot(point.x, point.y) < 1) return;
      // Center the 38-degree arc on the pointer; the second arc is opposite it.
      // Update only this SVG decoration, without rerendering every document.
      cluster.style.setProperty(
        "--orbit-angle",
        `${(Math.atan2(point.y, point.x) * 180) / Math.PI - 19}deg`,
      );
    },
    [reducedMotion],
  );
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
      data-theme="neon-pulse"
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
        data-pointer-focus={pointerFocus}
        onBlur={(e) => {
          if (e.target === e.currentTarget) setPointerFocus(false);
        }}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          setPointerFocus(false);
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
          setPointerFocus(true);
          const point = pointAt(e);
          drag.current = { x: point.x, y: point.y, camera: stop() };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const point = pointAt(e);
          move(
            {
              ...drag.current.camera,
              x: drag.current.camera.x + point.x - drag.current.x,
              y: drag.current.camera.y + point.y - drag.current.y,
            },
            false,
          );
        }}
        onPointerUp={() => {
          if (drag.current) move(stop());
          drag.current = null;
        }}
        onPointerCancel={() => {
          if (drag.current) move(stop());
          drag.current = null;
        }}
      >
        <defs>
          {Object.entries(NEON_COLORS).map(([category, color]) => (
            <g key={category}>
              <radialGradient
                id={`${marker}-${category}-body`}
                cx="42%"
                cy="35%"
                r="68%"
              >
                <stop offset="0" stopColor="#091322" />
                <stop offset="0.72" stopColor="#07101f" />
                <stop offset="1" stopColor={color} stopOpacity="0.38" />
              </radialGradient>
              <radialGradient id={`${marker}-${category}-halo`}>
                <stop offset="0.63" stopColor={color} stopOpacity="0" />
                <stop offset="0.77" stopColor={color} stopOpacity="0.04" />
                <stop offset="0.86" stopColor={color} stopOpacity="0.35" />
                <stop offset="1" stopColor={color} stopOpacity="0" />
              </radialGradient>
              <radialGradient id={`${marker}-${category}-field`}>
                <stop offset="0" stopColor={color} stopOpacity="0.065" />
                <stop offset="1" stopColor={color} stopOpacity="0" />
              </radialGradient>
              <radialGradient
                id={`${marker}-${category}-title-light`}
                cx="95%"
                cy="100%"
                r="95%"
              >
                <stop offset="0" stopColor={color} stopOpacity="0.8" />
                <stop offset="0.45" stopColor={color} stopOpacity="0.22" />
                <stop offset="1" stopColor={color} stopOpacity="0" />
              </radialGradient>
            </g>
          ))}
          <radialGradient id={`${marker}-scan-trail`}>
            <stop offset="0.90" stopColor="#49dfff" stopOpacity="0" />
            <stop offset="0.985" stopColor="#49dfff" stopOpacity="0.08" />
            <stop offset="1" stopColor="#49dfff" stopOpacity="0.22" />
          </radialGradient>
          <marker
            id={`${marker}-arrow`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="context-stroke" />
          </marker>
        </defs>
        <g
          style={{
            transformBox: "view-box",
            transform: `translate(50%, 50%) translate(${camera.x * MAP_SCALE}px, ${camera.y * MAP_SCALE}px) scale(${camera.zoom * MAP_SCALE})`,
          }}
        >
          {clusters.map((cluster) => (
            <PulseCluster
              key={cluster.issueKey}
              cluster={cluster}
              active={cluster.issueKey === selectedKey}
              nodeId={cluster.issueKey === selectedKey ? nodeId : null}
              emphasized={
                emphasized?.issueKey === cluster.issueKey
                  ? emphasized.pageId
                  : null
              }
              camera={camera}
              compact={compact}
              viewport={viewport}
              marker={marker}
              meta={meta}
              onSelect={onSelect}
              onNodeSelect={onNodeSelect}
              onEmphasize={setEmphasized}
              trackClusterOrbit={trackClusterOrbit}
            />
          ))}
          <g className="pulse-scan" aria-hidden="true" pointerEvents="none">
            <circle className="pulse-scan__echo" r="0" />
            <circle
              className="pulse-scan__wave"
              r="0"
              fill={`url(#${marker}-scan-trail)`}
            />
          </g>
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
            className="wp-icon-button document-map__scan-control"
            aria-label={
              reducedMotion
                ? "모션 감소 설정으로 스캔 효과 꺼짐"
                : scanEnabled
                  ? "스캔 효과 일시정지"
                  : "스캔 효과 재생"
            }
            title={
              reducedMotion ? "모션 감소 설정 적용 중" : "원형 스캔 시각 효과"
            }
            disabled={reducedMotion}
            onClick={onToggleScan}
          >
            {scanEnabled && !reducedMotion ? (
              <Pause size={16} />
            ) : (
              <Radar size={17} />
            )}
          </button>
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
