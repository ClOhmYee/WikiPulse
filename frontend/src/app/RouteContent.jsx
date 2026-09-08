import { lazy } from "react";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "../components/ui/EmptyState";
import ExplorePage from "../pages/explore/ExplorePage";
import SavedPage from "../pages/saved/SavedPage";
import { PageDataBoundary } from "../data/hooks/PageData";
const EventPage = lazy(() => import("../pages/event/EventPage"));
const EntityPage = lazy(() => import("../pages/entity/EntityPage"));
const StocksPage = lazy(() => import("../pages/stocks/StocksPage"));
export default function RouteContent({
  pathname,
  route,
  savedEvents,
  savedStocks,
  onToggleEvent,
  onToggleStock,
  onSource,
}) {
  const parts = pathname.split("/").filter(Boolean);
  const separator = route.indexOf("?");
  const queryParams = new URLSearchParams(
    separator < 0 ? "" : route.slice(separator + 1),
  );
  let content;
  if (pathname === "/pulse" || pathname === "/explore")
    content = (
      <ExplorePage
        key={route}
        listView={pathname === "/explore"}
        initialQuery={queryParams.get("q") || ""}
        savedEvents={savedEvents}
        onToggleEvent={onToggleEvent}
      />
    );
  else if (parts[0] === "events" && parts.length === 2)
    content = (
      <EventPage
        eventId={parts[1]}
        savedEvents={savedEvents}
        onToggleEvent={onToggleEvent}
      />
    );
  else if (parts[0] === "events" && parts.length === 3 && parts[2] === "stocks")
    content = (
      <StocksPage
        eventId={parts[1]}
        savedStocks={savedStocks}
        onToggleStock={onToggleStock}
      />
    );
  else if (parts[0] === "intelligence" && parts.length === 2)
    content = <EntityPage entityId={parts[1]} />;
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
    pathname === "/pulse" || pathname === "/explore"
      ? "explore"
      : parts[0] === "events" && parts.length === 2
        ? "event"
        : parts[0] === "events" && parts.length === 3 && parts[2] === "stocks"
          ? "eventStocks"
          : parts[0] === "intelligence" && parts.length === 2
            ? "entity"
            : parts[0] === "stocks" && parts.length <= 2
              ? parts[1]
                ? "stock"
                : "stocks"
              : pathname === "/saved"
                ? "saved"
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
