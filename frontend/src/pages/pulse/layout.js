import {
  forceSimulation,
  forceLink,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";
export const nodeRadius = (score) =>
  score === null ? 6 : 6 + 18 * Math.sqrt(score);
const hash = (text) =>
  [...text].reduce((value, ch) => (value * 31 + ch.charCodeAt(0)) >>> 0, 7);
// Cached per page visit; filtering, ordering and scores do not reassign positions.
export function createLayoutEngine() {
  const clusters = new Map();
  let cellSize = 365;
  return (input) => {
    for (const cluster of [...input].sort((a, b) =>
      a.issueKey.localeCompare(b.issueKey),
    )) {
      let cached = clusters.get(cluster.issueKey);
      if (!cached) {
        const slot = clusters.size;
        cached = {
          slot,
          x: 210 + (slot % 3) * 410,
          y: 185 + Math.floor(slot / 3) * 365,
          positions: new Map(),
        };
        clusters.set(cluster.issueKey, cached);
      }
      const ordered = [...cluster.nodes].sort((a, b) =>
        a.pageId.localeCompare(b.pageId),
      );
      if (ordered.some((node) => !cached.positions.has(node.pageId))) {
        const nodes = ordered.map((node, index) => {
          const old = cached.positions.get(node.pageId);
          const angle = hash(node.pageId) * 0.01 + index * 2.39996;
          const distance = 35 + Math.sqrt(index + 1) * 25;
          return {
            id: node.pageId,
            ...(old
              ? { x: old.x, y: old.y, fx: old.x, fy: old.y }
              : {
                  x: Math.cos(angle) * distance,
                  y: Math.sin(angle) * distance,
                }),
          };
        });
        const links = cluster.edges.map((edge) => ({
          source: edge.sourcePageId,
          target: edge.targetPageId,
        }));
        const simulation = forceSimulation(nodes)
          .stop()
          .force(
            "link",
            forceLink(links)
              .id((node) => node.id)
              .distance(85)
              .strength(0.08),
          )
          .force("collision", forceCollide(31).iterations(3))
          .force("x", forceX(0).strength(0.02))
          .force("y", forceY(0).strength(0.02));
        simulation.tick(100);
        simulation.stop();
        for (const node of nodes)
          cached.positions.set(node.id, { x: node.x, y: node.y });
      }
    }
    const scene = input.map((cluster) => {
      const cached = clusters.get(cluster.issueKey);
      const nodes = cluster.nodes.map((node) => ({
        ...node,
        ...cached.positions.get(node.pageId),
        radius: nodeRadius(node.sizeScore),
      }));
      const radius = Math.max(
        112,
        ...nodes.map((v) => Math.hypot(v.x, v.y) + 38),
      );
      return {
        ...cluster,
        slot: cached.slot,
        x: cached.x,
        y: cached.y,
        radius,
        nodes,
      };
    });
    cellSize = Math.max(cellSize, ...scene.map((v) => v.radius * 2 + 100));
    return {
      clusters: scene.map((v) => ({
        ...v,
        x: ((v.slot % 3) + 0.5) * cellSize,
        y: (Math.floor(v.slot / 3) + 0.5) * cellSize,
      })),
      cellSize,
      totalSlots: clusters.size,
      width: cellSize * 3,
      height: Math.max(2, Math.ceil(clusters.size / 3)) * cellSize,
    };
  };
}
