import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import Ajv from 'ajv';
import yaml from 'js-yaml';
import { DEMO_DATE, HISTORY_START, categories, entities, events, stocks } from '../src/data/mock/fixtures/catalog.js';

// This checks the proposed frontend contract and its fixtures, not a running API.
// Resolve files relative to this script so both root and frontend invocations work.
const contractUrl = new URL('../docs/openapi.yaml', import.meta.url);
const require = createRequire(import.meta.url);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']);

function run() {
  const contract = yaml.load(readFileSync(contractUrl, 'utf8'));
  assert.equal(contract.openapi, '3.0.3', 'Validator expects the documented OpenAPI 3.0.3 contract.');
  assert(contract.components?.schemas, 'Contract is missing components.schemas.');
  assert(contract.paths, 'Contract is missing paths.');

  function resolveRef(reference) {
    assert(reference.startsWith('#/'), `Unsupported external reference: ${reference}`);
    const tokens = decodeURIComponent(reference.slice(2))
      .split('/')
      .map((token) => token.replaceAll('~1', '/').replaceAll('~0', '~'));
    let target = contract;
    for (const token of tokens) {
      assert(target && typeof target === 'object' && own(target, token), `Unresolved reference: ${reference}`);
      target = target[token];
    }
    return target;
  }

  let references = 0;
  function visitReferences(value) {
    if (!value || typeof value !== 'object') return;
    if (own(value, '$ref')) {
      assert.equal(typeof value.$ref, 'string', '$ref must be a string.');
      resolveRef(value.$ref);
      references += 1;
    }
    for (const child of Object.values(value)) visitReferences(child);
  }
  visitReferences(contract);
  assert(references > 0, 'Contract unexpectedly contains no schema references.');

  const operationIds = new Set();
  for (const [path, pathItem] of Object.entries(contract.paths)) {
    for (const [method, operation] of Object.entries(pathItem)) {
      if (!methods.has(method)) continue;
      assert.equal(typeof operation.operationId, 'string', `${method.toUpperCase()} ${path}: operationId is required.`);
      assert(operation.operationId.trim(), `${method.toUpperCase()} ${path}: operationId must not be empty.`);
      assert(!operationIds.has(operation.operationId), `Duplicate operationId: ${operation.operationId}`);
      operationIds.add(operation.operationId);
      const parameters = [...(pathItem.parameters || []), ...(operation.parameters || [])]
        .map((parameter) => parameter.$ref ? resolveRef(parameter.$ref) : parameter);
      for (const [, name] of path.matchAll(/\{([^}]+)\}/g)) {
        assert(
          parameters.some((parameter) => parameter.name === name && parameter.in === 'path' && parameter.required === true),
          `${method.toUpperCase()} ${path}: required path parameter "${name}" is missing.`,
        );
      }
    }
  }

  // Ajv validates schema constraints. OpenAPI examples are annotations, so remove
  // those annotations from its registry and validate their values separately below.
  // This also prevents legacy JSON Schema `id` discovery inside fixture examples.
  function forAjv(value) {
    if (Array.isArray(value)) return value.map(forAjv);
    if (!value || typeof value !== 'object') return value;
    const converted = {};
    for (const [key, child] of Object.entries(value)) {
      if (key === 'example' || key === 'examples') continue;
      converted[key] = key === '$ref' && typeof child === 'string'
        ? child.replace('#/components/schemas/', '#/definitions/')
        : forAjv(child);
    }
    return converted;
  }

  const ajv = new Ajv({ allErrors: true, nullable: true });
  ajv.addSchema({ definitions: forAjv(contract.components.schemas) }, 'wikipulse-contract');
  const validators = new Map();
  const validationFailures = [];

  function validateAgainst(name, value, context) {
    if (!validators.has(name)) {
      validators.set(name, ajv.compile({ $ref: `wikipulse-contract#/definitions/${name}` }));
    }
    const validate = validators.get(name);
    if (!validate(value)) {
      validationFailures.push({ context, schema: name, errors: structuredClone(validate.errors) });
    }
  }

  function propertyNames(schema) {
    if (schema.$ref) return propertyNames(resolveRef(schema.$ref));
    return new Set([
      ...Object.keys(schema.properties || {}),
      ...(schema.allOf || []).flatMap((part) => [...propertyNames(part)]),
    ]);
  }

  const fixtureGroups = { Category: categories, Event: events, Entity: entities, Stock: stocks };
  let fixtures = 0;
  for (const [name, values] of Object.entries(fixtureGroups)) {
    const allowed = propertyNames(contract.components.schemas[name]);
    const ids = new Set();
    for (const value of values) {
      const id = value.id || value.symbol;
      assert(!ids.has(id), `${name}: duplicate fixture ID ${id}`);
      ids.add(id);
      assert.deepEqual(Object.keys(value).filter((key) => !allowed.has(key)), [], `${name} ${id}: undocumented fixture fields.`);
      validateAgainst(name, value, `${name} fixture ${id}`);
      fixtures += 1;
    }
  }

  const categoryIds = new Set(categories.map((category) => category.id));
  const eventIds = new Set(events.map((event) => event.id));
  const entityIds = new Set(entities.map((entity) => entity.id));
  const symbols = new Set(stocks.map((stock) => stock.symbol));
  for (const event of events) {
    assert(categoryIds.has(event.category), `${event.id}: unknown category ${event.category}`);
    assert(event.date >= HISTORY_START && event.date <= DEMO_DATE, `${event.id}: date outside archive.`);
    for (const id of event.articleIds) assert(entityIds.has(id), `${event.id}: missing document ${id}`);
    for (const symbol of event.stockSymbols) assert(symbols.has(symbol), `${event.id}: missing stock ${symbol}`);
    for (const entry of event.timeline) {
      if (entry.entityId !== null) assert(entityIds.has(entry.entityId), `${entry.id}: missing timeline document ${entry.entityId}`);
    }
    const latest = event.chart.at(-1);
    assert(latest, `${event.id}: fixture activity chart must have a final point.`);
    for (const metric of ['edits', 'baseline', 'pageviews']) {
      assert.equal(latest[metric], event[metric], `${event.id}: latest ${metric} disagrees with its 24h snapshot.`);
    }
    assert.equal(Math.round(event.edits / event.baseline * 10) / 10, event.pulse, `${event.id}: inconsistent Pulse.`);
  }
  for (const entity of entities) {
    assert(categoryIds.has(entity.category), `${entity.id}: unknown category ${entity.category}`);
    for (const id of entity.eventIds) assert(eventIds.has(id), `${entity.id}: missing event ${id}`);
    for (const id of entity.relatedIds) assert(entityIds.has(id), `${entity.id}: missing related document ${id}`);
  }
  for (const stock of stocks) {
    for (const id of stock.eventIds) assert(eventIds.has(id), `${stock.symbol}: missing event ${id}`);
    for (const relation of stock.relations) assert(eventIds.has(relation.eventId), `${stock.symbol}: missing relation event ${relation.eventId}`);
    assert.equal(stock.chart.at(-1)?.price, stock.price, `${stock.symbol}: latest chart price disagrees with fixture price.`);
  }

  let schemaExamples = 0;
  function visitSchemaExamples(schema, context) {
    if (!schema || typeof schema !== 'object') return;
    if (own(schema, 'example')) {
      const validate = ajv.compile({ ...forAjv(schema), definitions: forAjv(contract.components.schemas) });
      if (!validate(schema.example)) {
        validationFailures.push({ context, errors: structuredClone(validate.errors) });
      }
      schemaExamples += 1;
    }
    for (const [key, child] of Object.entries(schema)) {
      if (key !== 'example' && key !== 'examples') visitSchemaExamples(child, `${context}.${key}`);
    }
  }
  for (const [name, schema] of Object.entries(contract.components.schemas)) {
    visitSchemaExamples(schema, `Schema example ${name}`);
  }

  let responseExamples = 0;
  let requestExamples = 0;
  function validateContentExamples(response, context) {
    let checked = 0;
    const resolved = response.$ref ? resolveRef(response.$ref) : response;
    for (const [mediaType, media] of Object.entries(resolved.content || {})) {
      const examples = [
        ...(own(media, 'example') ? [media.example] : []),
        ...Object.entries(media.examples || {}).map(([name, example]) => {
          const entry = example.$ref ? resolveRef(example.$ref) : example;
          assert(own(entry, 'value'), `${context} ${name}: external or empty examples are unsupported by this validator.`);
          return entry.value;
        }),
      ];
      if (!examples.length) continue;
      assert(media.schema, `${context}: an example has no schema.`);
      const validate = ajv.compile({ ...forAjv(media.schema), definitions: forAjv(contract.components.schemas) });
      for (const example of examples) {
        if (!validate(example)) validationFailures.push({ context: `${context} ${mediaType}`, errors: structuredClone(validate.errors) });
        checked += 1;
      }
    }
    return checked;
  }
  for (const [name, response] of Object.entries(contract.components.responses || {})) {
    responseExamples += validateContentExamples(response, `Response example ${name}`);
  }
  // Referenced shared responses were checked above; validate inline examples too.
  for (const [path, item] of Object.entries(contract.paths)) {
    for (const [method, operation] of Object.entries(item)) {
      if (!methods.has(method)) continue;
      if (operation.requestBody) {
        requestExamples += validateContentExamples(operation.requestBody, `${method.toUpperCase()} ${path} request body`);
      }
      for (const [status, response] of Object.entries(operation.responses || {})) {
        if (!response.$ref) responseExamples += validateContentExamples(response, `${method.toUpperCase()} ${path} ${status}`);
      }
    }
  }

  // Examples are independently schema-checked above, not coupled to a changing demo catalogue.
  if (validationFailures.length) {
    throw new Error(`Schema validation failed:\n${JSON.stringify(validationFailures, null, 2)}`);
  }

  console.log(JSON.stringify({
    contract: fileURLToPath(contractUrl),
    paths: Object.keys(contract.paths).length,
    uniqueOperations: operationIds.size,
    schemas: Object.keys(contract.components.schemas).length,
    resolvedReferences: references,
    validatedFixtures: fixtures,
    validatedSchemaExamples: schemaExamples,
    validatedResponseExamples: responseExamples,
    validatedRequestExamples: requestExamples,
    archiveRange: [HISTORY_START, DEMO_DATE],
    dependencies: { ajv: require('ajv/package.json').version, 'js-yaml': require('js-yaml/package.json').version },
  }, null, 2));
}

try {
  run();
} catch (error) {
  console.error(`[contract] ${error instanceof Error ? error.stack || error.message : String(error)}`);
  process.exitCode = 1;
}
