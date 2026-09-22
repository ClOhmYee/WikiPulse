/** Keep an issue snapshot fixed while paging; a new filter starts a fresh query. */
export function nextListParams(previous, partial, snapshotTs, sourceSnapshots) {
  const changedFilter = Object.keys(partial).some(
    (name) =>
      !["offset", "snapshotTs", "sourceSnapshots"].includes(name) &&
      partial[name] !== previous[name],
  );
  const next = { ...previous, ...partial };
  if (changedFilter) {
    next.offset = 0;
    delete next.snapshotTs;
    delete next.sourceSnapshots;
  } else if (partial.offset !== undefined) {
    if (sourceSnapshots) next.sourceSnapshots = sourceSnapshots;
    if (snapshotTs) next.snapshotTs = snapshotTs;
  }
  return next;
}
