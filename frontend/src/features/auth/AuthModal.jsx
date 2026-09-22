import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { authRequest } from "./client";
import "./auth.css";

export default function AuthModal({ initialMode = "login", onClose, onLogin }) {
  const dialog = useRef(null);
  const request = useRef(null);
  const firstInput = useRef(null);
  const [mode, setMode] = useState(initialMode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const signup = mode === "signup";
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    firstInput.current?.focus();
    return () => {
      request.current?.abort();
      element.close();
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  function switchMode() {
    setMode(signup ? "login" : "signup");
    setError("");
    setMessage("");
  }
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const values = Object.fromEntries(new window.FormData(event.currentTarget));
    if (signup && values.password !== values.confirmPassword) {
      setError("비밀번호가 일치하지 않습니다. 다시 확인해 주세요.");
      return;
    }
    if (signup && !values.displayName.trim()) {
      setError("닉네임을 입력해 주세요.");
      return;
    }
    if (new window.TextEncoder().encode(values.password).length > 72) {
      setError("비밀번호는 UTF-8 기준 72바이트 이내로 입력해 주세요.");
      return;
    }
    setEmail(values.email.trim());
    setError("");
    setMessage("");
    setBusy(true);
    const controller = new AbortController();
    request.current = controller;
    const timer = window.setTimeout(() => controller.abort("timeout"), 15000);
    try {
      const body = { email: values.email.trim(), password: values.password };
      if (signup) {
        await authRequest("/auth/signup", {
          body: { ...body, displayName: values.displayName.trim() },
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setMode("login");
        setMessage("회원가입이 완료되었습니다. 로그인해 주세요.");
      } else {
        await onLogin(body, controller.signal);
        if (!controller.signal.aborted) onClose();
      }
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure.message);
      else if (controller.signal.reason === "timeout")
        setError("응답이 지연되고 있습니다. 다시 시도해 주세요.");
    } finally {
      window.clearTimeout(timer);
      if (!controller.signal.aborted || controller.signal.reason === "timeout")
        setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="auth-modal"
      aria-labelledby="auth-title"
      aria-describedby="auth-description"
      onCancel={onClose}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = [
          ...dialog.current.querySelectorAll(
            "button:not(:disabled), input:not(:disabled)",
          ),
        ];
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const rect = dialog.current.getBoundingClientRect();
          if (
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom
          )
            onClose();
        }
      }}
    >
      <button
        type="button"
        className="wp-icon-button auth-close"
        aria-label="인증 창 닫기"
        onClick={onClose}
      >
        <X size={20} />
      </button>
      <h2 id="auth-title">{signup ? "회원가입" : "로그인"}</h2>
      <p id="auth-description">
        {signup
          ? "관심 있는 변화들을 나만의 보관함에 모아 보세요."
          : "저장한 이슈와 관심 종목을 이어서 살펴보세요."}
      </p>
      <form key={mode} onSubmit={submit} aria-busy={busy}>
        <fieldset disabled={busy}>
          {signup && (
            <label>
              닉네임
              <input
                ref={firstInput}
                name="displayName"
                autoComplete="nickname"
                required
                maxLength={40}
                placeholder="사용할 이름"
              />
            </label>
          )}
          <label>
            이메일
            <input
              ref={signup ? undefined : firstInput}
              defaultValue={email}
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              placeholder="name@example.com"
            />
          </label>
          <label>
            비밀번호
            <input
              name="password"
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              required
              minLength={signup ? 8 : undefined}
              maxLength={128}
              placeholder={
                signup ? "8자 이상 입력해 주세요" : "비밀번호를 입력해 주세요"
              }
            />
          </label>
          {signup && (
            <label>
              비밀번호 확인
              <input
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                maxLength={128}
                placeholder="비밀번호를 다시 입력해 주세요"
              />
            </label>
          )}
        </fieldset>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p className="auth-message" role="status">
            {message}
          </p>
        )}
        <button
          className="wp-button auth-submit"
          data-variant="primary"
          disabled={busy}
        >
          {busy ? "처리 중…" : signup ? "회원가입" : "로그인"}
        </button>
      </form>
      <div className="auth-switch">
        <span>
          {signup ? "이미 계정이 있으신가요?" : "아직 계정이 없으신가요?"}
        </span>
        <button type="button" disabled={busy} onClick={switchMode}>
          {signup ? "로그인" : "회원가입"}
        </button>
      </div>
    </dialog>
  );
}
