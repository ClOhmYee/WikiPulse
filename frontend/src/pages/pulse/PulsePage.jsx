import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import { issueCategories } from "../../data/categories.js";
import { searchableTitles } from "../../data/titles.js";
import {
  calendarDays,
  kstDate,
  kstTimestamp,
  snapshotKey,
} from "../../data/pulse/time.js";
import PulseMap from "./PulseMap";
import PulseMapFrame from "./PulseMapFrame";
import PulseTimeline from "./PulseTimeline";
import PulsePreview, { SignalBadges } from "./PulsePreview";
import "./pulse.css";
import { createLayoutEngine } from "./layout.js";

export default function PulsePage({ savedEvents, onToggleEvent, onSource }) {
  const loadIndex = useCallback(
    (signal) => dataClient.listSnapshots({}, { signal }),
    [],
  );
  const index = useAsyncResource(loadIndex, "pulse-snapshots");
  const [requested, setRequested] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [nodeId, setNodeId] = useState(null);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [scanEnabled, setScanEnabled] = useState(true);
  const returnScroll = useRef(null);
  const cameraState = useRef(null);
  const [category, setCategory] = useState("all");
  const items = index.data?.data;
  const latest =
    items?.filter((v) => v.source === "live").at(-1) || items?.at(-1);
  const target =
    items?.find(
      (v) => requested && snapshotKey(v) === snapshotKey(requested),
    ) || latest;
  const key = target ? snapshotKey(target) : "no-snapshot";
  const loadMap = useCallback(
    (signal) =>
      target
        ? dataClient.getPulseMap(
            { snapshotTs: target.snapshotTs, source: target.source },
            { signal },
          )
        : Promise.resolve(null),
    [target],
  );
  const map = useAsyncResource(loadMap, key);
  const clusters = map.data?.data.clusters;
  const [layoutEngine] = useState(() => createLayoutEngine());
  const selected = (clusters || []).find((v) => v.issueKey === selectedKey);
  useEffect(() => {
    if (map.data) onSource?.(map.data.meta);
  }, [map.data, onSource]);
  useEffect(() => {
    if (!clusters) return;
    if (selectedKey && !selected) {
      setSelectedKey(null);
      setNodeId(null);
      setNotice("선택한 이슈가 이 시점에 없어 선택을 해제했습니다.");
    } else if (
      nodeId &&
      selected &&
      !selected.nodes.some((v) => v.pageId === nodeId)
    ) {
      setNodeId(null);
      setNotice("선택한 문서가 이 시점의 구성에서 제외되었습니다.");
    }
  }, [clusters, selected, selectedKey, nodeId]);
  const filtered = useMemo(
    () =>
      (clusters || []).filter(
        (v) =>
          (category === "all" || v.category === category) &&
          // 한국어로 보이는 제목은 한국어로도 검색돼야 한다. 영문 원문도 계속 색인한다.
          `${v.label} ${v.summary || ""} ${v.nodes.map(searchableTitles).join(" ")}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
      ) || [],
    [clusters, category, query],
  );
  const visibleSelected = filtered.find((v) => v.issueKey === selectedKey);
  const scene = useMemo(() => layoutEngine(filtered), [layoutEngine, filtered]);
  function selectCluster(issueKey) {
    setSelectedKey(issueKey);
    setNodeId(null);
    setNotice("");
  }
  function selectTime(value) {
    setRequested(value);
    setNotice("");
  }
  function toggleExpanded() {
    if (!expanded) {
      // Capture before replacing the inline map shrinks the document.
      returnScroll.current = { left: window.scrollX, top: window.scrollY };
    }
    setExpanded((value) => !value);
  }
  const sourceItems = items?.filter((v) => v.source === target?.source) || [];
  const days = calendarDays(sourceItems);
  const categoryFilters = (
    <div
      className="wp-filter-chips pulse-filters"
      role="group"
      aria-label="사건 주제"
    >
      {[{ id: "all", label: "전체" }, ...issueCategories].map((v) => (
        <button
          key={v.id}
          className="wp-chip"
          data-active={category === v.id}
          aria-pressed={category === v.id}
          onClick={() => setCategory(v.id)}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
  const timeline = target && (
    <PulseTimeline
      compact
      snapshots={sourceItems}
      selected={target}
      latest={latest}
      onSelect={selectTime}
    />
  );
  return (
    <div className="wp-page pulse-page">
      <div className="wp-page-header">
        <div>
          <h1>세상의 변화가 모이는 곳</h1>
          <p className="wp-subtitle">
            시간을 따라, 이슈를 이루는 문서의 연결을 살펴보세요.
          </p>
        </div>
      </div>
      {index.loading ? (
        <p role="status">선택 가능한 시점을 불러오는 중입니다.</p>
      ) : index.error ? (
        <div role="alert">
          <p>{index.error.message}</p>
          <button className="wp-button" onClick={index.reload}>
            시점 목록 다시 불러오기
          </button>
        </div>
      ) : !target ? (
        <div className="pulse-empty">
          <h2>아직 저장된 스냅샷이 없습니다</h2>
          <p>이슈 데이터가 준비되면 시간별 지도가 표시됩니다.</p>
          <button className="wp-button" onClick={index.reload}>
            다시 확인
          </button>
        </div>
      ) : (
        <>
          <div className="pulse-toolbar">
            <label className="wp-search">
              <Search size={17} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="이슈, 문서 검색"
                aria-label="사건 검색"
              />
              {query && (
                <button
                  className="wp-icon-button"
                  onClick={() => setQuery("")}
                  aria-label="검색어 지우기"
                >
                  <X size={16} />
                </button>
              )}
            </label>
            <label className="pulse-date">
              날짜
              <select
                aria-label="스냅샷 날짜"
                value={kstDate(target.snapshotTs)}
                onChange={(e) =>
                  selectTime(
                    sourceItems
                      .filter((v) => kstDate(v.snapshotTs) === e.target.value)
                      .at(-1),
                  )
                }
              >
                {days.map((day) => (
                  <option
                    value={day.value}
                    key={day.value}
                    disabled={!day.available}
                  >
                    {day.value}
                    {day.available ? "" : " · 데이터 없음"}
                  </option>
                ))}
              </select>
            </label>
            <label className="pulse-date">
              데이터
              <select
                aria-label="스냅샷 출처"
                value={target.source}
                onChange={(e) =>
                  selectTime(
                    items.filter((v) => v.source === e.target.value).at(-1),
                  )
                }
              >
                {["live", "replay"]
                  .filter((source) => items.some((v) => v.source === source))
                  .map((source) => (
                    <option key={source} value={source}>
                      {source === "live" ? "실시간 수집" : "과거 재구성"}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          {categoryFilters}
          <div className="pulse-reading-guide">
            <span>
              <b>NEW</b> {map.data?.meta.newWindowHours || 24}시간 내 최초 감지
            </span>
            <span>노드 크기 = 공통 척도의 급증도</span>
          </div>
          <p className="data-scope">
            중앙에는 이슈 급증 점수가 높은 클러스터가 배치됩니다. AI 검증 상태와
            탐지 신호의 충족 여부는 별개입니다. 점수는 편집 배수나 확률이
            아닙니다.
            {map.data?.meta.scoreVersion &&
              ` 점수 척도 ${map.data.meta.scoreVersion}`}
          </p>
          {!expanded && timeline}
          <PulseMapFrame
            expanded={expanded}
            onClose={() => setExpanded(false)}
            timeline={
              <>
                {timeline}
                {categoryFilters}
              </>
            }
            hasMap={Boolean(map.data && filtered.length)}
            returnScroll={returnScroll}
          >
            <p className="pulse-notice" role="status">
              {notice ||
                (map.loading
                  ? `${kstTimestamp(target.snapshotTs)} 지도를 불러오는 중입니다.`
                  : "")}
            </p>
            {map.error ? (
              <div className="pulse-empty" role="alert">
                <h2>이 시점의 지도를 불러오지 못했습니다</h2>
                <p>{map.error.message}</p>
                <button className="wp-button" onClick={map.reload}>
                  지도 다시 불러오기
                </button>
              </div>
            ) : map.loading || !map.data ? (
              <div className="pulse-loading" aria-busy="true">
                클러스터와 문서 관계를 불러오는 중입니다.
              </div>
            ) : (
              <>
                {map.data.meta.truncated && (
                  <p role="status">
                    전체 {map.data.meta.clusterCount}개 이슈 중{" "}
                    {clusters.length}
                    개를 표시합니다. 서버에서 일부 데이터만 제공했습니다.
                  </p>
                )}
                <div
                  className="explore-map-layout pulse-layout"
                  data-snapshot={map.data.meta.snapshotTs}
                  data-has-selection={Boolean(visibleSelected)}
                >
                  {filtered.length ? (
                    <PulseMap
                      scene={scene}
                      cameraState={cameraState}
                      expanded={expanded}
                      onToggleExpanded={toggleExpanded}
                      scanEnabled={scanEnabled}
                      onToggleScan={() => setScanEnabled((value) => !value)}
                      selectedKey={visibleSelected?.issueKey}
                      nodeId={nodeId}
                      meta={map.data.meta}
                      onSelect={selectCluster}
                      onNodeSelect={(issueKey, pageId) => {
                        setSelectedKey(issueKey);
                        setNodeId(pageId);
                        setNotice("");
                      }}
                    />
                  ) : (
                    <div className="pulse-empty">
                      <h2>
                        {(clusters || []).length
                          ? "일치하는 사건이 없습니다"
                          : "이 시점에 감지된 이슈가 없습니다"}
                      </h2>
                      {(clusters || []).length > 0 && (
                        <button
                          className="wp-button"
                          onClick={() => {
                            setCategory("all");
                            setQuery("");
                          }}
                        >
                          필터 초기화
                        </button>
                      )}
                    </div>
                  )}
                  {visibleSelected && (
                    <PulsePreview
                      cluster={visibleSelected}
                      meta={map.data.meta}
                      nodeId={nodeId}
                      onNodeSelect={setNodeId}
                      savedEvents={savedEvents}
                      onToggleEvent={onToggleEvent}
                      onClose={() => {
                        setSelectedKey(null);
                        setNodeId(null);
                      }}
                    />
                  )}
                </div>
                {!expanded && (
                  <div className="pulse-cluster-list" aria-label="이슈 선택">
                    {filtered.map((v) => (
                      <button
                        key={v.issueKey}
                        aria-pressed={v.issueKey === selectedKey}
                        onClick={() => selectCluster(v.issueKey)}
                      >
                        <span>{v.label}</span>
                        <SignalBadges cluster={v} meta={map.data.meta} />
                        <small>{v.memberCount}개 문서</small>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </PulseMapFrame>
        </>
      )}
    </div>
  );
}
