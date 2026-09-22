import { useCallback, useEffect, useRef, useState } from "react";
import { authRequest, clearCsrf, validMember } from "./client";

export function useAuth() {
  const [member, setMember] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const request = useRef(null);
  const channel = useRef(null);
  const restore = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const value = await authRequest("/me", { signal: controller.signal });
      if (!validMember(value))
        throw new Error("로그인 정보를 확인하지 못했습니다.");
      if (!controller.signal.aborted) {
        setMember(value);
        setStatus("ready");
        setError("");
      }
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (failure.status === 401) {
        setMember(null);
        setStatus("ready");
        setError("");
      } else {
        setStatus("error");
        setError(failure.message);
      }
    }
  }, []);
  useEffect(() => {
    try {
      window.sessionStorage.removeItem("wikipulse.auth.token");
    } catch {
      /* cookies are authoritative */
    }
    const unauthorized = () => {
      setMember(null);
      setStatus("ready");
      clearCsrf();
    };
    channel.current =
      typeof window.BroadcastChannel === "function"
        ? new window.BroadcastChannel("wikipulse-account")
        : null;
    if (channel.current)
      channel.current.onmessage = () => {
        // Clear private views immediately; then resolve the new shared cookie identity.
        setMember(null);
        setStatus("loading");
        restore();
      };
    const visibility = () => {
      if (document.visibilityState === "visible") restore();
    };
    restore();
    window.addEventListener("wikipulse:unauthorized", unauthorized);
    window.addEventListener("focus", restore);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      request.current?.abort();
      channel.current?.close();
      window.removeEventListener("wikipulse:unauthorized", unauthorized);
      window.removeEventListener("focus", restore);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [restore]);
  async function login(values, signal) {
    request.current?.abort();
    const result = await authRequest("/auth/login", { body: values, signal });
    if (!validMember(result?.member))
      throw new Error("로그인 정보를 확인하지 못했습니다.");
    clearCsrf();
    if (signal?.aborted) return null;
    setMember(result.member);
    setStatus("ready");
    setError("");
    channel.current?.postMessage("changed");
    return result.member;
  }
  async function logout() {
    request.current?.abort();
    try {
      await authRequest("/auth/logout", { method: "POST" });
      clearCsrf();
      setMember(null);
      setStatus("ready");
      setError("");
      channel.current?.postMessage("changed");
    } catch (failure) {
      setError(failure.message);
    }
  }
  return { member, status, error, restore, login, logout };
}
