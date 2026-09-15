# 프론트엔드 구조와 확장 규칙

기준일: 2026-09-15. 대상은 이 저장소의 `frontend/` React/Vite 앱이다. 2026-09-08에 책임과 데이터 접근을 분리했고, 2026-09-09에 [11개 페이지 URL](PAGES.md)을 반영했다. JavaScript·해시 라우팅·온보딩 그래픽은 유지한다. 이전 문서의 루트 Next.js 앱 설명은 이관 전 데모 저장소 기준으로 폐기한다.

## 폴더와 책임

```text
frontend/src/
  main.jsx                         폰트·기본 CSS 로드와 React mount
  app/
    App.jsx                        앱 수명주기·공유 상태 조립
    router.js, RouteContent.jsx     해시 해석·페이지 선택·데이터 경계 연결
    navigation.js                  메뉴 정의
    layout/                        공통 레이아웃·렌더링 오류 경계
  pages/
    onboarding/                    OnboardingPage·NodeField·온보딩 CSS
    explore/                       이슈 탐색 카드/리스트
    pulse/                         시점 선택·문서 그래프·근거 패널
    event/                         사건 상세·EventSections·로컬 토론/CSS
    account/                       마이페이지·로그인·회원가입 준비 안내
    stocks/                        목록·상세·공유 종목 요소/CSS
    saved/                         보관함 표시와 로컬 검색
  features/
    bookmarks/                     저장 ID·토글·영속화·알림
    global-search/                 빠른 종목 검색 UI·지연 조회
  components/
    event/                         여러 화면이 쓰는 EventRow
    entity/                        문서 배열을 받는 ArticleNetwork
    charts/                        TrendChart
    ui/                            EmptyState·CategoryTag
  data/
    index.js, config.js             구현 선택·환경변수 검증
    contracts.js                   JSDoc 계약·DataError·출처 안내
    resources.js                   페이지 단위 요청·화면별 데이터 조합
    hooks/                         비동기 조회·페이지 데이터 Context
    mock/                          비동기 목 구현·fixtures/catalog.js
    api/                           HTTP 호출·endpoint 연결·응답 어댑터
  lib/                             숫자 표시·위키백과 원문 주소 같은 순수 함수
  styles/                          워크스페이스·공통 상세 화면 CSS
```

## 의존성과 데이터 흐름

`app → 페이지 데이터 경계 → 페이지/기능 → 표시 컴포넌트`로 구성한다. 한 페이지는 다른 페이지를 import하지 않는다. 여러 화면이 사용하는 사건 행은 `components/event`에, 사건에서만 사용하는 토론은 `pages/event`에 둔다. 범용 UI는 fixture나 서버 주소를 알지 않고 props로 데이터를 받는다.

페이지의 `usePageData()`는 **해당 화면에서 이미 로드한 데이터**를 읽는다. 이 Context는 앱 전체 데이터를 쌓는 전역 저장소가 아니다. `PageDataBoundary`가 `useAsyncResource`를 통해 `resources.js`와 공통 `dataClient`를 호출하고, 로딩/오류를 처리한 뒤 기존 화면을 렌더한다. `getEvent`, `getEntity`, `getStock`, `getCategory`는 이 화면에 로드된 데이터에서 찾는 동기 selector이며 HTTP 메서드와 구분한다.

펄스맵은 일반 이슈 목록 로더를 사용하지 않는다. `PulsePage`가 공통 클라이언트의 `listSnapshots`·`getPulseMap`을 `useAsyncResource`로 조회하고 원자적인 시점별 그래프를 받는다. `data/pulse/contract.js`에서 무결성을 확인하고 `pages/pulse/layout.js`가 복사된 노드의 배치만 계산한다. [펄스맵 설계·계약](PULSE_MAP.md)을 참조한다.

`dataClient`는 모든 조회를 Promise로 제공한다. 목 구현만 fixture를 import하며 원시 mock과 API는 같은 8개 GET DTO를 반환한다. 페이지·기능·앱·컴포넌트의 직접 fixture import는 ESLint가 차단한다. `resources.js`가 members/relatedStocks 등 DTO를 화면 모델로 변환한다. 시계열·뉴스·가격 등 서버가 주지 않은 정보는 합성하지 않는다. 목록은 초기 20개이며 이전/다음 이동에 같은 스냅샷을 유지한다. 출처 필터를 고르면 해당 출처의 최신 완료 스냅샷을 조회한다.

스타일은 소유 페이지 가까이에 둔다. 여러 상세 화면이 쓰는 기존 클래스는 `styles/details.css`, 공통 워크스페이스는 `styles/workspace.css`에 유지했다. 온보딩 CSS는 기존 전역 기본값도 포함하여 진입점에서 로드한다. 이번 작업에서는 CSS Modules 전환이나 디자인 변경을 하지 않았다.

## 상태 소유권

| 상태                    | 소유 위치                        | 유지 범위                            |
| ----------------------- | -------------------------------- | ------------------------------------ |
| 현재 경로               | App                              | hashchange·브라우저 뒤로/앞으로      |
| 사건/종목 저장 ID       | 앱에서 한 번 호출한 useBookmarks | React 상태 + 모드별 localStorage 키  |
| 알림·도움말·본문 포커스 | App/레이아웃                     | 현재 앱 세션                         |
| 탭·필터·정렬·차트 선택  | 해당 페이지                      | 기존 화면 수명주기                   |
| 검색어·선택 결과        | GlobalSearch                     | 경로 이동·닫기 시 초기화             |
| 조회 데이터·요청 오류   | 페이지 데이터 경계/검색 훅       | 현재 조회 수명주기                   |
| 토론 글·답글·공감       | EventDiscussion                  | 모드/사건별 localStorage + 세션 폴백 |

저장 훅을 페이지마다 따로 호출하지 않는다. 페이지에는 저장 ID와 토글 콜백을 전달한다. 저장소에서 문자열 ID의 중복과 형식을 정리하지만, 서버 조회 전 알 수 없는 ID를 지우지 않는다. 보관함은 ID별 단건 조회를 하며 404 항목은 조회할 수 없는 저장 항목에서 해제할 수 있다. 서버 오류는 빈 보관함으로 숨기지 않는다. 저장 해제 후 재조회 중 직전 데이터를 유지하여 선택 탭이 초기화되지 않도록 했다.

## 새 화면과 기능 추가

1. `pages/<화면>/`에 화면과 전용 컴포넌트를 둔다. 파일이 적으면 내부 폴더를 먼저 늘리지 않는다.
2. 기존 데이터로 만들 수 있으면 `resources.js`에 화면 로더를 추가한다. 새 조회가 필요하면 공통 JSDoc 계약, mock 구현, API 구현을 함께 추가한다.
3. `RouteContent`에 해시와 데이터 resource를 연결한다. 페이지는 `usePageData`를 읽고, UI에는 객체/배열을 props로 전달한다.
4. 화면 둘 이상에서 공유하는 UI만 `components`로 이동한다. 상태와 동작을 공유하는 기능은 `features`에 둔다.
5. API 응답 필드 변경은 `data/api/adapters.js` 검증, raw mock, OpenAPI와 `resources.js` 화면 변환을 함께 확인한다. 숫자 단위·데이터 의미가 달라지면 계약과 UI 대응도 함께 검토한다.

온보딩은 `lazy()`로 유지한다. 서비스 직접 진입에서 OnboardingPage/Three.js 청크를 내려받지 않는지 production smoke로 확인한다. 프론트의 mock 모드는 백엔드·수집기·DB 실행 없이 동작한다.

설정과 실제 연결 절차, 검증 범위는 [DATA_SOURCE.md](./DATA_SOURCE.md)를 참고한다.

API 저장 키는 `wikipulse.api.*`, mock은 기존 `wikipulse.*`를 사용한다. API 토론은 빈 상태로 시작하고 내용은 이 브라우저에만 저장한다.
