import { useEffect, useRef, useState } from "react";
import { authRequest, validMember } from "./client";

const sessionKey = "wikipulse.auth.token";
function saveToken(token) {
  try {
    if (token) window.sessionStorage.setItem(sessionKey, token);
    else window.sessionStorage.removeItem(sessionKey);
  } catch {
    /* Session remains usable in memory when storage is unavailable. */
  }
}

export function useAuth() {
  const [member, setMember] = useState(null);
  const restoring = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    restoring.current = controller;
    let token;
    try {
      token = window.sessionStorage.getItem(sessionKey);
    } catch {
      return;
    }
    if (!token) return;
    authRequest("/me", { token, signal: controller.signal })
      .then((value) => {
        if (!validMember(value)) throw new Error("Invalid member");
        if (!controller.signal.aborted) setMember(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) saveToken(null);
      });
    return () => controller.abort();
  }, []);

  async function login(values, signal) {
    restoring.current?.abort();
    const result = await authRequest("/auth/login", { body: values, signal });
    if (
      !result ||
      typeof result.token !== "string" ||
      !result.token ||
      !validMember(result.member)
    )
      throw new Error("로그인 정보를 확인하지 못했습니다. 다시 시도해 주세요.");
    if (signal.aborted) return;
    saveToken(result.token);
    setMember(result.member);
  }
  function logout() {
    restoring.current?.abort();
    saveToken(null);
    setMember(null);
  }
  return { member, login, logout };
}
