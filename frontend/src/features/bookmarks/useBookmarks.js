import { useRef, useState } from "react";
// Local examples and backend IDs belong to different datasets.
const storagePrefix =
  import.meta.env.VITE_DATA_SOURCE === "api" ? "wikipulse.api" : "wikipulse";
function readSaved(key) {
  try {
    const data = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(data)
      ? [...new Set(data.filter((id) => typeof id === "string" && id.trim()))]
      : [];
  } catch {
    return [];
  }
}
export function useBookmarks() {
  const [savedEvents, setSavedEvents] = useState(() =>
    readSaved(`${storagePrefix}.savedEvents`),
  );
  const [savedStocks, setSavedStocks] = useState(() =>
    readSaved(`${storagePrefix}.savedStocks`),
  );
  const current = useRef({ events: savedEvents, stocks: savedStocks });
  const [notice, setNotice] = useState("");
  function toggleSaved(id, type, aliases = []) {
    const previous = current.current[type];
    const matchingIds = new Set([id, ...aliases]);
    const existed = previous.some((value) => matchingIds.has(value));
    const next = existed
      ? previous.filter((value) => !matchingIds.has(value))
      : [...previous, id];
    current.current[type] = next;
    (type === "events" ? setSavedEvents : setSavedStocks)(next);
    try {
      localStorage.setItem(
        `${storagePrefix}.${type === "events" ? "savedEvents" : "savedStocks"}`,
        JSON.stringify(next),
      );
      setNotice(
        existed ? "보관함에서 삭제했습니다." : "보관함에 저장했습니다.",
      );
    } catch {
      setNotice(
        "현재 화면에 저장했습니다. 브라우저 저장 공간을 사용할 수 없어 새로고침하면 사라집니다.",
      );
    }
  }
  return {
    savedEvents,
    savedStocks,
    notice,
    setNotice,
    onToggleEvent: (id, aliases) => toggleSaved(id, "events", aliases),
    onToggleStock: (id) => toggleSaved(id, "stocks"),
  };
}
