# 프론트엔드 데이터 연결

2026-09-15 · WP-95/-96/-97/-98

프론트는 Spring의 현재 **8개 GET DTO**를 공통 계약으로 쓴다. mock도 같은 응답 봉투를 반환한다. 이전 `/events`, `/entities`, `/categories`, `/search` 제안 경로는 현재 클라이언트에서 사용하지 않는다. 실제 서버의 운영·파이프라인 완료 여부는 이 변경과 별개다.

## 실행 설정

`frontend/.env.example`을 `.env`로 복사한다. 기본 로컬 실행은 mock이다.

```dotenv
VITE_DATA_SOURCE=mock
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8080
```

Spring 연동은 `VITE_DATA_SOURCE=api`로 변경하고 개발 서버를 재시작한다. `/api/v1` 요청은 Vite proxy가 `VITE_API_PROXY_TARGET`으로 전달한다. `vite preview`도 이 proxy 설정을 상속하지만 운영 서버 용도는 아니다. 정적 `dist/` 배포에는 별도 reverse proxy나 CORS가 허용된 API 절대 주소가 필요하다. `VITE_` 값에는 비밀키를 넣지 않는다.

루트 `docker-compose.yml`의 frontend는 기본 `api`, `/api/v1`, proxy target `http://backend:8080`을 사용한다. 컨테이너 이름은 Vite 서버가 해석하며 브라우저에 backend 컨테이너 주소를 직접 넘기지 않는다. Compose가 실행됐다는 사실만으로 데이터가 채워졌다고 볼 수 없다.

환경변수는 빌드 시 반영된다. 배포 모드를 바꿀 때는 재빌드한다. 잘못된 source/base URL은 설정 오류로 표시하며 API 실패 시 mock으로 전환하지 않는다.

## 요청과 데이터 소유권

| 공통 메서드       | HTTP 요청                                                | 화면                     |
| ----------------- | -------------------------------------------------------- | ------------------------ |
| `listIssues`      | `/issues?snapshotTs=&status=&source=&offset=&limit=`     | 이슈 탐색                |
| `getIssue`        | `/issues/{id}`                                           | 이슈 상세·부모 이슈 확인 |
| `listIssueStocks` | `/issues/{id}/stocks?limit=`                             | 연관 종목                |
| `listStocks`      | `/stocks?q=&sector=&exchange=&hasIssues=&offset=&limit=` | 종목 탐색·상단 종목 검색 |
| `getStock`        | `/stocks/{ticker}`                                       | 종목 상세                |
| `listStockIssues` | `/stocks/{ticker}/issues`                                | 종목의 관련 이슈         |
| `listSnapshots`   | `/issues/snapshots?from=&to=&source=`                    | 시간 선택                |
| `getPulseMap`     | `/issues/map?snapshotTs=&source=`                        | 펄스맵                   |

경로에는 공통 base URL이 앞에 붙는다. 일반 성공은 `{data}` 또는 `{data,meta}`다. 일반 목록 두 개만 `meta.pagination`을 갖는다. `meta.dataMode`는 wire 필수가 아니며 실행 모드는 로컬 설정에서 구분한다. 요청별 AbortSignal과 수명 검사로 이전 응답이 새 화면을 덮지 못하게 한다.

`data/api`와 `data/mock`은 raw DTO를 반환한다. 공통 데이터 경계는 null·생략·ID 정밀도·pagination·그래프 참조를 검사하고 화면에 필요한 이름을 연결한다. UI에 없는 가격·뉴스·시계열을 주입하지 않는다. 페이지는 fixture를 직접 import하지 않는다.

이슈·종목 탐색은 현재 페이지를 요청하고 pagination의 total/hasMore를 표시한다. 서버 전체 목록을 시작할 때 전부 모으지 않는다. 보관함은 저장 ID별 상세만 조회한다. 관련 종목의 5개 preview, 최대 100개 관련 목록, 종목별 최대 50개 역목록은 각각 다른 한도이며 전체 건수로 추정하지 않는다.

## 로컬 상태와 데이터 경계

mock 저장 키는 `wikipulse.savedEvents`, `wikipulse.savedStocks`, `wikipulse.discussion.{id}`다. API 모드는 `wikipulse.api.` 접두사로 분리한다. 이 기능은 로그인·서버 공유가 아니다. API 토론은 자동 예시 없이 시작하고, mock 토론 예시는 합성임을 표시한다.

HTTP 응답을 받았다는 이유로 LIVE나 확정 상태를 만들지 않는다. `source=live/replay`, 서버 `status`, 지도 집계 구간·결측 상태를 각각 사용한다. 관련 협의 항목은 [API_DECISIONS.md](API_DECISIONS.md)에 있다.

## 검증

기본 이슈 목록은 서버가 고른 최신 시점을 사용한다. 출처를 지정하면 `listSnapshots({source})`의 최신 완료 시점을 `listIssues`에 전달한다. 완료 시점이 없으면 빈 목록을 표시한다. 이전/다음 페이지는 응답 `meta.snapshotTs`를 유지하고, 상태/출처 필터를 바꾸면 시점을 다시 선택하며 offset을 0으로 돌린다.

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run test:data
npm.cmd --prefix frontend run test:contract
npm.cmd --prefix frontend run build
$env:WIKIPULSE_E2E_PORT = '5184'
npm.cmd --prefix frontend run test:e2e
Remove-Item Env:WIKIPULSE_E2E_PORT
npm.cmd --prefix frontend run test:api
```

`test:contract`는 raw mock 응답을 현재 OpenAPI로 검사한다. `test:api`는 Playwright가 HTTP를 가로채는 FE 검사다. 실제 Spring·PostgreSQL·데이터 생산기 통합 검증은 별도로 기록해야 한다. 접근성은 mock dev 서버 5174, production smoke는 mock build의 preview 서버 4174가 필요하다. 결과와 미실행 범위는 [VALIDATION.md](../../frontend/docs/VALIDATION.md)에 남긴다.
