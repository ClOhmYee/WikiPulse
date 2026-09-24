import {
  Suspense,
  lazy,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { readTheme, saveTheme, applyTheme } from "./theme";
import { isHistoryPreviewRoute, readRoute } from "./router";
import RouteContent from "./RouteContent";
import WorkspaceLayout from "./layout/WorkspaceLayout";
import { PageBoundary, PageSkeleton } from "./layout/PageBoundary";
import { useBookmarks } from "../features/bookmarks/useBookmarks";
import { useAuth } from "../features/auth/useAuth";
import AuthModal from "../features/auth/AuthModal";
import "../styles/workspace.css";
const Onboarding = lazy(() => import("../pages/onboarding/OnboardingPage"));
export default function App() {
  const [theme, setTheme] = useState(readTheme);
  const [route, setRoute] = useState(readRoute);
  const requestedPath = route.split("?")[0];
  const authRoute = ["/login", "/signup"].includes(requestedPath);
  const pathname = authRoute ? "/pulse" : requestedPath;
  const localHistoryPreview = isHistoryPreviewRoute(
    pathname,
    import.meta.env.DEV,
  );
  const auth = useAuth();
  const [authMode, setAuthMode] = useState(null);
  const [saveIntent, setSaveIntent] = useState(null);
  const bookmarks = useBookmarks(auth.member, (intent) => {
    setSaveIntent(intent);
    setAuthMode("login");
  });
  const pendingSave = useRef(null);
  useEffect(() => {
    if (auth.member && pendingSave.current) {
      const intent = pendingSave.current;
      pendingSave.current = null;
      bookmarks.completeSave(intent);
    }
  }, [auth.member, bookmarks]);
  const searchRef = useRef(null);
  const mainRef = useRef(null);
  const previousRoute = useRef(route);
  const onboarding = pathname === "/";
  useLayoutEffect(() => applyTheme(theme, onboarding), [theme, onboarding]);
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    saveTheme(next);
    setTheme(next);
  };
  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("workspace-active", !onboarding);
    document.title = onboarding
      ? "WikiPulse — Signal to Context"
      : "WikiPulse — 사건의 맥락을 따라가다";
    window.scrollTo({ top: 0, behavior: "instant" });
    if (previousRoute.current !== route && !onboarding)
      mainRef.current?.focus({ preventScroll: true });
    previousRoute.current = route;
    return () => document.documentElement.classList.remove("workspace-active");
  }, [route, onboarding]);
  useEffect(() => {
    const key = (event) => {
      if (document.querySelector("dialog[open]")) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const { notice, setNotice } = bookmarks;
  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 3500);
    return () => window.clearTimeout(timeout);
  }, [notice, setNotice]);
  if (onboarding)
    return (
      <PageBoundary key="onboarding">
        <Suspense fallback={<PageSkeleton />}>
          <Onboarding />
        </Suspense>
      </PageBoundary>
    );
  const first = pathname.split("/")[1];
  const active = localHistoryPreview ? "issues" : first;
  const mode = authMode || (authRoute ? requestedPath.slice(1) : null);
  const closeAuth = () => {
    setAuthMode(null);
    setSaveIntent(null);
    if (authRoute) window.location.hash = "/pulse";
  };
  return (
    <WorkspaceLayout
      theme={theme}
      onToggleTheme={toggleTheme}
      {...bookmarks}
      active={active}
      member={auth.member}
      onLogin={() => setAuthMode("login")}
      onLogout={auth.logout}
      searchRef={searchRef}
      mainRef={mainRef}
      route={route}
    >
      {auth.error && !localHistoryPreview && (
        <div className="wp-page" role="alert">
          {auth.error}{" "}
          <button className="wp-button" onClick={auth.restore}>
            다시 시도
          </button>
        </div>
      )}
      <RouteContent
        key={auth.member?.id ?? "guest"}
        authStatus={auth.status}
        {...bookmarks}
        route={route}
        pathname={pathname}
        member={auth.member}
        onLogin={() => setAuthMode("login")}
      />
      {mode && (
        <AuthModal
          key={mode}
          initialMode={mode}
          onClose={closeAuth}
          onLogin={async (values, signal) => {
            const member = await auth.login(values, signal);
            if (member && saveIntent) pendingSave.current = saveIntent;
          }}
        />
      )}
    </WorkspaceLayout>
  );
}
