import { useEffect, useRef, useState } from "react";
import { Maximize, Minus, Plus } from "lucide-react";

const POSITIONS = [
  [270, 255],
  [610, 145],
  [720, 380],
  [370, 475],
  [135, 475],
  [870, 180],
];
const MOBILE_POSITIONS = [
  [155, 125],
  [445, 125],
  [155, 305],
  [445, 305],
  [155, 485],
  [445, 485],
];
const SHORT_LABELS = {
  geopolitics: "호르무즈 · 에너지",
  technology: "AI 반도체 통제",
  energy: "원자력 발전",
  space: "재사용 발사체",
  materials: "배터리 공급망",
  security: "클라우드 보안",
};
const hash = (text) =>
  [...text].reduce((n, ch) => (n * 31 + ch.charCodeAt(0)) >>> 0, 1234);

export default function PulseMap({
  events,
  categories,
  isExample = false,
  selectedId,
  onSelect,
  period = "24h",
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [compact, setCompact] = useState(
    () => window.matchMedia("(max-width: 720px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(max-width: 720px)");
    const update = () => setCompact(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const drag = useRef(null);
  const svgRef = useRef(null);
  const sceneWidth = compact ? 600 : 1000;
  const sceneHeight = compact ? 650 : 600;
  const sceneEvents = events.map((event, i) => ({
    ...event,
    position: (compact ? MOBILE_POSITIONS : POSITIONS)[i % POSITIONS.length],
  }));
  const stars = Array.from({ length: 65 }, (_, i) => ({
    x: (i * 137 + 31) % 1000,
    y: (i * 73 + 17) % 600,
    r: i % 5 === 0 ? 1.7 : 0.9,
  }));
  const reset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };
  function startDrag(event) {
    if (event.target.closest("[data-event-node]")) return;
    drag.current = { x: event.clientX, y: event.clientY, pan };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function moveDrag(event) {
    if (!drag.current) return;
    const factor = sceneWidth / (svgRef.current?.clientWidth || sceneWidth);
    setPan({
      x: drag.current.pan.x + (event.clientX - drag.current.x) * factor,
      y: drag.current.pan.y + (event.clientY - drag.current.y) * factor,
    });
  }
  return (
    <div className="pulse-map" role="region" aria-label="사건 관계 지도">
      <div className="pulse-map__caption">
        <span className="pulse-map__status" />
        <span>{events.length}개의 사건 신호</span>
        <span className="wp-muted">
          {period === "24h" ? "24시간" : period === "3d" ? "3일" : "7일"} 누적
          편집
        </span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${sceneWidth} ${sceneHeight}`}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        aria-label="사건을 선택하면 요약을 볼 수 있습니다"
      >
        <defs>
          <radialGradient id="map-atmosphere">
            <stop stopColor="#12404b" stopOpacity=".32" />
            <stop offset="1" stopColor="#050a0f" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="1000" height="600" fill="url(#map-atmosphere)" />
        {stars.map((star, i) => (
          <circle
            key={i}
            {...star}
            cx={star.x}
            cy={star.y}
            fill="#72949d"
            opacity=".25"
          />
        ))}
        <g
          transform={`translate(${sceneWidth / 2 + pan.x} ${sceneHeight / 2 + pan.y}) scale(${zoom}) translate(${-sceneWidth / 2} ${-sceneHeight / 2})`}
        >
          {sceneEvents.map((event) => {
            const [cx, cy] = event.position;
            const selected = event.id === selectedId;
            const color =
              categories.find((category) => category.id === event.category)
                ?.color || "#86c9c4";
            const count = Math.max(10, event.articleIds.length * 5);
            const seed = hash(event.id);
            const radius = compact
              ? 57
              : selected
                ? 83
                : 57 + Math.min(25, event.pulse);
            const dots = Array.from({ length: count }, (_, n) => {
              const angle = n * 2.39996 + seed;
              const distance = Math.sqrt((n + 1) / count) * radius;
              return {
                x: cx + Math.cos(angle) * distance,
                y: cy + Math.sin(angle) * distance * 0.67,
              };
            });
            return (
              <g
                key={event.id}
                className="pulse-map__cluster"
                data-selected={selected}
                data-event-node="true"
                role="button"
                tabIndex="0"
                aria-pressed={selected}
                aria-label={`${event.title}, Pulse ${event.pulse}배`}
                onClick={() => onSelect(event.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(event.id);
                  }
                }}
              >
                <ellipse
                  cx={cx}
                  cy={cy}
                  rx={radius + 30}
                  ry={radius * 0.7 + 25}
                  fill={color}
                  fillOpacity={selected ? ".06" : ".015"}
                  stroke={color}
                  strokeOpacity={selected ? ".4" : ".12"}
                  strokeDasharray={selected ? "none" : "3 6"}
                />
                {dots.map((dot, i) => (
                  <g key={i}>
                    <line
                      x1={dot.x}
                      y1={dot.y}
                      x2={cx}
                      y2={cy}
                      stroke={color}
                      strokeOpacity={selected ? ".32" : ".19"}
                    />
                    {i > 0 && (
                      <line
                        x1={dot.x}
                        y1={dot.y}
                        x2={dots[i - 1].x}
                        y2={dots[i - 1].y}
                        stroke={color}
                        strokeOpacity=".17"
                      />
                    )}
                    <circle
                      cx={dot.x}
                      cy={dot.y}
                      r={i % 4 === 0 ? 3 : 1.8}
                      fill={color}
                      opacity={i % 4 === 0 ? ".9" : ".5"}
                    />
                  </g>
                ))}
                <circle
                  cx={cx}
                  cy={cy}
                  r={selected ? 12 : 8}
                  fill={color}
                  fillOpacity=".16"
                />
                <circle cx={cx} cy={cy} r={selected ? 5 : 3.5} fill={color} />
                <text
                  x={cx}
                  y={cy + radius * 0.7 + (compact ? 30 : 42)}
                  textAnchor="middle"
                  fill={selected ? "#f3f7f7" : "#c2d0d5"}
                  fontSize={compact ? 21 : 18}
                  fontWeight={selected ? 600 : 450}
                >
                  {(isExample && SHORT_LABELS[event.category]) || event.title}
                </text>
                <text
                  x={cx}
                  y={cy + radius * 0.7 + (compact ? 55 : 65)}
                  textAnchor="middle"
                  fill={color}
                  fontSize={compact ? 18 : 14}
                >
                  {event.pulse.toFixed(1)}× · {event.articleIds.length}개 문서
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <div className="pulse-map__legend">
        <span>
          <i />
          편집 신호
        </span>
        <span>
          <b />
          문서 연결 예시
        </span>
      </div>
      <div className="pulse-map__controls">
        <button
          className="wp-icon-button"
          onClick={() => setZoom((v) => Math.min(2, v + 0.2))}
          disabled={zoom >= 2}
          aria-label="지도 확대"
        >
          <Plus size={16} />
        </button>
        <button
          className="wp-icon-button"
          onClick={() => setZoom((v) => Math.max(0.6, v - 0.2))}
          disabled={zoom <= 0.6}
          aria-label="지도 축소"
        >
          <Minus size={16} />
        </button>
        <button
          className="wp-icon-button"
          onClick={reset}
          aria-label="지도 위치 초기화"
        >
          <Maximize size={15} />
        </button>
      </div>
    </div>
  );
}
