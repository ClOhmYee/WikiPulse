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
  const values = data.map((item) => Number(item[valueKey]) || 0);
  const isPrice = valueKey === "price";
  const minValue = Math.min(...values);
  const maxValue = Math.max(
    1,
    ...values,
    ...(baseline ? data.map((item) => item.baseline || 0) : []),
  );
  const span = Math.max(maxValue - minValue, maxValue * 0.01);
  const min = isPrice ? Math.max(0, minValue - span * 0.2) : 0;
  const max = isPrice ? maxValue + span * 0.2 : maxValue * 1.12;
  const x = (i) =>
    left + (i / Math.max(1, data.length - 1)) * (width - left - right);
  const y = (v) =>
    top +
    (1 - (v - min) / Math.max(1, max - min)) * (chartHeight - top - bottom);
  const points = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const active =
    hover === null ? data.length - 1 : Math.min(hover, data.length - 1);
  const selected = data[active];
  const valueLabel = (value) =>
    isPrice
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
            <strong>{valueLabel(selected[valueKey] || 0)}</strong>
            <small>{selected.date}</small>
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${chartHeight}`}
        style={{ height }}
        role="img"
        tabIndex="0"
        aria-label={`${label}. ${data.length}개 시점. ${selected?.date ?? ""} 값 ${selected?.[valueKey] ?? 0}. 좌우 방향키로 날짜 탐색.`}
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
            <polygon
              points={`${x(0)},${y(min)} ${points} ${x(data.length - 1)},${y(min)}`}
              fill={`url(#fill-${id})`}
            />
            <polyline
              points={points}
              fill="none"
              stroke={color}
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            {baseline && (
              <polyline
                points={data
                  .map((v, i) => `${x(i)},${y(v.baseline || 0)}`)
                  .join(" ")}
                fill="none"
                stroke="#dbb057"
                strokeWidth="1.5"
                strokeDasharray="5 5"
              />
            )}
            <line
              x1={x(active)}
              x2={x(active)}
              y1={top}
              y2={y(min)}
              stroke={color}
              strokeOpacity=".3"
            />
            <circle
              cx={x(active)}
              cy={y(values[active])}
              r="4"
              fill={color}
              stroke="#0b141b"
              strokeWidth="2"
            />
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
            <title>{`${item.date}: ${item[valueKey]}`}</title>
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
