import { DataError } from "./contracts.js";

export function readDataConfig(env = {}) {
  const source = env.VITE_DATA_SOURCE ?? "mock";
  if (!["mock", "api"].includes(source)) {
    throw new DataError("VITE_DATA_SOURCE는 mock 또는 api여야 합니다.", {
      code: "INVALID_CONFIG",
    });
  }
  const baseURL = (env.VITE_API_BASE_URL ?? "/api/v1")
    .trim()
    .replace(/\/+$/, "");
  if (
    source === "api" &&
    (!baseURL || !/^(https?:\/\/|\/(?!\/))/.test(baseURL))
  ) {
    throw new DataError(
      "VITE_API_BASE_URL에 /api/v1 또는 HTTP(S) 주소를 설정해 주세요.",
      { code: "INVALID_CONFIG" },
    );
  }
  return { source, baseURL };
}
