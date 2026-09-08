import { useGlobalSearch } from "./useGlobalSearch";
import { useEffect, useRef, useState } from "react";
import {
  Search,
  Network,
  FileText,
  Layers3,
  X,
  ArrowDownLeft,
} from "lucide-react";
export default function GlobalSearch({ searchRef }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const wrapperRef = useRef(null);
  const search = query.trim().toLowerCase();
  const { data, loading, error, reload } = useGlobalSearch(query);
  const kinds = {
    event: { path: "events", icon: Network },
    entity: { path: "intelligence", icon: FileText },
    stock: { path: "stocks", icon: Layers3 },
  };
  const results = (data || [])
    .filter((item) => kinds[item.kind])
    .map((item) => ({
      ...item,
      id: `${item.kind}-${item.id}`,
      href: `#/${kinds[item.kind].path}/${encodeURIComponent(item.id)}`,
      icon: kinds[item.kind].icon,
    }));
  const close = () => {
    setOpen(false);
    setQuery("");
    setActive(-1);
  };
  useEffect(() => {
    const onPointer = (event) => {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false);
    };
    const onHash = () => close();
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("hashchange", onHash);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("hashchange", onHash);
    };
  }, []);
  return (
    <div className="global-search" ref={wrapperRef}>
      <Search size={17} />
      <input
        ref={searchRef}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((v) => Math.max(0, Math.min(results.length - 1, v + 1)));
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((v) => Math.max(0, v - 1));
          }
          if (event.key === "Enter" && results.length) {
            event.preventDefault();
            window.location.hash =
              results[
                Math.min(results.length - 1, Math.max(0, active))
              ].href.slice(1);
            close();
          }
        }}
        aria-label="전체 검색"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && !!search}
        aria-controls="global-search-results"
        aria-activedescendant={
          active >= 0 && results[active] ? results[active].id : undefined
        }
        placeholder="사건, 문서, 종목 검색"
      />
      <kbd>Ctrl K</kbd>
      {query && (
        <button
          className="wp-icon-button"
          aria-label="전체 검색 지우기"
          onClick={close}
        >
          <X size={14} />
        </button>
      )}
      {open && search && (
        <div
          className="global-search__results"
          role="listbox"
          id="global-search-results"
          aria-label="전체 검색 결과"
        >
          {loading ? (
            <div className="global-search__empty" role="status">
              검색 중…
            </div>
          ) : error ? (
            <div className="global-search__empty" role="alert">
              검색하지 못했습니다.{" "}
              <button className="wp-button" onClick={reload}>
                검색 다시 시도
              </button>
            </div>
          ) : results.length ? (
            results.map((item, i) => (
              <a
                key={item.id}
                id={item.id}
                href={item.href}
                role="option"
                aria-selected={active === i}
                onMouseEnter={() => setActive(i)}
                onClick={close}
              >
                <item.icon size={18} />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                </span>
                <ArrowDownLeft size={14} />
              </a>
            ))
          ) : (
            <div className="global-search__empty">
              “{query}”에 대한 결과가 없습니다.
              <small>다른 사건명, 영문 문서명 또는 티커를 입력해 보세요.</small>
            </div>
          )}
          <div className="global-search__hint">
            방향키로 선택 · Enter로 이동 · Esc로 닫기
          </div>
        </div>
      )}
    </div>
  );
}
