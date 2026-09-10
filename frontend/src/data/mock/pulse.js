import { dates, snapshotAt, timestamp } from "./fixtures/history.js";
import { validateMap, validateSnapshots } from "../pulse/contract.js";
import { DataError } from "../contracts.js";
const snapshotIndex = dates.map((date) => ({
  snapshotTs: timestamp(date),
  source: "replay",
  clusterCount: snapshotAt(date).meta.clusterCount,
}));
export function listSnapshots(params = {}) {
  return validateSnapshots({
    data: snapshotIndex
      .filter(
        (v) =>
          (!params.from || v.snapshotTs >= params.from) &&
          (!params.to || v.snapshotTs <= params.to) &&
          (!params.source || params.source === v.source),
      )
      .map((v) => ({ ...v })),
  });
}
export function getPulseMap(params = {}) {
  const found = snapshotIndex.findLast(
    (v) =>
      (!params.source || v.source === params.source) &&
      (!params.snapshotTs || v.snapshotTs === params.snapshotTs),
  );
  if (!found)
    throw new DataError("해당 시점의 스냅샷이 없습니다.", {
      status: 404,
      code: "SNAPSHOT_NOT_FOUND",
    });
  return validateMap(snapshotAt(found.snapshotTs.slice(0, 10)), params);
}
