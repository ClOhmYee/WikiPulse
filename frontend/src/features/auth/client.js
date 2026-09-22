// Adapter for the future auth contract in docs/api-v0.3.md §5.
// No local authentication fallback: only a server response establishes identity.
const baseURL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(
  /\/+$/,
  "",
);

export async function authRequest(path, { body, token, signal } = {}) {
  let response;
  try {
    response = await globalThis.fetch(`${baseURL}${path}`, {
      method: body ? "POST" : "GET",
      signal,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
  }
  if ([404, 405, 501].includes(response.status))
    throw new Error("계정 서비스를 준비 중입니다. 잠시 후 다시 이용해 주세요.");
  if (response.status === 401)
    throw new Error("이메일 또는 비밀번호를 확인해 주세요.");
  if (response.status === 409)
    throw new Error("이미 가입한 이메일입니다. 로그인해 주세요.");
  if (!response.ok)
    throw new Error("요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
  if (response.status === 204) return null;
  try {
    const result = await response.json();
    return result.data ?? result;
  } catch {
    throw new Error(
      "계정 서비스 응답을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    );
  }
}

export function validMember(member) {
  return member && member.id != null && typeof member.displayName === "string";
}
