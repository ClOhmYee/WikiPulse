import { useCallback, useEffect, useRef, useState } from "react";
import { authRequest, clearCsrf, validMember } from "./client";

export function useAuth() {
  const [member, setMember] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const request = useRef(null);
  const channel = useRef(null);
  const mutation = useRef(null);
  const revision = useRef(0);
  const mounted = useRef(false);
  const restore = useCallback(async () => {
    if (!mounted.current || mutation.current) return;
    request.current?.abort();
    const version = revision.current;
    const controller = new AbortController();
    request.current = controller;
    try {
      const value = await authRequest("/me", { signal: controller.signal });
      if (!validMember(value))
        throw new Error("로그인 정보를 확인하지 못했습니다.");
      if (!controller.signal.aborted && version === revision.current) {
        setMember(value);
        setStatus("ready");
        setError("");
      }
    } catch (failure) {
      if (controller.signal.aborted || version !== revision.current) return;
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
    mounted.current = true;
    revision.current = revision.current + 1;
    try {
      window.sessionStorage.removeItem("wikipulse.auth.token");
    } catch {
      /* cookies are authoritative */
    }
    const unauthorized = () => {
      if (mutation.current) return;
      revision.current++;
      request.current?.abort();
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
        revision.current++;
        request.current?.abort();
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
      mounted.current = false;
      revision.current++;
      request.current?.abort();
      channel.current?.close();
      window.removeEventListener("wikipulse:unauthorized", unauthorized);
      window.removeEventListener("focus", restore);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [restore]);
  async function login(values, signal) {
    if (mutation.current) return null;
    const operation = {};
    mutation.current = operation;
    const version = ++revision.current;
    request.current?.abort();
    try {
      const result = await authRequest("/auth/login", { body: values, signal });
      if (!validMember(result?.member))
        throw new Error("로그인 정보를 확인하지 못했습니다.");
      clearCsrf();
      if (signal?.aborted || version !== revision.current) return null;
      setMember(result.member);
      setStatus("ready");
      setError("");
      channel.current?.postMessage("changed");
      return result.member;
    } finally {
      if (mutation.current === operation) mutation.current = null;
      if (version !== revision.current || signal?.aborted) restore();
    }
  }
  async function logout() {
    if (mutation.current) return;
    const operation = {};
    mutation.current = operation;
    const version = ++revision.current;
    request.current?.abort();
    try {
      await authRequest("/auth/logout", { method: "POST" });
      if (version !== revision.current) return;
      clearCsrf();
      setMember(null);
      setStatus("ready");
      setError("");
      channel.current?.postMessage("changed");
    } catch (failure) {
      if (version === revision.current) setError(failure.message);
    } finally {
      if (mutation.current === operation) mutation.current = null;
      if (version !== revision.current) restore();
    }
  }
  return { member, status, error, restore, login, logout };
}
