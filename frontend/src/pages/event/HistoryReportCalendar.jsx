import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { dataClient } from "../../data/index.js";
import { allIssueHistoryReports } from "../../data/historyProduction.js";
import { calendarDays, kstDateKey } from "../../data/historyPreview.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import { timestampLabel } from "./presentation.js";
import "../issue-history-preview/issue-history-preview.css";

const moveMonth = (month, delta) => {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1 + delta, 1))
    .toISOString()
    .slice(0, 7);
};

export default function HistoryReportCalendar({ event }) {
  const load = useCallback(
    (signal) => allIssueHistoryReports(dataClient, event.id, { signal }),
    [event.id],
  );
  const { data, loading, error, reload } = useAsyncResource(load, event.id);
  const eventDate = kstDateKey(event.snapshotTs);
  const [month, setMonth] = useState(() => eventDate.slice(0, 7));
  useEffect(() => {
    setMonth(eventDate.slice(0, 7));
  }, [eventDate]);
  useEffect(() => {
    if (data?.length && !data.some((row) => String(row.id) === event.id)) {
      setMonth(kstDateKey(data[0].snapshotTs).slice(0, 7));
    }
  }, [data, event.id]);
  const byDay = useMemo(() => {
    const days = new Map();
    for (const row of data || []) {
      const day = kstDateKey(row.snapshotTs);
      if (!days.has(day)) days.set(day, []);
      days.get(day).push(row);
    }
    return days;
  }, [data]);
  const selectedDate = data?.some((row) => String(row.id) === event.id)
    ? eventDate
    : null;
  const cells = calendarDays(month, byDay);
  const sameDay = selectedDate ? byDay.get(selectedDate) || [] : [];
  const monthLabel = `${Number(month.slice(0, 4))}년 ${Number(month.slice(5))}월`;
  const query = new URLSearchParams(
    window.location.hash.split("?")[1] || "",
  ).get("q");
  const hrefFor = (id) =>
    `#/issues/${id}${query ? `?q=${encodeURIComponent(query)}` : ""}`;

  if (error)
    return (
      <section className="hp-calendar-section" role="alert">
        <h2>날짜별 기록</h2>
        <p>
          리포트 날짜를 불러오지 못했습니다. 아래 이슈 상세는 계속 볼 수
          있습니다.
        </p>
        <button className="wp-text-button" onClick={reload}>
          날짜 다시 불러오기
        </button>
      </section>
    );
  return (
    <section
      className="hp-calendar-section"
      aria-label="날짜별 기록 달력"
      aria-busy={loading}
    >
      <div className="dt-section-heading">
        <div>
          <h2>날짜별 기록</h2>
          <p>
            같은 대표 문서의 기록입니다. DB 리포트가 있는 날짜만 선택할 수
            있습니다. 기준 시간대는 한국 시간입니다.
          </p>
        </div>
      </div>
      <div className="hp-calendar-heading">
        <button
          type="button"
          aria-label="이전 달"
          onClick={() => setMonth(moveMonth(month, -1))}
        >
          <ChevronLeft size={18} />
        </button>
        <strong>{monthLabel}</strong>
        <button
          type="button"
          aria-label="다음 달"
          onClick={() => setMonth(moveMonth(month, 1))}
        >
          <ChevronRight size={18} />
        </button>
      </div>
      {loading && <p role="status">리포트 날짜를 불러오는 중입니다.</p>}
      {!loading && data?.length === 0 && (
        <p>이 대표 문서에 저장된 리포트가 없습니다.</p>
      )}
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
              aria-label={`${Number(month.slice(5))}월 ${cell.day}일, 리포트 ${cell.count}건`}
              aria-pressed={cell.date === selectedDate}
              disabled={!cell.enabled || loading}
              onClick={() => {
                window.location.hash = hrefFor(
                  byDay.get(cell.date)[0].id,
                ).slice(1);
              }}
            >
              <span>{cell.day}</span>
              {cell.enabled && <i aria-hidden="true" />}
            </button>
          ) : (
            <span key={`blank-${index}`} aria-hidden="true" />
          ),
        )}
      </div>
      {sameDay.length > 1 && (
        <div
          className="hp-same-day"
          role="group"
          aria-label="선택한 날짜의 시각별 기록"
        >
          <strong>이 날짜의 리포트 {sameDay.length}건</strong>
          {sameDay.map((row) => (
            <a
              key={row.id}
              href={hrefFor(row.id)}
              aria-current={String(row.id) === event.id ? "page" : undefined}
            >
              {row.source === "live"
                ? "실시간 · "
                : row.source === "replay"
                  ? "과거 재구성 · "
                  : ""}
              {timestampLabel(row.snapshotTs)}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
