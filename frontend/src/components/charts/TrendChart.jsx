import { useEffect, useId, useRef, useState } from "react";
import { formatNumber } from "../../lib/format";
export function TrendChart({
  data = [],
  isExample = false,
  valueKey = "edits",
  label = "편집 추이",
  color = "#86c9c4",
  baseline = false,
  height = 180,
  markers = [],
}) {
  const id = useId().replace(/:/g, "");
  const [hover, setHover] = useState(null);
  const figureRef = useRef(null);
  const [width, setWidth] = useState(720);
  useEffect(() => {
    const element = figureRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(200, entries[0].contentRect.width)),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const chartHeight = height,
    left = 40,
    right = 10,
    top = 13,
    bottom = 28;
  const numeric = (value) =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const values = data.map((item) => numeric(item[valueKey]));
  const baselineValues = data.map((item) => numeric(item.baseline));
  const available = values.filter((value) => value !== null);
  const times = data.map((item) => Date.parse(item.date));
  const timeAxis =
    times.length > 1 && times.every(Number.isFinite) && times.at(-1) > times[0];
  const isPrice = valueKey === "price";
  const minValue = available.length ? Math.min(...available) : 0;
  const maxValue = Math.max(
    1,
    ...available,
    ...(baseline ? baselineValues.filter((value) => value !== null) : []),
  );
  const span = Math.max(maxValue - minValue, maxValue * 0.01);
  const min = isPrice ? Math.max(0, minValue - span * 0.2) : 0;
  const max = isPrice ? maxValue + span * 0.2 : maxValue * 1.12;
  const x = (i) =>
    left +
    (timeAxis
      ? (times[i] - times[0]) / (times.at(-1) - times[0])
      : i / Math.max(1, data.length - 1)) *
      (width - left - right);
  const y = (v) =>
    top +
    (1 - (v - min) / Math.max(1, max - min)) * (chartHeight - top - bottom);
  const segments = (series) => {
    const parts = [];
    let current = [];
    series.forEach((value, i) => {
      if (value === null) {
        if (current.length) parts.push(current);
        current = [];
      } else current.push({ index: i, value });
    });
    if (current.length) parts.push(current);
    return parts;
  };
  const valueSegments = segments(values);
  const referenceSegments = segments(baselineValues);
  // 실제로 그려질 마커만 미리 계산한다 — 범례 노출과 렌더를 같은 조건으로 묶어
  // "이슈 발생 시점" 범례만 뜨고 마커는 없는 불일치를 막는다. 창보다 이른 이슈는
  // 버리고, 최신 봉 이후(가격 미도착) 이슈는 30일 유예 안에서 오른쪽 끝에 붙인다.
  const markerGraceMs = 1000 * 60 * 60 * 24 * 30;
  const visibleMarkers = timeAxis
    ? markers.flatMap((marker) => {
        const ms = Date.parse(marker.date);
        if (
          !Number.isFinite(ms) ||
          ms < times[0] ||
          ms > times.at(-1) + markerGraceMs
        )
          return [];
        const frac = Math.min(1, (ms - times[0]) / (times.at(-1) - times[0]));
        return [{ marker, mx: left + frac * (width - left - right) }];
      })
    : [];
  const active =
    hover === null ? data.length - 1 : Math.min(hover, data.length - 1);
  const selected = data[active];
  const valueLabel = (value) =>
    numeric(value) === null
      ? "미제공"
      : isPrice
        ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(
            value,
          )
        : formatNumber(value);
  return (
    <figure
      ref={figureRef}
      className="wp-chart"
      style={{ "--chart-color": color }}
    >
      <div className="wp-chart__readout">
        <span>{label}</span>
        {selected && (
          <span>
            <strong>{valueLabel(selected[valueKey])}</strong>
            <small>{selected.date}</small>
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${chartHeight}`}
        style={{ height }}
        role="img"
        tabIndex="0"
        aria-label={`${label}. ${data.length}개 시점. ${selected?.date ?? ""} 값 ${valueLabel(selected?.[valueKey])}. 좌우 방향키로 날짜 탐색.`}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            setHover(
              Math.max(
                0,
                Math.min(
                  data.length - 1,
                  active + (event.key === "ArrowLeft" ? -1 : 1),
                ),
              ),
            );
          }
        }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`fill-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity=".18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((i) => {
          const tick = min + ((max - min) * i) / 3;
          return (
            <g key={i}>
              <line
                x1={left}
                x2={width - right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="#24313a"
                strokeDasharray="3 5"
              />
              <text x={left - 8} y={y(tick) + 4} textAnchor="end">
                {new Intl.NumberFormat("en", {
                  notation: "compact",
                  maximumFractionDigits: isPrice ? 1 : 0,
                }).format(tick)}
              </text>
            </g>
          );
        })}
        {data.length > 0 && (
          <>
            {valueSegments.map((part) => {
              const points = part
                .map(({ index, value }) => `${x(index)},${y(value)}`)
                .join(" ");
              return (
                <g key={part[0].index} data-series-segment="value">
                  <polygon
                    points={`${x(part[0].index)},${y(min)} ${points} ${x(part.at(-1).index)},${y(min)}`}
                    fill={`url(#fill-${id})`}
                  />
                  <polyline
                    points={points}
                    fill="none"
                    stroke={color}
                    strokeWidth="2.5"
                    strokeLinejoin="round"
                  />
                  {part.length === 1 && (
                    <circle
                      cx={x(part[0].index)}
                      cy={y(part[0].value)}
                      r="3"
                      fill={color}
                    />
                  )}
                </g>
              );
            })}
            {baseline &&
              referenceSegments.map((part) => (
                <polyline
                  key={part[0].index}
                  data-series-segment="baseline"
                  points={part
                    .map(({ index, value }) => `${x(index)},${y(value)}`)
                    .join(" ")}
                  fill="none"
                  stroke="#dbb057"
                  strokeWidth="1.5"
                  strokeDasharray="5 5"
                />
              ))}
            <line
              x1={x(active)}
              x2={x(active)}
              y1={top}
              y2={y(min)}
              stroke={color}
              strokeOpacity=".3"
            />
            {values[active] !== null && (
              <circle
                cx={x(active)}
                cy={y(values[active])}
                r="4"
                fill={color}
                stroke="#0b141b"
                strokeWidth="2"
              />
            )}
            {visibleMarkers.map(({ marker, mx }) => {
                const node = (
                  <>
                    <line
                      x1={mx}
                      x2={mx}
                      y1={top}
                      y2={y(min)}
                      stroke="#dbb057"
                      strokeWidth="1.5"
                      strokeDasharray="2 3"
                    />
                    <circle
                      cx={mx}
                      cy={top}
                      r="4"
                      fill="#dbb057"
                      stroke="#0b141b"
                      strokeWidth="1.5"
                    />
                    <title>{`${marker.date} · ${marker.label}`}</title>
                  </>
                );
                return marker.href ? (
                  <a
                    key={marker.key ?? marker.href}
                    href={marker.href}
                    aria-label={`이슈 ${marker.label} (${marker.date})`}
                  >
                    {node}
                  </a>
                ) : (
                  <g key={marker.key ?? marker.date}>{node}</g>
                );
              })}
          </>
        )}
        {data.map((item, i) => (
          <rect
            key={item.date}
            x={x(i) - (width - left - right) / Math.max(1, data.length - 1) / 2}
            y={top}
            width={(width - left - right) / Math.max(1, data.length - 1)}
            height={chartHeight - top - bottom}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          >
            <title>{`${item.date}: ${valueLabel(item[valueKey])}`}</title>
          </rect>
        ))}
        {[0, Math.floor((data.length - 1) / 2), data.length - 1]
          .filter((n, i, a) => n >= 0 && a.indexOf(n) === i)
          .map((i) => (
            <text
              key={i}
              x={x(i)}
              y={chartHeight - 8}
              textAnchor={
                i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"
              }
            >
              {data[i]?.date?.slice(5).replace("-", ".")}
            </text>
          ))}
      </svg>
      {!available.length && (
        <p className="data-scope" role="status">
          표시할 관측값이 없습니다.
        </p>
      )}
      <figcaption>
        <span>
          <i style={{ background: color }} />
          {label}
        </span>
        {baseline && (
          <span>
            <i style={{ background: "#dbb057" }} />
            평소 편집량
          </span>
        )}
        {visibleMarkers.length > 0 && (
          <span>
            <i style={{ background: "#dbb057" }} />
            이슈 발생 시점
          </span>
        )}
        <span className="wp-muted">
          {isPrice
            ? `세로축 확대${isExample ? " · 예시" : ""}`
            : isExample
              ? "예시 데이터"
              : "제공된 데이터"}
        </span>
      </figcaption>
    </figure>
  );
}
