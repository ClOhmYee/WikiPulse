import { ArrowRight, ChevronRight, CircleHelp, X } from "lucide-react";
import { Suspense } from "react";
import { NAV_ITEMS } from "../navigation";
import { PageBoundary, PageSkeleton } from "./PageBoundary";
import GlobalSearch from "../../features/global-search/GlobalSearch";
export default function WorkspaceLayout({
  active,
  savedEvents,
  savedStocks,
  help,
  setHelp,
  searchRef,
  mainRef,
  route,
  notice,
  children,
  source,
}) {
  return (
    <div className="workspace">
      <a
        href="#workspace-content"
        className="wp-skip-link"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        본문으로 이동
      </a>
      <aside className="workspace-sidebar">
        <a href="#/pulse" className="workspace-brand" aria-label="WikiPulse 홈">
          <img src="/wikipulse-icon.png" alt="" />
          <span>
            WIKI<strong>PULSE</strong>
          </span>
        </a>
        <div className="sidebar-subtitle">변화에서 맥락으로</div>
        <nav className="workspace-nav" aria-label="주 메뉴">
          {NAV_ITEMS.map((item) => (
            <a
              href={item.href}
              key={item.key}
              aria-label={item.label}
              title={item.label}
              aria-current={active === item.key ? "page" : undefined}
            >
              <item.icon size={19} strokeWidth={1.7} />
              <span>{item.label}</span>
              {item.key === "saved" &&
                savedEvents.length + savedStocks.length > 0 && (
                  <small>{savedEvents.length + savedStocks.length}</small>
                )}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-guide">
            <div className="sidebar-guide__line">
              <span>Track</span>
              <i />
              <span>Cluster</span>
              <i />
              <span>Match</span>
            </div>
            <p>
              작은 변화를 따라가면
              <br />
              새로운 맥락이 보입니다.
            </p>
          </div>
          <a href="#/">
            <CircleHelp size={16} />
            WikiPulse 소개
            <ArrowRight size={13} />
          </a>
          <div className="sidebar-snapshot">
            <span />
            데모 워크스페이스
          </div>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-header">
          <a
            href="#/pulse"
            className="workspace-mobile-brand"
            aria-label="WikiPulse 홈"
          >
            <img src="/wikipulse-icon.png" alt="" />
          </a>
          <div className="workspace-breadcrumb">
            Workspace
            <ChevronRight size={13} />
            <span>
              {NAV_ITEMS.find((item) => item.key === active)?.label || "탐색"}
            </span>
          </div>
          <GlobalSearch searchRef={searchRef} />
          <button
            className="workspace-demo"
            aria-expanded={help}
            onClick={() => setHelp(!help)}
          >
            <span />
            {source.label}
            <CircleHelp size={13} />
          </button>
        </header>
        {help && (
          <div className="workspace-help">
            <div>
              <strong>자유롭게 탐색할 수 있는 데모입니다.</strong>
              <p>
                {source.description}
                저장한 항목은 이 브라우저에서 다시 볼 수 있습니다.
              </p>
            </div>
            <button
              className="wp-icon-button"
              aria-label="데모 안내 닫기"
              onClick={() => setHelp(false)}
            >
              <X size={17} />
            </button>
          </div>
        )}
        <main id="workspace-content" ref={mainRef} tabIndex="-1">
          <PageBoundary key={route}>
            <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
          </PageBoundary>
        </main>
        <footer className="workspace-footer">
          <span>WIKIPULSE</span>
          <span>Track the signal. Understand the context.</span>
          <span>{source.label}</span>
        </footer>
      </div>
      <div
        className={`workspace-toast${notice ? " is-visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {notice}
      </div>
    </div>
  );
}
