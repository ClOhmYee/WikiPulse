import { lazy } from "react";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "../components/ui/EmptyState";
import ExplorePage from "../pages/explore/ExplorePage";
import HistoryExplorePage from "../pages/explore/HistoryExplorePage";
import SavedPage from "../pages/saved/SavedPage";
import { PageDataBoundary } from "../data/hooks/PageData";
import { isHistoryPreviewRoute } from "./router";
import { dataClient } from "../data/index.js";
import { issueHistoryEnabled } from "../data/historyProduction.js";
const EventPage = lazy(() => import("../pages/event/EventPage"));
const IssueHistoryPreviewPage = import.meta.env.DEV
  ? lazy(() => import("../pages/issue-history-preview/IssueHistoryPreviewPage"))
  : null;
const AccountPage = lazy(() => import("../pages/account/AccountPage"));
const StocksPage = lazy(() => import("../pages/stocks/StocksPage"));
const PulsePage = lazy(() => import("../pages/pulse/PulsePage"));
export default function RouteContent({
  pathname,
  route,
  savedEvents,
  savedStocks,
  onToggleEvent,
  onToggleStock,
  onSource,
  member,
  onLogin,
  authStatus,
  savedStatus,
  reloadSaved,
}) {
  if (
    !member &&
    authStatus !== "ready" &&
    ["/saved", "/mypage"].includes(pathname)
  )
    return (
      <div className="wp-page" role="status">
        {authStatus === "loading"
          ? "로그인 상태를 확인하고 있습니다."
          : "로그인 상태를 확인하지 못했습니다. 다시 시도해 주세요."}
      </div>
    );
  if (!member && ["/saved", "/mypage"].includes(pathname))
    return (
      <EmptyState
        title="로그인이 필요합니다"
        description="로그인하고 내 정보와 보관함을 확인해 보세요."
        action={
          <button
            className="wp-button"
            data-variant="primary"
            onClick={onLogin}
          >
            로그인
          </button>
        }
      />
    );
  const parts = pathname.split("/").filter(Boolean);
  const separator = route.indexOf("?");
  const queryParams = new URLSearchParams(
    separator < 0 ? "" : route.slice(separator + 1),
  );
  const historyMode = issueHistoryEnabled(
    import.meta.env,
    dataClient.dataSource,
  );
  let content;
  if (isHistoryPreviewRoute(pathname, import.meta.env.DEV))
    content = <IssueHistoryPreviewPage pathname={pathname} />;
  else if (pathname === "/pulse")
    content = (
      <PulsePage
        savedEvents={savedEvents}
        onToggleEvent={onToggleEvent}
        onSource={onSource}
      />
    );
  else if (pathname === "/issues")
    content = historyMode ? (
      <HistoryExplorePage
        key={route}
        initialQuery={queryParams.get("q") || ""}
      />
    ) : (
      <ExplorePage
        key={route}
        initialQuery={queryParams.get("q") || ""}
        savedEvents={savedEvents}
        onToggleEvent={onToggleEvent}
      />
    );
  else if (parts[0] === "issues" && parts.length === 2)
    content = (
      <EventPage
        eventId={parts[1]}
        savedEvents={savedEvents}
        onToggleEvent={onToggleEvent}
      />
    );
  else if (parts[0] === "issues" && parts.length === 3 && parts[2] === "stocks")
    content = (
      <StocksPage
        eventId={parts[1]}
        savedStocks={savedStocks}
        onToggleStock={onToggleStock}
      />
    );
  else if (pathname === "/mypage") content = <AccountPage member={member} />;
  else if (parts[0] === "stocks" && parts.length <= 2)
    content = (
      <StocksPage
        symbol={parts[1]}
        savedStocks={savedStocks}
        onToggleStock={onToggleStock}
      />
    );
  else if (pathname === "/saved")
    content = (
      <SavedPage
        savedStatus={savedStatus}
        reloadSaved={reloadSaved}
        savedEvents={savedEvents}
        savedStocks={savedStocks}
        onToggleEvent={onToggleEvent}
        onToggleStock={onToggleStock}
      />
    );
  else
    content = (
      <EmptyState
        title="페이지를 찾을 수 없습니다"
        description="주소를 확인하거나 Pulse Map에서 다시 시작해 주세요."
        action={
          <a href="#/pulse" className="wp-button" data-variant="primary">
            Pulse Map으로 이동
            <ArrowRight size={16} />
          </a>
        }
      />
    );
  const resource =
    pathname === "/issues"
      ? historyMode
        ? null
        : "explore"
      : parts[0] === "issues" && parts.length === 2
        ? "event"
        : parts[0] === "issues" && parts.length === 3 && parts[2] === "stocks"
          ? "eventStocks"
          : parts[0] === "stocks" && parts.length <= 2
            ? parts[1]
              ? "stock"
              : "stocks"
            : null;
  return resource ? (
    <PageDataBoundary
      resource={resource}
      id={parts[1]}
      savedEvents={savedEvents}
      savedStocks={savedStocks}
      onSource={onSource}
    >
      {content}
    </PageDataBoundary>
  ) : (
    content
  );
}
