import { DataError } from "../contracts.js";

export function createHttpClient(baseURL, fetcher = globalThis.fetch) {
  return async (path, params = {}, { signal } = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== undefined),
    );
    const url = `${baseURL.replace(/\/+$/, "")}${path}${query.size ? `?${query}` : ""}`;
    let response;
    try {
      response = await fetcher(url, {
        signal,
        headers: { Accept: "application/json" },
      });
    } catch (error) {
      if (signal?.aborted || error.name === "AbortError") throw error;
      throw new DataError(
        "서버에 연결할 수 없습니다. 네트워크와 API 주소를 확인해 주세요.",
      );
    }
    let body;
    try {
      body = await response.json();
    } catch {
      throw new DataError("서버가 올바른 JSON 응답을 보내지 않았습니다.", {
        status: response.status,
        code: "INVALID_RESPONSE",
      });
    }
    if (!response.ok) {
      throw new DataError(
        response.status === 404
          ? "요청한 데이터를 찾을 수 없습니다."
          : "데이터를 불러오지 못했습니다.",
        {
          status: response.status,
          code: body?.error?.code || "HTTP_ERROR",
        },
      );
    }
    return body;
  };
}
