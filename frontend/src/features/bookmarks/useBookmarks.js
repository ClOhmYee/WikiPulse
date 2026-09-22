import { useCallback, useEffect, useRef, useState } from "react";
import { authRequest } from "../auth/client";
import { dataClient } from "../../data/index";

const empty = { events: [], stocks: [], owner: null };
export function useBookmarks(member, requestLogin) {
  const [saved, setSaved] = useState(empty);
  const [status, setStatus] = useState("loading");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const current = useRef(empty);
  const pending = useRef(new Map());
  const owner = member?.id ?? null;
  const identity = useRef(owner);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    const activeRequests = pending.current;
    identity.current = owner;
    current.current = empty;
    for (const controller of pending.current.values()) controller.abort();
    pending.current.clear();
    if (owner === null) return;
    const controller = new AbortController();
    authRequest("/me/saved-state", { signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        const next = {
          owner,
          events: value.issueIds.map(String),
          stocks: value.tickers,
        };
        current.current = next;
        setSaved(next);
        setStatus("ready");
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setSaved((previous) => ({
            ...(previous.owner === owner ? previous : empty),
            owner,
          }));
          setStatus("error");
          setNotice(error.message);
        }
      });
    return () => {
      controller.abort();
      for (const item of activeRequests.values()) item.abort();
      activeRequests.clear();
    };
  }, [owner, version]);
  async function toggleSaved(id, type, forceSave = false) {
    if (dataClient.dataSource !== "api") {
      setNotice("예시 데이터는 계정 보관함에 저장할 수 없습니다.");
      return;
    }
    id = String(id);
    if (owner === null) {
      requestLogin({ id, type });
      return;
    }
    if (!forceSave && (current.current.owner !== owner || status !== "ready")) {
      setNotice("보관함 정보를 확인한 뒤 다시 시도해 주세요.");
      reload();
      return;
    }
    const key = `${type}:${id}`;
    if (pending.current.has(key)) return;
    const controller = new AbortController();
    pending.current.set(key, controller);
    const existed = !forceSave && current.current[type].includes(id);
    try {
      await authRequest(
        `/me/${type === "events" ? "bookmarks" : "watchlist"}/${encodeURIComponent(id)}`,
        { method: existed ? "DELETE" : "PUT", signal: controller.signal },
      );
      if (controller.signal.aborted || identity.current !== owner) return;
      const previous =
        current.current.owner === owner ? current.current : { ...empty, owner };
      const next = {
        ...previous,
        [type]: existed
          ? previous[type].filter((v) => v !== id)
          : [...new Set([...previous[type], id])],
      };
      current.current = next;
      setSaved(next);
      setNotice(
        existed ? "보관함에서 해제했습니다." : "보관함에 저장했습니다.",
      );
      // Refresh full state after a login-triggered write that may race initial restoration.
      if (forceSave) reload();
    } catch (error) {
      if (!controller.signal.aborted) setNotice(error.message);
    } finally {
      if (pending.current.get(key) === controller) pending.current.delete(key);
    }
  }
  const visible = saved.owner === owner && owner !== null ? saved : empty;
  return {
    savedEvents: visible.events,
    savedStocks: visible.stocks,
    notice,
    setNotice,
    savedStatus: saved.owner === owner ? status : "loading",
    reloadSaved: reload,
    onToggleEvent: (id) => toggleSaved(id, "events"),
    onToggleStock: (id) => toggleSaved(id, "stocks"),
    completeSave: (intent) => toggleSaved(intent.id, intent.type, true),
  };
}
