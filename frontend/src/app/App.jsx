import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { readRoute } from "./router";
import RouteContent from "./RouteContent";
import WorkspaceLayout from "./layout/WorkspaceLayout";
import { PageBoundary, PageSkeleton } from "./layout/PageBoundary";
import { useBookmarks } from "../features/bookmarks/useBookmarks";
import { describeSource } from "../data/contracts";
import "../styles/workspace.css";
const Onboarding = lazy(() => import("../pages/onboarding/OnboardingPage"));
export default function App() {
  const [route, setRoute] = useState(readRoute);
  const pathname = route.split("?")[0];
  const bookmarks = useBookmarks();
  const [help, setHelp] = useState(false);
  const [meta, setMeta] = useState(null);
  const searchRef = useRef(null);
  const mainRef = useRef(null);
  const previousRoute = useRef(route);
  const onboarding = pathname === "/" || pathname === "/onboarding";
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
  const active = ["events", "intelligence"].includes(first) ? "explore" : first;
  return (
    <WorkspaceLayout
      {...bookmarks}
      active={active}
      help={help}
      setHelp={setHelp}
      searchRef={searchRef}
      mainRef={mainRef}
      route={route}
      source={describeSource(meta)}
    >
      <RouteContent
        {...bookmarks}
        route={route}
        pathname={pathname}
        onSource={setMeta}
      />
    </WorkspaceLayout>
  );
}
