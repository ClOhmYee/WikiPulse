import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import Ajv from 'ajv';
import { pulseMaps, pulseSnapshots, makeStressMap } from '../src/data/mock/fixtures/pulse.js';
import { validateMap, validateSnapshots } from '../src/data/pulse/contract.js';

const spec = JSON.parse(readFileSync(new URL('../docs/pulse-openapi.json', import.meta.url), 'utf8'));
assert.equal(spec.openapi, '3.0.3');
function jsonSchema(value) {
  if (Array.isArray(value)) return value.map(jsonSchema);
  if (!value || typeof value !== 'object') return value;
  const result = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, jsonSchema(v)]));
  if (typeof result.exclusiveMinimum === 'boolean') {
    if (result.exclusiveMinimum) result.exclusiveMinimum = result.minimum;
    else delete result.exclusiveMinimum;
  }
  return result;
}
const ajv = new Ajv({ allErrors: true, nullable: true });
ajv.addSchema({ $id: 'pulse', components: jsonSchema(spec.components) });
const validate = ajv.compile({ $ref: 'pulse#/components/schemas/MapResponse' });
const index = ajv.compile({ $ref: 'pulse#/components/schemas/SnapshotResponse' });
assert(index(pulseSnapshots), JSON.stringify(index.errors));
validateSnapshots(pulseSnapshots);
for (const map of [...pulseMaps, makeStressMap()]) {
  assert(validate(map), JSON.stringify(validate.errors));
  validateMap(map);
}
for (const item of pulseSnapshots.data) {
  const map = pulseMaps.find(v => v.meta.snapshotTs === item.snapshotTs && v.meta.source === item.source);
  assert.equal(map.data.clusters.length, item.clusterCount);
}
console.log('Pulse OpenAPI 3.0.3: 7 historical snapshots + 20 clusters / 500 nodes / 1000 edges validated. No live backend was called.');
