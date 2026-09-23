// 표시 제목 정책 한 곳. 펄스맵과 이슈 피드·상세가 같은 규칙을 쓰게 하려고 분리했다.
//
// 🔴 영문 `title` 을 대체하지 않는다. 위키백과 링크(lib/wiki.js)·클러스터링 키·내부
//    식별자는 계속 `title` 을 쓰고, 여기서 만드는 값은 화면에 찍는 문자열뿐이다.
//
// 서버가 내리는 `titleKo` 는 ko.wikipedia 대응 제목이며 없으면 null 이거나 필드 자체가
// 없다(이슈 멤버 DTO 는 NON_NULL 이라 빠진다). 실측상 클러스터 편입 문서의 절반 가까이가
// ko 판이 없다 — 영문으로 떨어지는 것이 정상 경로다.
const usable = (value) =>
  typeof value === "string" && value.trim() ? value.trim() : null;

/**
 * 문서 한 건의 표시 제목: ko.wikipedia 정식 제목 → Azure 기계 번역 → 영문 원문.
 *
 * 🔴 두 한국어 값은 출처가 다르다. `titleKo` 는 ko.wikipedia 의 실제 문서 제목이고,
 *    `titleKoFallback` 은 기계 번역이라 정식 제목이 아니다 — 위키 링크는 어느 쪽도 쓰지
 *    않고 언제나 영문 `title` 로 만든다(lib/wiki.js).
 */
export const documentTitle = (node) =>
  usable(node?.titleKo) || usable(node?.titleKoFallback) || node?.title || "";

// 한글이 한 글자라도 있으면 "사람에게 보여줄 한국어 문구"로 본다. 음절(가–힣)뿐 아니라
// 자모 영역까지 포함한다 — "ㄱㄴ" 같은 조합 전 문자열도 한국어다.
// 🔴 "전부 한글인가"가 아니라 "한글이 섞였는가"다. 실제 이슈 제목은 "엔비디아 실적 서프라이즈"
//    처럼 라틴 문자·숫자가 섞이는 게 정상이라, 전부 검사로 만들면 멀쩡한 한국어 제목이 탈락한다.
const HANGUL = /[가-힣ᄀ-ᇿ㄰-㆏ꥠ-꥿ힰ-퟿]/;

/** 문자열에 한글이 들어 있는가. 표시 정책이 "이 label 이 한국어인가"를 판정하는 유일한 기준. */
export const hasHangul = (value) => HANGUL.test(usable(value) || "");

/**
 * 클러스터의 표시 제목.
 *
 * <pre>
 *   1. label 에 한글이 있으면          label             (= AI 가 붙인 한국어 이슈 제목)
 *   2. 아니면 root 의 titleKo           titleKo           (ko.wikipedia 정식 제목)
 *   3. 아니면 root 의 titleKoFallback   titleKoFallback   (Azure 기계 번역)
 *   4. 아니면 label                     label             (영문이라도 버리지 않는다)
 *   5. 아니면 root 의 title             title
 *   6. 아무것도 없으면                   "제목 미제공"
 *
 * ⚠️ 3번이 4번보다 위인 것은 판단이다. 둘 다 같은 사건을 가리키는데 한쪽은 한국어,
 *    한쪽은 영문이고, 이 기능의 목적이 "한국어로 보이게" 하는 것이다. 기계 번역이
 *    어색할 수 있다는 점(마이그레이션 머리말의 실측 10건)은 감수한다 — 뒤집으려면
 *    이 두 줄만 바꾸면 된다.
 * </pre>
 *
 * root/lead 는 `nodes[0]` 이다 — 조회가 `is_seed DESC, weight DESC` 로 정렬해 내려준다
 * (PulseMapRepository.findNodes / IssueQueryRepository.findMembers).
 *
 * ⚠️ ~~label 이 있으면 무조건 label~~ → 한글 판정을 앞에 뒀다 (2026-09-22, WP-205).
 *    운영 `2026-09-21T12:00:00Z` 스냅샷을 로컬에 복제해 보니 `issue_cluster.label` 이
 *    **전부 채워져 있고 값이 영문 문서명**이었다(`September 21`·`Carol Ferris`). 옛 순서로는
 *    label 이 늘 1순위라 ko 제목이 있어도 버블 제목이 영어로 남았다 — 같은 화면에서 버블은
 *    `September 21`, 그 안 노드는 `9월 21일` 로 갈렸다.
 *
 * 🔴 영문 label 을 버리지 않는다(3번). `ASML` 처럼 라틴 문자지만 그대로 써야 하는 이름이
 *    있고, 그때 titleKo 가 없으면 label 로 되돌아가야 한다. 한글 label 이 들어오면 1번에서
 *    최우선으로 잡히므로, 나중에 AI 한국어 제목이 붙어도 이 함수는 그대로 둔다.
 */
export function clusterTitle(cluster) {
  const root = cluster?.nodes?.[0] || cluster?.members?.[0];
  const label = usable(cluster?.label);
  if (hasHangul(label)) return label;
  return (
    usable(root?.titleKo) ||
    usable(root?.titleKoFallback) ||
    label ||
    root?.title ||
    "제목 미제공"
  );
}

/** 검색 색인용. 한국어로 보이는 제목을 한국어로 검색할 수 있어야 한다. */
export const searchableTitles = (node) =>
  [node?.title, usable(node?.titleKo), usable(node?.titleKoFallback)]
    .filter(Boolean)
    .join(" ");
