import StockDirectory from "./StockDirectory";
import StockDetail from "./StockDetail";
import "./stocks.css";
export default function StocksPage({
  symbol,
  eventId,
  savedStocks = [],
  onToggleStock,
}) {
  return symbol ? (
    <StockDetail
      key={symbol}
      symbol={symbol}
      savedStocks={savedStocks}
      onToggleStock={onToggleStock}
    />
  ) : (
    <StockDirectory
      key={eventId || "all"}
      eventId={eventId}
      savedStocks={savedStocks}
      onToggleStock={onToggleStock}
    />
  );
}
