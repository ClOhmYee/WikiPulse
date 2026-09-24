import { useEffect, useMemo, useState } from "react";
import {
  groupIssueSnapshots,
  parseJsonLines,
  searchIssueGroups,
  snapshotsForGroup,
} from "../../data/historyPreview.js";
import "./issue-history-preview.css";

const DATA_ROOT = "/__local_issue_history_preview";
const PAGE_SIZE = 20;
const stateName = {
  DETECTED: "감지",
  VERIFYING: "분석 중",
  CONFIRMED: "확인",
};
const dateLabel = (value) =>
  `${new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value))} KST`;

async function readLocalFile(name, signal) {
  const response = await globalThis.fetch(`${DATA_ROOT}/${name}.jsonl`, { signal });
  if (!response.ok) {
    throw new Error("로컬 추출본을 찾지 못했습니다.");
  }
  return parseJsonLines(await response.text());
}

export default function IssueHistoryPreviewPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedKey, setSelectedKey] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      readLocalFile("metadata", controller.signal),
      readLocalFile("details", controller.signal),
    ]).then(
      ([metadata, details]) => setData({ metadata, details }),
      (cause) => {
        if (!controller.signal.aborted) setError(cause.message);
      },
    );
    return () => controller.abort();
  }, []);

  const groups = useMemo(
    () => groupIssueSnapshots(data?.metadata || []),
    [data],
  );
  const result = useMemo(
    () => searchIssueGroups(groups, query, offset, PAGE_SIZE),
    [groups, query, offset],
  );
  const selectedGroup = groups.find((group) => group.key === selectedKey);
  const occurrences = useMemo(
    () => selectedKey ? snapshotsForGroup(data?.metadata || [], selectedKey) : [],
    [data, selectedKey],
  );
  const selectedDetail = data?.details.find((item) => item.id === selectedId);

  return (
    <div className="wp-page history-preview-page">
      <header className="hp-header">
        <div>
          <a href="#/issues" className="hp-back">← 기존 이슈 탐색</a>
          <h1>과거 이슈 미리보기</h1>
          <p>서버에서 읽기 전용으로 추출한 로컬 사본입니다. 기존 이슈 탐색과 운영 DB는 바뀌지 않습니다.</p>
        </div>
        <span className="hp-badge">로컬 검증 전용</span>
      </header>

      {error ? (
        <div className="hp-panel" role="alert">
          <h2>로컬 데이터를 불러오지 못했습니다</h2>
          <p>{error} <code>frontend/tmp/issue-history-preview/</code>의 추출본을 확인해 주세요.</p>
        </div>
      ) : !data ? (
        <p role="status">로컬 추출본을 읽는 중입니다.</p>
      ) : (
        <>
          <p className="hp-scope">{data.metadata.length.toLocaleString("ko-KR")}개 시점 기록 · {groups.length.toLocaleString("ko-KR")}개 대표 문서 묶음 · 상세 추출 {data.details.length}건</p>
          <div className="hp-layout">
            <section className="hp-panel hp-search" aria-label="대표 문서 검색 결과">
              <label htmlFor="hp-query">대표 문서 검색</label>
              <input
                id="hp-query"
                type="search"
                value={query}
                onChange={(event) => { setQuery(event.target.value); setOffset(0); }}
                placeholder="예: The Odyssey (2026 film)"
                maxLength={200}
              />
              <p>{result.total.toLocaleString("ko-KR")}개 묶음 검색됨 · 대표 제목만 검색</p>
              {result.items.length ? (
                <div className="hp-results">
                  {result.items.map((group) => (
                    <button
                      key={group.key}
                      type="button"
                      className="hp-group"
                      aria-pressed={selectedKey === group.key}
                      onClick={() => { setSelectedKey(group.key); setSelectedId(group.latestId); }}
                    >
                      <strong>{group.label}</strong>
                      <span>{group.count}건 · {group.source === "replay" ? "과거 재구성" : "실시간"}</span>
                      <small>{dateLabel(group.firstSeen)} ~ {dateLabel(group.lastSeen)}</small>
                    </button>
                  ))}
                </div>
              ) : <p>일치하는 대표 문서가 없습니다.</p>}
              {result.total > PAGE_SIZE && (
                <div className="hp-pagination">
                  <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>이전</button>
                  <span>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(result.total / PAGE_SIZE)}</span>
                  <button type="button" disabled={offset + PAGE_SIZE >= result.total} onClick={() => setOffset(offset + PAGE_SIZE)}>다음</button>
                </div>
              )}
            </section>

            <section className="hp-panel hp-detail" aria-label="선택한 문서의 시점별 기록">
              {!selectedGroup ? (
                <p>왼쪽에서 대표 문서를 선택하면 날짜별 기록을 볼 수 있습니다.</p>
              ) : (
                <>
                  <h2>{selectedGroup.label}</h2>
                  <p>같은 대표 문서의 기록입니다. 날짜가 같더라도 동일한 현실 사건이라고 단정하지 않습니다.</p>
                  <h3>날짜별 기록</h3>
                  <div className="hp-timeline">
                    {occurrences.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        data-testid={`preview-snapshot-${item.id}`}
                        aria-pressed={selectedId === item.id}
                        onClick={() => setSelectedId(item.id)}
                      >
                        <time dateTime={item.snapshot_ts}>{dateLabel(item.snapshot_ts)}</time>
                        <span>{stateName[item.status] || item.status} · 급증 점수 {item.pulse_score.toFixed(2)}</span>
                      </button>
                    ))}
                  </div>
                  {selectedDetail ? (
                    <div className="hp-snapshot">
                      <h3>선택한 시점의 데이터</h3>
                      <p>{dateLabel(selectedDetail.snapshot_ts)} · 이슈 ID {selectedDetail.id}</p>
                      <h4>구성 문서</h4>
                      <ul>{selectedDetail.members.map((member) => <li key={member.pageId}>{member.titleKo || member.title}</li>)}</ul>
                      <h4>요약</h4>
                      <p className="hp-summary">{selectedDetail.summary || "이 시점에는 요약이 없습니다."}</p>
                      <h4>검증된 연관 종목</h4>
                      {selectedDetail.stocks.length ? (
                        <ul>{selectedDetail.stocks.map((stock) => <li key={stock.ticker}><strong>{stock.ticker}</strong> · {stock.name}{stock.rationale && <p>{stock.rationale}</p>}</li>)}</ul>
                      ) : <p>이 시점에는 검증된 종목이 없습니다.</p>}
                    </div>
                  ) : (
                    <p className="hp-missing">이 시점의 상세는 로컬에 추출하지 않았습니다. 날짜와 점수는 전체 메타데이터에서 확인할 수 있습니다.</p>
                  )}
                </>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
