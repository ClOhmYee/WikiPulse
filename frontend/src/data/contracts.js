/**
 * @typedef {{signal?: AbortSignal}} RequestOptions
 * @typedef {{q?: string, offset?: number, limit?: number, category?: string, window?: string, sort?: string, sector?: string, eventId?: string, relationType?: string}} ListParams
 * @typedef {{dataMode: string, asOf?: string, timezone?: string, pagination?: {offset: number, limit: number, total: number, hasMore: boolean}}} Meta
 * @template T
 * @typedef {{data: T, included?: {events?: object[], entities?: object[], stocks?: object[]}, meta: Meta}} DataResponse
 * @typedef {Object} DataClient
 * @property {(options?: RequestOptions) => Promise<DataResponse<object[]>>} listCategories
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} listEvents
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} listEntities
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} listStocks
 * @property {(id: string, options?: RequestOptions) => Promise<DataResponse<object>>} getEvent
 * @property {(id: string, options?: RequestOptions) => Promise<DataResponse<object>>} getEntity
 * @property {(symbol: string, options?: RequestOptions) => Promise<DataResponse<object>>} getStock
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} searchWorkspace
 */
export class DataError extends Error {
  constructor(message, { status = 0, code = "REQUEST_FAILED" } = {}) {
    super(message);
    this.name = "DataError";
    this.status = status;
    this.code = code;
  }
}

export function describeSource(meta) {
  if (meta?.dataMode === "mock")
    return {
      label: "데모 데이터",
      description:
        "모든 사건·문서·뉴스·가격은 화면 체험을 위한 목데이터입니다.",
    };
  return {
    label: "출처 확인 필요",
    description:
      "제공된 데이터의 출처와 기준 시각을 확인해 주세요. 연결 방식만으로 실시간 데이터임을 보장하지 않습니다.",
  };
}
