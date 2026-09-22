import test from "node:test";
import assert from "node:assert/strict";
import {
  clusterTitle,
  documentTitle,
  hasHangul,
  searchableTitles,
} from "../src/data/titles.js";
import { presentPulseMap } from "../src/data/index.js";
import { issueView, memberView } from "../src/data/resources.js";
import { wikipediaUrl } from "../src/lib/wiki.js";

const node = (overrides = {}) => ({
  pageId: "901",
  wiki: "enwiki",
  title: "Strait of Hormuz",
  titleKo: "호르무즈 해협",
  isSeed: true,
  ...overrides,
});

const mapOf = (cluster) => ({
  meta: { snapshotTs: "2026-09-20T00:00:00Z", source: "live" },
  data: {
    clusters: [
      {
        id: "42",
        issueKey: "k",
        label: null,
        nodes: [],
        edges: [],
        ...cluster,
      },
    ],
  },
});

test("문서 표시명 3단: ko.wikipedia → Azure 번역 → 영문", () => {
  const withBoth = node({ titleKoFallback: "기계 번역 호르무즈" });
  // 🔴 정식 ko 제목이 있으면 기계 번역보다 먼저다 — 출처가 다르다.
  assert.equal(documentTitle(withBoth), "호르무즈 해협");
  // ko 가 없으면 번역이 쓰인다.
  assert.equal(
    documentTitle(node({ titleKo: null, titleKoFallback: "잭슨 다트" })),
    "잭슨 다트",
  );
  // 둘 다 없으면 영문 원문.
  assert.equal(
    documentTitle(node({ titleKo: null, titleKoFallback: null })),
    "Strait of Hormuz",
  );
  // 번역이 공백뿐이면 값이 아니다.
  assert.equal(
    documentTitle(node({ titleKo: null, titleKoFallback: "  " })),
    "Strait of Hormuz",
  );
});

test("문서 표시명은 ko 제목을 쓰고, 없으면 영문으로 떨어진다", () => {
  assert.equal(documentTitle(node()), "호르무즈 해협");
  assert.equal(documentTitle(node({ titleKo: null })), "Strait of Hormuz");
  // 필드 자체가 없는 경우(구버전 백엔드·NON_NULL 직렬화)도 같은 결과여야 한다.
  assert.equal(documentTitle({ title: "Generac" }), "Generac");
  // 공백뿐인 값은 값이 아니다 — 화면에 빈 제목이 뜨면 안 된다.
  assert.equal(documentTitle(node({ titleKo: "   " })), "Strait of Hormuz");
});

test("한글 판정은 한 글자라도 섞이면 참이다", () => {
  assert.equal(hasHangul("허리케인 밀턴 관련 이슈"), true);
  // 실제 이슈 제목은 라틴 문자·숫자가 섞이는 게 정상이다 — "전부 한글"로 재면 탈락한다.
  assert.equal(hasHangul("엔비디아 GTC 2026 발표"), true);
  assert.equal(hasHangul("ㄱㄴㄷ"), true); // 자모만 있어도 한국어다
  assert.equal(hasHangul("September 21"), false);
  assert.equal(hasHangul("ASML"), false);
  assert.equal(hasHangul("Avengers: Doomsday"), false);
  // 한자·가나는 한글이 아니다 — 한국어 제목으로 오인하면 안 된다.
  assert.equal(hasHangul("東京"), false);
  assert.equal(hasHangul("ひらがな"), false);
  assert.equal(hasHangul(null), false);
  assert.equal(hasHangul("   "), false);
});

test("클러스터 표시명 우선순위: 한글 label → root ko → 영문 label → root 영문 → 안내문", () => {
  const nodes = [
    node(),
    node({ pageId: "902", title: "Iran", titleKo: "이란" }),
  ];

  // 1. label 에 한글이 있으면 최우선. 나중에 AI 한국어 제목이 붙으면 여기서 잡힌다.
  assert.equal(
    clusterTitle({ label: "호르무즈 긴장", nodes }),
    "호르무즈 긴장",
  );
  // 🔴 한글 label 은 root ko 를 이긴다 — AI 제목이 문서명보다 사건을 잘 설명한다.
  assert.equal(
    clusterTitle({ label: "허리케인 밀턴 관련 이슈", nodes }),
    "허리케인 밀턴 관련 이슈",
  );

  // 2. label 이 영문이면 root/lead 문서의 ko 제목이 이긴다 (운영 실측에서 바뀐 지점).
  assert.equal(
    clusterTitle({
      label: "September 21",
      nodes: [node({ titleKo: "9월 21일" })],
    }),
    "9월 21일",
  );
  // label 이 없을 때도 같다.
  assert.equal(clusterTitle({ label: null, nodes }), "호르무즈 해협");

  // 3. 🔴 영문 label 을 버리지 않는다. ko 가 없으면 label 로 돌아온다.
  assert.equal(
    clusterTitle({
      label: "Carol Ferris",
      nodes: [node({ title: "Carol Ferris", titleKo: null })],
    }),
    "Carol Ferris",
  );
  // 라틴 문자지만 그대로 써야 하는 이름(ASML)도 같은 경로로 유지된다.
  assert.equal(
    clusterTitle({
      label: "ASML",
      nodes: [node({ title: "ASML Holding", titleKo: null })],
    }),
    "ASML",
  );

  // 4. label 도 ko 도 없으면 root/lead 문서의 영문 제목.
  assert.equal(
    clusterTitle({ label: null, nodes: [node({ titleKo: null })] }),
    "Strait of Hormuz",
  );

  // 5. 문서조차 없으면 안내문.
  assert.equal(clusterTitle({ label: null, nodes: [] }), "제목 미제공");
  assert.equal(clusterTitle({}), "제목 미제공");
});

test("클러스터 제목도 번역 폴백을 쓰되 정식 ko 제목이 먼저다", () => {
  const root = (over) => ({
    nodes: [{ pageId: "1", wiki: "enwiki", ...over }],
  });
  // 영문 label + 정식 ko 없음 + 번역 있음 → 번역이 영문 label 을 이긴다.
  assert.equal(
    clusterTitle({
      label: "Jaxson Dart",
      ...root({
        title: "Jaxson Dart",
        titleKo: null,
        titleKoFallback: "잭슨 다트",
      }),
    }),
    "잭슨 다트",
  );
  // 정식 ko 가 있으면 번역은 쓰이지 않는다.
  assert.equal(
    clusterTitle({
      label: "September 21",
      ...root({
        title: "September 21",
        titleKo: "9월 21일",
        titleKoFallback: "구월 이십일일",
      }),
    }),
    "9월 21일",
  );
  // 한글 label 은 여전히 최우선 — AI 제목이 붙으면 그게 이긴다.
  assert.equal(
    clusterTitle({
      label: "다트 이적 이슈",
      ...root({
        title: "Jaxson Dart",
        titleKo: null,
        titleKoFallback: "잭슨 다트",
      }),
    }),
    "다트 이적 이슈",
  );
  // 번역도 없으면 영문 label 로 돌아온다.
  assert.equal(
    clusterTitle({
      label: "Carol Ferris",
      ...root({ title: "Carol Ferris", titleKo: null, titleKoFallback: null }),
    }),
    "Carol Ferris",
  );
});

test("검색 색인에 기계 번역도 들어간다", () => {
  const haystack = searchableTitles(
    node({ titleKo: null, titleKoFallback: "잭슨 다트" }),
  );
  assert.ok(
    haystack.includes("잭슨 다트"),
    "번역으로 보이면 번역으로도 찾아야 한다",
  );
  assert.ok(haystack.includes("Strait of Hormuz"), "영문 원문도 계속 색인한다");
});

test("지시받은 다섯 케이스", () => {
  const root = (over) => ({
    nodes: [{ pageId: "1", wiki: "enwiki", ...over }],
  });
  assert.equal(
    clusterTitle({
      label: "September 21",
      ...root({ title: "September 21", titleKo: "9월 21일" }),
    }),
    "9월 21일",
  );
  assert.equal(
    clusterTitle({
      label: "Carol Ferris",
      ...root({ title: "Carol Ferris", titleKo: null }),
    }),
    "Carol Ferris",
  );
  assert.equal(
    clusterTitle({
      label: "허리케인 밀턴 관련 이슈",
      ...root({ title: "Hurricane Milton", titleKo: "허리케인 밀턴" }),
    }),
    "허리케인 밀턴 관련 이슈",
  );
  assert.equal(
    clusterTitle({
      label: null,
      ...root({ title: "Bitcoin", titleKo: "비트코인" }),
    }),
    "비트코인",
  );
  assert.equal(
    clusterTitle({ label: null, ...root({ title: "Bitcoin", titleKo: null }) }),
    "Bitcoin",
  );
});

test("클러스터 표시명은 두 번째 문서의 ko 로 새지 않는다", () => {
  // root 에 ko 가 없다고 다음 문서 이름을 갖다 쓰면 다른 사건 제목이 붙는다.
  const nodes = [
    node({ titleKo: null }),
    node({ pageId: "902", title: "Iran", titleKo: "이란" }),
  ];
  assert.equal(clusterTitle({ label: null, nodes }), "Strait of Hormuz");
});

test("펄스맵 표현은 영문 title 을 보존한 채 표시명만 덧붙인다", () => {
  const withKo = node();
  const withoutKo = node({ pageId: "902", title: "Generac", titleKo: null });
  const result = presentPulseMap(mapOf({ nodes: [withKo, withoutKo] }), "mock");
  const [first, second] = result.data.clusters[0].nodes;

  assert.equal(first.displayTitle, "호르무즈 해협");
  assert.equal(second.displayTitle, "Generac");

  // 🔴 이 변경의 금지선. title 은 위키 링크·클러스터링 키·식별자다.
  assert.equal(first.title, "Strait of Hormuz");
  assert.equal(second.title, "Generac");
  assert.equal(first.titleKo, "호르무즈 해협");

  // 클러스터 제목도 root ko 로 선다.
  assert.equal(result.data.clusters[0].label, "호르무즈 해협");
});

test("위키백과 링크는 한국어 표시명이 붙어도 영문 문서로 간다", () => {
  const member = memberView(
    {
      pageId: 901,
      wiki: "enwiki",
      title: "Strait of Hormuz",
      titleKo: "호르무즈 해협",
    },
    42,
  );
  assert.equal(member.displayTitle, "호르무즈 해협");
  assert.equal(member.name, "호르무즈 해협");
  assert.equal(member.title, "Strait of Hormuz");
  assert.equal(
    wikipediaUrl(member),
    "https://en.wikipedia.org/wiki/Strait_of_Hormuz",
  );

  // 🔴 기계 번역만 있는 문서도 링크는 영문이어야 한다 — 번역은 실제 ko.wikipedia
  //    문서 제목이 아니라서, 이 값으로 링크를 만들면 없는 문서로 보낸다.
  const translated = memberView(
    {
      pageId: 902,
      wiki: "enwiki",
      title: "Jaxson Dart",
      titleKo: null,
      titleKoFallback: "잭슨 다트",
    },
    42,
  );
  assert.equal(translated.displayTitle, "잭슨 다트");
  assert.equal(translated.title, "Jaxson Dart");
  assert.equal(
    wikipediaUrl(translated),
    "https://en.wikipedia.org/wiki/Jaxson_Dart",
  );
});

test("이슈 상세도 펄스맵과 같은 규칙으로 제목을 만든다", () => {
  const members = [
    {
      pageId: 901,
      wiki: "enwiki",
      title: "Strait of Hormuz",
      titleKo: "호르무즈 해협",
    },
    { pageId: 902, wiki: "enwiki", title: "Iran", titleKo: null },
  ];
  const base = {
    id: 42,
    pulseScore: 1,
    status: "DETECTED",
    source: "live",
    snapshotTs: "2026-09-20T00:00:00Z",
    members,
  };

  assert.equal(issueView({ ...base, label: null }).title, "호르무즈 해협");
  assert.equal(
    issueView({ ...base, label: "호르무즈 긴장" }).title,
    "호르무즈 긴장",
  );
  assert.equal(
    issueView({ ...base, label: null, members: [members[1]] }).title,
    "Iran",
  );
  assert.equal(
    issueView({ ...base, label: null, members: [] }).title,
    "제목 미제공",
  );

  // 멤버 목록도 한국어/영문이 섞여 내려간다 — 없는 쪽이 결함이 아니다.
  const view = issueView({ ...base, label: null });
  assert.deepEqual(
    view.members.map((v) => v.displayTitle),
    ["호르무즈 해협", "Iran"],
  );
  assert.deepEqual(
    view.members.map((v) => v.title),
    ["Strait of Hormuz", "Iran"],
  );
});

test("검색 색인은 한국어와 영문을 모두 담는다", () => {
  const haystack = searchableTitles(node()).toLowerCase();
  assert.ok(
    haystack.includes("호르무즈"),
    "한국어로 보이면 한국어로 찾을 수 있어야 한다",
  );
  assert.ok(
    haystack.includes("strait of hormuz"),
    "영문 원문도 계속 찾을 수 있어야 한다",
  );

  // ko 가 없으면 영문만 담긴다 — undefined 가 색인에 섞이지 않는다.
  assert.equal(searchableTitles(node({ titleKo: null })), "Strait of Hormuz");
});
