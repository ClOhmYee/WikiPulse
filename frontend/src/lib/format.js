const numberFormatter = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 1,
});

export function formatNumber(value) {
  return numberFormatter.format(
    Number.isFinite(Number(value)) ? Number(value) : 0,
  );
}
