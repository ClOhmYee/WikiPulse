// Every document keeps an in-bubble label. CSS clamps long titles with an
// ellipsis; the original title remains available in the active callout.
export default function DocumentLabels({
  nodes,
  fontSize,
  emphasized,
  selected,
  bounds,
}) {
  const widthOf = (line) =>
    [...line].reduce(
      (width, char) => width + (/[^\u0000-\u00ff]/u.test(char) ? 1 : 0.62),
      0,
    ) *
      fontSize +
    8;
  const active =
    nodes.find((node) => node.pageId === emphasized) ||
    nodes.find((node) => node.pageId === selected);
  const activeLines = active
    ? active.title.replaceAll("_", " ").match(/.{1,28}(?:\s|$)|.{1,28}/gu)
    : [];
  const activeWidth = active ? Math.max(...activeLines.map(widthOf)) : 0;
  const calloutX = active
    ? Math.max(
        bounds.left + activeWidth / 2 + 6,
        Math.min(active.x, bounds.right - activeWidth / 2 - 6),
      )
    : 0;
  const calloutY = active
    ? Math.max(
        bounds.top + activeLines.length * fontSize * 1.25 + 4,
        Math.min(active.y - active.radius - 16, bounds.bottom - 4),
      )
    : 0;
  return (
    <g className="document-labels" aria-hidden="true" pointerEvents="none">
      {nodes.map((node) => (
        <foreignObject
          key={node.pageId}
          className="document-node-label"
          data-page-id={node.pageId}
          x={node.x - node.radius * 0.775}
          y={node.y - node.radius * 0.575}
          width={node.radius * 1.55}
          height={node.radius * 1.15}
        >
          <div className="document-node-label__box">
            <span
              className="document-node-label__text"
              data-font-cap={Math.max(8, node.radius * 0.36)}
              data-font-size={Math.min(
                fontSize,
                Math.max(8, node.radius * 0.36),
              )}
              style={{
                fontSize: Math.min(fontSize, Math.max(8, node.radius * 0.36)),
                WebkitLineClamp: node.radius >= 20 ? 2 : 1,
              }}
            >
              {node.title.replaceAll("_", " ")}
            </span>
          </div>
        </foreignObject>
      ))}
      {active && (
        <g
          className="document-label-callout"
          data-node-x={active.x}
          data-node-y={active.y}
          data-node-radius={active.radius}
          data-font-size={fontSize}
          data-box-width={activeWidth + 12}
          data-box-height={activeLines.length * fontSize * 1.25 + 8}
          transform={`translate(${calloutX} ${calloutY})`}
        >
          <rect
            x={-activeWidth / 2 - 6}
            y={-activeLines.length * fontSize * 1.25 - 4}
            width={activeWidth + 12}
            height={activeLines.length * fontSize * 1.25 + 8}
            rx="4"
          />
          <text
            className="document-label"
            textAnchor="middle"
            dominantBaseline="central"
            style={{ fontSize }}
            y={-(activeLines.length - 0.5) * fontSize * 1.25}
          >
            {activeLines.map((line, index) => (
              <tspan key={index} x="0" dy={index ? fontSize * 1.25 : 0}>
                {line}
              </tspan>
            ))}
          </text>
        </g>
      )}
    </g>
  );
}
