// PulseMap-only palette: topic identity stays stable across snapshots and filters.
export const NEON_COLORS = {
  politics: "#b78aff",
  world: "#8399ff",
  society: "#64dce8",
  economy: "#ffc46b",
  technology: "#42d9ff",
  science: "#c4ed76",
  culture: "#f477d8",
  sports: "#61ddd0",
  environment: "#43e5d6",
  other: "#91bce8",
};

export const neonColor = (category) =>
  NEON_COLORS[category] || NEON_COLORS.other;
