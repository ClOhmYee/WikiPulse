# 프론트엔드 검증 기록

## 2026-09-15 — NEW 중심 펄스맵과 전체화면 탐색

대상: WP-101. 프론트엔드 표시·배치·탐색 변경이며 서버의 HOT/NEW 데이터 계약은 유지한다.

- lint, build, 변경 파일 Prettier, `git diff --check` 통과. 기존 Onboarding 906.71 kB 청크 경고 유지.
- `test:data` 27개 통과: 500노드 배치, 점수에 따른 반지름, 중요도와 중심 거리, 클러스터 충돌 방지, 과거 탐색 순서와 무관한 순위 검증.
- `test:contract` 통과: 8개 GET·24개 스키마·290개 응답, 375개 스냅샷 및 부하 그래프.
- `playwright test e2e/pulse.spec.js` 3개 통과: NEW만 표시, NEW가 없는 시점, 날짜 탐색, 일반·전체화면 패널의 리포트 이동, 오른쪽 패널, Esc/닫기/포커스 복귀, 모바일 표시.
- `playwright test --config playwright.api.config.js pulse.spec.js` 5개 통과: **HTTP 가로채기**로 숫자 ID 이동·nullable 필드·응답 경합·오류 복구·500노드/1,000간선 선택 검증. 실제 Spring/DB를 호출하지 않았다.
- 1440px 데스크톱 및 390px 모바일의 일반/전체화면 캡처 확인. Impeccable 스캔은 기존 지도 색상과 전체화면 배경 dim 처리의 DESIGN.md 팔레트 advisory를 보고했다. 기존 화면 색상 유지와 배경 구분을 위한 의도된 선택이다.
- Playwright의 테스트 본문 완료 후 Windows 샌드박스에서 Vite 종료가 대기하여, 이번 검증에서 생성한 서버만 별도로 종료했다.

## 2026-09-15 — 실제 8개 GET DTO와 mock/API 화면 정합

대상: WP-95/-96/-97/-98. Spring 코드 기준 `f3c0160`, Windows · Node.js 24.18.0 · Playwright Chromium. 현재 연결 계약은 [API_SPEC.md](API_SPEC.md), 남은 서버/AI 협의는 [API_DECISIONS.md](../../docs/frontend/API_DECISIONS.md)를 따른다. 아래 과거 날짜의 기록은 당시 실행 결과이며 현재 API·화면 범위가 아니다.

| 검사                                    | 결과                | 범위                                                                                                                                                                                       |
| --------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `npm.cmd run test:data`                 | 26개 통과           | raw DTO 검증, safe-integer ID, null/생략/0, 페이지 범위·시점 고정, source별 완료 시점 선택, 저장 alias·종목 역연결, 그래프 무결성                                                          |
| `npm.cmd run test:contract`             | 통과                | 실제 8개 GET·24개 스키마·raw mock 응답 290개(최신 이슈 36개/종목 102개), 지도 375개와 500노드·1,000간선 stress, nullable label/issueKey·wire dataMode 생략                                 |
| `npm.cmd run test:e2e`                  | 27개 통과, exit 0   | 목록 20개씩 이동, 현재 페이지 검색, 상세 미제공 상태, 지도→과거 이슈→연관 종목→종목→이슈, 저장·중복 alias 해제, 로컬 토론, 경로/키보드/390px/태블릿/온보딩                                 |
| `npm.cmd run test:api`                  | 12개 통과, exit 0   | **HTTP 가로채기**. 실제 형태 DTO, source별 스냅샷·페이지 시점 고정, null/생략/0, 숫자 ID 지도→상세, API/mock 저장 분리, API 빈 토론, 500/잘못된 응답/네트워크/재시도·오래된 검색 응답 차단 |
| `npm.cmd run test:a11y`                 | 48개 상태, 위반 0개 | mock 모드, 11개 경로×1440/820/390/320px + 이슈 토론 확장. axe WCAG 2 A/AA·2.1 AA 규칙 자동 검사                                                                                            |
| `npm.cmd run test:production`           | 11개 경로 통과      | mock build의 preview 4174, 데이터 API 요청 없음, 런타임 오류 없음, 직접 Pulse 진입 시 Onboarding 청크 미로딩, 온보딩에서 탐색 진입                                                         |
| `npm.cmd run build`                     | 통과                | Onboarding 청크 906.71 kB / gzip 242.80 kB, 기존 500 kB 초과 경고 유지                                                                                                                     |
| `npm.cmd run lint` · 변경 파일 Prettier | 통과                | 변경 소스·E2E·검증 스크립트·문서 검사. 전체 저장소의 기존 형식 경고를 모두 수정한 작업은 아님                                                                                              |
| `docker compose config --quiet`         | 통과                | Compose 정적 설정 검사. Docker 엔진이 없어 컨테이너 실행은 검증하지 못함                                                                                                                   |
| Vite preview proxy 경로 검사            | 통과                | preview 4174→임시 HTTP stub 8080에 `/api/v1/issues?offset=0&limit=20`이 유지됨. `{proxyForwarding:true,pathPreserved:true,realBackend:false}`. Spring/DB 검사 아님                         |
| 문서 정합 스캔 · `git diff --check`     | 통과                | 현재 FE 계약과 과거 기록의 경계, URL·원시 DTO·미제공 기능 설명 확인. 스캔의 기존 BE/인프라 역사 문서 항목은 이번 범위 밖                                                                   |

1440×1000·390×844에서 이슈 목록/상세·종목 목록·Pulse Map의 8개 화면을 캡처하여 확인했다. 가로 넘침과 페이지 오류는 0개였다. 자동 접근성 검사는 수동 스크린리더·실기기 GPU·Safari/Firefox 검증을 대신하지 않는다. 성능 수치는 합성 fixture 환경이며 실제 운영 데이터 부하를 보장하지 않는다.

mock E2E는 5174, API E2E는 5175를 사용했다. Windows에서 mock E2E의 모든 테스트 종료 후 Vite 종료 대기가 남아 접근성 검사까지 완료한 뒤 이번 실행의 PID와 5174 리스너를 확인하고 해당 Vite만 종료했다. 최종 E2E 종료 코드 0을 회수했다. 캡처·JSON은 ignored `test-results/`에 있으며 다음 실행에서 바뀔 수 있다.

실제 Spring·PostgreSQL·수집/탐지/클러스터/AI worker를 연결한 end-to-end 검증은 **미실행**이다. 기존 저장 행의 DISCARDED 정책, 과거 members 지표 범위, source 생산 배선, 점수 v1과 WP-93 산식 변경의 일치·재적재 여부는 FE mock/HTTP 검사로 확인할 수 없다. 구현과 기존 적재 기록만으로 운영 연결 완료라고 보고하지 않는다.

재현 명령은 [DATA_SOURCE.md](../../docs/frontend/DATA_SOURCE.md#검증)를 따른다. `test:a11y`는 mock dev 5174, `test:production`은 mock build + preview 4174를 먼저 실행한다. API E2E는 자체 서버와 intercepted 응답을 사용한다. 실제 서버 검증 시에는 별도 환경과 실행 증거를 남긴다.

## 2026-09-10 — 실제 Wikipedia 기반 연간 목데이터

대상: WP-78. Windows · Node.js · Playwright Chromium. [데이터 구성과 파이프라인 차이](../../docs/frontend/MOCK_HISTORY.md)를 함께 참고한다.

| 검사                        | 결과           | 범위                                                                                                                                     |
| --------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 출처 갱신 스크립트          | 완료           | 공개 MediaWiki API로 요청 제목 298개의 정규 문서 ID·원문 URL·최초 리비전 확인, Nasdaq-100 증권 102개와 구성표 리비전 보관                |
| `npm.cmd run test:data`     | 15개 통과      | 고유 클러스터 문서 287개, 월별 리포트 468개, 375일의 클러스터 리포트 9,698개. 문서 생성일·동일 날짜 수치·합계·리포트·종목·저장 연결 검사 |
| `npm.cmd run test:contract` | 통과           | 기존 계약 fixture 867개, 날짜별 지도 375개, 500노드·1,000간선 스트레스 fixture                                                           |
| `npm.cmd run test:e2e`      | 34개 통과      | 연간 슬라이더 양끝·연도 경계·날짜 선택, 과거 지도 → 리포트 → 종목, 모든 주제·대표 월·102개 종목 상세, 기존 화면 회귀                     |
| `npm.cmd run test:api`      | 11개 통과      | HTTP 응답 가로채기, 페이지네이션·지연 응답·오류·재시도·대규모 지도 검사. 라이브 백엔드 검증 아님                                         |
| `npm.cmd run lint`          | 통과, 경고 0개 | 최종 모바일 배치 변경 포함                                                                                                               |
| 변경 소스 Prettier 검사     | 통과           | 전체 `format:check`에는 이번에 수정하지 않은 기존 파일 45개의 형식 경고가 남아 있음                                                      |
| `npm.cmd run build`         | 통과           | mock 클라이언트 95.78 kB, gzip 28.02 kB. 기존 온보딩 906.33 kB 청크 경고 유지                                                            |

1440px 데스크톱 전체/선택 화면과 390px 모바일 전체/선택 화면을 캡처해 확인했다. 모바일 36개 클러스터를 5열로 배치하고 선택한 묶음을 확대한다. 가로 넘침과 지도 아래 상세 패널 위치는 자동 검사했다. 캡처는 `test-results/pulse-desktop.png`, `pulse-desktop-selected.png`, `pulse-mobile.png`, `pulse-mobile-selected.png`이며 이후 테스트 실행 시 초기화될 수 있다. 전체 접근성 감사·실기기 GPU·Safari/Firefox는 이번 검증 범위에 없다.

목 모드 검증은 포트 5184, API 모드는 5175를 사용했다. Windows에서 검사 종료 뒤 Vite 정리가 대기 상태로 남아, 이번 실행의 PID와 명령줄을 확인한 후 해당 Vite만 종료하고 각 테스트의 종료 코드 0을 회수했다. 기존 개발 서버 5174는 유지했다.

실제 Wikipedia 본문·편집 기록·조회수·주가·자동 클러스터링 결과를 수집한 검사가 아니다. 문서 식별자는 실제이며, 급증 수치·관계·리포트·가격은 합성이다. 현재 Nasdaq-100 목록을 과거 전체 기간에도 고정 적용했다.

## 2026-09-09 — 펄스맵 시간 탐색·문서 그래프

대상: WP-37, WP-71, WP-72, WP-73. Windows · Node.js · Playwright Chromium에서 검증했다. 범위는 프론트·합성 mock·HTTP 계약이며, 실제 Spring API와 파이프라인 연결은 WP-74/75의 후속 작업이다. [구현·계약 설명](../../docs/frontend/PULSE_MAP.md)을 함께 참고한다.

| 검사                                | 결과               | 범위                                                                                               |
| ----------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------- |
| `npm.cmd run lint`                  | 통과, 경고 0개     | 최종 SVG·컴포넌트 변경 포함                                                                        |
| `npm.cmd run test:data`             | 12개 통과          | 기존 데이터·라우팅 7개, 스냅샷/NEW/KST/무결성/API/배치 5개                                         |
| `npm.cmd run test:contract`         | 통과               | 기존 OpenAPI + Pulse OpenAPI 3.0.3, 7개 시점 및 대규모 fixture                                     |
| `npm.cmd run test:e2e`              | 34개 통과 (30.5초) | 카드/리스트 상태 보존, 시간 이동, 지도 선택·확대·드래그, 기존 페이지 회귀                          |
| 지도 관련 E2E 재검증                | 3개 통과 (6.8초)   | 최종 제목 줄바꿈 수정 후 모바일 제목 겹침, 선택·키보드·시점·확대 확인                              |
| `npm.cmd run test:api`              | 11개 통과          | 실제 HTTP 클라이언트에 Playwright 응답 가로채기. 지연 응답 역전·실패·재시도·계약 오류·fixture 분리 |
| `npm.cmd run build`                 | 종료 코드 0        | 최신 PulsePage 청크 34.12 kB. 기존 온보딩 청크 906.33 kB 경고 유지                                 |
| 문서 정합 스캔 · `git diff --check` | 확인 완료          | 페이지 역할·API 현재 상태·폐기된 토글 및 변경 공백 확인                                            |

20개 클러스터·500개 문서·1,000개 간선 fixture를 모두 렌더링했다. Node에서 초기 배치 계산 약 90ms를 관측했고, Chromium에서 지도 로딩·문서 선택·확대가 테스트의 3초 한도 안에 완료되었다. 특정 개발 환경의 합성 데이터 측정이며 실기기나 운영 데이터의 성능 보장은 아니다. 누락 지표는 0과 구분하고, 고립 노드는 유지하며 잘못된 참조·중복 간선·미래 지표는 응답 오류로 검증했다.

1440×1000 데스크톱의 전체 지도·선택 상태와 390×844 모바일 화면을 직접 캡처해 확인했다. 모바일은 2열 그래프와 지도 아래 패널을 사용하며 긴 제목은 줄바꿈한다. 화면 가로 넘침과 제목끼리의 겹침을 검사했다. 파일은 `test-results/pulse-desktop.png`, `pulse-desktop-selected.png`, `pulse-mobile.png`이며 이후 Playwright 실행 시 초기화될 수 있다.

전체 axe·프로덕션 smoke·실기기 GPU·Safari/Firefox는 이번 변경에서 다시 검증하지 않았다. API 모드는 `/issues/snapshots`와 `/issues/map`의 응답을 가로챈 검사이며 서버 구현 완료를 뜻하지 않는다. 실패 시 mock 자동 대체가 없음을 확인했다.

테스트는 기존 5174 개발 서버와 별개로 mock 5176/API 5175를 사용했다. 재현은 아래 명령을 사용한다. 서버를 정리할 때는 이번 실행에서 시작한 프로세스인지 먼저 확인한다.

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run test:data
npm.cmd --prefix frontend run test:contract
npm.cmd --prefix frontend run build
$env:WIKIPULSE_E2E_PORT = '5176'
npm.cmd --prefix frontend run test:e2e
Remove-Item Env:WIKIPULSE_E2E_PORT
npm.cmd --prefix frontend run test:api
```

## 2026-09-09 — 페이지 URL 재구성 검증

대상: WP-70의 로컬 작업 트리, Windows · Node.js · Playwright Chromium. 페이지 구성의 정본은 [PAGES.md](../../docs/frontend/PAGES.md)다. 아래 결과는 2026-09-09 구현 작업에서 실행한 결과이며, 배포·병합 완료를 뜻하지 않는다.

| 검사                                                        | 결과           | 확인 범위                                                                    |
| ----------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------- |
| `npm.cmd run lint`                                          | 통과           | `src` ESLint, 경고 0개                                                       |
| `npm.cmd run test:data`                                     | 7개 통과       | 기존 데이터 계약 6개 + URL 정규화 1개                                        |
| `npm.cmd run test:contract`                                 | 통과           | 기존 OpenAPI 제안의 경로 13개·작업 14개·스키마 37개·참조 138개, fixture 34개 |
| `npm.cmd run test:e2e`                                      | 31개 통과      | 토론 6개·예외/데이터 7개·라우팅 4개·워크스페이스 14개                        |
| `npm.cmd run test:api`                                      | 7개 통과       | Playwright가 응답을 대체하는 HTTP 모드. 실제 Spring 서버 연동 검증 아님      |
| `npm.cmd run build`                                         | 빌드 생성 확인 | 기존 온보딩 청크 약 906.30 kB, 500 kB 경고 유지                              |
| `node node_modules/vite/bin/vite.js build --logLevel error` | 종료 코드 0    | PowerShell의 stderr 경고 처리와 빌드 실패를 구분해 재확인                    |
| `git diff --check`                                          | 통과           | 변경 파일 공백 검사                                                          |

라우팅 검증은 새 계정 경로의 직접 접속·새로고침·상호 이동, 티커 대문자 및 마지막 슬래시 정규화, 검색 쿼리 보존, 이슈→리포트→연관주식의 ID 유지, 뒤로·앞으로 이동을 포함한다. 이전 경로는 페이지 없음 안내로 복구하고, 리포트의 근거 링크는 위키백과 원문을 새 탭으로 가리킨다. 인증 안내 화면은 비밀번호를 받거나 쓰기 요청을 보내지 않는다.

화면 캡처는 `test-results/routes-mobile.png`(390×844 마이페이지)와 `test-results/routes-desktop.png`(1440×1000 로그인)를 직접 확인했다. 모바일 5개 메뉴와 안내·이동 링크에 가로 넘침이 없었다. 실기기·전체 브라우저 시각 검증을 뜻하지 않는다. 캡처는 재생성 가능한 임시 산출물이며 이후 테스트 실행 시 삭제될 수 있다.

이번 변경 후 `format:check`, 전체 axe 검사(`test:a11y`), 프로덕션 smoke(`test:production`)는 재실행하지 않았다. 해당 스크립트의 페이지 경로는 갱신했지만 아래 과거 통과 기록을 현재 버전의 통과 근거로 사용하지 않는다. 실제 API·인증·금융 데이터는 이번 검증 대상이 아니다.

### 재현

저장소 루트에서 실행한다. 기존 개발 서버가 5174를 사용하면 E2E 전용 포트를 지정한다.

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

API 모드 테스트는 5175를 사용한다. 당시 Windows에서 테스트 종료 후 Vite 정리가 대기 상태로 남아, 이번 작업에서 시작한 프로세스의 PID·명령줄을 확인한 뒤 종료했다. 두 테스트 실행은 최종 종료 코드 0을 반환했고, 5175·5184 리스너가 해제됨을 확인했다. 기존 5174 개발 서버는 유지했다. 다른 실행에서 프로세스를 정리할 때는 기록된 PID를 재사용하지 않고 그 실행에서 생성한 프로세스를 확인한다.

## 이전 검증 기록

2026-09-08 데이터 계층 리팩터 검증은 [데이터 전환 검증](../../docs/frontend/DATA_SOURCE.md#검증과-실행)에 있다. 이하 내용은 2026-09-07의 이전 페이지 구성에서 얻은 기록으로 보존한다. 당시 단일 문서 상세 화면은 현재 제거되었다.

검증일: 2026-09-07. 대상은 `frontend/`의 독립 React/Vite 앱이며 Windows, Node.js, Playwright Chromium에서 실행했다. 서비스 데이터는 합성 목데이터이고 토론 입력은 브라우저 안에서만 처리된다. 백엔드, 실제 수집 데이터, 다중 사용자 통신은 검증 범위가 아니다.

## 결과

| 검사                          | 최종 결과                | 범위                                             |
| ----------------------------- | ------------------------ | ------------------------------------------------ |
| `npm.cmd run lint`            | 통과, 경고 0개           | 전체 `src`의 ESLint 검사                         |
| `npm.cmd run format:check`    | 통과                     | 신규 앱·화면·컴포넌트·목데이터 형식              |
| `npm.cmd run build`           | 통과                     | Vite 배포 파일 생성                              |
| `npm.cmd run test:e2e`        | 28개 통과                | 사용자 흐름 15개, 예외/데이터 7개, 토론 6개      |
| `npm.cmd run test:a11y`       | 32개 화면/상태, 위반 0개 | 7개 대표 경로 × 4개 너비 + 펼친 토론 4개         |
| `npm.cmd run test:production` | 8개 경로 통과            | 배포 결과의 직접 진입·화면 전환·온보딩 진입/종료 |
| `npm.cmd run test:contract`   | 통과                     | OpenAPI 참조, 실제 fixture와 요청/응답 예시      |

## 실제로 확인한 흐름

- 온보딩의 탐색 시작 버튼, 스크롤 상태 해제, 모션 감소 설정, WebGL을 사용할 수 없는 환경의 대체 화면.
- 지도 사건 선택, 드래그, 확대/축소 범위와 초기화, 기간별 합산 수치. 사건 검색·주제 필터·정렬·빈 결과 복구.
- 사건 탭의 방향키/Home/End 이동, 기간과 기준선, 문서 선택, 뉴스 검색/유형, 근거 문서 진입.
- 문서의 편집·조회 차트, 날짜별 키보드 탐색, 편집 전후 비교와 검색.
- 사건별 연관 주식, 종목 검색·분류·관심 종목, 연결 유형·연결 경로·가격 예시·기간 변경.
- 사건/종목 보관, 새로고침 유지, 삭제, 저장 공간 차단과 손상된 저장값 복구.
- 전역 검색의 Ctrl/Cmd+K, 방향키/Enter, Escape와 결과 없음. 한국어 및 `&`, `?`, `+` 검색 URL 보존. 뒤로/앞으로 이동과 잘못된 경로의 복구.
- 사건 6개·문서 14개·종목 8개의 개별 상세 주소. 해당 탐색에서 데이터 fetch/XHR/API 요청이 발생하지 않음을 확인.

## 리포트의 연관 주식과 토론

리포트 상단의 **연관 주식**이 해당 사건의 종목 목록으로 연결되는지 확인했다. 모바일 390px에서도 이 진입 버튼이 첫 화면에 보인다. 리포트의 보조 영역에는 개별 종목과 연결 근거 진입점이 있다.

토론은 개요 하단과 다섯 번째 **토론** 탭에서 제공한다. 사건별 예시 글 3개, 예시 답글 1개, 새 글·답글 작성, 공감·취소, 최신순·공감순 정렬을 검증했다. 공백 입력 차단, 1,000자 제한, 앞뒤 공백 제거, HTML 문자열의 일반 텍스트 표시, 답글 접기/펼치기, 탭 이동과 새로고침 후 유지, 사건별 데이터 분리도 확인했다. 저장 실패 시에는 안내와 함께 현재 페이지 세션에서 동작한다. 다른 사용자에게 전송하는 기능은 없다.

## 반응형·접근성·시각 확인

axe-core의 WCAG 2 A/AA 및 WCAG 2.1 AA 자동 규칙을 1440/820/390/320px에서 실행했다. 자동 검사 결과는 위반 0개이며, 보조기술 전체의 접근성 인증을 의미하지 않는다.

데스크톱 1440px과 모바일 390px의 대표 화면 14개를 캡처해 확인했다. 지도 도구와 마지막 노드가 겹치던 부분, 태블릿에서 아이콘만 남는 메뉴의 접근 가능한 이름을 수정하고 재확인했다. 토론 추가 후 개요/토론의 데스크톱·모바일 4개 화면을 추가 확인했으며 작성 글과 열린 답글도 포함했다. 페이지 전체의 가로 넘침은 없었다. 탭·필터·편집 비교 영역의 의도한 가로 스크롤은 유지한다.

재현용 스크립트는 `scripts/capture.mjs`, `scripts/review-fixes.mjs`, `scripts/capture-discussion.mjs`이며 이미지와 측정값은 작업 폴더의 `.impeccable/review/`에 생성된다. `scripts/accessibility.mjs`와 `scripts/production-smoke.mjs`의 JSON 결과는 `test-results/`에 생성된다. Playwright 실행은 이 임시 결과 폴더를 초기화할 수 있다.

## API 계약 확인

[OpenAPI 제안](openapi.yaml)의 경로 13개, 중복 없는 작업 14개, 스키마 37개, 내부 참조 138개를 검사했다. fixture 객체 34개, 스키마 예시 3개, 응답 예시 5개, 요청 예시 3개를 스키마로 검증했다. 전체 사건 응답 예시가 실제 목데이터와 중첩 필드까지 일치한다.

토론 조회·작성·답글·공감은 미래 연동을 위한 제안 계약이다. 현재 앱이 이 API를 호출하거나 서버가 구현되어 있다는 뜻은 아니다. [API 설명](API_SPEC.md)에 UI 동작과 제안 계약의 차이를 기록했다.

## 남아 있는 범위와 제한

- 기존 온보딩의 WebGL 청크는 약 906.29kB(gzip 242.61kB)로 Vite의 500kB 청크 경고가 남는다. 서비스 경로에 직접 진입할 때 이 온보딩 청크를 내려받지 않는 것은 배포 결과에서 확인했다.
- 헤드리스 Chromium과 지정한 화면 너비에서 검사했다. 실제 모바일 기기, Safari/Firefox, 실기기 GPU 및 모든 스크린리더 조합은 확인하지 않았다.
- 가격·뉴스·관계·AI 해석은 기능을 설명하는 예시다. 실제 금융 데이터나 투자 성과를 검증한 결과가 아니다.

실행 순서와 주소는 [README](../README.md)를 참고한다.
