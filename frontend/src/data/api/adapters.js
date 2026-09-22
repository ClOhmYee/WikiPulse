import { DataError } from "../contracts.js";

const object = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const id = (v) =>
  (typeof v === "string" && v.length > 0) || (Number.isSafeInteger(v) && v > 0);
const text = (v) => typeof v === "string" && v.length > 0;
const optionalText = (v) => v == null || typeof v === "string";
const number = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const optionalNumber = (v) => v == null || number(v);
const count = (v) => Number.isSafeInteger(v) && v >= 0;
const timestamp = (v) =>
  text(v) && /Z$/.test(v) && Number.isFinite(Date.parse(v));
const status = (v) => ["DETECTED", "VERIFYING", "CONFIRMED"].includes(v);
const source = (v) => ["live", "replay"].includes(v);
const completeness = (v) => ["complete", "pending", "unavailable"].includes(v);
const reportStatus = (v) =>
  ["ready", "generating", "insufficient_evidence", "failed"].includes(v);
const reportSection = (v) =>
  object(v) &&
  text(v.id) &&
  text(v.title) &&
  optionalText(v.body) &&
  Array.isArray(v.evidenceIds) &&
  v.evidenceIds.every(id);
const report = (v) =>
  object(v) &&
  reportStatus(v.status) &&
  optionalText(v.model) &&
  (v.generatedAt == null || timestamp(v.generatedAt)) &&
  Array.isArray(v.sections) &&
  v.sections.every(reportSection);

export const issueCard = (v) =>
  object(v) &&
  id(v.id) &&
  optionalText(v.label) &&
  number(v.pulseScore) &&
  status(v.status) &&
  source(v.source) &&
  timestamp(v.snapshotTs) &&
  count(v.memberCount) &&
  count(v.stockCount);
export const stockCard = (v) =>
  object(v) &&
  text(v.ticker) &&
  text(v.name) &&
  text(v.exchange) &&
  optionalText(v.sector) &&
  count(v.issueCount) &&
  optionalNumber(v.lastClose);
export const stockDetail = (v) =>
  object(v) &&
  text(v.ticker) &&
  text(v.name) &&
  text(v.exchange) &&
  optionalText(v.sector) &&
  optionalText(v.cik) &&
  optionalText(v.businessSummary);
const dateOnly = (v) =>
  text(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v));
// 일봉 한 점. 거래일만·보간 없음. close 는 서버 NOT NULL, 나머지는 결측 가능.
export const stockPrice = (v) =>
  object(v) &&
  dateOnly(v.tradeDate) &&
  number(v.close) &&
  optionalNumber(v.open) &&
  optionalNumber(v.high) &&
  optionalNumber(v.low) &&
  (v.volume == null || (Number.isSafeInteger(v.volume) && v.volume >= 0));
export const relatedStock = (v) =>
  object(v) &&
  text(v.ticker) &&
  text(v.name) &&
  text(v.exchange) &&
  optionalText(v.sector) &&
  ["BOTH", "GDELT_ONLY", "EMBEDDING_ONLY"].includes(v.tier) &&
  (v.matchPath == null ||
    ["DIRECT_MENTION", "PRODUCT_INDUSTRY", "SUPPLY_CHAIN", "REGION"].includes(
      v.matchPath,
    )) &&
  optionalNumber(v.similarity) &&
  (v.similarity == null || v.similarity <= 1) &&
  optionalNumber(v.gdeltLift) &&
  optionalText(v.rationale);
const member = (v) =>
  object(v) &&
  id(v.pageId) &&
  text(v.wiki) &&
  text(v.title) &&
  // 표시 전용. ko 문서가 없으면 null 이거나 NON_NULL 직렬화로 필드가 빠진다.
  optionalText(v.titleKo) &&
  number(v.weight) &&
  typeof v.isSeed === "boolean" &&
  optionalNumber(v.editCount) &&
  optionalNumber(v.views) &&
  completeness(v.completeness);
export const issueDetail = (v) =>
  object(v) &&
  id(v.id) &&
  optionalText(v.label) &&
  number(v.pulseScore) &&
  status(v.status) &&
  source(v.source) &&
  timestamp(v.snapshotTs) &&
  optionalText(v.summary) &&
  optionalText(v.summaryModel) &&
  (v.report == null || report(v.report)) &&
  Array.isArray(v.members) &&
  v.members.every(member) &&
  Array.isArray(v.relatedStocks) &&
  v.relatedStocks.every(relatedStock);

/** Validate Spring DTOs without inventing included records or source metadata. */
export function adaptResponse(
  body,
  { list = false, paginated = false, validate } = {},
) {
  const invalid = () => {
    throw new DataError("응답 데이터 형식이 계약과 다릅니다.", {
      code: "INVALID_RESPONSE",
    });
  };
  if (!object(body) || (body.meta !== undefined && !object(body.meta)))
    invalid();
  if (list ? !Array.isArray(body.data) : !object(body.data)) invalid();
  if (validate && !(list ? body.data.every(validate) : validate(body.data)))
    invalid();
  if (paginated) {
    const p = body.meta?.pagination;
    if (
      !object(p) ||
      !count(p.offset) ||
      !Number.isInteger(p.limit) ||
      p.limit < 1 ||
      p.limit > 100 ||
      !count(p.total) ||
      typeof p.hasMore !== "boolean" ||
      body.data.length > p.limit ||
      p.hasMore !== p.offset + body.data.length < p.total ||
      (p.hasMore && body.data.length === 0)
    )
      invalid();
  }
  return body;
}
