# 프론트가 사용하는 실제 조회 계약

2026-09-15 · WP-95/-97/-98 · Spring 기준 커밋 `f3c0160`

이전 `0.2.0-proposal`의 `/events`, `/entities`, `/categories`, `/search` 및 쓰기 API는 현재 연결 계약에서 폐기했다. 원래 제안은 Git 이력에서 확인할 수 있다. [공통 서비스 명세](../../docs/api-v0.3.md)에는 미구현 제안과 이전 구현 상태도 있으므로 현재 연결은 아래 Controller·DTO를 기준으로 한다.

## 정본과 범위

- [현재 8개 GET OpenAPI](openapi.yaml): mock/API가 함께 검증하는 wire 계약.
- [지도 OpenAPI](pulse-openapi.json): 지도 두 경로의 상세 계약. 전체 OpenAPI와 스키마 동등성을 검사한다.
- [IssueController](../../backend/src/main/java/io/wikipulse/backend/issue/IssueController.java), [StockController](../../backend/src/main/java/io/wikipulse/backend/stock/StockController.java): 실제 요청 경로.
- [협의 기록](../../docs/frontend/API_DECISIONS.md): 미구현 API·상태·과거 지표·ID·한도에 대한 질문과 후속 작업.
- [환경 설정과 실행](../../docs/frontend/DATA_SOURCE.md).

## 현재 응답

| 경로 (`/api/v1` 아래)     | DTO / meta                                                |
| ------------------------- | --------------------------------------------------------- |
| `/issues`                 | `IssueCard[]`, pagination·선택 snapshotTs                 |
| `/issues/{id}`            | `IssueDetail`, members·상위 5개 relatedStocks, meta 없음  |
| `/issues/{id}/stocks`     | `RelatedStock[]`, limit 기본 50/최대 100, pagination 없음 |
| `/stocks`                 | `StockCard[]`, pagination                                 |
| `/stocks/{ticker}`        | `StockDetail`, meta 없음                                  |
| `/stocks/{ticker}/issues` | `IssueCard[]`, 최대 50개, 관계 근거·pagination 없음       |
| `/issues/snapshots`       | 완료된 `{snapshotTs,source,clusterCount}[]`, meta 없음    |
| `/issues/map`             | `{clusters}`, 시점·출처·scoreVersion·개수 meta            |

일반 목록 pagination은 `offset/limit/total/hasMore`, limit 범위는 1~100이다. 이슈 정렬은 pulseScore 내림차순·id 오름차순이다. 이슈 키워드·카테고리 검색은 지원하지 않는다. 종목 검색은 q·sector·exchange·hasIssues를 지원한다.

이슈 탐색의 **모든 출처**는 `/issues/snapshots`에서 live·replay 각각의 최신 완료 스냅샷을 선택하고, 출처·시각·상태를 명시한 `/issues` 결과를 프론트에서 합친다. 서버의 출처 생략은 LIVE 우선 단일 스냅샷 조회이므로 전체 조회로 사용하지 않는다. 합친 결과에도 점수 내림차순·ID 오름차순과 전체 건수 기준 페이지네이션을 적용하며, 화면에 출처별 시각을 표시한다. 페이지 이동은 내부 `sourceSnapshots`에 두 시각을 고정하고, 필터 변경은 첫 페이지에서 최신 시각을 다시 선택한다. 이 내부 상태는 API 쿼리에 보내지 않는다.

서버 정렬을 유지하기 위해 각 출처에서 최대 `offset + limit`개까지 읽고 전역 페이지를 자른다(요청당 최대 100개). 단일 출처만 있으면 서버 페이지를 그대로 사용한다. 깊은 페이지에서는 재조회량이 늘어나므로 데이터가 커질 경우 서버의 통합 페이지네이션으로 옮길 수 있다. 빈 완료 스냅샷은 이전의 비어 있지 않은 시점으로 대체하지 않으며, 한 출처의 요청 실패를 정상적인 부분 결과로 숨기지 않는다.

## null과 식별자

`IssueDetail`, `IssueMember`, `StockDetail`, `RelatedStock`은 Java `NON_NULL` 때문에 값 없는 필드가 생략될 수 있다. 카드 label은 null일 수 있다. 지도 Node의 지표 필드는 필수지만 null 가능하다. 지도 label·firstDetectedAt·이전 데이터의 issueKey도 null 가능하다. 없는 수치를 0으로 바꾸지 않는다.

지도 ID는 문자열이다. 카드·상세·멤버는 현재 JSON 숫자 ID이므로 FE가 안전 정수 범위를 확인한 뒤 내부 경로 키를 문자열로 보관한다. 범위를 넘은 ID는 오류이며 임의 반올림하지 않는다. 문자열 ID 통일은 협의 대상이다.

## 상태와 사용하지 않는 데이터

서버 status는 AI 검증 전·AI 검증 중·AI 검증 완료로 표시한다. source·API 실행 모드와 서로 다른 개념이다. `pulseScore`는 단위 없는 급증 점수다. 지도 크기는 서버 sizeScore를 사용한다. summary 부재·가격 부재·뉴스 부재를 fixture로 채우지 않는다.

상단 검색은 종목만 검색한다. 인증·계정 생성·뉴스·가격·문서 시계열·서버 토론·서버 보관함은 현재 제공되지 않는다. 보관함과 토론은 로컬 상태이며 API 모드와 mock 모드의 저장 공간을 분리한다.

## 오류와 검증 범위

오류 봉투는 `{error:{code,message}}`다. INVALID_QUERY·NOT_FOUND·INTERNAL과 네트워크 오류·잘못된 DTO를 구분한다. 서버 영문 message를 그대로 제품 안내로 쓰지 않으며 API 실패를 mock으로 숨기지 않는다.

OpenAPI·mock·intercepted HTTP 검사 통과는 실제 Spring/DB 연결 증거가 아니다. 최신 실행 결과와 제한은 [VALIDATION.md](VALIDATION.md)에 기록한다.
