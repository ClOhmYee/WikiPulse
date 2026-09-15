/**
 * @typedef {{signal?: AbortSignal}} RequestOptions
 * @typedef {{offset?: number, limit?: number, snapshotTs?: string, status?: string, source?: string, q?: string, sector?: string, exchange?: string, hasIssues?: boolean}} ListParams
 * @typedef {{offset: number, limit: number, total: number, hasMore: boolean}} Pagination
 * @template T
 * @typedef {{data: T, meta?: {snapshotTs?: string, pagination?: Pagination}}} DataResponse
 * @typedef {Object} DataClient
 * @property {string} dataSource
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} listIssues
 * @property {(id: string, options?: RequestOptions) => Promise<DataResponse<object>>} getIssue
 * @property {(id: string, params?: {limit?: number}, options?: RequestOptions) => Promise<DataResponse<object[]>>} listIssueStocks
 * @property {(params?: ListParams, options?: RequestOptions) => Promise<DataResponse<object[]>>} listStocks
 * @property {(ticker: string, options?: RequestOptions) => Promise<DataResponse<object>>} getStock
 * @property {(ticker: string, options?: RequestOptions) => Promise<DataResponse<object[]>>} listStockIssues
 * @property {(params?: {from?: string, to?: string, source?: string}, options?: RequestOptions) => Promise<object>} listSnapshots
 * @property {(params?: {snapshotTs?: string, source?: string}, options?: RequestOptions) => Promise<object>} getPulseMap
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
  if (!meta)
    return {
      label: "출처 확인 중",
      description: "데이터를 불러오면 출처와 기준 시각을 표시합니다.",
    };
  if (meta?.dataMode === "mock")
    return {
      label: "데모 데이터",
      description:
        "실제 위키 문서와 현재 Nasdaq-100 목록을 바탕으로 만든 시연용 합성 이슈·지표·종목 연결입니다. 실제 AI 검증 결과나 과거 지수 구성을 재현하지 않습니다.",
    };
  return {
    label: "API 데이터",
    description:
      "서버가 제공한 이슈와 종목 정보입니다. 표시된 출처와 스냅샷 시각을 확인해 주세요. API 연결만으로 실시간 수집이나 AI 검증 완료를 뜻하지 않습니다.",
  };
}
