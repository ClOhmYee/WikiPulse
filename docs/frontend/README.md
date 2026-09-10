# WikiPulse 프론트엔드 문서

> 상태: **확정**  
> 기준일: 2026-09-08  
> 대상: 독립 React/Vite 프론트엔드의 온보딩·워크스페이스·Mock/API 전환

이 디렉터리는 현재 프론트엔드 구조와 데이터 연결 방법, 온보딩 디자인·인터랙션 결정, 시행착오와 검증 기준을 기록한다. 새 기능을 추가하기 전에 아래 문서와 [`frontend/DESIGN.md`](../../frontend/DESIGN.md)를 함께 확인한다.

## 문서 안내

- [PAGES.md](./PAGES.md): 확정된 11개 페이지·URL, 제거된 화면, API·인증 구현과의 경계
- [PULSE_MAP.md](./PULSE_MAP.md): 시점 선택·HOT/NEW·문서 그래프, 백엔드 데이터 계약과 후속 작업
- [MOCK_HISTORY.md](./MOCK_HISTORY.md): 2025-09~2026-09 실제 위키 문서 기반 시연 이력, Nasdaq-100 출처, 합성 범위와 파이프라인 차이
- [프론트엔드 검증 기록](../../frontend/docs/VALIDATION.md): 2026-09-09 라우팅 검증 결과·재현 명령과 이전 검증 이력
- [ARCHITECTURE.md](./ARCHITECTURE.md): 페이지 중심 구조, 의존성, 상태 소유권과 확장 규칙
- [DATA_SOURCE.md](./DATA_SOURCE.md): `.env` 전환, 공통 조회 계약, 백엔드 연결 절차와 검증 결과

- [DECISIONS.md](./DECISIONS.md): 제품 범위, 장면별 내러티브, 비주얼·모션 결정과 폐기한 접근
- [IMPLEMENTATION.md](./IMPLEMENTATION.md): React/React Three Fiber/Three.js 구조, 데이터 소유권, 렌더링 및 입력 처리
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): 작업 중 발생한 문제, 원인, 해결 방법과 회귀 확인 항목
- [`frontend/DESIGN.md`](../../frontend/DESIGN.md): 색상·타이포그래피·레이아웃·모션의 상세 디자인 규격

## 저장소 경계

~~저장소 루트는 Next.js 기반 메인 애플리케이션~~ → 이전 데모 저장소 설명이다. 현재 저장소는 `frontend/`, `backend/`, `data-pipeline/`, `db/` 등을 함께 관리하며, [`frontend/`](../../frontend/)는 온보딩과 워크스페이스를 제공하는 **Vite + React 애플리케이션**이다(2026-09-09 코드 확인). 프론트를 실행하거나 빌드할 때는 `frontend`를 대상으로 명령을 실행한다.

```powershell
npm.cmd --prefix frontend install
npm.cmd --prefix frontend run dev
npm.cmd --prefix frontend run build
```

`dev` 실행 후 Vite가 출력하는 로컬 주소에서 확인한다. 기본 주소는 `http://127.0.0.1:5174/`이며 서비스 바로 진입은 `http://127.0.0.1:5174/#/pulse`다. preview는 4174를 사용한다. 기본 데이터 모드는 mock이므로 백엔드 없이 실행할 수 있다.

## 현재 범위

- 4개의 전체 화면 장면으로 `Scattered changes → Track → Cluster → Match`를 설명한다.
- `탐색 시작하기`와 마지막 장면 CTA로 Pulse Map에 진입한다.
- 펄스맵·이슈 탐색·리포트·연관주식·종목 탐색·상세·보관함을 제공한다. 단일 문서 분석 화면은 제거했으며 근거는 위키백과 원문으로 연결한다.
- 마이페이지·로그인·회원가입은 각각 준비 안내 화면이다. 인증·계정 생성·접근 제한은 구현하지 않는다.
- 데이터 조회는 `.env`의 mock/API 설정으로 전환하며 보관함과 토론은 브라우저에 저장한다.
- 온보딩 노드·클러스터·주식 그래프는 제품 개념을 설명하기 위한 추상적 조형이다. 펄스맵은 합성 스냅샷의 문서 노드·근거 간선을 개별 표시한다.
- 목데이터는 실제 Wikipedia 문서와 현재 Nasdaq-100 구성 목록을 사용한다. 편집 기록·리포트·관계·가격은 합성이고 실제 수익률·매칭 정확도나 과거 지수 구성을 재현하지 않는다.
- PC에서는 휠 한 번에 인접 장면 하나, 모바일에서는 수직 스와이프 한 번에 하나씩 이동한다.

## 주요 진입점

| 파일 | 책임 |
| --- | --- |
| [`frontend/src/pages/onboarding/OnboardingPage.jsx`](../../frontend/src/pages/onboarding/OnboardingPage.jsx) | 장면 카피, 스크롤·키보드·터치 입력, DOM 전환, WebGL 폴백 |
| [`frontend/src/pages/onboarding/NodeField.jsx`](../../frontend/src/pages/onboarding/NodeField.jsx) | R3F 캔버스, Three.js 노드·간선·배경별, 셰이더, 장면 보간 |
| [`frontend/src/pages/onboarding/onboarding.css`](../../frontend/src/pages/onboarding/onboarding.css) | 레이아웃, 타이포그래피, 색상, 반응형, 접근성 스타일 |
| [`frontend/public/wikipulse-icon.png`](../../frontend/public/wikipulse-icon.png) | 서비스 아이콘 및 파비콘 |
| [`frontend/index.html`](../../frontend/index.html) | HTML 메타데이터와 앱 진입점 |

## 완료 기준

코드 빌드만으로 WebGL 모션의 완성도를 보장할 수 없다. 변경 후 아래를 모두 확인한다.

1. `npm.cmd --prefix frontend run build`가 성공한다.
2. 데스크톱과 모바일에서 1→2→3→4, 4→3→2→1 전환을 확인한다.
3. 휠·터치·키보드 입력이 한 번에 한 장면만 이동한다.
4. `prefers-reduced-motion: reduce`에서 공간 모션이 멈추고 정보가 유지된다.
5. WebGL을 사용할 수 없거나 컨텍스트가 손실되어도 DOM 폴백에서 네 장면의 설명을 읽을 수 있다.
6. 실제 데이터로 오해할 수 있는 가격·수익률·정확도 표현이 추가되지 않았는지 확인한다.

## 현재 알려진 후속 과제

- Vite 프로덕션 빌드는 성공하지만 Three.js 계열을 포함한 JavaScript 청크가 500 kB 경고 기준을 넘는다. 온보딩은 이미 지연 로딩하며, 서비스 직접 진입에서 해당 청크를 불러오지 않는지 production smoke로 검증한다.
- `.hero-brand__name-accent`의 `#7f7cff`는 현재 의도된 로고 포인트지만, 디자인 토큰으로 승격되지 않은 리터럴 값이다. 색 체계를 확장할 때 토큰화한다.
- E2E·접근성·브라우저 캡처 확인은 자동화한 범위에 한한다. GPU·브라우저 차이까지 포함한 전체 시각 회귀를 보장하지 않는다.
