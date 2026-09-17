# API 연동 협의 기록

기준: 2026-09-15, `f3c0160`의 Spring Controller·Service·DTO와 이번 프론트 변경.
관련 작업: **WP-95**(조회 계층·mock), **-96**(화면), **-97**(검증), **-98**(문서).
이 문서는 서버 변경을 승인하거나 미구현 API를 확정하지 않는다. 현재 가능한 화면 처리와 팀에서 결정할 계약을 구분한다.

## 현재 사용할 수 있는 조회 API

`/api/v1` 아래 `GET /issues`, `/issues/{id}`, `/issues/{id}/stocks`, `/issues/snapshots`, `/issues/map`, `/stocks`, `/stocks/{ticker}`, `/stocks/{ticker}/issues`의 **8개**다.
근거: [IssueController](../../backend/src/main/java/io/wikipulse/backend/issue/IssueController.java), [StockController](../../backend/src/main/java/io/wikipulse/backend/stock/StockController.java).
기계 검사용 현재 계약은 [openapi.yaml](../../frontend/docs/openapi.yaml), 지도 상세 계약은 [pulse-openapi.json](../../frontend/docs/pulse-openapi.json)이다.

## 협의할 항목

### 1. 미구현 API와 화면 범위

- **근거:** 위 두 Controller에는 통합 검색, 이슈 키워드 검색, 페이지 시계열, 주가, 뉴스, 인증, 회원 보관함, 토론 쓰기 API가 없다. `docs/api-v0.2.md`의 해당 항목은 제안이다.
- **현재 FE 처리:** 상단 검색은 `/stocks?q=`를 쓰는 종목 검색이다. 이슈 화면은 지원되는 상태·출처·시점과 페이지네이션만 서버에 보낸다. 종목 가격·가상 수익률·뉴스·편집 전후 비교를 서버 결과처럼 보충하지 않는다. 보관함·토론은 브라우저의 로컬 기능이며 실제 계정 동기화가 아니다.
- **협의 질문:** 통합 검색·주가·뉴스·문서 지표·인증 중 다음 제공 순서는 무엇인가? 과거 제안의 경로·필드·접근 권한을 그대로 채택하는가?
- **후속 작업:** 확정한 API별로 BE 구현과 FE 연결을 따로 등록하고 실제 응답 검증을 추가한다. 이번 연동은 WP-95/-96/-97 범위.

### 2. 상태, 실패, 두 종류의 ‘확정’

- **근거:** `IssueDetailResponse.status`와 지도 `Cluster.status`는 `DETECTED / VERIFYING / CONFIRMED`를 전달한다. 새 계약에서는 편집 1건→조회수 급등을 모두 통과한 뒤에만 이슈가 만들어지므로, 이 상태값은 조회수 판정 단계가 아니라 이후 종목 매칭·요약 검증 진행 상태다(WP-118).
- **현재 FE 처리:** 서버 상태를 AI 검증 전·AI 검증 중·AI 검증 완료로 표시한다. API를 쓴다는 이유로 LIVE·확정으로 승격하지 않는다. 요약 부재를 오류나 검증 실패로 단정하지 않는다. 지도 결측은 `pending`이면 집계 중, `unavailable`이면 미제공, 실제 0이면 0으로 구분한다.
- **협의 질문:** 검증 실패·재시도·장시간 검증 중을 사용자에게 구분할 필드는 무엇인가? `verification_failed` 같은 별도 상태 또는 `failureReason / retryAfter / updatedAt`이 필요한가? 확정 상태를 급증 점수보다 먼저 정렬할 것인가?
- **후속 작업:** BE 워커 실패 계약·표시 문구·정렬 정책을 함께 정한다. **WP-94**의 detector 런타임 연결도 상태 생산의 선행 작업이다.

### 3. 급증 점수 단위, HOT, 점수 버전

- **근거:** 현재 코드는 WP-93의 편집·조회수 혼합 점수를 사용한다. 제품 계약 변경 후 조회수 중심 `pulse_score`로 바꾸는 작업과 UI 크기 회귀는 WP-118 범위다. API의 `sizeScore=s/(s+5)` 변환 자체는 서버 점수가 바뀌어도 유지한다.
- **현재 FE 처리:** `pulseScore`를 단위 없는 급증 점수로 표시하며 배수·확률·정확도·수익률로 읽지 않는다. `sizeScore`, HOT, `scoreVersion`은 서버 값에 따른다. 화면마다 최댓값으로 다시 정규화하지 않는다.
- **협의 질문:** detector 산식 변경도 `scoreVersion`에 포함하는가? 과거 스냅샷을 재계산할 것인가, 버전별 비교를 제한할 것인가? 신규/기존 문서 점수와 HOT 임계의 비교 기준은 무엇인가?
- **후속 작업:** -93 후속으로 점수 버전·재집계·HOT 기준을 정하고 이전/새 버전 혼합 검증을 추가한다. 점수 변경이 현재 운영 데이터에 적용됐다는 증거는 이번 FE 검사에 포함하지 않는다.

### 4. DISCARDED의 과거 조회와 관련 종목

- **근거:** [IssueService.detail](../../backend/src/main/java/io/wikipulse/backend/issue/IssueService.java)은 DISCARDED를 404로 처리한다. 같은 Service의 `stocks`는 `existsById`만 검사한다. [IssueQueryRepository](../../backend/src/main/java/io/wikipulse/backend/issue/IssueQueryRepository.java)의 관련 종목 조회에는 verified 조건은 있으나 부모 상태 검사가 없다. 지도·역방향 이슈 목록은 DISCARDED를 제외한다.
- **현재 FE 처리:** 관련 종목 페이지에서도 부모 이슈 상세를 조회하고 404이면 노출하지 않는다. 이는 화면 차원의 처리이며 `/issues/{id}/stocks` 자체의 노출 제한을 보장하지 않는다.
- **협의 질문:** 폐기된 과거 스냅샷의 직접 조회를 404로 통일하는가? 과거 보관함 항목은 삭제·폐기 안내를 위해 별도 tombstone 응답이 필요한가?
- **후속 작업:** BE에서 모든 조회 경로의 비노출 규칙을 통일하고 직접 API 회귀 검증을 추가한다. 스냅샷 목록 `clusterCount`가 저장 당시 수인지 현재 노출 가능한 수인지도 정한다.

### 5. 과거 이슈의 지표 범위와 데이터 출처

- **근거:** [IssueQueryRepository.findMembers](../../backend/src/main/java/io/wikipulse/backend/issue/IssueQueryRepository.java)는 문서별 최신 편집·조회 행을 읽는다. `IssueMemberResponse`는 지표의 `windowStart/windowEnd`를 제공하지 않는다. 반면 지도 `PulseMap.Node`는 시점에 저장된 값과 집계 구간을 제공한다.
- **현재 FE 처리:** 지도에서는 서버가 준 구간과 값만 표시한다. 일반 이슈 상세의 지표를 선택한 과거 시점의 확정값이나 24시간 합계로 표기하지 않는다. 없는 시계열을 만들거나 0으로 채우지 않는다.
- **협의 질문:** 상세도 스냅샷 당시 멤버 지표를 반환할 것인가? 지표별 집계 구간·수집 시각·완전성을 상세 DTO에 넣을 것인가?
- **후속 작업:** 상세와 지도 사이 값의 기준시각을 일치시키고 과거→상세→종목 탐색에 실데이터 검증을 추가한다. 데이터 수집부터 지도 저장까지 완결되는지는 WP-94와 cluster driver 후속 범위다.

### 6. BIGINT 전송 정밀도

- **근거:** 지도는 `id/pageId`를 문자열로 보낸다. 이슈 카드·상세·멤버 DTO는 Java `long`으로 JSON 숫자를 보낸다. JavaScript 안전 정수 범위를 넘으면 JSON 파싱 시 원래 ID를 복원할 수 없다.
- **현재 FE 처리:** 경로·보관함 내부 키는 문자열로 다룬다. 숫자로 수신한 ID가 안전 정수가 아니면 계약 오류로 거절한다. 이미 손실된 숫자를 `String()`으로 바꿔 정상값처럼 쓰지 않는다.
- **협의 질문:** 지도와 나머지 조회의 ID를 모두 문자열로 통일할 것인가? 전환 기간에 문자열/숫자를 같이 허용할 것인가?
- **후속 작업:** BE DTO·OpenAPI·클라이언트를 한 번에 전환하고 `9007199254740993` 같은 경계 ID로 검증한다.

### 7. nullable label과 목록 제목

- **근거:** `IssueCardResponse.label`은 null 가능하며 대표 문서명은 카드에 없다. `IssueDetailResponse`는 `NON_NULL`이라 label·summary·summaryModel이 아예 생략될 수 있다. 지도 label도 DB 값이 null이면 null이다.
- **현재 FE 처리:** 목록에서 제목이 없으면 “제목 미제공”으로 표시하여 N+1 상세 호출을 만들지 않는다. 상세·지도는 제공된 멤버 제목으로 대체한다. 누락과 null을 모두 처리한다. 지도에서 `issueKey`가 null인 이전 행은 시점 안에서만 식별하며 시점 간 연속성을 추정하지 않는다.
- **협의 질문:** 카드에 `representativeTitle` 또는 `seedTitle`을 추가할 것인가? DTO별로 null 필드의 생략 정책을 통일할 것인가?
- **후속 작업:** 목록 제목 필드 확정 후 fallback 문구와 nullable 스키마를 갱신한다.

### 8. 역방향 연관 정보와 목록 한도

- **근거:** `/stocks/{ticker}/issues`는 `IssueCardResponse` 배열이며 문서 제안의 `tier/matchPath/rationale`를 제공하지 않는다. `StockService.TICKER_ISSUE_LIMIT=50`이며 pagination meta가 없다. `/issues/{id}/stocks`는 limit 기본 50, 최대 100이고 offset·total·hasMore가 없다. 상세 `relatedStocks`는 상위 5개다.
- **현재 FE 처리:** 역방향 목록에서는 제공되는 이슈 카드만 표시한다. 상세의 5개 preview를 전체 목록으로 간주하지 않는다. 관련 종목은 지원 한도 내에서 요청하며 응답 개수를 전체 개수라고 단정하지 않는다. 정상 페이지네이션은 `/issues`와 `/stocks`의 `meta.pagination`을 따른다.
- **확정:** 제품 정책상 검증 통과 종목의 전체 노출 상한은 두지 않는다(WP-22). 현재 API의 50/100 제한은 전송 응답 크기 보호용이며 제품 노출 상한이 아니다.
- **남은 질문:** 역방향에도 관계 메타를 제공할 것인가? 관련 목록 두 개에 offset/cursor와 total/hasMore를 제공할 것인가?

### 9. 실제 서비스 검증과 실패 응답

- **근거:** 현재 `GlobalExceptionHandler`의 code는 `INVALID_QUERY`, `NOT_FOUND`, `INTERNAL` 등이며 `meta.dataMode`는 일반 성공 DTO에 없다. Playwright의 `route.fulfill`은 Spring·DB를 실행하지 않는다.
- **현재 FE 처리:** wire에 dataMode를 요구하지 않고 선택한 mock/api 실행 모드는 로컬에서 기록한다. 400·404·500·네트워크 장애와 잘못된 DTO를 구분하며 실패를 mock으로 대체하지 않는다.
- **협의 질문:** 통합 검증용 서버·DB seed·접속 주소와 CORS/HTTPS 구성이 준비됐는가? 실제 pipeline 산출물의 완료 시점·데이터 신선도는 어떤 필드로 전달할 것인가?
- **후속 작업:** WP-97의 intercepted HTTP 검사와 실제 Spring/DB 통합 검증을 각각 기록한다. 빌드 통과나 API 모드 테스트만으로 실서버 연결 완료라고 보고하지 않는다.
