import {
  forceSimulation,
  forceLink,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";
export const nodeRadius = (score) =>
  score === null ? 12 : 12 + 28 * Math.sqrt(score);
const hash = (text) =>
  [...text].reduce((value, ch) => (value * 31 + ch.charCodeAt(0)) >>> 0, 7);
// Cache document positions; rank cluster centers for each filtered snapshot.
export function createLayoutEngine() {
  const clusters = new Map();
  return (input) => {
    for (const cluster of [...input].sort((a, b) =>
      a.issueKey.localeCompare(b.issueKey),
    )) {
      let cached = clusters.get(cluster.issueKey);
      if (!cached) {
        cached = {
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
          const distance = 50 + Math.sqrt(index + 1) * 40;
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
              .distance(125)
              .strength(0.08),
          )
          .force("collision", forceCollide(48).iterations(3))
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
        160,
        ...nodes.map((v) => Math.hypot(v.x, v.y) + 56),
      );
      return {
        ...cluster,
        radius,
        nodes,
      };
    });
    const ranked = [...scene].sort(
      (a, b) =>
        b.pulseScore - a.pulseScore || a.issueKey.localeCompare(b.issueKey),
    );
    const placed = [];
    let distance = 0;
    for (const [rank, cluster] of ranked.entries()) {
      const angle = rank * Math.PI * (3 - Math.sqrt(5));
      if (rank) distance += 40;
      let x, y;
      do {
        x = Math.cos(angle) * distance;
        y = Math.sin(angle) * distance;
        if (
          placed.every(
            (other) =>
              Math.hypot(x - other.x, y - other.y) >=
              cluster.radius + other.radius + 240,
          )
        )
          break;
        distance += 20;
      } while (distance > 0);
      Object.assign(cluster, { x, y, rank });
      placed.push(cluster);
    }
    const extent = Math.max(
      400,
      ...placed.map((v) => Math.hypot(v.x, v.y) + v.radius + 100),
    );
    return {
      clusters: scene,
      width: extent * 2,
      height: extent * 2,
    };
  };
}
