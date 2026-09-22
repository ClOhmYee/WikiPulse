const baseURL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(
  /\/+$/,
  "",
);
let csrf;
export const clearCsrf = () => {
  csrf = undefined;
};
export async function authRequest(
  path,
  { body, method = body ? "POST" : "GET", signal, envelope = false } = {},
) {
  const headers = {
    Accept: "application/json",
    ...(body ? { "Content-Type": "application/json" } : {}),
  };
  if (!["GET", "HEAD"].includes(method)) {
    // Fetch per mutation: another tab may have rotated the session's token.
    csrf = await authRequest("/auth/csrf", { signal });
    headers[csrf.headerName] = csrf.token;
  }
  let response;
  try {
    response = await globalThis.fetch(`${baseURL}${path}`, {
      method,
      signal,
      credentials: "same-origin",
      headers,
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
  }
  signal?.throwIfAborted();
  if (!response.ok) {
    const messages = {
      400: "입력 내용을 확인해 주세요.",
      401:
        path === "/auth/login"
          ? "이메일 또는 비밀번호를 확인해 주세요."
          : "로그인이 필요합니다.",
      403: "인증 정보가 변경되었습니다. 다시 시도해 주세요.",
      404: "항목을 찾을 수 없습니다.",
      409: "이미 가입한 이메일입니다. 로그인해 주세요.",
    };
    const error = new Error(
      messages[response.status] ||
        "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    );
    error.status = response.status;
    if (response.status === 401 && path.startsWith("/me"))
      window.dispatchEvent(new window.Event("wikipulse:unauthorized"));
    throw error;
  }
  if (response.status === 204) return null;
  const result = await response.json();
  return envelope ? result : result.data;
}
export function validMember(member) {
  return member && member.id != null && typeof member.displayName === "string";
}
