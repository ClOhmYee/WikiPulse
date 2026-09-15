import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import yaml from "js-yaml";

function jsonSchema(value) {
  if (Array.isArray(value)) return value.map(jsonSchema);
  if (!value || typeof value !== "object") return value;
  const converted = Object.fromEntries(
    Object.entries(value).map(([key, child]) => [key, jsonSchema(child)]),
  );
  // int64 is an OpenAPI numeric annotation; JS safe-integer rejection is tested
  // at the runtime adapter boundary, independently from the wire schema.
  if (converted.format === "int64") delete converted.format;
  if (typeof converted.exclusiveMinimum === "boolean") {
    if (converted.exclusiveMinimum)
      converted.exclusiveMinimum = converted.minimum;
    else delete converted.exclusiveMinimum;
  }
  return converted;
}
export function loadSchema(relativePath) {
  const spec = yaml.load(
    readFileSync(new URL(relativePath, import.meta.url), "utf8"),
  );
  assert.equal(spec.openapi, "3.0.3");
  const ajv = new Ajv({ allErrors: true, nullable: true });
  ajv.addSchema({ $id: "contract", components: jsonSchema(spec.components) });
  const validators = new Map();
  function validate(name, body) {
    if (!validators.has(name))
      validators.set(
        name,
        ajv.compile({ $ref: `contract#/components/schemas/${name}` }),
      );
    const check = validators.get(name);
    assert(check(body), `${name}: ${JSON.stringify(check.errors)}`);
  }
  return { spec, validate };
}
