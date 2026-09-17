# WikiPulse 프론트엔드

React/Vite 앱. 온보딩, 펄스맵, 이슈·종목 탐색과 상세를 제공한다. 브라우저 로컬 보관함·토론 UI도 남아 있지만 서버·계정 기능이 아닌 시연용 프로토타입이며 MVP 완료 범위에 포함하지 않는다. mock과 API 모드는 Spring의 현재 8개 GET DTO를 공통으로 쓴다. 실제 데이터 생산·배포·서버 연동 검증 상태는 별도로 확인한다.

## 실행

Node.js 22.12 이상 권장(Vite 지원 범위: `^20.19.0 || >=22.12.0`). `frontend`에서 실행한다.

```powershell
npm.cmd ci
# .env가 없는 새 체크아웃에서만 복사
Copy-Item .env.example .env
npm.cmd run dev
```

온보딩은 http://127.0.0.1:5174/, 서비스는 http://127.0.0.1:5174/#/pulse 이다. `VITE_DATA_SOURCE=mock`은 백엔드 없이 실행된다. Spring 연결은 `api`로 변경하고 Vite를 재시작한다.

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8080
```

`npm.cmd run build`는 `dist/`를 만들고, `npm.cmd run preview`는 4174에서 확인한다. Vite dev/preview는 API proxy를 사용한다. 정적 배포에는 별도 reverse proxy 또는 CORS가 허용된 API URL이 필요하다. Vite preview 자체는 운영 서버가 아니다.

## 화면과 데이터

- [11개 페이지·URL](../docs/frontend/PAGES.md): 기존 hash routing을 유지한다.
- [현재 API](docs/API_SPEC.md) / [OpenAPI](docs/openapi.yaml): 8개 읽기 경로와 null·페이지네이션.
- [환경 설정·구조](../docs/frontend/DATA_SOURCE.md) / [협의 항목](../docs/frontend/API_DECISIONS.md).
- [합성 데이터 출처와 범위](../docs/frontend/MOCK_HISTORY.md): 실제 문서 식별자를 바탕으로 만든 고정 시연 데이터이며 실제 신호·주가가 아니다.

상단 `Ctrl/Cmd+K` 검색은 종목명·티커를 검색한다. 이슈 목록은 서버가 지원하는 필터와 페이지 단위 조회를 쓴다. 지도는 날짜·출처·슬라이더·HOT/NEW·키보드 선택·확대/이동을 제공한다. 상세는 제공된 요약·멤버·관련 종목만 표시하며 없는 가격·뉴스·시계열을 보충하지 않는다.

보관함·토론은 이 브라우저에만 저장되는 UI 프로토타입이다. 다른 사용자에게 전송되지 않고 서버에 보존되지 않으며, 요구사항의 회원·관심종목·알림·공개 토론 기능을 구현한 것으로 보지 않는다. API 키는 `wikipulse.api.*`, mock 키는 기존 `wikipulse.*`로 분리한다. API 모드 토론은 자동 예시 없이 시작한다. 로그인·회원가입·마이페이지는 안내 화면이며 실제 인증이나 계정 동기화를 수행하지 않는다.

## 검증

```powershell
npx.cmd playwright install chromium
npm.cmd run lint
npm.cmd run test:data
npm.cmd run test:contract
npm.cmd run test:e2e
npm.cmd run test:api
npm.cmd run build
```

mock E2E는 기본 5174(`WIKIPULSE_E2E_PORT`로 변경), API E2E는 5175를 사용한다. API E2E는 응답 가로채기 검사다. `test:a11y`는 실행 중인 mock dev 5174, `test:production`은 mock build의 preview 4174가 필요하다. [검증 기록](docs/VALIDATION.md)에 실제 실행·미실행 범위를 남긴다.

온보딩은 lazy loading이다. 서비스 직접 진입에서 Three.js를 먼저 받지 않으며, 온보딩 번들 자체의 500 kB 경고와 실기기 GPU·Safari/Firefox 검증은 별도로 관리한다.
