import { useState } from "react";
import { ChevronDown, MessageSquare, Send, ThumbsUp } from "lucide-react";
import "./discussion.css";

const MAX_LENGTH = 1000;
const sessionDiscussions = new Map();
const examples = {
  "iran-hormuz-2025": [
    "해협 문서와 석유 문서의 편집이 함께 늘었네요. 항로에 대한 설명이 바뀐 것인지, 운송량에 대한 새로운 근거가 추가된 것인지 먼저 비교해 보고 싶어요.",
    "이란 문서의 외교 관계와 호르무즈 해협의 지리 설명은 서로 다른 맥락일 수 있어요. 같은 시점의 편집이라는 이유만으로 하나의 원인으로 묶어도 될까요?",
    "에너지 기업으로 연결되는 경로가 흥미롭습니다. 원유 생산·정제·운송 중 어떤 사업 영역이 이 사건과 맞닿는지 연결 근거를 나눠 보면 좋겠어요.",
  ],
  "ai-chip-controls": [
    "수출 통제 문서에서 허가 대상과 적용 범위를 구분해서 읽어야 할 것 같아요. 반도체 문서의 어느 항목이 함께 바뀌었는지 비교해 보셨나요?",
    "기업 문서가 사건에 포함된 것과 특정 제품이 규제 대상인 것은 다른 이야기 같아요. 제품명과 적용 시점을 확인할 수 있는 근거가 필요하겠네요.",
    "설계·제조·장비 기업이 각각 다른 위치에 있네요. 관련 종목의 연결 경로를 먼저 보고 문서 변화와 대조해 보려 합니다.",
  ],
  "nuclear-energy": [
    "원자력 문서의 관심과 데이터센터 전력 수요를 연결해 읽고 있어요. 실제 발전량 변화인지, 수요 전망에 대한 서술 변화인지 나누어 보고 싶어요.",
    "우라늄 문서의 편집 내용이 연료 공급과 관련된 것인지 확인해 보셨나요? 발전 기술과 원료 조달은 참고해야 할 근거가 다를 것 같아요.",
    "전력 수요의 기간과 발전 설비의 운영 시점이 일치하는지부터 확인하면 사건의 맥락을 더 정확히 읽을 수 있겠네요.",
  ],
  "space-launch": [
    "발사체 문서의 변화가 시험 결과를 추가한 것인지, 기존 기술 설명을 정리한 것인지 구분해 보고 싶어요. 편집 전후 비교가 출발점이 되겠네요.",
    "재사용 발사체와 우주 수송 산업의 연결을 읽었습니다. 시험 단계와 상업 운영 단계의 표현을 따로 확인할 필요가 있어 보여요.",
    "관련 기업이 같은 산업에 속한다는 것과 해당 발사에 참여했다는 것은 구분해야겠네요. 연결 근거에서 직접 참여 여부를 확인하고 싶어요.",
  ],
  "battery-supply": [
    "배터리 문서와 리튬 문서의 편집이 함께 움직이네요. 소재 설명, 생산 공정, 수급 전망 중 어떤 변화가 연결된 것인지 살펴보고 싶어요.",
    "원재료에서 배터리 셀까지의 공급망을 따라가며 보고 있어요. 특정 기업 사이의 거래를 뜻하는 연결인지, 산업 분류의 연결인지 나누면 좋겠어요.",
    "리튬 이온 배터리의 기술 설명을 읽을 때 적용 분야도 함께 확인하고 싶어요. 차량용과 에너지 저장용의 맥락이 다를 수 있으니까요.",
  ],
  "cyber-security": [
    "보안 문서에서 인증과 접근 제어 설명이 바뀌었네요. 개념을 정리한 편집인지, 새로운 취약점에 대한 내용인지 먼저 구분해 보려고 합니다.",
    "클라우드 문서의 보안 책임 항목을 함께 읽으면 좋겠어요. 서비스 제공자와 이용자의 역할이 어떻게 나뉘는지 근거 문서를 비교하고 싶어요.",
    "보안 기업으로 연결되어 있지만 특정 피해 사건과의 관련성을 뜻하지는 않네요. 제품의 기능과 사건 문서의 내용을 각각 확인하는 게 도움이 되겠습니다.",
  ],
};

function seedThreads(event) {
  const reportTime = Date.parse(event.updatedAt || event.startAt);
  const startTime = Date.parse(event.startAt);
  const exampleTime = (minutes) =>
    new Date(Math.max(startTime, reportTime - minutes * 60_000)).toISOString();
  const bodies = examples[event.id] || [
    `${event.keywords?.[0] || event.title}와 연결된 문서에서 어떤 내용이 달라졌는지 살펴보고 싶어요. 편집량과 함께 편집 전후의 근거를 비교해 보셨나요?`,
    `${event.keywords?.[1] || "이 사건"}의 맥락을 이해할 때 어떤 출처를 먼저 보면 좋을까요? 같은 시점의 변화라도 서로 다른 이유가 있을 수 있겠네요.`,
    "관련 문서와 종목의 연결 경로를 비교하고 있어요. 직접적인 관계와 산업 분야의 공통점을 나누어서 읽으면 도움이 될 것 같습니다.",
  ];
  return bodies.map((body, index) => ({
    id: `${event.id}-discussion-example-${index + 1}`,
    author: `리서처 ${["A", "B", "C"][index]}`,
    body,
    createdAt: exampleTime(60 + index * 60),
    isOwn: false,
    isSeed: true,
    likes: [4, 2, 1][index],
    liked: false,
    replies:
      index === 0
        ? [
            {
              id: `${event.id}-reply-example`,
              author: "리서처 B",
              body: "근거 문서의 편집 전후와 출처를 같이 확인해 보면 좋겠어요. 이 글과 답글은 토론 기능을 보여 주는 예시입니다.",
              createdAt: exampleTime(45),
              isOwn: false,
              isSeed: true,
            },
          ]
        : [],
  }));
}

function isMessage(value) {
  return (
    value &&
    typeof value.id === "string" &&
    value.id.length <= 120 &&
    typeof value.author === "string" &&
    value.author.length <= 80 &&
    typeof value.body === "string" &&
    value.body.trim().length > 0 &&
    value.body.length <= MAX_LENGTH &&
    Number.isFinite(Date.parse(value.createdAt)) &&
    typeof value.isOwn === "boolean" &&
    typeof value.isSeed === "boolean"
  );
}

function readDiscussion(event) {
  if (sessionDiscussions.has(event.id)) return sessionDiscussions.get(event.id);
  try {
    const raw = window.localStorage.getItem(`wikipulse.discussion.${event.id}`);
    if (!raw) return { threads: seedThreads(event), notice: "" };
    const stored = JSON.parse(raw);
    if (
      stored.version !== 1 ||
      !Array.isArray(stored.threads) ||
      stored.threads.length > 200 ||
      !stored.threads.every(
        (thread) =>
          isMessage(thread) &&
          Number.isInteger(thread.likes) &&
          thread.likes >= 0 &&
          typeof thread.liked === "boolean" &&
          Array.isArray(thread.replies) &&
          thread.replies.length <= 200 &&
          thread.replies.every(isMessage),
      )
    )
      throw new Error("Invalid discussion data");
    return { threads: stored.threads, notice: "" };
  } catch {
    return {
      threads: seedThreads(event),
      notice:
        "저장된 토론을 읽을 수 없어 예시 토론으로 시작했어요. 이 화면에서는 계속 작성할 수 있습니다.",
    };
  }
}

const createId = () =>
  globalThis.crypto?.randomUUID?.() ||
  `discussion-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const displayTime = (value) =>
  new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));

function DiscussionBoard({ event }) {
  const [initial] = useState(() => readDiscussion(event));
  const [threads, setThreads] = useState(initial.threads);
  const [notice, setNotice] = useState(initial.notice);
  const [draft, setDraft] = useState("");
  const [sort, setSort] = useState("latest");
  const [openReplies, setOpenReplies] = useState([]);
  const [replyDrafts, setReplyDrafts] = useState({});
  const sorted = [...threads].sort((a, b) =>
    sort === "popular"
      ? b.likes - a.likes || Date.parse(b.createdAt) - Date.parse(a.createdAt)
      : Date.parse(b.createdAt) - Date.parse(a.createdAt),
  );

  function commit(next, successMessage) {
    setThreads(next);
    try {
      window.localStorage.setItem(
        `wikipulse.discussion.${event.id}`,
        JSON.stringify({ version: 1, threads: next }),
      );
      sessionDiscussions.set(event.id, { threads: next, notice: "" });
      setNotice(successMessage);
    } catch {
      const fallbackNotice = `${successMessage} 브라우저 저장 공간을 사용할 수 없어 새로고침하면 사라집니다.`;
      sessionDiscussions.set(event.id, {
        threads: next,
        notice:
          "브라우저 저장 공간을 사용할 수 없어 이 페이지를 새로고침하면 작성 내용이 사라집니다.",
      });
      setNotice(fallbackNotice);
    }
  }

  function submitThread(eventSubmit) {
    eventSubmit.preventDefault();
    const body = draft.trim();
    if (!body || body.length > MAX_LENGTH) {
      setNotice("공백을 제외한 토론 내용을 1~1,000자로 입력해 주세요.");
      return;
    }
    if (threads.length >= 200) {
      setNotice(
        "이 브라우저에는 사건별로 최대 200개의 토론을 보관할 수 있어요.",
      );
      return;
    }
    const thread = {
      id: createId(),
      author: "나 (데모)",
      body,
      createdAt: new Date().toISOString(),
      isOwn: true,
      isSeed: false,
      likes: 0,
      liked: false,
      replies: [],
    };
    commit(
      [thread, ...threads],
      "토론을 추가했습니다. 이 브라우저에서만 볼 수 있어요.",
    );
    setDraft("");
    setSort("latest");
  }

  function submitReply(eventSubmit, threadId) {
    eventSubmit.preventDefault();
    const body = (replyDrafts[threadId] || "").trim();
    if (!body || body.length > MAX_LENGTH) {
      setNotice("공백을 제외한 답글 내용을 1~1,000자로 입력해 주세요.");
      return;
    }
    const thread = threads.find((item) => item.id === threadId);
    if (!thread || thread.replies.length >= 200) {
      setNotice("한 토론에는 답글을 최대 200개까지 보관할 수 있어요.");
      return;
    }
    const reply = {
      id: createId(),
      author: "나 (데모)",
      body,
      createdAt: new Date().toISOString(),
      isOwn: true,
      isSeed: false,
    };
    commit(
      threads.map((item) =>
        item.id === threadId
          ? { ...item, replies: [...item.replies, reply] }
          : item,
      ),
      "답글을 추가했습니다. 이 브라우저에만 반영됩니다.",
    );
    setReplyDrafts((current) => ({ ...current, [threadId]: "" }));
  }

  function toggleLike(threadId) {
    const thread = threads.find((item) => item.id === threadId);
    commit(
      threads.map((item) =>
        item.id === threadId
          ? {
              ...item,
              liked: !item.liked,
              likes: Math.max(0, item.likes + (item.liked ? -1 : 1)),
            }
          : item,
      ),
      thread.liked
        ? "공감을 취소했습니다."
        : "공감했습니다. 이 브라우저에만 반영됩니다.",
    );
  }

  return (
    <section
      className="dc-discussion"
      aria-labelledby="event-discussion-heading"
    >
      <div className="dc-heading">
        <h2 id="event-discussion-heading">이 사건에 대한 토론</h2>
        <p>
          궁금한 점을 남기고, 문서의 변화와 연결 근거에 대한 생각을 나눠 보세요.
        </p>
      </div>
      <p className="dc-local-notice">
        <MessageSquare size={16} />
        <span>
          이 브라우저에만 저장되는 데모 토론 · 다른 사용자에게 전송되지
          않습니다.
        </span>
      </p>
      <form className="dc-compose" onSubmit={submitThread}>
        <label htmlFor="event-discussion-draft">내 의견 작성</label>
        <textarea
          id="event-discussion-draft"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={MAX_LENGTH}
          rows={4}
          placeholder="어떤 문서의 변화가 눈에 띄었나요? 확인하고 싶은 근거나 질문을 적어 주세요."
          aria-describedby="event-discussion-count"
        />
        <div className="dc-compose-actions">
          <span id="event-discussion-count">
            {draft.length.toLocaleString()} / 1,000자
          </span>
          <button
            className="wp-button"
            data-variant="primary"
            type="submit"
            disabled={!draft.trim()}
          >
            <Send size={15} />
            토론 등록
          </button>
        </div>
      </form>
      <p className="dc-status" role="status" aria-live="polite">
        {notice}
      </p>
      <div className="dc-list-heading">
        <h3>
          토론 <span>{threads.length}</span>
        </h3>
        <label>
          <span>정렬</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="토론 정렬"
          >
            <option value="latest">최신순</option>
            <option value="popular">공감순</option>
          </select>
        </label>
      </div>
      <div className="dc-threads">
        {sorted.map((thread) => {
          const expanded = openReplies.includes(thread.id);
          const replyDraft = replyDrafts[thread.id] || "";
          return (
            <article className="dc-thread" key={thread.id}>
              <div className="dc-author">
                <div
                  className="dc-avatar"
                  data-own={thread.isOwn}
                  aria-hidden="true"
                >
                  {thread.isOwn ? "나" : thread.author.slice(-1)}
                </div>
                <div>
                  <strong>{thread.author}</strong>
                  <span>
                    {thread.isSeed ? "예시 토론" : "내 브라우저"}
                    <i aria-hidden="true" />{" "}
                    <time dateTime={thread.createdAt}>
                      {displayTime(thread.createdAt)}
                    </time>
                  </span>
                </div>
              </div>
              <p className="dc-body">{thread.body}</p>
              <div className="dc-thread-actions">
                <button
                  type="button"
                  className="dc-like"
                  aria-pressed={thread.liked}
                  onClick={() => toggleLike(thread.id)}
                  aria-label={`${thread.author}의 토론 공감 ${thread.likes}개`}
                >
                  <ThumbsUp size={15} />
                  공감 <span>{thread.likes}</span>
                </button>
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={`replies-${thread.id}`}
                  onClick={() =>
                    setOpenReplies((current) =>
                      expanded
                        ? current.filter((id) => id !== thread.id)
                        : [...current, thread.id],
                    )
                  }
                >
                  <MessageSquare size={15} />
                  답글 <span>{thread.replies.length}</span>
                  <ChevronDown
                    size={14}
                    className={expanded ? "dc-chevron-expanded" : ""}
                  />
                </button>
              </div>
              <div
                id={`replies-${thread.id}`}
                className="dc-replies"
                hidden={!expanded}
              >
                {thread.replies.length > 0 && (
                  <div className="dc-reply-list">
                    {thread.replies.map((reply) => (
                      <article className="dc-reply" key={reply.id}>
                        <div className="dc-reply-author">
                          <strong>{reply.author}</strong>
                          <span>
                            {reply.isSeed ? "예시 답글" : "내 브라우저"} ·{" "}
                            <time dateTime={reply.createdAt}>
                              {displayTime(reply.createdAt)}
                            </time>
                          </span>
                        </div>
                        <p className="dc-body">{reply.body}</p>
                      </article>
                    ))}
                  </div>
                )}
                <form
                  className="dc-reply-compose"
                  onSubmit={(e) => submitReply(e, thread.id)}
                >
                  <label htmlFor={`reply-draft-${thread.id}`}>
                    {thread.author}에게 답글 작성
                  </label>
                  <textarea
                    id={`reply-draft-${thread.id}`}
                    value={replyDraft}
                    onChange={(e) =>
                      setReplyDrafts((current) => ({
                        ...current,
                        [thread.id]: e.target.value,
                      }))
                    }
                    maxLength={MAX_LENGTH}
                    rows={3}
                    placeholder="이 의견에 대한 생각이나 참고할 근거를 적어 주세요."
                  />
                  <div className="dc-compose-actions">
                    <span>{replyDraft.length.toLocaleString()} / 1,000자</span>
                    <button
                      type="submit"
                      className="wp-button"
                      disabled={!replyDraft.trim()}
                    >
                      답글 등록 <Send size={14} />
                    </button>
                  </div>
                </form>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function EventDiscussion({ event }) {
  if (!event?.id) return null;
  return <DiscussionBoard key={event.id} event={event} />;
}
