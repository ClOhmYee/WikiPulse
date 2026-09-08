import { ArrowDown, ArrowRight, ArrowUp, Bookmark } from "lucide-react";
export const RELATION_LABELS = {
  direct: "직접 언급",
  industry: "산업·기술",
  supply: "공급망",
  region: "지역 노출",
};

export function isSaved(savedStocks, symbol) {
  return savedStocks instanceof Set
    ? savedStocks.has(symbol)
    : Array.isArray(savedStocks) && savedStocks.includes(symbol);
}

export function priceLabel(stock) {
  if (typeof stock.price !== "number") return "—";
  const isKorean =
    stock.currency === "KRW" ||
    /KRX|KOSPI|KOSDAQ/.test(stock.market) ||
    /^\d{6}(?:\.KS|\.KQ)?$/.test(stock.symbol);
  return new Intl.NumberFormat(isKorean ? "ko-KR" : "en-US", {
    style: "currency",
    currency: stock.currency || (isKorean ? "KRW" : "USD"),
    maximumFractionDigits: isKorean ? 0 : 2,
  }).format(stock.price);
}

export function dateLabel(value) {
  if (!value) return "날짜 미정";
  const parts = String(value).slice(0, 10).split("-");
  return parts.length === 3 ? `${parts[0]}.${parts[1]}.${parts[2]}` : value;
}

export function StockMark({ stock, large = false }) {
  return (
    <span
      className={`st-stock-mark${large ? " st-stock-mark-large" : ""}`}
      aria-hidden="true"
    >
      {stock.symbol.slice(0, 2)}
    </span>
  );
}

export function SaveButton({
  stock,
  savedStocks,
  onToggleStock,
  full = false,
}) {
  const saved = isSaved(savedStocks, stock.symbol);
  return (
    <button
      type="button"
      className={full ? "wp-button st-save-full" : "wp-icon-button st-save"}
      data-saved={saved}
      aria-pressed={saved}
      aria-label={`${stock.name} ${saved ? "관심 종목에서 해제" : "관심 종목에 추가"}`}
      title={saved ? "관심 종목에서 해제" : "관심 종목에 추가"}
      onClick={() => onToggleStock?.(stock.symbol)}
    >
      <Bookmark
        size={17}
        fill={saved ? "currentColor" : "none"}
        aria-hidden="true"
      />
      {full && <span>{saved ? "관심 종목에 저장됨" : "관심 종목에 추가"}</span>}
    </button>
  );
}

export function PriceChange({ value }) {
  if (typeof value !== "number") return <span className="wp-muted">—</span>;
  const Direction = value < 0 ? ArrowDown : ArrowUp;
  return (
    <span
      className="st-price-change"
      data-direction={value < 0 ? "down" : "up"}
    >
      <Direction size={12} aria-hidden="true" />
      {Math.abs(value).toFixed(2)}%
    </span>
  );
}

export function RelationPath({ path }) {
  if (!path?.length) return null;
  return (
    <ol className="st-relation-path" aria-label="사건과 기업의 연결 경로">
      {path.map((step, index) => (
        <li key={`${step}-${index}`}>
          <span>{step}</span>
          {index < path.length - 1 && (
            <ArrowRight size={14} aria-hidden="true" />
          )}
        </li>
      ))}
    </ol>
  );
}
