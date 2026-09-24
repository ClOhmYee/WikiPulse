# 이슈 탐색의 과거 기록 검색·타임라인 구현 계획

> **구현 담당자 안내:** 작업별로 `superpowers:subagent-driven-development`(권장) 또는 `superpowers:executing-plans`를 사용한다. 진행 상태는 체크박스(`- [ ]`)로 기록한다.

**목표:** 완료된 스냅샷 전체에서 대표 문서를 검색해 `issue_key`별 한 건으로 보여주고, 각 시점의 기존 상세 화면을 타임라인에서 탐색한다.

**구조:** 기존 `/issues`, `/issues/{id}`, DB 스키마, 저장된 클러스터는 바꾸지 않고 읽기 전용 API 두 개만 추가한다. 새 프론트 화면은 기본값이 꺼진 Vite 빌드 플래그 뒤에 두고, 날짜를 합쳐 새 이슈를 만들지 않고 기존 상세 ID와 데이터를 재사용한다.

**기술 스택:** Java 21, Spring Boot/JPA 네이티브 SQL, PostgreSQL, React/Vite, Node 테스트 러너, Playwright.

**설계서:** `docs/superpowers/specs/2026-09-24-issue-history-explore-design.md`

## 공통 제약

- `origin/develop`의 `5d9768d`를 기준으로 만든 격리 작업 공간 `feature/issue-history-explore`에서만 작업한다. 사용자의 기존 체크아웃은 수정하지 않는다.
- `VITE_ISSUE_HISTORY_ENABLED`의 기본값은 **꺼짐**이다. 이 계획만으로 운영에서 켜거나 배포하지 않는다.
- 읽기 전용 API와 UI만 추가한다. 스키마 변경·백필·삭제·클러스터링·기존 API 응답 변경은 금지한다.
- `issue_key`가 있으면 그 값으로 묶고, 없으면 각각 독립된 건으로 취급한다. 묶음을 현실의 동일 사건이라고 부르지 않는다.
- 검색 대상은 대표 제목 `label`뿐이다. 구성 문서 B/C/D, 별칭, 의미 기반 사건 검색은 범위에서 제외한다.
- `limit`은 1~100, `offset`은 0 이상, `q`는 공백 제거 후 1~200자다. `%`, `_`, `\`는 와일드카드가 아니라 문자 그대로 검색한다.
- 타임라인에는 완료된 `cluster_snapshot`에 속한 비폐기 행만 정확한 `snapshotTs`와 함께 최신순으로 표시한다.
- 구성 문서·리포트·종목은 기존 `/issues/{id}`로 이동해 각 스냅샷의 데이터를 그대로 사용한다.

## 파일별 역할

- `backend/.../issue/IssueQueryRepository.java`: 읽기 전용 검색·건수·타임라인 SQL과 조회 결과 정의.
- `backend/.../issue/IssueService.java`: 입력 검증, 페이지네이션, 기준 이슈 ID 처리.
- `backend/.../issue/IssueController.java`: 기존 API와 독립된 새 경로.
- `backend/.../issue/dto/IssueHistoryGroupResponse.java`, `IssueOccurrenceResponse.java`: 새 API 응답 형식.
- `backend/src/test/java/io/wikipulse/backend/issue/IssueControllerTest.java`: HTTP 응답 형식과 잘못된 입력 검사.
- `db/tests/test_issue_history_sql.py`: 테스트마다 롤백하는 PostgreSQL 환경에서 묶음·필터·정렬·페이지네이션 검증.
- `frontend/src/data/api/adapters.js`, `client.js`, `frontend/src/data/index.js`, `contracts.js`: 새 API 응답 검증과 호출 노출.
- `frontend/.env.example`: 실제 운영 환경값은 바꾸지 않고 기본 꺼짐 플래그 사용법만 기록.
- `frontend/src/data/history.js`: 플래그 판정과 필요한 최소 표시 변환. 스냅샷 간 데이터를 합치지 않는다.
- `frontend/src/pages/explore/ExplorePage.jsx`, `frontend/src/pages/explore/explore.css`: 기존 목록은 유지하고 검색할 때만 묶음 결과 표시.
- `frontend/src/pages/event/EventPage.jsx`, `frontend/src/styles/details.css`: 기존 ID로 이동하는 상세 타임라인.
- `frontend/tests/history.test.js`, `frontend/e2e-api/issue-history.spec.js`: 데이터·화면 회귀 검사.

## 중점 검토 항목

1. `q`의 `%`, `_`, `\`가 SQL 와일드카드로 해석되어 무관한 문서까지 검색되지 않는지 확인한다(작업 1).
2. `issue_key`가 없거나 대표 문서가 바뀐 경우, 또는 LIVE/replay 출처가 다른 경우 잘못 합쳐지지 않는지 확인한다(작업 1).
3. 폐기 행과 미완료 스냅샷이 검색 결과·건수·타임라인에 섞이지 않는지 확인한다(작업 1~2).
4. 같은 날의 여러 스냅샷이 유지되고 페이지 경계에서 중복·누락이 없는지 확인한다(작업 2).
5. 새 API가 실패해도 기존 상세가 사라지지 않고, 플래그가 꺼졌을 때 새 API를 호출하지 않는지 확인한다(작업 3~5).

---

### 작업 1: 대표 문서별 검색 API

**파일:** `backend/src/main/java/io/wikipulse/backend/issue/{IssueController,IssueService,IssueQueryRepository}.java` 수정, `backend/src/main/java/io/wikipulse/backend/issue/dto/IssueHistoryGroupResponse.java` 추가. `backend/src/test/java/io/wikipulse/backend/issue/IssueControllerTest.java`, `db/tests/test_issue_history_sql.py`에서 검증.

**연결 규약:** `GET /api/v1/issues/history/search?q=&source=&offset=&limit=`는 기존 `ApiResponse<List<IssueHistoryGroupResponse>>` 봉투와 `PageMeta.Pagination`을 반환한다. 필드는 `id`(최신 클러스터 ID), `label`, `source`, `snapshotTs`(최신 시각), `status`, `pulseScore`, `firstSeen`, `occurrenceCount`다. 프론트 작업 3에서 이 이름을 사용한다.

HTTP 테스트는 아래 응답 검증으로 시작한다. Mockito 응답에는 이 작업에서 정의한 DTO를 사용한다.

```java
mvc.perform(get("/api/v1/issues/history/search")
        .param("q", "Odyssey").param("offset", "0").param("limit", "20"))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.data[0].occurrenceCount").value(10))
   .andExpect(jsonPath("$.meta.pagination.total").value(1));
```

컨트롤러 경로와 서비스 호출 형태:

```java
@GetMapping("/history/search")
public ApiResponse<List<IssueHistoryGroupResponse>> searchHistory(
        @RequestParam String q, @RequestParam(required = false) String source,
        @RequestParam(required = false) Integer offset,
        @RequestParam(required = false) Integer limit) {
    return service.searchHistory(q, source, offset, limit);
}
```

- [ ] **1단계: 기존 테스트 상태 확인.** `backend`에서 `.\gradlew.bat test --tests io.wikipulse.backend.issue.IssueControllerTest`를 실행하고 기존 실패가 있으면 기록한다. 작업 공간 루트에서 `python -m pytest db/tests/test_issue_rankings_sql.py -q`를 실행한다. 의존성 부족으로 건너뛰면 통과로 세지 않는다.
- [ ] **2단계: 먼저 실패하는 HTTP 테스트 작성.** `GET /api/v1/issues/history/search?q=Odyssey&offset=0&limit=20`의 `id`, `occurrenceCount`, `firstSeen`, `meta.pagination.total`을 검사한다. 빈 검색어·201자 검색어·잘못된 출처/limit/offset은 400을 검사한다. 새 `service.searchHistory(...)` 호출을 모킹한다.
- [ ] **3단계: 먼저 실패하는 SQL 테스트 작성.** `db/tests/test_issue_rankings_sql.py` 패턴대로 `IssueQueryRepository`의 새 `@Query`를 추출해 매 테스트 롤백 환경에서 실행한다. 같은 키의 서로 다른 완료 날짜 2건, 같은 제목의 다른 키, replay 키, NULL 키 2건, 폐기 행, 미완료 스냅샷을 넣는다. 묶음 건수·최신 ID·최초/최신 시각·출처 분리·1건 단위 페이지네이션을 검사한다. 제목 `100%`, `A_B`, `C\D`도 넣어 특수문자가 문자 그대로 검색되는지 확인한다.
- [ ] **4단계: 해당 테스트가 예상대로 실패하는지 확인.** Java에서는 새 메서드 부재, Python에서는 새 SQL 부재로 실패해야 한다.
- [ ] **5단계: 최소한의 읽기 전용 구현.** CTE에서 `label ILIKE :pattern ESCAPE '\'`에 맞는 묶음 키를 찾고, 그 키의 **모든 적격 시점**을 모은다. 대표 행은 `row_number() OVER (PARTITION BY group_key ORDER BY snapshot_ts DESC,id DESC)`로, 발생 횟수와 최초 시각은 `count(*)`/`min(snapshot_ts)`로 계산한다. NULL 키에 `COALESCE(issue_key, 'legacy-id:' || id)`를 쓸 경우 기존 `source:wiki:title` 키와 충돌하지 않는지 확인하고 NULL 키 테스트를 유지한다. 총건수는 `OFFSET/LIMIT` 적용 전의 묶음 수로 센다. `cluster_snapshot` 확인은 **출처와 시각을 모두** 맞춘다. 서비스에서 `trim()`, `Locale.ROOT`, `replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")`로 문자 그대로 검색할 패턴을 만들고, 검색어가 비거나 200자를 넘으면 400을 반환한다. `QueryParams.source/offset/limit`, `PageMeta.Pagination.of`를 재사용한다.
- [ ] **6단계: 테스트 통과 확인.** 두 집중 테스트를 다시 실행하고, `backend`에서 `.\gradlew.bat test --tests 'io.wikipulse.backend.issue.*'`를 실행한다. PostgreSQL 테스트가 건너뛰어졌다면 SQL 검증 완료로 보지 않고 격리 PostgreSQL 환경에서 실행한다.
- [ ] **7단계: 커밋.** 작업 1 파일만 `git add`하고 `git diff --cached --check` 후 `git commit -m "feat: 대표 문서별 이슈 기록 검색 API 추가"`를 실행한다.

### 작업 2: 이슈 ID별 시점 타임라인 API

**파일:** `backend/src/main/java/io/wikipulse/backend/issue/{IssueController,IssueService,IssueQueryRepository}.java` 수정, `backend/src/main/java/io/wikipulse/backend/issue/dto/IssueOccurrenceResponse.java` 추가. `IssueControllerTest.java`, `db/tests/test_issue_history_sql.py` 확장.

**연결 규약:** `GET /api/v1/issues/{id}/history?offset=&limit=`가 `ApiResponse<List<IssueOccurrenceResponse>>`와 페이지네이션을 반환한다. 항목 필드는 `id`, `snapshotTs`, `status`, `pulseScore`, `memberCount`이며 작업 3에서 사용한다. 기준 ID의 키가 NULL이면 해당 ID만 반환하고, 없는 ID·폐기된 ID는 404다.

기존 `/{id}`와 구별되는 경로에 같은 페이지네이션 봉투를 쓴다.

```java
@GetMapping("/{id}/history")
public ApiResponse<List<IssueOccurrenceResponse>> history(
        @PathVariable Long id,
        @RequestParam(required = false) Integer offset,
        @RequestParam(required = false) Integer limit) {
    return service.history(id, offset, limit);
}
```

- [ ] **1단계: 먼저 실패하는 컨트롤러 테스트 작성.** `service.history(42L, 0, 20)`을 모킹해 정확한 시각과 페이지네이션을 검사한다. 없는 기준 ID·폐기된 ID는 404, 잘못된 limit은 400을 검사한다.
- [ ] **2단계: 먼저 실패하는 SQL 테스트 작성.** 같은 키를 같은 날의 서로 다른 두 시각과 다음 날 한 시각에 넣는다. 세 ID가 최신순인지, 두 번째 페이지가 맞는지 검사한다. 다른 출처/키·폐기 행·미완료 스냅샷은 제외하고, NULL 키는 해당 ID 한 건만 나오는지 검사한다.
- [ ] **3단계: 집중 테스트 실패 확인.** 작업 1의 명령과 새 타임라인 테스트의 Python 선택 실행을 사용한다.
- [ ] **4단계: 최소 API 구현.** `IssueService.history(Long id,Integer offset,Integer limit)`에서 `clusterRepository.findById`로 기준 행을 읽고 `DISCARDED`를 거부한다. `anchor.getSource()`, NULL 가능 키, 기준 ID를 SQL 조회·건수 조회에 전달한다. 조건은 `(:issueKey IS NOT NULL AND c.issue_key = :issueKey) OR (:issueKey IS NULL AND c.id = :anchorId)`이며 출처 일치, 완료된 스냅샷, 비폐기 상태도 요구한다. `snapshot_ts DESC,id DESC`로 정렬하고 페이지 적용 전 건수를 센다. `QueryParams`/`PageMeta`를 재사용한다.
- [ ] **5단계: 테스트 통과·커밋.** 집중 테스트와 `git diff --check`를 실행하고 작업 2 파일만 `feat: 이슈 시점 타임라인 API 추가`로 커밋한다.

### 작업 3: 프론트 API 응답 검증과 기본 꺼짐 플래그

**파일:** `frontend/src/data/api/{adapters,client}.js`, `frontend/src/data/{index,contracts}.js`, `frontend/.env.example` 수정. `frontend/src/data/history.js`, `frontend/tests/history.test.js` 추가.

**연결 규약:** `dataClient.searchIssueHistory(params, options)`와 `dataClient.listIssueHistory(id, params, options)`는 작업 1~2의 응답을 검증한 `DataResponse`를 반환한다. `issueHistoryEnabled(env, dataSource)`는 `env.VITE_ISSUE_HISTORY_ENABLED === "true" && dataSource === "api"`일 때만 참이다. 작업 4~5가 이 API를 사용한다.

플래그 판정과 API 호출 형태:

```js
export const issueHistoryEnabled = (env = {}, dataSource) =>
  env.VITE_ISSUE_HISTORY_ENABLED === "true" && dataSource === "api";

searchIssueHistory: (params = {}, options) =>
  list("/issues/history/search", params, options, issueHistoryGroup, true),
listIssueHistory: (id, params = {}, options) =>
  list(`/issues/${pathId(id)}/history`, params, options, issueOccurrence, true),
```

- [ ] **1단계: 먼저 실패하는 Node 테스트 작성.** `history.test.js`에서 플래그 누락·`false`·mock 모드는 거짓, `true`+api 모드는 참인지 검사한다. 잘못된 `snapshotTs`, 음수 `occurrenceCount`, 잘못된 출처/상태, 누락된 페이지네이션은 거부해야 한다. fetch를 대체해 API 경로와 인코딩된 ID를 검사한다.
- [ ] **2단계: 테스트 실패 확인.** `cd frontend; node --test tests/history.test.js`에서 새 export/메서드가 없어 실패해야 한다.
- [ ] **3단계: 응답 검증과 클라이언트 위임 추가.** 묶음은 `id`, `label`, `source`, UTC `snapshotTs`/`firstSeen`, 상태, 음수가 아닌 점수/건수를 검사한다. 시점 항목은 `id`, 시각, 상태, 점수, `memberCount`를 검사한다. `adaptResponse(...,{list:true,paginated:true,validate})`를 사용하고 `createApiClient`와 `createDataClient`에 메서드를 추가한다. 기존 메서드 형태는 바꾸지 않는다. `history.js`에는 플래그 판정과 필요한 최소 표시 변환만 둔다. 실제 `.env`가 아니라 `frontend/.env.example`에 `VITE_ISSUE_HISTORY_ENABLED=false`와 짧은 설명을 추가한다.
- [ ] **4단계: 테스트 통과·커밋.** `npm run test:data`, `npm run test:contract`를 실행하고 작업 3 파일만 `feat: 이슈 기록 프론트 API 규약 추가`로 커밋한다.

### 작업 4: 이슈 탐색의 묶음 검색 화면

**파일:** `frontend/src/pages/explore/ExplorePage.jsx`, `frontend/src/pages/explore/explore.css` 수정. `frontend/tests/history.test.js` 확장, `frontend/e2e-api/issue-history.spec.js` 추가·확장.

**연결 규약:** `issueHistoryEnabled`, `searchIssueHistory`를 사용한다. 검색어가 없거나 플래그가 꺼지면 기존 `usePageData()`의 최신 목록을 그대로 사용한다. 묶음 카드 제목은 `#/issues/{group.id}`로 연결하고, 묶음 카드에는 저장 버튼을 두지 않는다.

검색 모드로 바꿔도 기존 경로는 유지한다.

```js
const historyMode = issueHistoryEnabled(import.meta.env, dataClient.dataSource);
const [settledQuery, setSettledQuery] = useState("");
useEffect(() => {
  const timer = setTimeout(() => setSettledQuery(query.trim()), 250);
  return () => clearTimeout(timer);
}, [query]);
const searchMode = historyMode && settledQuery.length > 0;
const searchKey = JSON.stringify({ q: settledQuery, offset: searchOffset, searchMode });
const loadSearch = useCallback(
  (signal) => searchMode
    ? dataClient.searchIssueHistory(
        { q: settledQuery, offset: searchOffset, limit: 20 }, { signal })
    : Promise.resolve(null),
  [searchMode, settledQuery, searchOffset],
);
const search = useAsyncResource(loadSearch, searchKey);
```

- [ ] **1단계: 먼저 실패하는 화면·데이터 테스트 작성.** 플래그가 꺼지면 입력값이 현재 페이지만 걸러내고 과거 API를 호출하지 않아야 한다. 플래그가 켜진 API 모드에서 `Odyssey`를 입력하면 공백 제거된 `q`, offset 0, limit 20으로 서버를 호출하고, 발생 횟수·최초/최근 시각·출처가 있는 묶음 카드 한 건과 최신 ID 링크를 표시해야 한다. 페이지 이동은 서버 페이지네이션을 사용하고 검색어를 지우면 기존 최신 목록으로 돌아가야 한다. 검색 중에는 현재 스냅샷용 분석 상태 필터를 숨기고 이전 선택값을 적용하지 않는다.
- [ ] **2단계: 테스트 실패 확인.** `frontend`에서 `npm run test:data`, `npx playwright test --config playwright.api.config.js e2e-api/issue-history.spec.js`를 실행한다.
- [ ] **3단계: 최소 UI 구현.** 검색어가 없거나 플래그가 꺼지면 기존 `filtered`와 JSX를 유지한다. 250ms 입력 지연 처리, `searchOffset` 상태, 검색어·offset·플래그를 키로 하는 `useAsyncResource`를 추가하고 `dataClient.searchIssueHistory({q,offset,limit:20},{signal})`를 호출한다. 검색어가 바뀌면 offset을 0으로 초기화한다. 묶음 전용 카드를 그리며 스냅샷 ID를 저장하는 `EventRow` 버튼은 재사용하지 않는다. 검색 중에만 새 페이지네이션을 쓰고 로딩·오류·결과 없음 상태를 구분한다. 오래된 요청은 중단한다.
- [ ] **4단계: 테스트 통과·커밋.** `npm run test:data`, 해당 Playwright 검사, `npm run lint`, `npm run build`를 실행하고 작업 4 파일만 `feat: 과거 이슈 묶음 검색 화면 추가`로 커밋한다.

### 작업 5: 기존 상세 화면의 시점 타임라인

**파일:** `frontend/src/pages/event/EventPage.jsx`, `frontend/src/styles/details.css` 수정. `frontend/tests/history.test.js`, `frontend/e2e-api/issue-history.spec.js` 확장.

**연결 규약:** `listIssueHistory(event.id,{offset:0,limit:100})`를 사용하고 각 항목을 `#/issues/{entry.id}`로 연결한다. 선택한 상세 내용은 계속 기존 `getIssue(eventId)`에서만 받는다.

상세 조회와 이력 조회는 분리한다.

```js
const historyMode = issueHistoryEnabled(import.meta.env, dataClient.dataSource);
const historyKey = JSON.stringify({ eventId, offset: historyOffset, historyMode });
const loadHistory = useCallback(
  (signal) => historyMode && eventId
    ? dataClient.listIssueHistory(eventId, { offset: historyOffset, limit: 100 }, { signal })
    : Promise.resolve(null),
  [historyMode, eventId, historyOffset],
);
const history = useAsyncResource(loadHistory, historyKey);
```

- [ ] **1단계: 먼저 실패하는 테스트 작성.** 플래그가 꺼지면 이력 API 호출과 타임라인이 없어야 한다. 켜지면 같은 날의 서로 다른 두 시각까지 정확히 표시하고, 현재 선택 ID를 구분해야 한다. 다른 ID를 누르면 해당 시점의 구성 문서·리포트·종목으로 이동해야 한다. 이력 API 실패 시 기존 상세는 남고 오류·재시도를 표시해야 한다. 100건을 넘으면 조용히 자르지 않고 다음 페이지로 이동할 수 있어야 한다.
- [ ] **2단계: 테스트 실패 확인.** 관련 Node·Playwright 테스트를 실행한다.
- [ ] **3단계: 최소 타임라인 구현.** `eventId`와 페이지 offset을 키로 `useAsyncResource`를 사용하되, 플래그가 꺼지면 새 API를 호출하지 않는다. 기존 탭 위에 간결한 목록을 두고 파생된 키가 아닌 기존 이슈 ID로 연결한다. 기존 상세 탭(`report/overview/evidence`)과 저장 동작은 바꾸지 않는다. “하나의 사건” 대신 “대표 문서의 기록”과 출처를 표시한다.
- [ ] **4단계: 테스트 통과·커밋.** `npm run test:data`, 해당 Playwright 검사, `npm run lint`, `npm run build`를 실행하고 작업 5 파일만 `feat: 이슈 상세의 시점별 탐색 추가`로 커밋한다.

### 작업 6: 회귀 검사와 롤백 확인

**파일:** 제품 파일 변경 없음. 검증 근거는 최종 보고에 적고, AGENTS.md나 별도 현황 문서에 중복 기록하지 않는다.

**산출물:** MR 검토자가 재현할 수 있는 검증·롤백 보고. 배포는 하지 않는다.

- [ ] **1단계: 기본 꺼짐 검증.** 플래그 없이 `npm run build`하고 기존 `frontend/e2e/issue-view.spec.js`, `frontend/tests/explore.test.js`를 실행한다. 기존 `/issues`, `/issues/{id}` 요청과 화면이 바뀌지 않았는지 확인한다.
- [ ] **2단계: 켠 상태 검증.** PowerShell에서 `$env:VITE_ISSUE_HISTORY_ENABLED='true'; npm run build; Remove-Item Env:VITE_ISSUE_HISTORY_ENABLED`를 실행하고 격리 API/모의 데이터에서 새 테스트를 수행한다. 운영 플래그는 바꾸지 않는다.
- [ ] **3단계: 백엔드·SQL 검증.** 백엔드 전체 테스트와 실제 PostgreSQL SQL 테스트를 실행한다. PostgreSQL 테스트 환경을 실행할 수 없다면 차단 사유를 보고하고 SQL 검증 완료를 주장하거나 플래그를 켜지 않는다.
- [ ] **4단계: 실제 사례 읽기 전용 확인.** 비운영 또는 읽기 전용 환경에서 Odyssey처럼 반복되는 대표 문서를 새 API로 조회하고, 발생 횟수·시각을 직접 SQL과 비교하며 서로 다른 두 ID를 열어본다. 시간을 측정하고 묶음 검색이 느리면 인덱스 변경을 몰래 넣지 않고 별도 작업으로 제안한다.
- [ ] **5단계: 변경 범위·롤백 검토.** `git diff origin/develop...HEAD --check`로 확인하고 `db/migrations`, 파이프라인, 기존 API 응답 형식, 운영 설정이 바뀌지 않았는지 살핀다. 플래그를 끄고 이전 배포로 돌리는 절차와 이 기능 커밋의 `git revert` 명령을 제시한다. 머지 전 프론트 담당자의 검토를 받으며, 사용자 요청 없이 push·배포하지 않는다.

## 구현 인계 메모

이슈 탐색의 기존 담당자는 팀원 4이며 Jira #198은 2026-09-24 기준 완료 상태다. 이 브랜치는 격리되어 있고 추가형 변경만 계획하지만, MR 머지 전 프론트 담당자 검토는 필요하다. 이 계획은 운영 기능 활성화를 승인하지 않는다.
