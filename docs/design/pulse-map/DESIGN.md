---
name: WikiPulse PulseMap — NEON PULSE
description: 실제 사건·문서 관계를 짙은 네이비와 주제별 네온 테두리로 읽는 지도
colors: { map-bg: "#040b17", bubble-body: "#07101f", bubble-light: "#091322", footer-bg: "#050e1c", surface: "#0b141b", border: "#24313a", label: "#e2f1ff", muted: "#9cafb6", paper: "#f3f7f7", teal: "#86c9c4", focus: "#82e4ff", scan: "#55ddff", politics: "#b78aff", world: "#8399ff", society: "#64dce8", economy: "#ffc46b", technology: "#42d9ff", science: "#c4ed76", culture: "#f477d8", sports: "#61ddd0", environment: "#43e5d6", other: "#91bce8" }
typography:
  body: { fontFamily: '"Noto Sans KR Variable", "Noto Sans KR", sans-serif', fontSize: "14px", lineHeight: 1.6, letterSpacing: "-0.015em" }
  cluster-title: { fontWeight: 500 }
  caption: { fontSize: "13px", fontWeight: 500 }
  legend: { fontSize: "10px" }
  new-badge: { fontSize: "11px", fontWeight: 650, letterSpacing: "1px" }
rounded: { callout: "4px", control: "5px", field: "6px", dialog: "12px" }
spacing: { small: "8px", compact: "12px", regular: "16px", wide: "20px", caption: "24px" }
components:
  scan-control: { backgroundColor: "transparent", textColor: "#adcfe8", rounded: "{rounded.control}", width: "36px", height: "36px", padding: "0" }
  category-chip: { backgroundColor: "transparent", textColor: "#afc1c9", rounded: "{rounded.control}", padding: "6px 11px" }
  search: { backgroundColor: "{colors.surface}", rounded: "{rounded.field}", padding: "0 13px" }
  map: { backgroundColor: "{colors.map-bg}", height: "740px" }
  document-callout: { backgroundColor: "{colors.bubble-body}", textColor: "{colors.label}", rounded: "{rounded.callout}" }
---

# Design System: WikiPulse PulseMap

## Overview

**Creative North Star: "NEON PULSE"**

짙은 네이비 위에 주제별 테두리와 절제된 발광으로 문서 관계를 드러낸다. 이 문서는 `/pulse`의 일반·전체화면 지도에만 적용한다. 온보딩이나 전체 제품의 디자인 규칙을 대체하지 않는다.

승인 시안은 색·재질·분위기의 기준이며, 화면의 주제·문서·연결·순위는 실제 응답과 기존 배치 로직을 따른다. 구현 기준은 [PulseMap.jsx](../../../frontend/src/pages/pulse/PulseMap.jsx), [DocumentLabels.jsx](../../../frontend/src/pages/pulse/DocumentLabels.jsx), [pulse.css](../../../frontend/src/pages/pulse/pulse.css), [neonTheme.js](../../../frontend/src/pages/pulse/neonTheme.js), [useNeonScan.js](../../../frontend/src/pages/pulse/useNeonScan.js)다. 데이터·시간 탐색 계약은 [PULSE_MAP.md](../../frontend/PULSE_MAP.md)를 따른다.

**Key Characteristics:**

- 어두운 내부 면과 주제별 청록·파랑·보라·마젠타·앰버·라임 테두리.
- 펄스맵 좌표 중심에서 출발하고 지도와 함께 움직이는 하나의 원형 스캔.
- 모든 노드 내부에 말줄임 문서 라벨, 상호작용 시 전체 이름 표시.

## Colors

`technology`, `society`, `sports`, `environment`의 청록 계열은 각 주제의 노드·연결·클러스터 테두리에 함께 사용한다. `scan`은 지도 중심의 파동, `focus`는 조작 요소의 키보드 포커스다.

`world`, `politics`는 파랑·보라 계열, `culture`는 마젠타다. 보라 계열의 중복을 줄이기 위해 `economy`는 소프트 앰버 `#ffc46b`, `science`는 라임 옐로 `#c4ed76`를 사용한다. 알 수 없는 주제는 `other`로 표시한다. 지도 클릭·드래그에는 기본 포커스 테두리를 표시하지 않고, 키보드 진입 시 `focus-visible`로 청록색 포커스를 표시한다.

`map-bg`를 지도 바탕과 글자 외곽선에, `bubble-body`·`bubble-light`를 문서 내부 그라디언트에 사용한다. `footer-bg`는 범례·조작 바, `label`은 지도 제목과 라벨, `muted`는 보조 설명이다. 주변 검색·필터·패널은 기존 `surface`·`border`·`teal`을 유지한다.

**The Stable Category Rule.** 색은 주제 정체성이다. 시점·필터·순위·점수에 따라 주제 색을 재배정하지 않는다.

클러스터 경계는 전체 점선이며, 마우스가 올라간 클러스터에만 38도 실선 호 두 개를 180도 간격으로 표시한다. 120ms 투명도 전환으로 나타나고 사라지며, 첫 호의 중심이 마우스 방향을 즉시 따라간다. 클러스터 로컬 좌표를 사용해 확대·이동 후에도 방향을 유지하고, 회전값만 갱신해 문서 전체의 React 재렌더링을 피한다. 터치에는 호를 표시하지 않으며 모션 감소 설정에서는 고정 방향으로 표시한다.

## Typography

본문은 기존 Noto Sans KR 계열을 상속한다. 지도에서는 제목과 문서명을 구분하고, 숫자는 주변 페이지의 고정폭 숫자 설정을 유지한다.

- 클러스터 제목: 굵기 500, 고정 글꼴 크기 20(모바일 23), 줄 간격 1.3. 제목 그룹에 `(zoom / DEFAULT_ZOOM)^0.35 / zoom` 배율을 적용해 기존 지도 좌표 글자 크기를 유지한다. 기본 배율의 크기를 유지하면서 클러스터보다 완만하게 확대·축소한다. 최대 세 줄이며 긴 제목의 끝은 줄인다. 박스 치수와 줄바꿈을 매 프레임 다시 계산하지 않는다.
- 문서 라벨: 지도 좌표 글자 크기 `13 / zoom^0.8`(모바일 `14 / zoom^0.8`)를 `max(8, radius × 0.36)` 이하로 제한한다. 카메라 변환에는 별도의 `MAP_SCALE = 0.85`가 있으므로 이 값을 그대로 화면 px로 해석하지 않는다.
- 연속 줌 중에는 문서 글자에 scale을 적용하고, 줌이 멈추면 최종 글꼴과 줄바꿈·말줄임을 반영한다. 제목 박스는 한 묶음의 transform으로 글자·여백·빛번짐을 함께 조절한다.
- 노드 내부 라벨은 밝은 글자로 표시하며, 별도 전체 이름 callout에는 어두운 외곽선을 둔다. 접근 가능한 이름에는 원래 제목을 유지한다.

## Layout

기본 지도 높이는 데스크톱 740px, 720px 이하에서 640px이다. 선택 전에는 지도만 전체 너비로 보인다. 전체화면 dialog는 바깥 여백 16px(모바일 8px)을 두고 남은 높이를 사용한다. 전체화면 선택 패널은 데스크톱 360px 열, 모바일에서는 오른쪽 `min(320px, 85%)` 오버레이다.

모든 클러스터를 데이터에 따라 배치한다. `pulseScore` 순위가 중심과 바깥 배치를 정하고, 문서 반지름은 `12 + 28 * sqrt(sizeScore)`다. 값 미제공은 기본 반지름과 점선으로 구분한다. 화면에 모두 맞추려고 노드를 임의 축소하거나 제거하지 않는다.

화면 밖 클러스터는 140 화면 px의 여유 영역을 넘어가면 그리기·탭 이동·스캔 갱신에서 제외하고, 다시 들어오면 복원한다. 데이터·DOM·선택 상태는 유지하며 화면 안의 노드와 라벨을 생략하지 않는다.

일반·전체화면 전환과 리사이즈 시 배율과 중심을 유지한다. 필터·시점 변경 시 기존 배치 초기화 규칙을 따른다. 시간축은 일반 화면에서는 간결한 바, 전체화면에서는 상단 자동 숨김 패널이며 모바일은 두 줄이다.

## Elevation & Depth

깊이는 어두운 내부 면, 얇은 테두리, 재사용 SVG 방사형 그라디언트로 만든다. 노드 halo는 반지름 바깥 7, echo는 바깥 4의 지도 좌표를 사용한다. 큰 블러를 반복해서 쌓지 않는다. 선택된 노드에는 `drop-shadow(0 0 5px var(--cluster-color))`를 적용한다. 제목 박스는 우측 3·아래 4·블러 5의 값을 제목 배율 단위로 보정한 빛번짐을 사용한다. 주제색 빛의 중심은 박스 우측 하단이며, 글자는 별도 레이어에서 선명하게 유지한다.

**The Restrained Glow Rule.** 발광은 관계와 상태를 읽는 보조 수단이며 글자의 대비나 데이터 크기 척도를 바꾸지 않는다.

## Shapes

문서는 원, 클러스터는 점선 원과 짧은 궤도 호로 표현한다. Clickstream은 실선과 방향 화살표, Wikidata는 점선이다. 감지 문서는 작은 밝은 점으로 구분한다. 조작 요소는 작은 둥근 모서리, 전체화면은 더 넓은 둥근 모서리를 사용한다.

## Components

### Document node and label

노드 선택은 밝은 테두리, 연결 문서는 굵어진 주제 테두리, 관련 간선은 밝은 선으로 드러낸다. hover·키보드 focus에도 밝은 테두리를 준다. 모든 배율에서 각 노드 내부에 라벨을 표시한다. 반지름의 1.55배 너비·1.15배 높이의 내부 영역에서 작은 노드는 한 줄, 반지름 20 이상은 두 줄로 제한하고 넘치면 말줄임한다. 자리가 부족해도 라벨을 생략하지 않는다.

hover·focus·선택 문서에는 전체 이름 callout을 표시한다. 일반 라벨은 최대 두 줄로 줄일 수 있지만 callout과 접근 가능한 이름에는 원래 이름을 유지한다. callout은 지도 경계를 기준으로 위치를 보정하며 텍스트 블록을 박스 세로 가운데에 맞춘다. 클러스터 제목에도 같은 네이비 배경·주제색 테두리·둥근 모서리 박스를 적용하고, 제목 박스·여백·모서리·글자 외곽선은 글자와 같은 완만한 배율로 보정한다.

### Scan and map controls

제목 박스도 스캔 대상이다. 박스 중심의 지도 좌표를 기준으로 테두리 두께·우측 하단 그라디언트·외부 글로우의 강도를 높였다가 600ms 잔광으로 줄인다. 제목의 완만한 확대·축소로 위치가 달라지므로 현재 좌표를 읽되 스캔 주기는 재시작하지 않는다. 스캔 중에는 블러 반경을 고정하고 투명도를 변경한다. 일시정지·모션 감소·화면 밖에서는 기본 빛번짐을 유지한다.

하나의 스캔이 펄스맵 좌표 중심 `(0, 0)`에서 4초 주기로 시작해 2.5초 동안 전체 지도 배치의 외곽까지 확장한다. 지도와 카메라 변환을 공유하므로 이동·확대에 함께 반응한다. 같은 파동의 약한 echo가 뒤따르며, 통과한 노드·간선에는 최대 600ms의 주제색 잔광을 준다. 통과 시점은 지도 좌표 거리로 계산한다. 스캔은 데이터 갱신이나 실시간 수집 상태를 뜻하지 않는다.

하단에 스캔 일시정지/재생, 축소, 확대, 초기화, 전체화면 버튼을 둔다. 버튼 크기는 36px, 모바일 44px이다. 정지 상태는 일반·전체화면 및 필터·시점 변경에도 유지한다. 모션 감소 설정에서는 스캔을 끄고 해당 버튼에 이유를 표시하며 비활성화한다. 지도 offscreen·숨겨진 탭에서는 프레임을 중단한다. SVG 속성 갱신 간격은 최소 32ms로 제한한다.

### Surrounding controls

검색 필드, 주제 chip, 날짜·출처 선택과 시간축은 기존 작업 화면의 시각 체계를 유지한다. Enter/Space로 문서·클러스터를 선택하고, 방향키로 지도를 이동한다. 선택 패널은 일반·전체화면 모두 이슈 리포트 이동을 제공한다.

## Do's and Don'ts

### Do:

- **Do** 주제 색과 실제 응답의 문서·연결·점수·순위를 유지한다.
- **Do** 문서 전체 이름을 hover·focus·선택과 접근 가능한 이름으로 제공한다.
- **Do** 일반·전체화면·모바일에서 정지, 모션 감소, 화면 밖 중단을 유지한다.

### Don't:

- **Don't** 승인 시안의 예시 주제·개수·연결을 실제 데이터로 대체 주입한다.
- **Don't** 스캔 효과를 서버 데이터 갱신이나 수집 완료 신호로 설명한다.
- **Don't** HTTP 가로채기 검사를 실제 백엔드 검증이나 성능 벤치마크로 설명한다.
