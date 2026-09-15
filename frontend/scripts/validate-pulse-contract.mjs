import assert from "node:assert/strict";
import { mockClient } from "../src/data/mock/client.js";
import { makeStressMap } from "../src/data/mock/fixtures/pulse.js";
import { validateMap, validateSnapshots } from "../src/data/pulse/contract.js";
import { loadSchema } from "./contract-schema.mjs";

const { spec, validate } = loadSchema("../docs/pulse-openapi.json");
const unified = loadSchema("../docs/openapi.yaml");
for (const name of Object.keys(spec.components.schemas))
  assert.deepEqual(
    unified.spec.components.schemas[name],
    spec.components.schemas[name],
    `Pulse schema drift: ${name}`,
  );
const snapshots = await mockClient.listSnapshots();
validate("SnapshotResponse", snapshots);
validateSnapshots(snapshots);
for (const item of snapshots.data) {
  const map = await mockClient.getPulseMap({
    snapshotTs: item.snapshotTs,
    source: item.source,
  });
  validate("MapResponse", map);
  validateMap(map, item);
  assert.equal(map.data.clusters.length, item.clusterCount);
}
const stress = makeStressMap();
delete stress.meta.dataMode;
validate("MapResponse", stress);
validateMap(stress);
const nullable = structuredClone(stress);
nullable.data.clusters[0].label = null;
nullable.data.clusters[0].issueKey = null;
validate("MapResponse", nullable);
validateMap(nullable);
console.log(
  `Pulse DTO: ${snapshots.data.length} snapshots + 500-node/1000-edge stress graph, null label/identity and omitted dataMode validated. No live backend was called.`,
);
