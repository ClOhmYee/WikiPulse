import { DataError } from "../contracts.js";

// The server contract is a proposal. Keep wire-format changes in this adapter.
export function adaptResponse(body, { list = false, paginated = false } = {}) {
  const invalid = () => {
    throw new DataError("응답 데이터 형식이 계약과 다릅니다.", {
      code: "INVALID_RESPONSE",
    });
  };
  if (!body || !body.meta || typeof body.meta.dataMode !== "string") invalid();
  if (
    list
      ? !Array.isArray(body.data)
      : !body.data || typeof body.data !== "object" || Array.isArray(body.data)
  )
    invalid();
  if (
    body.included &&
    (typeof body.included !== "object" || Array.isArray(body.included))
  )
    invalid();
  for (const values of Object.values(body.included || {}))
    if (!Array.isArray(values)) invalid();
  if (paginated) {
    const page = body.meta.pagination;
    if (
      !page ||
      !Number.isInteger(page.offset) ||
      page.offset < 0 ||
      !Number.isInteger(page.limit) ||
      page.limit < 1 ||
      !Number.isInteger(page.total) ||
      page.total < 0 ||
      typeof page.hasMore !== "boolean"
    )
      invalid();
  }
  return { data: body.data, included: body.included || {}, meta: body.meta };
}
