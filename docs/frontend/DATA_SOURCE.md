# Mock/API 전환과 백엔드 연결

기준일: 2026-09-08. 현재 기본 모드는 `mock`이다. 공통 비동기 조회 인터페이스와 HTTP 클라이언트는 구현되어 있으며, 실제 백엔드 서버는 아직 연결하지 않았다.

2026-09-10 목데이터 확장: 실제 위키 문서와 현재 Nasdaq-100 목록을 사용한 2025-09-01~2026-09-10 시연 이력을 제공한다. `history.js`에서 동일한 문서/날짜 지표로 지도·리포트를 만들고 과거 리포트 종목 관계도 반환한다. 데이터 구성·출처·운영 파이프라인과의 차이는 [MOCK_HISTORY.md](./MOCK_HISTORY.md)를 따른다. 이 변경은 mock 모드에만 적용된다.

2026-09-09 페이지 변경: [PAGES.md](PAGES.md)의 URL로 갱신했고 단일 문서 상세 화면을 제거했다. 아래 데이터 계약은 유지한다. 전체 검색은 같은 요청으로 받은 결과에서 이슈·종목만 표시한다. 이 문서의 2026-09-08 테스트 수치는 당시 기록이며 최신 결과는 [검증 기록](../../frontend/docs/VALIDATION.md)에 있다.

## `.env` 설정

설정 파일은 **`frontend/.env`**다. `.env.example`은 Git에 공유하는 예시이며 `.env`는 기존 `.gitignore`의 `.env*` 규칙으로 제외한다. 설정 파일이 없는 새 체크아웃에서만 다음을 실행한다.

```powershell
Copy-Item frontend/.env.example frontend/.env
```

```dotenv
# frontend/.env: 백엔드 없이 개발
VITE_DATA_SOURCE=mock
VITE_API_BASE_URL=/api/v1
```

```dotenv
# frontend/.env: 서버 연결
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=https://backend.example.com/api/v1
```

`VITE_DATA_SOURCE`는 생략 시 `mock`, 허용값은 `mock`/`api`뿐이다. 잘못된 값은 조회 화면에서 설정 오류로 표시한다. API 주소는 `/api/v1` 같은 동일 origin 경로나 HTTP(S) 절대 주소다. 끝의 `/`는 제거하고 endpoint를 붙인다. `/api/v1` 기본값은 Vite에 API 서버가 생긴다는 뜻이 아니며, 별도 proxy를 자동 설정하지 않는다.

개발 서버에서는 변경 후 재시작한다. 배포 결과물은 다시 빌드해야 한다. 이 설정은 앱 실행 중 토글이 아니다. Vite의 셸 환경변수 또는 별도 mode 파일에 같은 키가 있으면 `.env`보다 우선할 수 있으므로 기존 설정도 확인한다. `VITE_` 값은 브라우저에 공개되므로 비밀키를 넣지 않는다. [Vite 환경변수 문서](https://vite.dev/guide/env-and-mode)

## 전환하는 데이터와 유지하는 기능

| 영역 | 조회 방식 |
|---|---|
| 카테고리 | listCategories |
| 이슈 탐색·상세 | listEvents / getEvent |
| 펄스맵 시점 목록·그래프 | listSnapshots / getPulseMap — /api/v1/issues/snapshots, /issues/map ([계약](PULSE_MAP.md)) |
| 기존 문서 목록·상세 데이터 계약(독립 페이지 제거) | listEntities / getEntity |
| 종목 목록·상세 | listStocks / getStock |
| 통합 검색 | searchWorkspace |
| 보관함 내용 조회 | 저장 ID별 getEvent / getStock; 확인된 404는 표시 제외 |
| 보관함 저장·해제 | 기존 localStorage, 서버 전송 없음 |
| 토론 읽기·작성·답글·공감 | 기존 예시와 브라우저 저장, 서버 전송 없음 |

페이지와 URL은 두 모드에서 동일하다. API 호출 실패 시 fixture로 대체하지 않으며, 출처가 `mock`인 응답은 API를 통해 받아도 데모로 표시한다. `meta.dataMode`가 알려지지 않은 값이면 출처 확인 안내를 표시하고 `LIVE`라고 단정하지 않는다. 문서 관계도와 지도 간선은 계속 설명용 조형이며 실제 관계의 증거로 바뀌지 않는다.

## 공통 계약과 응답 처리

`src/data/contracts.js`에 JSDoc 인터페이스가 있다. 카테고리는 `listCategories({ signal })`, 목록/검색은 `method(params, { signal })`, 단건은 `method(id, { signal })` 형식이며 모두 Promise를 반환한다.

```js
const response = await dataClient.getEvent(eventId, { signal });
// { data: Event, included: { entities: [...], stocks: [...] }, meta: {...} }
```

필드와 단위는 [API 제안 명세](../../frontend/docs/API_SPEC.md), [OpenAPI](../../frontend/docs/openapi.yaml)를 따른다. 목 구현도 실제 fixture에서 요약/상세 응답을 구분하고 검색·기간·정렬·페이지네이션·404를 처리한다. 반환 객체는 복제하여 화면 수정이 원본 fixture에 누적되지 않도록 했다.

HTTP 처리는 `data/api/http.js`, endpoint 연결은 `client.js`, 응답 변환은 `adapters.js`에 있다. 동적 경로는 인코딩하고 쿼리는 URLSearchParams로 만든다. HTTP 오류, JSON 오류, 네트워크 실패를 DataError로 전달한다. 어댑터는 응답 봉투·배열·페이지 정보의 기본 형태를 검사한다. 전체 도메인 필드의 런타임 검증기는 아니므로 필수 필드와 단위는 서버 계약 및 테스트로 확인해야 한다.

`resources.js`는 필요한 목록의 모든 페이지를 조회하고 연관 객체를 ID로 합친다. 현재 필터·정렬은 화면에서 유지하므로 첫 페이지에서 멈추지 않는다. 중복 ID, 진행하지 않는 페이지, 조회 중 바뀐 total/기준일/출처는 오류로 처리한다. 상세 페이지는 단건 응답을 사용하고, 뉴스·변경 내역은 상세 응답에 포함된 배열을 로컬 필터링한다. 별도 뉴스/변경 내역 endpoint는 현재 UI에서 호출하지 않는다.

조회 훅은 로딩/오류/재시도, AbortController 취소와 오래된 응답 무시를 처리한다. 검색은 250ms 동안 입력이 멈춘 뒤 요청하고 최대 7개를 표시한다. 전역 장기 캐시나 자동 재시도는 추가하지 않았다.

## 실제 백엔드 연결 순서

1. 백엔드 팀과 제안 endpoint, 필수 필드, 단위, `included`, 페이지네이션, 출처 메타데이터를 확정한다. 현재 OpenAPI의 출처 값은 `mock`으로 제한되어 있으므로 실제 출처 모델 도입 시 명세도 갱신한다.
2. 응답 구조가 다르면 API 어댑터와 테스트에서 맞춘다. 화면이 필요로 하는 정보 자체가 없는 경우는 어댑터만으로 해결할 수 없다.
3. `.env`를 `api`와 실제 주소로 바꾸고 서버를 재시작한다. 교차 origin이면 백엔드가 프론트 origin의 CORS를 허용해야 한다. 현재 인증·토큰·쿠키 전달 정책은 구현하지 않았다.
4. 목록·상세·검색·실패 복구를 실제 서버에서 검증한다. 페이지별 환경변수 분기나 fixture import를 추가하지 않는다.

현재 전체 목록 수집 방식은 기존 UI 동작을 보존하기 위한 선택이다. 큰 데이터셋에서는 서버 필터/페이지네이션 UI 또는 별도 집계 계약이 필요할 수 있다. 실제 근거 URL, 원문 revision ID, 결측/기준선, 가격 시점 등 확장 요구는 기존 API 명세 8절에 유지했다.

## 검증과 실행

저장소 루트에서 실행한다. E2E는 각 모드를 셸 환경변수로 명시하므로 개발자의 `.env`를 수정하지 않는다. Mock E2E는 5174, API E2E는 5175 포트가 비어 있어야 하며 기존 서버를 재사용하지 않는다.

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run test:data
npm.cmd --prefix frontend run test:contract
npm.cmd --prefix frontend run test:e2e
npm.cmd --prefix frontend run test:api
npm.cmd --prefix frontend run build
```

접근성 검증은 별도 터미널의 Mock dev 서버(5174), production smoke는 Mock build 후 preview 서버(4174)가 필요하다.

```powershell
npm.cmd --prefix frontend run dev
# 다른 터미널
npm.cmd --prefix frontend run test:a11y
```

```powershell
npm.cmd --prefix frontend run preview
# 다른 터미널
npm.cmd --prefix frontend run test:production
```

아래는 2026-09-08 실행 결과다. API E2E는 Playwright가 HTTP 요청에 테스트 응답을 제공한 결과이며 실제 백엔드 가용성·인증·CORS·데이터 정확성 검증이 아니다.

| 검증 | 결과 |
|---|---|
| lint / format:check | 통과 |
| 데이터 계층 테스트 | 6개 통과: 설정·OpenAPI 응답 호환·필터/404/취소·다중 페이지·화면 조합·HTTP 오류 |
| API 계약 검증 | 13 paths, 14 operations, 37 schemas, 34 fixtures 검증 통과 |
| Mock E2E | 28개 통과: 기존 동선·검색·저장·토론·해시·모바일·온보딩 폴백 |
| API E2E | 7개 통과: HTTP 페이지 데이터·전체 페이지 수집·출처 표시·오류/재시도·지연/순서 역전·로컬 토론 |
| 접근성 | 1440/820/390/320px, 32개 화면·상태에서 자동 검사 위반 0 |
| build | mock/API 설정 모두 성공 |
| production smoke | 8개 경로 통과, 조회 API 요청 0, 온보딩 종료 정상, 브라우저 오류 0 |
| 브라우저 화면 확인 | API 테스트 응답 기반 데스크톱 종목 목록·모바일 토론 및 Mock 배포 빌드 캡처 확인 |

`frontend/test-results/accessibility.json`, `production-smoke.json`에 자동 검사 결과가 남는다. `test-results/api/`, `test-results/visual/`의 캡처는 로컬 검증 산출물이다. Mock 배포의 직접 진입 스크립트는 앱과 목 클라이언트뿐이며 OnboardingPage/Three.js 청크는 로드하지 않았다.

이 Windows 실행 환경에서는 Playwright 테스트 완료 후 Vite 자식 프로세스 정리가 대기하는 현상이 있어, 실행한 검증 서버 PID만 확인하여 종료한 후 테스트 종료 코드 0을 확인했다. 테스트 중인 서버나 다른 사용자의 서버를 포트 번호만 보고 종료하지 않는다.

온보딩 WebGL 청크의 500kB 경고는 기존과 같이 남아 있다. 작업 중 실행한 검증 서버는 종료했으며, 완료 시 5174·5175·4174 포트에 LISTENING 프로세스가 없음을 확인했다.
