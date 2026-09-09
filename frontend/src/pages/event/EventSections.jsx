import { useState } from "react";
import {
  ArrowUpRight,
  ChevronRight,
  ExternalLink,
  FileText,
  Info,
  Search,
} from "lucide-react";
import { formatNumber } from "../../lib/format";
import { EmptyState } from "../../components/ui/EmptyState";
import { wikipediaUrl } from "../../lib/wiki";
const newsTypes = [
  { id: "all", label: "전체" },
  { id: "news", label: "뉴스" },
  { id: "official", label: "공식 자료" },
  { id: "analysis", label: "분석" },
];
const kindNames = { signal: "편집 신호", news: "관련 소식", context: "배경" };
const newsNames = {
  news: "뉴스 예시",
  official: "공식 자료 예시",
  analysis: "분석 예시",
};
const formatDate = (value) =>
  value
    ? String(value).replace("T", " ").replace(/Z$/, "").slice(0, 16)
    : "날짜 미제공";

export function Timeline({ entries, articles = [], compact = false }) {
  if (!entries.length)
    return (
      <EmptyState
        title="아직 등록된 흐름이 없어요"
        description="이 이벤트의 타임라인 예시가 준비되면 이곳에서 확인할 수 있어요."
      />
    );
  return (
    <ol className={`dt-timeline ${compact ? "dt-timeline--compact" : ""}`}>
      {entries.map((entry) => (
        <li key={entry.id}>
          <div
            className="dt-timeline-marker"
            data-kind={entry.kind}
            aria-hidden="true"
          />
          <div className="dt-timeline-content">
            <div className="dt-meta">
              <span className="dt-kind" data-kind={entry.kind}>
                {kindNames[entry.kind] || "기록"}
              </span>
              <time>{formatDate(entry.time)}</time>
            </div>
            <h3>{entry.title}</h3>
            <p>{entry.body}</p>
            {articles.some((article) => article.id === entry.entityId) && (
              <a
                className="dt-text-link"
                href={wikipediaUrl(
                  articles.find((article) => article.id === entry.entityId),
                )}
                target="_blank"
                rel="noreferrer"
              >
                위키백과 원문 보기 <ArrowUpRight size={14} />
                <span className="dt-sr-only"> (새 탭)</span>
              </a>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function EventNews({ items, isExample }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const filtered = items.filter(
    (item) =>
      (filter === "all" || item.type === filter) &&
      `${item.title} ${item.source} ${item.summary}`
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase()),
  );
  return (
    <section aria-label="관련 소식 목록">
      <div className="dt-section-intro">
        <h2>이벤트를 이해하는 다른 시선</h2>
        <p>
          이벤트와 함께 읽을 소식과 참고 자료를 모았어요.{" "}
          {isExample
            ? "아래 목록은 화면 구성을 위한 예시입니다."
            : "각 소식의 출처와 기준 시각을 확인해 주세요."}
        </p>
      </div>
      <div className="dt-news-toolbar">
        <div className="dt-chip-group" role="group" aria-label="소식 유형">
          {newsTypes.map((type) => (
            <button
              type="button"
              key={type.id}
              className="wp-chip"
              data-active={filter === type.id}
              aria-pressed={filter === type.id}
              onClick={() => setFilter(type.id)}
            >
              {type.label}
              <span>
                {type.id === "all"
                  ? items.length
                  : items.filter((item) => item.type === type.id).length}
              </span>
            </button>
          ))}
        </div>
        <label className="dt-search">
          <Search size={17} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="제목·출처 검색"
            aria-label="관련 소식 검색"
          />
        </label>
      </div>
      <p className="dt-result-count" aria-live="polite">
        {filtered.length}개의 소식
      </p>
      {filtered.length ? (
        <div className="dt-news-list">
          {filtered.map((item) => (
            <article className="dt-news-item" key={item.id}>
              <div className="dt-meta">
                <span>{item.source}</span>
                <span>
                  {isExample
                    ? newsNames[item.type] || "자료 예시"
                    : newsTypes.find((type) => type.id === item.type)?.label ||
                      "자료"}
                </span>
                <time>{formatDate(item.publishedAt)}</time>
              </div>
              <h3>{item.title}</h3>
              <p>{item.summary}</p>
              {item.url && (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="dt-text-link"
                >
                  참고 출처 방문 <ExternalLink size={14} />
                  <span className="dt-sr-only"> (새 탭)</span>
                </a>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="조건에 맞는 소식이 없어요"
          description="검색어를 바꾸거나 전체 유형에서 다시 찾아보세요."
          action={
            <button
              className="wp-button"
              onClick={() => {
                setFilter("all");
                setQuery("");
              }}
            >
              검색 조건 초기화
            </button>
          }
        />
      )}
      <p className="dt-footnote">
        <Info size={15} />
        {isExample
          ? "소식은 가상 예시이며, 링크는 주제를 이해하기 위한 참고 문서입니다."
          : "제공된 소식과 연결된 원문의 내용을 함께 확인해 주세요."}
      </p>
    </section>
  );
}

export function Evidence({ articles, isExample }) {
  return (
    <section aria-label="이벤트 근거 문서">
      <div className="dt-section-intro">
        <h2>변화가 시작된 문서들</h2>
        <p>
          어떤 문서가 함께 바뀌었는지 확인하고, 위키백과 원문을 새 탭에서
          읽어보세요.
        </p>
      </div>
      {articles.length ? (
        <div className="dt-evidence-list">
          {articles.map((article) => (
            <a
              className="dt-evidence-row"
              href={wikipediaUrl(article)}
              target="_blank"
              rel="noreferrer"
              key={article.id}
            >
              <div className="dt-doc-icon">
                <FileText size={21} />
              </div>
              <div className="dt-evidence-copy">
                <h3>{article.name}</h3>
                <span>{article.title.replaceAll("_", " ")}</span>
                <p>{article.description}</p>
              </div>
              <div className="dt-evidence-numbers">
                <strong>
                  {formatNumber(article.edits)}
                  <small>회 편집</small>
                </strong>
                <span>평소 대비 {article.pulse}배</span>
              </div>
              <ChevronRight size={19} />
              <span className="dt-sr-only">위키백과 원문 (새 탭)</span>
            </a>
          ))}
        </div>
      ) : (
        <EmptyState
          title="연결된 문서가 없어요"
          description="다른 이벤트에서 편집 신호와 근거 문서를 살펴보세요."
        />
      )}
      <div className="dt-method">
        <h3>
          <Info size={18} />이 수치는 어떻게 읽나요?
        </h3>
        <p>
          편집량은 기준일에 문서가 수정된 횟수이고, 평소 대비 수치는 기준일
          편집량을 {isExample ? "예시 기준 편집량" : "기준 편집량"}과 비교한
          값입니다. 차트 기간을 바꾸어도 이 기준은 유지됩니다.
        </p>
        <p>
          {isExample
            ? "편집량, 연결 관계, 편집 내역은 모두 목데이터입니다."
            : "편집량, 연결 관계, 편집 내역의 출처를 확인해 주세요."}{" "}
          편집량만으로 사건의 중요도나 내용의 정확성을 판단할 수는 없습니다.
        </p>
      </div>
    </section>
  );
}
