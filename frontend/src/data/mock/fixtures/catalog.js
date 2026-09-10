import { issueCategories } from "../../categories.js";
import {
  DEMO_DATE,
  dates,
  documents,
  episodes,
  articleAt,
  reportAt,
  universe,
  hash,
} from "./history.js";
export { DEMO_DATE, DEMO_NOTICE, HISTORY_START } from "./history.js";
export const categories = issueCategories;
export const events = episodes
  .map((e) => reportAt(e))
  .filter(Boolean)
  .sort((a, b) => b.date.localeCompare(a.date) || b.pulse - a.pulse);
export const entities = documents.map((doc) =>
  articleAt(
    doc.id,
    DEMO_DATE,
    events.filter((e) => e.articleIds.includes(doc.id)).map((e) => e.id),
  ),
);
const names = {
  NVDA: "엔비디아",
  MSFT: "마이크로소프트",
  AAPL: "애플",
  AMZN: "아마존",
  TSLA: "테슬라",
  CRWD: "크라우드스트라이크",
  BKR: "베이커 휴스",
  FANG: "다이아몬드백 에너지",
};
const sectors = {
  Technology: "기술",
  Industrials: "산업재",
  "Consumer Discretionary": "경기소비재",
  "Consumer Staples": "필수소비재",
  "Health Care": "헬스케어",
  Utilities: "유틸리티",
  Telecommunications: "통신",
  Energy: "에너지",
  "Basic Materials": "소재",
};
export const stocks = universe.stocks.map((source) => {
  const symbol = source.symbol,
    name = names[symbol] || source.name;
  const seed = hash(symbol),
    price = (3000 + (seed % 70000)) / 100;
  const related = events.filter((e) => e.stockSymbols.includes(symbol));
  const chart = dates.slice(-30).map((date, i) => ({
    date,
    price:
      Math.round(price * (0.9 + i / 290 + Math.sin(i + seed) * 0.018) * 100) /
      100,
  }));
  chart.at(-1).price = price;
  return {
    symbol,
    name,
    market: "NASDAQ",
    currency: "USD",
    sector: sectors[source.industry] || source.industry,
    description: `${source.name} · ${source.subsector}. 현재 Nasdaq-100 구성 종목 스냅샷을 사용합니다. 가격과 이슈 연결은 시연용 합성 데이터입니다.`,
    price,
    change: Math.round((price / chart.at(-2).price - 1) * 10000) / 100,
    chart,
    eventIds: related.map((e) => e.id),
    relations: related.map((event) => ({
      eventId: event.id,
      type: "industry",
      strength: "medium",
      explanation: `${event.keywords[1]} 리포트와 ${source.name}의 ${source.subsector} 사업을 연결한 가설입니다. 실제 기사·계약·가격 영향에 대한 검증 결과가 아닙니다.`,
      path: [event.keywords[0], event.keywords[1], source.subsector, name],
    })),
  };
});
export const getEvent = (id) => events.find((e) => e.id === id);
export const getEntity = (id) => entities.find((e) => e.id === id);
export const getStock = (symbol) =>
  stocks.find((s) => s.symbol === String(symbol || "").toUpperCase());
export const getCategory = (id) => categories.find((c) => c.id === id);
