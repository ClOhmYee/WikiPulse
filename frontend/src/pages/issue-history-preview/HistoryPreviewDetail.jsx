import { useMemo, useState } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { IssueReport } from "../../components/event/IssueReport.jsx";
import { IssueSummary } from "../../components/event/IssueSummary.jsx";
import { IssueState } from "../../components/event/IssueState.jsx";
import {
  calendarDays,
  kstDateKey,
  preferredSnapshot,
  snapshotsByKstDay,
  snapshotsForGroup,
} from "../../data/historyPreview.js";
import { metricLabel, timestampLabel } from "../event/presentation.js";

function moveMonth(month, delta) {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1 + delta, 1))
    .toISOString()
    .slice(0, 7);
}

function HistoryCalendar({ month, onMonth, byDay, selectedDate, onSelect }) {
  const cells = calendarDays(month, byDay);
  const monthLabel = `${Number(month.slice(0, 4))}년 ${Number(month.slice(5))}월`;
  return (
    <section className="hp-calendar-section" aria-label="날짜별 기록 달력">
      <div className="dt-section-heading">
        <div>
          <h2>날짜별 기록</h2>
          <p>
            기록이 있는 날짜만 선택할 수 있습니다. 기준 시간대는 한국
            시간입니다.
          </p>
        </div>
      </div>
      <div className="hp-calendar-heading">
        <button
          type="button"
          aria-label="이전 달"
          onClick={() => onMonth(moveMonth(month, -1))}
        >
          <ChevronLeft size={18} />
        </button>
        <strong>{monthLabel}</strong>
        <button
          type="button"
          aria-label="다음 달"
          onClick={() => onMonth(moveMonth(month, 1))}
        >
          <ChevronRight size={18} />
        </button>
      </div>
      <div className="hp-calendar-grid" role="group" aria-label={monthLabel}>
        {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
          <span key={day} className="hp-weekday">
            {day}
          </span>
        ))}
        {cells.map((cell, index) =>
          cell ? (
            <button
              type="button"
              key={cell.date}
              data-testid={`calendar-day-${cell.date}`}
              aria-label={`${Number(month.slice(5))}월 ${cell.day}일, 기록 ${cell.count}건`}
              aria-pressed={cell.date === selectedDate}
              disabled={!cell.enabled}
              onClick={() => onSelect(cell.date)}
            >
              <span>{cell.day}</span>
              {cell.enabled && <i aria-hidden="true" />}
            </button>
          ) : (
            <span key={`blank-${index}`} aria-hidden="true" />
          ),
        )}
      </div>
    </section>
  );
}

function DateReport({ selected, report, detail }) {
  if (!report)
    return (
      <section className="dt-report hp-no-report" aria-label="리포트">
        <h2>리포트</h2>
        <p>이 날짜의 DB 리포트가 없습니다.</p>
        <p>다른 날짜의 내용을 이 날짜에 소급하여 표시하지 않습니다.</p>
      </section>
    );
  if (report.sections?.length) {
    const articles = (detail?.members || []).map((member) => ({
      id: member.pageId,
      name: member.titleKo || member.title,
      title: member.title,
      wiki: member.wiki,
    }));
    return (
      <IssueReport
        report={{
          status: "ready",
          sections: report.sections,
          model: report.model,
          generatedAt: report.generated_at,
          snapshotTs: selected.snapshot_ts,
        }}
        summary={report.summary}
        articles={articles}
      />
    );
  }
  return (
    <section className="dt-report" aria-label="리포트">
      <div className="dt-report-heading">
        <h2>리포트</h2>
      </div>
      <IssueSummary summary={report.summary} />
      <div className="dt-report-state" role="status">
        <div>
          <h3>본문 리포트는 저장되지 않았습니다</h3>
          <p>DB에 있는 요약만 표시합니다.</p>
        </div>
      </div>
      <dl className="dt-report-meta">
        <div>
          <dt>기준 시각</dt>
          <dd>{timestampLabel(selected.snapshot_ts)}</dd>
        </div>
        <div>
          <dt>생성 시각</dt>
          <dd>{timestampLabel(report.generated_at)}</dd>
        </div>
        <div>
          <dt>생성 정보</dt>
          <dd>{report.model || "미제공"}</dd>
        </div>
      </dl>
    </section>
  );
}

export default function HistoryPreviewDetail({ group, data }) {
  const occurrences = useMemo(
    () => snapshotsForGroup(data.metadata, group.key),
    [data, group.key],
  );
  const byDay = useMemo(() => snapshotsByKstDay(occurrences), [occurrences]);
  const reportById = useMemo(
    () => new Map(data.reports.map((report) => [report.id, report])),
    [data],
  );
  const detailById = useMemo(
    () => new Map(data.details.map((detail) => [detail.id, detail])),
    [data],
  );
  const [selectedId, setSelectedId] = useState(
    () => preferredSnapshot(occurrences, data.reports)?.id,
  );
  const selected =
    occurrences.find((row) => row.id === selectedId) || occurrences[0];
  const selectedDate = kstDateKey(selected.snapshot_ts);
  const [month, setMonth] = useState(() => selectedDate.slice(0, 7));
  const [tab, setTab] = useState("report");
  const detail = detailById.get(selected.id);
  const report = reportById.get(selected.id);
  const sameDay = byDay.get(selectedDate) || [];
  const backQuery = new URLSearchParams(
    window.location.hash.split("?")[1] || "",
  ).get("q");
  const backHref = `#/issue-history-preview${backQuery ? `?q=${encodeURIComponent(backQuery)}` : ""}`;

  return (
    <div className="wp-page dt-page history-preview-detail">
      <a href={backHref} className="dt-back">
        <ArrowLeft size={16} />
        이슈 탐색
      </a>
      <header className="dt-event-header">
        <div>
          <h1>{group.label}</h1>
          <div className="dt-meta">
            <time dateTime={selected.snapshot_ts}>
              {timestampLabel(selected.snapshot_ts)} 기준
            </time>
            <IssueState status={selected.status} />
            <span>{group.source === "replay" ? "과거 재구성" : "실시간"}</span>
          </div>
        </div>
        <span className="hp-local-label">로컬 검증 전용</span>
      </header>
      <p className="hp-detail-scope">
        같은 대표 문서의 날짜별 기록입니다. 날짜가 같거나 제목이 같아도 현실의
        동일 사건이라고 단정하지 않습니다.
      </p>
      <div className="dt-event-metrics" aria-label="이슈 데이터 요약">
        <div>
          <span>이슈 편집량</span>
          <strong>
            {metricLabel(
              detail?.members.reduce(
                (sum, member) => sum + (member.editCount || 0),
                0,
              ),
            )}
          </strong>
        </div>
        <div>
          <span>급증 점수</span>
          <strong className="dt-teal">
            {metricLabel(selected.pulse_score)}
          </strong>
        </div>
        <div>
          <span>함께 움직인 문서</span>
          <strong>{detail?.members.length ?? "미제공"}</strong>
        </div>
        <div>
          <span>검증된 연관 종목</span>
          <strong>{detail?.stocks.length ?? "미제공"}</strong>
        </div>
      </div>
      <HistoryCalendar
        month={month}
        onMonth={setMonth}
        byDay={byDay}
        selectedDate={selectedDate}
        onSelect={(date) => {
          const row = preferredSnapshot(byDay.get(date), data.reports);
          setSelectedId(row.id);
          setTab("report");
        }}
      />
      {sameDay.length > 1 && (
        <div
          className="hp-same-day"
          role="group"
          aria-label="선택한 날짜의 시각별 기록"
        >
          <strong>이 날짜의 기록 {sameDay.length}건</strong>
          {sameDay.map((row) => (
            <button
              key={row.id}
              type="button"
              aria-pressed={row.id === selectedId}
              onClick={() => setSelectedId(row.id)}
            >
              {timestampLabel(row.snapshot_ts)}
            </button>
          ))}
        </div>
      )}
      <nav className="dt-tabs" role="tablist" aria-label="이벤트 상세 보기">
        {[
          ["report", "리포트"],
          ["evidence", "근거 문서"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
          >
            {label}
            {id === "evidence" && <span>{detail?.members.length ?? "—"}</span>}
          </button>
        ))}
      </nav>
      <div className="dt-content-layout">
        <div className="dt-primary" role="tabpanel">
          {tab === "report" ? (
            <DateReport selected={selected} report={report} detail={detail} />
          ) : (
            <section className="hp-evidence">
              <h2>이 시점의 구성 문서</h2>
              {detail ? (
                <ul>
                  {detail.members.map((member) => (
                    <li key={member.pageId}>
                      <strong>{member.titleKo || member.title}</strong>
                      <span>
                        편집 {metricLabel(member.editCount, 0)}회 · 조회{" "}
                        {metricLabel(member.views, 0)}회
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>이 시점의 문서 상세는 로컬에 추출되지 않았습니다.</p>
              )}
            </section>
          )}
        </div>
        <aside className="dt-sidebar" aria-label="이벤트 참고 정보">
          <section className="dt-stock-preview">
            <div className="dt-section-heading">
              <h2>연관 주식</h2>
            </div>
            <p className="dt-sidebar-intro">
              선택한 시점에 검증된 종목만 표시합니다.
            </p>
            {detail?.stocks.length ? (
              <div className="dt-stock-links">
                {detail.stocks.map((stock) => (
                  <div key={stock.ticker} className="hp-stock">
                    <span className="dt-stock-symbol">{stock.ticker}</span>
                    <span>
                      <strong>{stock.name}</strong>
                      {stock.rationale && <small>{stock.rationale}</small>}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="wp-muted">
                {detail
                  ? "이 시점에는 검증된 종목이 없습니다."
                  : "이 시점의 종목 상세는 로컬에 추출되지 않았습니다."}
              </p>
            )}
            <p className="dt-footnote">
              연결은 탐색을 위한 가설이며 투자 권유가 아닙니다.
            </p>
          </section>
          <section className="dt-context-note">
            <h2>기록을 읽는 방법</h2>
            <p>
              달력은 DB에 기록된 시점만 활성화합니다. 리포트가 없는 날짜에 다른
              시점의 요약을 대신 표시하지 않습니다.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
