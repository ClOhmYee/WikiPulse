/** Keep an issue snapshot fixed while paging; a new filter starts a fresh query. */
export function nextListParams(previous, partial, snapshotTs) {
  const changedFilter = Object.keys(partial).some(
    (name) =>
      !["offset", "snapshotTs"].includes(name) &&
      partial[name] !== previous[name],
  );
  const next = { ...previous, ...partial };
  if (changedFilter) {
    next.offset = 0;
    delete next.snapshotTs;
  } else if (partial.offset !== undefined && snapshotTs) {
    next.snapshotTs = snapshotTs;
  }
  return next;
}
