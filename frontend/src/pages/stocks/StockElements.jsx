import { ArrowDown, ArrowRight, ArrowUp, Bookmark } from "lucide-react";
import { metricLabel } from "../event/presentation.js";
export const RELATION_LABELS = {
  DIRECT_MENTION: "직접 언급",
  PRODUCT_INDUSTRY: "제품·산업",
  SUPPLY_CHAIN: "공급망",
  REGION: "지역 노출",
};

const TIER_LABELS = {
  BOTH: "임베딩 · GDELT",
  GDELT_ONLY: "GDELT",
  EMBEDDING_ONLY: "임베딩",
};

export function MatchEvidence({ relation }) {
  if (!relation)
    return (
      <p className="wp-muted">이 연결의 상세 근거는 제공되지 않았습니다.</p>
    );
  return (
    <div className="st-relationship">
      <div className="st-relationship-heading">
        <span>{RELATION_LABELS[relation.matchPath] || "연결 유형 미제공"}</span>
      </div>
      <p>{relation.rationale || "연결 설명 미제공"}</p>
      {relation.tier && (
        <p className="wp-small">
          후보 탐색 경로: {TIER_LABELS[relation.tier] || relation.tier}
        </p>
      )}
      {(relation.similarity != null || relation.gdeltLift != null) && (
        <p className="wp-small">
          {relation.similarity != null && (
            <span>임베딩 유사도 {metricLabel(relation.similarity, 3)} </span>
          )}
          {relation.gdeltLift != null && (
            <span>GDELT 동시출현 {metricLabel(relation.gdeltLift)}배</span>
          )}
        </p>
      )}
    </div>
  );
}

export function isSaved(savedStocks, symbol) {
  return savedStocks instanceof Set
    ? savedStocks.has(symbol)
    : Array.isArray(savedStocks) && savedStocks.includes(symbol);
}

export function priceLabel(stock) {
  if (typeof stock.price !== "number" || !Number.isFinite(stock.price))
    return "미제공";
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
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
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
