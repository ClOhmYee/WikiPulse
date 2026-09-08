/**
 * WikiPulse frontend fixtures.
 * Every metric, timeline entry, revision, headline and price in this file is
 * synthetic. Reference links explain a topic; they do not substantiate fixtures.
 * No network, clock, randomness, backend or real personal data is required.
 */
export const DEMO_DATE = "2025-06-24";
export const DEMO_NOTICE =
  "2025.06.24 기준의 가상 데이터입니다. 편집·뉴스·가격과 연결 관계는 화면 체험을 위한 예시입니다.";

export const categories = [
  { id: "geopolitics", label: "국제 정세", color: "#edb778" },
  { id: "technology", label: "AI · 반도체", color: "#96ade7" },
  { id: "energy", label: "에너지", color: "#a6bd8c" },
  { id: "space", label: "우주 · 항공", color: "#b09cd4" },
  { id: "materials", label: "배터리 · 소재", color: "#d5a7bc" },
  { id: "security", label: "사이버 보안", color: "#83bcb9" },
];

const wiki = (title) =>
  `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replaceAll(" ", "_"))}`;
const day = (value) => `2025-06-${String(value).padStart(2, "0")}`;
const at = (value, time = "12:00") => `${day(value)}T${time}:00+09:00`;
const roundPulse = (edits, baseline) =>
  Math.round((edits / baseline) * 10) / 10;

// Profiles contain fixed multipliers, including rising, steady and cooling arcs.
const profiles = {
  rising: [
    0.13, 0.15, 0.12, 0.16, 0.14, 0.15, 0.13, 0.17, 0.14, 0.16, 0.19, 0.16, 0.2,
    0.24, 0.21, 0.3, 0.35, 0.39, 0.43, 0.54, 0.66, 0.74, 0.86, 1,
  ],
  sustained: [
    0.2, 0.18, 0.24, 0.23, 0.21, 0.25, 0.2, 0.26, 0.28, 0.3, 0.32, 0.38, 0.49,
    0.56, 0.7, 0.85, 0.94, 1.08, 0.98, 1.06, 1.04, 0.97, 1.02, 1,
  ],
  cooling: [
    0.3, 0.28, 0.34, 0.31, 0.29, 0.34, 0.3, 0.36, 0.42, 0.4, 0.52, 0.63, 0.72,
    0.98, 1.25, 1.55, 1.82, 1.68, 1.54, 1.42, 1.31, 1.2, 1.09, 1,
  ],
};

function makeActivityChart({
  edits,
  baseline,
  pageviews,
  profile = "rising",
  seed = 0,
}) {
  return profiles[profile].map((weight, index) => {
    const isLast = index === 23;
    const variation = 1 + ((((index + seed) * 7) % 9) - 4) * 0.025;
    return {
      date: day(index + 1),
      edits: isLast
        ? edits
        : Math.max(1, Math.round(edits * weight * variation)),
      baseline,
      pageviews: isLast
        ? pageviews
        : Math.round(pageviews * (0.22 + weight * 0.78) * variation),
    };
  });
}

function revisions(entityId, section, entries) {
  return entries.map(([time, before, after, summary, delta], index) => ({
    id: `${entityId}-revision-${index + 1}`,
    time: at(24, time),
    editor: `DemoEditor-${String(index + 1).padStart(2, "0")}`,
    section,
    before,
    after,
    summary,
    delta,
  }));
}

const entityFixtures = [
  {
    id: "strait-of-hormuz",
    title: "Strait of Hormuz",
    name: "호르무즈 해협",
    category: "geopolitics",
    description:
      "페르시아만과 오만만을 잇는 해상 통로. 에너지 운송과 주변 지역 문서의 변화를 함께 살펴봅니다.",
    edits: 412,
    baseline: 34,
    editors: 86,
    pageviews: 184260,
    eventIds: ["iran-hormuz-2025"],
    relatedIds: ["iran", "petroleum"],
    changes: revisions("strait-of-hormuz", "Strategic importance", [
      [
        "11:42",
        "해협은 주요 원유 수송로로 설명된다.",
        "해협의 원유 수송 역할과 인접 항로에 관한 설명이 별도 문단으로 정리되었다.",
        "에너지 운송 설명을 세분화한 편집 예시",
        684,
      ],
      [
        "10:18",
        "항로 관련 설명이 역사 문단에 포함되어 있다.",
        "항로 관련 내용을 지리 문단으로 이동하고 관련 문서 링크를 추가했다.",
        "항로 문단 이동 및 내부 링크 보강 예시",
        238,
      ],
      [
        "09:06",
        "주변 해역에 대한 짧은 설명.",
        "주변 해역 설명의 중복된 두 문장을 하나로 합쳤다.",
        "중복 설명 정리 예시",
        -124,
      ],
    ]),
  },
  {
    id: "iran",
    title: "Iran",
    name: "이란",
    category: "geopolitics",
    description:
      "중동의 국가 문서. 외교·지리·에너지 항목이 호르무즈 해협과 연결되는 맥락을 제공합니다.",
    edits: 248,
    baseline: 31,
    editors: 63,
    pageviews: 228410,
    eventIds: ["iran-hormuz-2025"],
    relatedIds: ["strait-of-hormuz", "petroleum"],
    changes: revisions("iran", "Foreign relations", [
      [
        "11:29",
        "주변국과의 관계가 한 문단에 요약되어 있다.",
        "지역별 외교 관계 설명을 나누고 해상 교역 문서 링크를 추가했다.",
        "외교 관계 문단 구조 변경 예시",
        452,
      ],
      [
        "10:03",
        "에너지 산업 설명의 출처 표기가 하나로 묶여 있다.",
        "에너지 산업 각 문장 뒤에 출처 표기 위치를 나누었다.",
        "문장별 출처 표기 정리 예시",
        172,
      ],
      [
        "08:45",
        "경제 문단에 유사한 문장 두 개가 있다.",
        "의미가 겹치는 문장을 제거하고 표현을 간결하게 다듬었다.",
        "경제 문단 중복 제거 예시",
        -89,
      ],
    ]),
  },
  {
    id: "petroleum",
    title: "Petroleum",
    name: "석유",
    category: "energy",
    description:
      "원유 생산과 정제, 운송을 다루는 문서. 지정학 이슈가 에너지 산업으로 이어지는 탐색 지점입니다.",
    edits: 164,
    baseline: 33,
    editors: 41,
    pageviews: 89160,
    eventIds: ["iran-hormuz-2025"],
    relatedIds: ["strait-of-hormuz", "iran", "nuclear-power"],
    changes: revisions("petroleum", "Transportation", [
      [
        "11:08",
        "원유는 여러 운송 수단으로 이동한다.",
        "원유의 해상·육상 운송을 구분하고 주요 해상 통로 문서로 연결했다.",
        "운송 경로 설명 확장 예시",
        366,
      ],
      [
        "09:34",
        "공급망 문단에 운송과 저장 설명이 혼재한다.",
        "운송과 저장 설명을 각각의 소제목 아래 정리했다.",
        "공급망 항목 재구성 예시",
        209,
      ],
      [
        "08:20",
        "정제 과정의 용어가 문단마다 다르게 쓰인다.",
        "같은 정제 공정의 용어를 일관되게 맞췄다.",
        "정제 용어 일관성 수정 예시",
        -46,
      ],
    ]),
  },
  {
    id: "semiconductor",
    title: "Semiconductor",
    name: "반도체",
    category: "technology",
    description:
      "반도체의 원리와 응용을 다루는 문서. AI 연산 수요와 장비·수출 규제 문서를 잇습니다.",
    edits: 286,
    baseline: 49,
    editors: 72,
    pageviews: 132640,
    eventIds: ["ai-chip-controls"],
    relatedIds: ["nvidia", "export-control", "cloud-computing"],
    changes: revisions("semiconductor", "Applications", [
      [
        "11:38",
        "응용 분야에 컴퓨팅과 통신이 나열되어 있다.",
        "AI 연산용 반도체의 응용을 설명하고 관련 가속기 문서 링크를 추가했다.",
        "AI 연산 응용 문단 보강 예시",
        517,
      ],
      [
        "10:12",
        "제조 공정과 설계 설명이 이어져 있다.",
        "설계와 제조 공정을 분리하고 두 단계의 관계를 정리했다.",
        "제조·설계 설명 구조화 예시",
        282,
      ],
      [
        "08:56",
        "용어 설명에 중복된 영문 약어가 있다.",
        "처음 등장하는 위치에 약어 풀이를 모으고 중복을 제거했다.",
        "용어 풀이 정리 예시",
        -71,
      ],
    ]),
  },
  {
    id: "nvidia",
    title: "Nvidia",
    name: "엔비디아",
    category: "technology",
    description:
      "GPU와 가속 컴퓨팅 관련 기업 문서. 제품 설명과 산업 환경의 편집 흐름을 살펴봅니다.",
    edits: 194,
    baseline: 36,
    editors: 54,
    pageviews: 174820,
    eventIds: ["ai-chip-controls"],
    relatedIds: ["semiconductor", "export-control", "cloud-computing"],
    changes: revisions("nvidia", "Products", [
      [
        "11:21",
        "데이터센터 제품이 세대별로 나열되어 있다.",
        "데이터센터 제품의 용도와 제품군을 표로 구분했다.",
        "가속기 제품군 설명 보강 예시",
        431,
      ],
      [
        "09:47",
        "사업 환경에 관한 설명이 짧게 제시된다.",
        "수출 규제라는 일반 개념과 관련 문서 링크를 추가했다.",
        "사업 환경의 맥락 링크 추가 예시",
        254,
      ],
      [
        "08:32",
        "동일한 제품 설명이 두 소제목에서 반복된다.",
        "중복 제품 설명을 한 소제목으로 합쳤다.",
        "제품 설명 중복 제거 예시",
        -98,
      ],
    ]),
  },
  {
    id: "export-control",
    title: "Export control",
    name: "수출 통제",
    category: "technology",
    description:
      "물품과 기술의 국경 간 이전에 관한 통제 개념. 반도체 사건의 정책 맥락을 읽는 문서입니다.",
    edits: 163,
    baseline: 34,
    editors: 38,
    pageviews: 47630,
    eventIds: ["ai-chip-controls"],
    relatedIds: ["semiconductor", "nvidia"],
    changes: revisions("export-control", "Dual-use items", [
      [
        "11:04",
        "이중 용도 품목의 정의가 제시된다.",
        "이중 용도 품목의 기술적 분류와 허가 절차를 별도 항목으로 설명했다.",
        "통제 개념의 범위 설명 추가 예시",
        614,
      ],
      [
        "09:22",
        "규제 수단들이 본문에 연속해서 나열된다.",
        "허가·목록·최종 사용자의 개념을 목록으로 정리했다.",
        "규제 수단 설명 정돈 예시",
        197,
      ],
      [
        "08:11",
        "두 문단이 같은 분류 체계를 설명한다.",
        "중복되는 분류 설명을 한 문단으로 통합했다.",
        "정의 중복 통합 예시",
        -132,
      ],
    ]),
  },
  {
    id: "nuclear-power",
    title: "Nuclear power",
    name: "원자력 발전",
    category: "energy",
    profile: "sustained",
    description:
      "원자력을 이용한 전력 생산 문서. 발전 방식, 연료와 장기 전력 수요의 관계를 살펴봅니다.",
    edits: 168,
    baseline: 36,
    editors: 43,
    pageviews: 92180,
    eventIds: ["nuclear-energy"],
    relatedIds: ["uranium", "petroleum", "cloud-computing"],
    changes: revisions("nuclear-power", "Economics", [
      [
        "11:16",
        "발전 비용에 관한 설명이 하나의 표에 들어 있다.",
        "건설·운영·연료 항목을 구분해 발전 비용 설명을 정리했다.",
        "발전 비용 항목 구분 예시",
        483,
      ],
      [
        "09:31",
        "전력 수요는 개요에서 짧게 언급된다.",
        "대규모 수요와 안정적 전력 공급이라는 개념을 관련 문서로 연결했다.",
        "전력 수요 맥락 연결 예시",
        276,
      ],
      [
        "08:04",
        "발전 기술 설명의 두 문장이 같은 내용을 반복한다.",
        "중복 문장을 삭제하고 관련 기술 링크를 남겼다.",
        "기술 설명 간결화 예시",
        -78,
      ],
    ]),
  },
  {
    id: "uranium",
    title: "Uranium",
    name: "우라늄",
    category: "energy",
    profile: "sustained",
    description:
      "원자력 연료로 사용되는 원소 문서. 연료 주기와 생산·가공 단계를 따라 탐색합니다.",
    edits: 126,
    baseline: 24,
    editors: 29,
    pageviews: 53840,
    eventIds: ["nuclear-energy"],
    relatedIds: ["nuclear-power", "lithium"],
    changes: revisions("uranium", "Nuclear fuel", [
      [
        "10:54",
        "연료 가공 과정이 간단하게 나열되어 있다.",
        "채굴 이후의 전환·농축·연료 제조 과정을 나누어 설명했다.",
        "연료 주기 설명 확장 예시",
        562,
      ],
      [
        "09:15",
        "용도 문단에 발전과 연구 활용이 함께 쓰여 있다.",
        "발전용 연료와 연구용 활용을 소제목으로 구분했다.",
        "주요 용도 문단 분리 예시",
        168,
      ],
      [
        "07:52",
        "원소 성질 표에 본문과 같은 설명이 반복된다.",
        "반복 설명을 줄이고 표에서 본문으로 연결했다.",
        "성질 표 중복 정리 예시",
        -53,
      ],
    ]),
  },
  {
    id: "spacex",
    title: "SpaceX",
    name: "스페이스X",
    category: "space",
    profile: "cooling",
    description:
      "우주 발사체와 우주 수송 관련 기업 문서. 발사체 개발 및 재사용 기술 문서와 연결됩니다.",
    edits: 188,
    baseline: 40,
    editors: 57,
    pageviews: 148920,
    eventIds: ["space-launch"],
    relatedIds: ["reusable-launch-system"],
    changes: revisions("spacex", "Launch vehicles", [
      [
        "10:41",
        "발사체의 역할이 한 단락으로 정리되어 있다.",
        "발사체별 임무와 재사용 구성 요소를 나누어 설명했다.",
        "발사체 문단 구조 변경 예시",
        379,
      ],
      [
        "09:02",
        "회수 과정은 발사 과정에 포함되어 있다.",
        "발사와 회수 과정을 구분하고 재사용 발사체 문서로 연결했다.",
        "발사·회수 단계 구분 예시",
        291,
      ],
      [
        "07:46",
        "개발 역사 문단에 같은 날짜 항목이 중복된다.",
        "중복 항목을 통합하고 시간순으로 재정렬했다.",
        "개발 연혁 정리 예시",
        -116,
      ],
    ]),
  },
  {
    id: "reusable-launch-system",
    title: "Reusable launch vehicle",
    name: "재사용 발사체",
    category: "space",
    profile: "cooling",
    description:
      "발사체 구성 요소를 회수해 다시 사용하는 기술 문서. 회수 방식과 운용 구조를 설명합니다.",
    edits: 92,
    baseline: 25,
    editors: 26,
    pageviews: 36470,
    eventIds: ["space-launch"],
    relatedIds: ["spacex"],
    changes: revisions("reusable-launch-system", "Recovery methods", [
      [
        "10:24",
        "발사체를 회수하는 여러 방법이 소개된다.",
        "추진 착륙과 기타 회수 방식의 특성을 비교하는 설명을 추가했다.",
        "회수 방식 비교 보강 예시",
        421,
      ],
      [
        "08:39",
        "재사용의 장점이 본문에 나열되어 있다.",
        "설계·정비·운용 단계의 고려 사항을 함께 설명했다.",
        "운용 조건 설명 추가 예시",
        217,
      ],
      [
        "07:21",
        "두 문장에서 동일한 회수 개념을 정의한다.",
        "회수 개념의 정의를 첫 문단으로 모았다.",
        "회수 용어 정의 통합 예시",
        -64,
      ],
    ]),
  },
  {
    id: "lithium-ion-battery",
    title: "Lithium-ion battery",
    name: "리튬 이온 배터리",
    category: "materials",
    profile: "sustained",
    description:
      "이차전지의 구성과 제조, 활용 문서. 원재료부터 완성 셀까지 공급망 맥락을 제공합니다.",
    edits: 117,
    baseline: 30,
    editors: 32,
    pageviews: 64180,
    eventIds: ["battery-supply"],
    relatedIds: ["lithium", "semiconductor"],
    changes: revisions("lithium-ion-battery", "Supply chain", [
      [
        "10:36",
        "배터리 재료들이 하나의 문단에 나열되어 있다.",
        "양극·음극·전해질 재료를 구분하고 원재료 문서로 연결했다.",
        "셀 구성 소재 설명 보강 예시",
        493,
      ],
      [
        "08:58",
        "제조와 재활용이 같은 소제목에 들어 있다.",
        "제조 과정과 재활용 과정을 각각의 소제목으로 정리했다.",
        "제조·재활용 항목 분리 예시",
        203,
      ],
      [
        "07:37",
        "두 문단에서 같은 성능 지표를 설명한다.",
        "성능 지표의 설명을 표 아래 하나로 모았다.",
        "성능 지표 설명 중복 정리 예시",
        -82,
      ],
    ]),
  },
  {
    id: "lithium",
    title: "Lithium",
    name: "리튬",
    category: "materials",
    profile: "sustained",
    description:
      "배터리 원재료와 연결되는 원소 문서. 생산 방식과 가공·활용 문서의 변화를 살펴봅니다.",
    edits: 79,
    baseline: 25,
    editors: 23,
    pageviews: 42690,
    eventIds: ["battery-supply"],
    relatedIds: ["lithium-ion-battery", "uranium"],
    changes: revisions("lithium", "Production", [
      [
        "10:09",
        "생산 과정이 염수와 광석으로 구분된다.",
        "생산 방식별 가공 단계와 최종 활용에 대한 설명을 보강했다.",
        "생산·가공 흐름 보강 예시",
        338,
      ],
      [
        "08:27",
        "산업 용도가 하나의 긴 문장으로 나열되어 있다.",
        "배터리와 기타 산업 용도를 소제목으로 나눴다.",
        "용도 항목 구조화 예시",
        184,
      ],
      [
        "07:08",
        "일부 화합물 설명이 두 위치에 반복된다.",
        "중복 설명을 지우고 화합물 문서로 연결했다.",
        "화합물 설명 간결화 예시",
        -57,
      ],
    ]),
  },
  {
    id: "cybersecurity",
    title: "Computer security",
    name: "사이버 보안",
    category: "security",
    description:
      "정보 시스템을 보호하는 원칙과 기술 문서. 인증, 클라우드와 보안 제품의 관계를 읽습니다.",
    edits: 132,
    baseline: 38,
    editors: 39,
    pageviews: 78340,
    eventIds: ["cyber-security"],
    relatedIds: ["cloud-computing"],
    changes: revisions("cybersecurity", "Vulnerabilities and attacks", [
      [
        "11:32",
        "접근 제어와 인증의 개념이 함께 설명된다.",
        "인증·권한·접근 제어를 구분하고 클라우드 환경의 맥락을 연결했다.",
        "보안 개념의 구분 보강 예시",
        458,
      ],
      [
        "09:43",
        "보안 운영은 대응 절차 중심으로 설명된다.",
        "탐지·분석·대응이라는 운영 단계를 나눠 설명했다.",
        "보안 운영 단계 정리 예시",
        263,
      ],
      [
        "08:16",
        "위협 분류의 정의가 목록과 본문에서 중복된다.",
        "분류 정의는 본문에 두고 목록을 간결하게 정리했다.",
        "위협 분류 중복 제거 예시",
        -94,
      ],
    ]),
  },
  {
    id: "cloud-computing",
    title: "Cloud computing",
    name: "클라우드 컴퓨팅",
    category: "security",
    description:
      "네트워크를 통해 제공되는 컴퓨팅 자원 문서. 보안 운영과 AI 인프라의 연결 맥락입니다.",
    edits: 76,
    baseline: 28,
    editors: 24,
    pageviews: 61280,
    eventIds: ["cyber-security"],
    relatedIds: ["cybersecurity", "nvidia", "nuclear-power"],
    changes: revisions("cloud-computing", "Security and privacy", [
      [
        "11:11",
        "보안 책임이 서비스 유형과 함께 설명된다.",
        "서비스 제공자와 이용자의 책임을 항목별로 구분했다.",
        "공동 책임 개념 구체화 예시",
        371,
      ],
      [
        "09:19",
        "접근 관리 설명은 짧은 개요로 제시된다.",
        "계정·권한·감사 기록의 관계를 관련 문서 링크와 함께 정리했다.",
        "접근 관리 설명 보강 예시",
        219,
      ],
      [
        "07:58",
        "개인정보 보호 문단에 중복 예시가 있다.",
        "중복 예시를 제거하고 용어 정의를 유지했다.",
        "개인정보 문단 정리 예시",
        -68,
      ],
    ]),
  },
];

export const entities = entityFixtures.map(({ profile, ...entity }, index) => ({
  ...entity,
  pulse: roundPulse(entity.edits, entity.baseline),
  chart: makeActivityChart({ ...entity, profile, seed: index }),
}));

function newsItem(id, title, type, date, summary, reference) {
  return {
    id,
    title,
    source:
      type === "official"
        ? "기관 발표 예시"
        : type === "analysis"
          ? "데모 분석"
          : "데모 뉴스",
    publishedAt: date,
    type,
    url: wiki(reference),
    summary,
  };
}

const eventFixtures = [
  {
    id: "iran-hormuz-2025",
    title: "호르무즈 해협, 에너지 공급망으로 번지는 관심",
    summary:
      "호르무즈 해협·이란·석유 문서의 편집이 함께 늘었습니다. 해상 운송에서 에너지 공급망까지 연결되는 맥락을 살펴보세요.",
    category: "geopolitics",
    status: "rising",
    startAt: at(18, "08:40"),
    updatedAt: at(24, "11:42"),
    articleIds: ["strait-of-hormuz", "iran", "petroleum"],
    stockSymbols: ["XOM"],
    keywords: ["호르무즈 해협", "해상 운송", "원유", "공급망"],
    timeline: [
      {
        id: "hormuz-1",
        time: at(24, "11:42"),
        title: "운송 맥락으로 문서 연결 확대",
        body: "석유 문서의 운송 항목과 해협 문서의 항로 항목을 함께 읽을 수 있도록 구성한 예시입니다.",
        kind: "context",
        entityId: "petroleum",
      },
      {
        id: "hormuz-2",
        time: at(24, "09:20"),
        title: "에너지 운송 관점의 뉴스 카드 추가",
        body: "원유 운송 경로를 설명하는 가상 뉴스 카드가 사건 맥락에 포함되었습니다.",
        kind: "news",
        entityId: "strait-of-hormuz",
      },
      {
        id: "hormuz-3",
        time: at(23, "14:35"),
        title: "세 문서에서 함께 커지는 편집 흐름",
        body: "해협·국가·원자재 문서의 활동량이 같은 구간에 높아지는 데모 신호입니다.",
        kind: "signal",
        entityId: "iran",
      },
      {
        id: "hormuz-4",
        time: at(18, "08:40"),
        title: "호르무즈 해협의 첫 편집 상승",
        body: "기준선과 비교한 편집량 변화가 사건 후보의 출발점이 되었습니다.",
        kind: "signal",
        entityId: "strait-of-hormuz",
      },
    ],
    news: [
      newsItem(
        "hormuz-news-1",
        "호르무즈 해협을 통해 읽는 원유 운송 경로",
        "news",
        at(24, "09:20"),
        "가상 기사 요약: 주요 항로와 주변 해역을 연결해 에너지 운송의 구조를 설명합니다. 링크는 주제 참고 문서입니다.",
        "Strait of Hormuz",
      ),
      newsItem(
        "hormuz-news-2",
        "해상 교역 지표를 확인하는 방법",
        "official",
        at(23, "16:10"),
        "기관 자료 형식을 보여 주는 예시입니다. 통항량·운송량·집계 시점을 각각 확인하도록 구성했습니다.",
        "Maritime transport",
      ),
      newsItem(
        "hormuz-news-3",
        "지역 이슈와 에너지 기업 사이의 연결 고리",
        "analysis",
        at(23, "11:30"),
        "가상 분석: 정유·생산·운송 사업은 서로 다른 맥락을 가집니다. 이 연결만으로 가격 방향을 판단할 수는 없습니다.",
        "Petroleum industry",
      ),
    ],
    insights: [
      {
        title: "한 문서의 급증에서 함께 움직이는 주제로",
        body: "해협 문서의 활동과 이란·석유 문서의 동시 변화를 함께 보여 줍니다. 데모 편집량을 합산한 Pulse로 사건의 관심도를 비교할 수 있습니다.",
      },
      {
        title: "해상 운송을 따라 에너지 산업으로",
        body: "호르무즈 해협 → 원유 운송 → 에너지 기업의 순서로 탐색합니다. 기업 연결은 산업 맥락의 예시이며 수익·가격 영향은 포함하지 않습니다.",
      },
      {
        title: "다음으로 확인할 맥락",
        body: "편집 변경 내용, 각 문서의 기준선, 기사 카드의 시점을 순서대로 살펴보세요. 같은 시간에 편집이 늘었다는 사실과 그 이유에 대한 해석은 구분합니다.",
      },
    ],
  },
  {
    id: "ai-chip-controls",
    title: "AI 반도체 수출 통제, 기술과 정책의 접점",
    summary:
      "반도체·엔비디아·수출 통제 문서가 하나의 주제로 이어집니다. 가속기 제품에서 정책 개념까지 편집 변화의 범위를 확인하세요.",
    category: "technology",
    status: "rising",
    startAt: at(19, "10:10"),
    updatedAt: at(24, "11:38"),
    articleIds: ["semiconductor", "nvidia", "export-control"],
    stockSymbols: ["NVDA", "ASML"],
    keywords: ["AI 가속기", "반도체", "수출 통제", "제조 장비"],
    timeline: [
      {
        id: "chip-1",
        time: at(24, "11:38"),
        title: "제품에서 제조 생태계로 맥락 확대",
        body: "응용 분야와 제조 공정의 편집을 연결한 데모 문서 흐름입니다.",
        kind: "context",
        entityId: "semiconductor",
      },
      {
        id: "chip-2",
        time: at(24, "10:00"),
        title: "수출 통제 용어를 설명하는 카드 추가",
        body: "허가, 품목, 최종 사용자라는 개념을 소개하는 가상 참고 카드입니다.",
        kind: "news",
        entityId: "export-control",
      },
      {
        id: "chip-3",
        time: at(22, "13:25"),
        title: "정책 문서까지 함께 편집 증가",
        body: "수출 통제 문서의 활동량이 기업·기술 문서와 함께 높아지는 예시입니다.",
        kind: "signal",
        entityId: "export-control",
      },
      {
        id: "chip-4",
        time: at(19, "10:10"),
        title: "반도체 문서에서 시작된 신호",
        body: "AI 응용과 관련된 문단의 편집량이 기준선 위로 올라왔습니다.",
        kind: "signal",
        entityId: "semiconductor",
      },
    ],
    news: [
      newsItem(
        "chip-news-1",
        "AI 가속기와 수출 통제의 개념을 함께 읽기",
        "news",
        at(24, "10:00"),
        "가상 기사 요약: 제품의 기술적 용도와 정책의 적용 개념을 분리해 설명합니다. 특정 규정 변경을 보도하는 기사가 아닙니다.",
        "Export control",
      ),
      newsItem(
        "chip-news-2",
        "첨단 반도체의 설계부터 제조까지",
        "analysis",
        at(23, "14:15"),
        "가상 분석: 칩 설계, 제조, 장비 공급의 각 단계를 구분해 관련 기업을 탐색하는 예시입니다.",
        "Semiconductor device fabrication",
      ),
      newsItem(
        "chip-news-3",
        "기술 품목과 허가 항목을 읽는 순서",
        "official",
        at(22, "09:30"),
        "기관 발표 형식의 예시입니다. 품목 범위·대상 지역·적용 시점 같은 확인 항목만 제시합니다.",
        "Dual-use technology",
      ),
    ],
    insights: [
      {
        title: "기업 문서와 정책 문서가 만나는 지점",
        body: "엔비디아의 제품 설명과 수출 통제의 일반 개념을 같은 사건 안에서 탐색할 수 있습니다. 실제 규제의 내용이나 적용 여부를 판정하지 않습니다.",
      },
      {
        title: "서로 다른 두 산업 역할",
        body: "엔비디아는 가속 컴퓨팅 제품, ASML은 반도체 제조 장비라는 경로로 연결된 예시입니다. 동일한 사건 안에서도 기업과 이어지는 이유가 다릅니다.",
      },
      {
        title: "편집량과 변경 내용을 함께 읽기",
        body: "활동량이 증가해도 문서 구조 정리와 내용 추가의 의미는 다를 수 있습니다. 문서별 변경 전후를 열어 실제로 달라진 항목을 비교해 보세요.",
      },
    ],
  },
  {
    id: "nuclear-energy",
    title: "원자력 발전과 우라늄, 전력 수요의 연결",
    summary:
      "원자력 발전과 연료 문서에서 높은 관심이 이어집니다. 전력 생산의 구조에서 연료 공급까지 문서 사이의 관계를 따라가세요.",
    category: "energy",
    status: "sustained",
    startAt: at(14, "09:15"),
    updatedAt: at(24, "11:16"),
    articleIds: ["nuclear-power", "uranium"],
    stockSymbols: ["CCJ"],
    keywords: ["원자력 발전", "우라늄", "전력 수요", "연료 주기"],
    timeline: [
      {
        id: "nuclear-1",
        time: at(24, "11:16"),
        title: "발전 비용과 연료 주기를 함께 탐색",
        body: "발전 문서의 비용 항목에서 우라늄의 연료 가공 과정으로 이어지는 예시입니다.",
        kind: "context",
        entityId: "uranium",
      },
      {
        id: "nuclear-2",
        time: at(23, "15:20"),
        title: "전력 수요를 설명하는 참고 카드 추가",
        body: "안정적인 전력 공급이라는 일반 개념을 설명하는 가상 분석을 덧붙였습니다.",
        kind: "news",
        entityId: "nuclear-power",
      },
      {
        id: "nuclear-3",
        time: at(19, "10:30"),
        title: "두 문서의 관심 수준 유지",
        body: "단기 상승 이후에도 기준선보다 높은 편집량이 이어지는 데모 흐름입니다.",
        kind: "signal",
        entityId: "uranium",
      },
      {
        id: "nuclear-4",
        time: at(14, "09:15"),
        title: "발전 문서의 편집 활동 확대",
        body: "경제성과 발전 방식 항목의 변경을 사건 후보로 묶었습니다.",
        kind: "signal",
        entityId: "nuclear-power",
      },
    ],
    news: [
      newsItem(
        "nuclear-news-1",
        "전력 수요를 원자력 발전 문서에서 살펴보기",
        "analysis",
        at(23, "15:20"),
        "가상 분석: 전력 수요·발전 방식·연료 조달은 서로 다른 설명 단위입니다. 이를 문서 링크로 이어 읽는 예시입니다.",
        "Nuclear power",
      ),
      newsItem(
        "nuclear-news-2",
        "우라늄이 발전용 연료가 되기까지",
        "news",
        at(22, "11:10"),
        "가상 기사 요약: 채굴 이후 연료 제조까지의 기본 단계를 소개하는 체험용 카드입니다.",
        "Nuclear fuel cycle",
      ),
      newsItem(
        "nuclear-news-3",
        "발전 설비 자료에서 확인할 항목",
        "official",
        at(20, "09:00"),
        "기관 자료 형식의 예시입니다. 설비 용량, 가동 시점, 연료 범위 같은 정보 항목의 구성을 보여 줍니다.",
        "Nuclear power plant",
      ),
    ],
    insights: [
      {
        title: "하루 급증 이후의 관심도",
        body: "이 사건은 편집량이 급격히 오르는 경우와 달리 높은 수준을 유지하는 시나리오입니다. 추세에서 기간을 바꿔 시작 구간과 현재 구간을 비교하세요.",
      },
      {
        title: "발전에서 연료 공급으로",
        body: "원자력 발전 → 우라늄 연료 → Cameco라는 산업 연결을 제시합니다. 연료 사업과의 관련성을 설명하는 예시이며 계약이나 공급량 정보는 아닙니다.",
      },
      {
        title: "넓어지는 문서 맥락",
        body: "관련 문서에서 클라우드 컴퓨팅으로 이동해 전력 수요라는 주제를 더 살펴볼 수 있습니다. 문서 간 연결이 기업 간 거래 관계를 뜻하지는 않습니다.",
      },
    ],
  },
  {
    id: "space-launch",
    title: "재사용 발사체, 발사 이후에도 이어지는 변화",
    summary:
      "우주 수송과 재사용 기술 문서의 편집량이 고점을 지나 완만해졌습니다. 신호가 잦아드는 동안 남은 기술 맥락을 읽어보세요.",
    category: "space",
    status: "cooling",
    startAt: at(13, "07:50"),
    updatedAt: at(24, "10:41"),
    articleIds: ["spacex", "reusable-launch-system"],
    stockSymbols: ["012450.KS"],
    keywords: ["재사용 발사체", "우주 수송", "회수 기술", "항공우주"],
    timeline: [
      {
        id: "space-1",
        time: at(24, "10:41"),
        title: "관심은 완만해지고 설명 편집이 이어짐",
        body: "최고 활동일 이후 편집량은 줄지만 기술 문단 정리가 이어지는 데모입니다.",
        kind: "signal",
        entityId: "spacex",
      },
      {
        id: "space-2",
        time: at(22, "14:00"),
        title: "회수와 정비를 설명하는 카드 추가",
        body: "발사 이후의 회수·점검 과정에 초점을 둔 가상 분석입니다.",
        kind: "news",
        entityId: "reusable-launch-system",
      },
      {
        id: "space-3",
        time: at(17, "18:20"),
        title: "편집 활동의 고점",
        body: "발사체 문서와 재사용 기술 문서의 동시 활동이 가장 커진 예시 시점입니다.",
        kind: "signal",
        entityId: "reusable-launch-system",
      },
      {
        id: "space-4",
        time: at(13, "07:50"),
        title: "발사체 설명의 변화 시작",
        body: "기술과 기업 문서에서 같은 주제의 편집이 증가하기 시작했습니다.",
        kind: "context",
        entityId: "spacex",
      },
    ],
    news: [
      newsItem(
        "space-news-1",
        "재사용 발사체에서 회수와 정비의 역할",
        "analysis",
        at(22, "14:00"),
        "가상 분석: 재사용 기술의 여러 단계를 소개하는 카드입니다. 실제 발사나 회수 결과를 보도하지 않습니다.",
        "Reusable launch vehicle",
      ),
      newsItem(
        "space-news-2",
        "발사체 문서에 담긴 우주 수송의 구조",
        "news",
        at(20, "10:40"),
        "가상 기사 요약: 임무, 발사체, 회수 기술의 관계를 설명하며 산업을 더 넓게 탐색하도록 구성했습니다.",
        "Space launch",
      ),
      newsItem(
        "space-news-3",
        "우주 임무 자료를 읽을 때의 기본 항목",
        "official",
        at(18, "08:30"),
        "기관 발표 형식의 예시입니다. 임무 목적·기체·시점 등 자료의 구성 요소를 보여 줍니다.",
        "Spaceflight",
      ),
    ],
    insights: [
      {
        title: "잦아드는 신호도 이어서 보기",
        body: "관심이 줄어드는 사건을 감추지 않습니다. 현재 수치와 이전 고점을 비교하고, 남은 편집이 기술 설명을 보강하는지 확인하는 흐름입니다.",
      },
      {
        title: "기술에서 산업으로 넓히는 연결",
        body: "한화에어로스페이스는 항공우주 산업의 탐색 예시입니다. SpaceX와의 직접 공급 관계나 특정 발사 참여를 의미하지 않습니다.",
      },
      {
        title: "회수와 재사용을 구분해서 읽기",
        body: "회수 방법뿐 아니라 점검·정비·다음 운용까지 문서의 설명 범위를 살펴보세요. 편집 내용으로 기술 문서가 보강되는 과정을 체험할 수 있습니다.",
      },
    ],
  },
  {
    id: "battery-supply",
    title: "배터리 소재에서 셀까지, 공급망을 잇는 편집",
    summary:
      "리튬과 리튬 이온 배터리 문서의 관심이 함께 유지됩니다. 원재료·가공·셀 제조의 서로 다른 연결 경로를 비교해 보세요.",
    category: "materials",
    status: "sustained",
    startAt: at(15, "09:40"),
    updatedAt: at(24, "10:36"),
    articleIds: ["lithium-ion-battery", "lithium"],
    stockSymbols: ["373220.KS", "ALB"],
    keywords: ["리튬", "이차전지", "배터리 소재", "셀 제조"],
    timeline: [
      {
        id: "battery-1",
        time: at(24, "10:36"),
        title: "소재와 셀 구성의 연결이 선명해짐",
        body: "리튬 문서의 가공 과정과 배터리 문서의 소재 설명을 이어 놓은 예시입니다.",
        kind: "context",
        entityId: "lithium-ion-battery",
      },
      {
        id: "battery-2",
        time: at(23, "09:10"),
        title: "원재료와 완성 셀을 구분한 카드 추가",
        body: "산업의 단계별 역할을 설명하는 가상 뉴스 카드입니다.",
        kind: "news",
        entityId: "lithium",
      },
      {
        id: "battery-3",
        time: at(20, "13:50"),
        title: "두 문서에서 기준선 위 활동 유지",
        body: "리튬과 배터리 문서의 편집량이 비슷한 시기에 높아진 데모 흐름입니다.",
        kind: "signal",
        entityId: "lithium",
      },
      {
        id: "battery-4",
        time: at(15, "09:40"),
        title: "공급망 관련 편집이 늘기 시작",
        body: "소재 설명과 생산 설명의 변경을 하나의 주제로 묶었습니다.",
        kind: "signal",
        entityId: "lithium-ion-battery",
      },
    ],
    news: [
      newsItem(
        "battery-news-1",
        "리튬 원재료와 배터리 셀의 서로 다른 역할",
        "news",
        at(23, "09:10"),
        "가상 기사 요약: 소재 생산과 셀 제조를 구분하는 공급망 탐색용 카드입니다.",
        "Lithium-ion battery",
      ),
      newsItem(
        "battery-news-2",
        "배터리 소재의 생산·가공 단계를 연결해 보기",
        "analysis",
        at(22, "16:20"),
        "가상 분석: 기업 연결 경로가 원재료에서 출발하는지 완성 셀에서 출발하는지 비교하는 예시입니다.",
        "Lithium",
      ),
      newsItem(
        "battery-news-3",
        "배터리 자료의 생산능력과 실제 생산량 구분",
        "official",
        at(20, "11:00"),
        "기관 자료 형식의 예시입니다. 서로 다른 산업 지표를 같은 수치로 읽지 않도록 항목 구성을 보여 줍니다.",
        "Lithium-ion battery",
      ),
    ],
    insights: [
      {
        title: "같은 공급망, 다른 위치",
        body: "LG에너지솔루션은 셀 제조, Albemarle은 리튬 소재라는 경로로 연결됩니다. 이는 산업 단계의 설명이며 두 회사의 직접 거래 관계를 주장하지 않습니다.",
      },
      {
        title: "문서의 구성 변화가 주는 맥락",
        body: "배터리 문서에서 소재별 소제목이 정리되고 리튬 문서에서 가공 설명이 보강되는 예시를 제공합니다. 변경 전후에서 설명이 구체화되는 과정을 비교하세요.",
      },
      {
        title: "여러 날 유지되는 관심도",
        body: "높은 관심이 이어지는 시나리오입니다. 기간을 넓혀 일시적인 급증과 지속적인 관심의 차이를 살펴볼 수 있습니다.",
      },
    ],
  },
  {
    id: "cyber-security",
    title: "클라우드 보안, 계정과 접근 관리로 모이는 관심",
    summary:
      "사이버 보안과 클라우드 컴퓨팅 문서의 편집이 늘고 있습니다. 접근 제어부터 보안 운영까지 연결되는 개념을 따라가세요.",
    category: "security",
    status: "rising",
    startAt: at(20, "10:25"),
    updatedAt: at(24, "11:32"),
    articleIds: ["cybersecurity", "cloud-computing"],
    stockSymbols: ["CRWD"],
    keywords: ["클라우드", "접근 제어", "인증", "보안 운영"],
    timeline: [
      {
        id: "cyber-1",
        time: at(24, "11:32"),
        title: "보안 개념과 클라우드 운영이 연결됨",
        body: "인증·권한 설명과 클라우드의 책임 구분을 이어 읽는 데모 맥락입니다.",
        kind: "context",
        entityId: "cloud-computing",
      },
      {
        id: "cyber-2",
        time: at(24, "08:50"),
        title: "계정과 권한을 설명하는 카드 추가",
        body: "접근 관리의 기본 개념을 소개하는 가상 참고 카드입니다.",
        kind: "news",
        entityId: "cybersecurity",
      },
      {
        id: "cyber-3",
        time: at(22, "16:15"),
        title: "클라우드 문서의 보안 항목도 상승",
        body: "연결된 두 문서의 활동이 함께 늘어나는 예시입니다.",
        kind: "signal",
        entityId: "cloud-computing",
      },
      {
        id: "cyber-4",
        time: at(20, "10:25"),
        title: "접근 제어 문단에서 시작한 변화",
        body: "보안 문서의 개념 정리 편집이 기준선보다 증가했습니다.",
        kind: "signal",
        entityId: "cybersecurity",
      },
    ],
    news: [
      newsItem(
        "cyber-news-1",
        "클라우드 계정에서 인증과 권한을 나누어 보기",
        "news",
        at(24, "08:50"),
        "가상 기사 요약: 계정 관리의 기본 개념을 설명합니다. 실제 침해 사건이나 피해 규모를 보도하는 내용이 아닙니다.",
        "Computer security",
      ),
      newsItem(
        "cyber-news-2",
        "탐지부터 대응까지 이어지는 보안 운영",
        "analysis",
        at(23, "13:40"),
        "가상 분석: 보안 기업을 제품·운영 역할의 맥락에서 탐색하도록 구성한 설명 카드입니다.",
        "Security operations center",
      ),
      newsItem(
        "cyber-news-3",
        "클라우드 서비스의 보안 책임 확인 항목",
        "official",
        at(22, "10:20"),
        "기관 안내문 형식의 예시입니다. 이용자와 서비스 제공자의 책임 범위를 구분하는 항목을 제시합니다.",
        "Cloud computing security",
      ),
    ],
    insights: [
      {
        title: "특정 사고 없이도 살펴볼 수 있는 주제",
        body: "이 시나리오는 보안 개념을 보강하는 편집을 중심으로 구성했습니다. 편집량 증가만으로 보안 사고가 발생했다고 해석하지 않습니다.",
      },
      {
        title: "개념에서 제품 영역으로",
        body: "사이버 보안 → 위협 탐지·대응 → CrowdStrike라는 산업 연결 예시입니다. 특정 고객·사고·계약과의 관련성을 나타내지 않습니다.",
      },
      {
        title: "연결된 문서로 이해 넓히기",
        body: "클라우드 문서를 열어 접근 관리와 책임 구분을 살펴보세요. 사건을 저장한 뒤 문서 변화와 관련 기업을 다시 찾아오는 흐름을 체험할 수 있습니다.",
      },
    ],
  },
];

export const events = eventFixtures.map((event) => {
  const articles = event.articleIds.map((id) =>
    entities.find((entity) => entity.id === id),
  );
  const sum = (key) =>
    articles.reduce((total, article) => total + article[key], 0);
  const edits = sum("edits");
  const baseline = sum("baseline");
  return {
    ...event,
    date: DEMO_DATE,
    edits,
    baseline,
    pulse: roundPulse(edits, baseline),
    editors: sum("editors"),
    pageviews: sum("pageviews"),
    chart: articles[0].chart.map((point, index) => ({
      date: point.date,
      edits: articles.reduce(
        (total, article) => total + article.chart[index].edits,
        0,
      ),
      baseline: articles.reduce(
        (total, article) => total + article.chart[index].baseline,
        0,
      ),
      pageviews: articles.reduce(
        (total, article) => total + article.chart[index].pageviews,
        0,
      ),
    })),
  };
});

function priceChart(price, change, index) {
  const previousClose = price / (1 + change / 100);
  return Array.from({ length: 24 }, (_, point) => {
    const wave =
      Math.sin((point + index) * 0.83) * 0.011 +
      Math.cos(point * 1.31 + index) * 0.007;
    const value =
      point === 23
        ? price
        : point === 22
          ? previousClose
          : price * (0.96 + point * 0.0015 + wave);
    return { date: day(point + 1), price: Math.round(value * 100) / 100 };
  });
}

const stockFixtures = [
  {
    symbol: "XOM",
    name: "엑슨모빌",
    market: "NYSE",
    currency: "USD",
    sector: "에너지",
    description:
      "원유·가스 생산과 정제 사업을 에너지 공급망의 맥락에서 탐색하는 기업 예시입니다.",
    price: 112.48,
    change: 1.26,
    eventIds: ["iran-hormuz-2025"],
    relations: [
      {
        eventId: "iran-hormuz-2025",
        type: "industry",
        strength: "high",
        explanation:
          "원유 운송을 중심으로 한 사건에서 에너지 생산·정제 산업으로 이어지는 연결 예시입니다. 특정 항로의 이용이나 실적 영향을 뜻하지 않습니다.",
        path: ["호르무즈 해협", "원유 운송", "에너지 산업", "엑슨모빌"],
      },
    ],
  },
  {
    symbol: "NVDA",
    name: "엔비디아",
    market: "NASDAQ",
    currency: "USD",
    sector: "AI · 반도체",
    description:
      "GPU와 가속 컴퓨팅 제품이라는 맥락에서 반도체 문서와 연결되는 기업 예시입니다.",
    price: 143.72,
    change: 2.14,
    eventIds: ["ai-chip-controls"],
    relations: [
      {
        eventId: "ai-chip-controls",
        type: "direct",
        strength: "high",
        explanation:
          "사건에 엔비디아 기업 문서가 직접 포함되어 있습니다. 직접 연결은 문서의 포함 여부이며 규제 적용이나 가격 영향을 판정한 결과가 아닙니다.",
        path: ["AI 반도체", "가속 컴퓨팅", "엔비디아 문서", "엔비디아"],
      },
    ],
  },
  {
    symbol: "ASML",
    name: "ASML",
    market: "NASDAQ",
    currency: "USD",
    sector: "반도체 장비",
    description:
      "반도체 제조 장비의 역할을 통해 AI 반도체 생태계를 더 넓게 살펴보는 기업 예시입니다.",
    price: 761.35,
    change: -0.84,
    eventIds: ["ai-chip-controls"],
    relations: [
      {
        eventId: "ai-chip-controls",
        type: "supply",
        strength: "medium",
        explanation:
          "반도체 생산에 쓰이는 제조 장비라는 산업 단계로 연결했습니다. 특정 고객과의 거래나 수출 통제 적용 여부를 제시하지 않습니다.",
        path: ["AI 반도체", "반도체 제조", "노광 장비", "ASML"],
      },
    ],
  },
  {
    symbol: "CCJ",
    name: "카메코",
    market: "NYSE",
    currency: "USD",
    sector: "우라늄 · 원자력",
    description:
      "우라늄과 핵연료 사업의 맥락에서 원자력 발전 문서를 탐색하는 기업 예시입니다.",
    price: 68.92,
    change: 1.78,
    eventIds: ["nuclear-energy"],
    relations: [
      {
        eventId: "nuclear-energy",
        type: "supply",
        strength: "high",
        explanation:
          "원자력 발전의 연료 주기에서 우라늄 사업으로 이어지는 연결 예시입니다. 공급 계약이나 생산량을 보여 주는 데이터는 아닙니다.",
        path: ["원자력 발전", "핵연료 주기", "우라늄", "카메코"],
      },
    ],
  },
  {
    symbol: "012450.KS",
    name: "한화에어로스페이스",
    market: "KRX",
    currency: "KRW",
    sector: "항공우주",
    description:
      "항공우주 산업이라는 넓은 맥락에서 발사체 기술과 함께 탐색하는 국내 기업 예시입니다.",
    price: 847000,
    change: -1.12,
    eventIds: ["space-launch"],
    relations: [
      {
        eventId: "space-launch",
        type: "industry",
        strength: "medium",
        explanation:
          "항공우주라는 산업 분류로 확장한 연결입니다. SpaceX의 공급사이거나 특정 발사에 참여했다는 의미는 아닙니다.",
        path: [
          "재사용 발사체",
          "우주 수송",
          "항공우주 산업",
          "한화에어로스페이스",
        ],
      },
    ],
  },
  {
    symbol: "373220.KS",
    name: "LG에너지솔루션",
    market: "KRX",
    currency: "KRW",
    sector: "배터리 셀",
    description:
      "배터리 셀 제조의 맥락에서 리튬 이온 배터리 문서와 이어지는 국내 기업 예시입니다.",
    price: 286500,
    change: 0.53,
    eventIds: ["battery-supply"],
    relations: [
      {
        eventId: "battery-supply",
        type: "industry",
        strength: "high",
        explanation:
          "리튬 이온 배터리의 셀 제조 단계와 연결한 예시입니다. 특정 원재료 조달처나 개별 공급 계약의 근거는 포함하지 않습니다.",
        path: ["리튬 이온 배터리", "배터리 셀 제조", "LG에너지솔루션"],
      },
    ],
  },
  {
    symbol: "ALB",
    name: "앨버말",
    market: "NYSE",
    currency: "USD",
    sector: "리튬 · 소재",
    description:
      "리튬 소재라는 공급망 위치를 통해 배터리 사건을 살펴보는 기업 예시입니다.",
    price: 63.18,
    change: -0.47,
    eventIds: ["battery-supply"],
    relations: [
      {
        eventId: "battery-supply",
        type: "supply",
        strength: "high",
        explanation:
          "배터리 공급망의 원재료 단계에서 리튬 소재 기업으로 이어지는 예시입니다. 다른 관련 종목과의 직접 거래 관계를 의미하지 않습니다.",
        path: ["리튬 이온 배터리", "리튬 소재", "앨버말"],
      },
    ],
  },
  {
    symbol: "CRWD",
    name: "크라우드스트라이크",
    market: "NASDAQ",
    currency: "USD",
    sector: "사이버 보안",
    description:
      "위협 탐지와 대응이라는 보안 제품 영역에서 관련 문서를 탐색하는 기업 예시입니다.",
    price: 481.26,
    change: 1.09,
    eventIds: ["cyber-security"],
    relations: [
      {
        eventId: "cyber-security",
        type: "industry",
        strength: "high",
        explanation:
          "위협 탐지·대응이라는 보안 제품 영역을 기준으로 연결했습니다. 특정 침해 사건이나 고객사와의 관련성을 나타내지 않습니다.",
        path: ["사이버 보안", "위협 탐지 · 대응", "크라우드스트라이크"],
      },
    ],
  },
];

export const stocks = stockFixtures.map((stock, index) => ({
  ...stock,
  chart: priceChart(stock.price, stock.change, index),
}));

export function getEvent(id) {
  return events.find((event) => event.id === id);
}

export function getEntity(id) {
  return entities.find((entity) => entity.id === id);
}

export function getStock(symbol) {
  return stocks.find(
    (stock) => stock.symbol === String(symbol ?? "").toUpperCase(),
  );
}

export function getCategory(id) {
  return categories.find((category) => category.id === id);
}
