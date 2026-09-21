import { MAP_SCALE } from "./useMapCamera.js";

export const overviewRadius = (cluster) => cluster.radius + 40;

// Fit text inside an inscribed square, including at the minimum zoom.
export function overviewTitle(cluster, zoom) {
  const fontSize =
    Math.min(18, 12 * (zoom / 0.12) ** 0.28) / (zoom * MAP_SCALE);
  const width = overviewRadius(cluster) * 1.3;
  const capacity = width / fontSize;
  const maxLines = Math.max(
    1,
    Math.min(3, Math.floor(width / (fontSize * 1.3))),
  );
  const lines = [""];
  const measure = (text) =>
    [...text].reduce(
      (sum, char) => sum + (/[^\u0000-\u00ff]/u.test(char) ? 1 : 0.65),
      0,
    );
  let used = 0;
  for (const char of cluster.label.replace(/\s+/gu, " ").trim()) {
    const unit = /[^\u0000-\u00ff]/u.test(char) ? 1 : 0.65;
    if (used + unit > capacity) {
      if (lines.length === maxLines) {
        lines[lines.length - 1] = `${[...lines.at(-1)].slice(0, -1).join("")}…`;
        break;
      }
      const last = lines.at(-1);
      const space = last.lastIndexOf(" ");
      if (space > last.length * 0.4) {
        lines[lines.length - 1] = last.slice(0, space);
        lines.push(last.slice(space + 1));
      } else lines.push("");
      used = measure(lines.at(-1));
    }
    if (!lines.at(-1) && char === " ") continue;
    lines[lines.length - 1] += char;
    used += unit;
  }
  return { lines, fontSize, lineHeight: fontSize * 1.3 };
}
