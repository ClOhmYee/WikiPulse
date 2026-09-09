# WikiPulse 프론트엔드

기존 4장면 온보딩에서 사건 지도, 사건 상세, 문서 분석, 관련 종목과 사건별 로컬 토론까지 이어지는 독립 React/Vite 앱입니다. 기본 데이터 공급처는 목데이터이며 `.env`로 API 조회 구현을 선택할 수 있습니다. 보관함과 토론은 현재 브라우저에서만 보관합니다. mock 모드는 API 서버 없이 실행됩니다.

## 실행

Node.js 22.12 이상을 사용합니다. 이 `frontend` 디렉토리에서 실행합니다.

```powershell
npm.cmd ci
# .env가 없는 새 체크아웃에서만 실행
Copy-Item .env.example .env
npm.cmd run dev
```

- 온보딩: http://127.0.0.1:5174/
- 서비스 바로 보기: http://127.0.0.1:5174/#/pulse
- 배포 파일 생성: `npm.cmd run build` → `dist/`
- 배포 파일 로컬 확인: `npm.cmd run preview` → http://127.0.0.1:4174/

경로는 hash routing을 사용하므로 새로고침과 뒤로/앞으로 이동이 가능하며, 정적 호스팅에서 서버 라우팅 설정이 필요하지 않습니다. 루트 Next.js 앱과 데이터 수집기를 실행할 필요가 없습니다.

## 제공 화면

| 경로 | 내용 |
|---|---|
| `#/` | 기존 Track → Cluster → Match 온보딩 |
| `#/pulse` | 날짜·시점 탐색, HOT/NEW, 문서 그래프·근거 패널 ([계약](../docs/frontend/PULSE_MAP.md)) |
| `#/issues` | 이슈 목록, 검색·주제·정렬 |
| `#/issues/iran-hormuz-2025` | 이슈 리포트: 개요, 타임라인, 뉴스 예시, 근거 문서, 토론 |
| `#/issues/iran-hormuz-2025/stocks` | 이슈에 연결된 종목과 연결 유형 |
| `#/stocks`, `#/stocks/NVDA` | 종목 탐색, 관련 사건과 연결 경로, 가격 예시 |
| `#/saved` | 저장한 사건과 관심 종목 |
| `#/mypage` | 계정 관리 준비 안내, 보관함·로그인·회원가입 이동 |
| `#/login`, `#/signup` | 각각 독립된 준비 안내 화면. 인증·계정 생성 기능 없음 |

전체 11개 페이지와 URL 규칙은 [페이지 구성 정본](../docs/frontend/PAGES.md)을 참고하세요. 단일 위키 문서 상세는 제거했으며, 근거 문서는 위키백과 원문으로 연결됩니다.

검색창은 `Ctrl/Cmd + K`로 이동하고, 결과는 방향키와 Enter로 선택합니다. 차트에 포커스를 두고 좌우 방향키를 누르면 날짜별 수치를 읽을 수 있습니다. 지도는 드래그·확대·축소·초기화를 지원하고, 사건 노드는 Enter/Space로 선택할 수 있습니다.

보관함은 `localStorage`의 `wikipulse.savedEvents`, `wikipulse.savedStocks`에 저장됩니다. 로그인이나 서버 동기화는 없습니다. 저장 공간을 사용할 수 없는 환경에서는 현재 화면에서만 상태를 유지하고 안내합니다.

## 리포트에서 종목과 토론으로

사건 리포트 상단의 **연관 주식**을 누르면 해당 사건에 연결된 종목 목록으로 이동합니다. **토론 참여하기**는 다섯 번째 **토론** 탭을 선택하며, 개요의 타임라인 미리보기 아래에서도 같은 토론을 볼 수 있습니다. 토론 탭 선택은 화면 내부 상태이므로 별도 URL은 없습니다.

사건별 예시 글 3개와 첫 글의 예시 답글 1개가 제공됩니다. 글·답글 작성, 글 공감·취소, 답글 접기·펼치기, 최신순·공감순 정렬을 지원합니다. 예시 작성자는 `리서처 A/B/C`, 직접 작성한 글의 표시명은 `나 (데모)`입니다. 다른 사용자에게 전송되지 않습니다. 글과 답글은 앞뒤 공백을 제거한 뒤 1~1,000자(JavaScript 문자열 길이 기준)이며, 사건당 글 200개(예시 포함), 글당 답글 200개까지 보관합니다. 편집·삭제·신고·대댓글은 구현하지 않았습니다.

토론 저장 키는 `wikipulse.discussion.{eventId}`이고 값은 `{ version: 1, threads: [...] }` JSON입니다. 글에는 `id`, `author`, `body`, `createdAt`, `isOwn`, `isSeed`, `likes`, `liked`, `replies`가 있으며, 답글에는 공감 필드와 중첩 `replies`가 없습니다. 읽기 시 형식과 한도를 검증하고, 잘못된 저장값은 안내와 함께 예시 토론으로 복구합니다. 제출한 글·답글·공감은 탭 전환과 화면 이동 후에도 유지됩니다. 저장 실패 시 페이지 세션의 메모리에서 유지하며 새로고침하면 사라집니다. 작성 중인 초안과 정렬·펼침 상태는 저장하지 않습니다.

작성 시각은 브라우저의 현재 시각입니다. 예시 데이터 기준일과 같지 않을 수 있습니다. 저장 데이터의 작성자·소유 표시와 고정 표시명은 로그인이나 실제 사용자 식별을 의미하지 않습니다. 상세한 로컬 동작은 [UI 가이드](docs/UI_GUIDE.md#event-discussion), 향후 연동 제안은 [API 계약 11절](docs/API_SPEC.md#11-사건-토론-현재-로컬-동작과-향후-계약)에 있습니다.

## 데이터와 API 명세

- 목데이터: [`src/data/mock/fixtures/catalog.js`](src/data/mock/fixtures/catalog.js), 사건 6개·문서 14개·종목 8개
- 기준일: 2025-06-24, 일별 차트: 2025-06-01~24
- [프론트엔드 API 계약](docs/API_SPEC.md)
- [OpenAPI 3.0 명세](docs/openapi.yaml)
- [화면·컴포넌트 안내](docs/UI_GUIDE.md)
- [검증 결과](docs/VALIDATION.md)

API 명세는 화면 연동을 위한 **제안 계약**입니다. 공통 비동기 mock/API 조회 클라이언트는 구현되어 있으나 실제 백엔드는 연결하지 않았습니다. 목데이터의 소식·편집 내역·AI 해석·가격·관계는 실제 사건의 사실 확인 자료가 아니며, Wikipedia 링크는 주제의 원문을 읽기 위한 링크입니다.

설정 파일은 `frontend/.env`이며 기본값은 `VITE_DATA_SOURCE=mock`, `VITE_API_BASE_URL=/api/v1`입니다. API 연결 시 source와 주소를 변경하고 개발 서버를 재시작하거나 배포 결과물을 다시 빌드합니다. [구조 안내](../docs/frontend/ARCHITECTURE.md), [데이터 전환과 검증 결과](../docs/frontend/DATA_SOURCE.md)를 참고하세요.

## 검증 명령

최초 한 번 테스트용 Chromium을 설치합니다.

```powershell
npx.cmd playwright install chromium
npm.cmd run lint
npm.cmd run test:data
npm.cmd run test:e2e
npm.cmd run test:api
npm.cmd run test:a11y
npm.cmd run test:contract
npm.cmd run build
```

`test:e2e`는 mock 모드 5174, `test:api`는 API 모드 5175의 전용 서버를 시작합니다. 테스트 전에 해당 포트가 비어 있어야 합니다. `test:a11y`와 아래 캡처 스크립트는 실행 중인 `npm.cmd run dev`를 사용합니다.

```powershell
npm.cmd run format:check
node scripts/capture.mjs
node scripts/capture-discussion.mjs
```

배포 파일 검사는 별도 터미널에서 `npm.cmd run preview`를 실행한 뒤 `npm.cmd run test:production`으로 수행합니다.

화면 캡처는 상위 작업 폴더의 `.impeccable/review/`, 테스트 결과는 `frontend/test-results/`에 저장됩니다. 반응형·키보드 검증은 자동화한 범위에 한하며, 실제 기기나 모든 보조기술의 동작을 보증하지 않습니다.

## 파일 구성

```text
src/
  app/             앱 조립·라우팅·공통 레이아웃
  pages/           온보딩·탐색·사건·문서·종목·보관함과 전용 코드
  features/        저장·통합 검색
  components/      공유 사건/문서 UI·차트·범용 UI
  data/            공통 비동기 조회·화면 로더·mock/API 구현
  lib/             순수 표시 함수
  styles/          워크스페이스·공통 상세 스타일
```

온보딩은 지연 로딩되므로 서비스 경로로 바로 진입할 때 Three.js 번들을 먼저 내려받지 않습니다. 온보딩 자체의 WebGL 번들은 큰 청크 경고가 남아 있습니다.
