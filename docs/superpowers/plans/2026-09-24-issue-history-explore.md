# Issue History Explore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search representative issue documents across completed snapshots as one result per `issue_key`, then navigate each snapshot's existing detail page from a timeline.

**Architecture:** Add two read-only endpoints without changing `/issues`, `/issues/{id}`, the schema, or stored clusters. Gate the new frontend path behind a default-off Vite build flag; reuse existing detail IDs and data instead of synthesizing a cross-date issue.

**Tech Stack:** Java 21, Spring Boot/JPA native SQL, PostgreSQL, React/Vite, Node test runner, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-24-issue-history-explore-design.md`

## Global Constraints

- Work only in the isolated `feature/issue-history-explore` worktree based on `origin/develop` `5d9768d`; do not modify the user's dirty checkout.
- `VITE_ISSUE_HISTORY_ENABLED` defaults **off**. Do not turn it on in production or deploy from this plan.
- Read-only API and UI only: no schema migration, backfill, deletion, clustering, or existing endpoint response change.
- Group by non-null `issue_key`; a null key is a singleton. Do not call the group a single real-world event.
- Only representative `label` is searchable; member documents B/C/D, aliases, and semantic event matching are out of scope.
- Limit is 1–100; offset is nonnegative; `q` trims to 1–200 characters; `%`, `_`, `\` match literally.
- The history list includes only non-discarded rows from completed `cluster_snapshot`s, newest first, with exact `snapshotTs`.
- Preserve snapshot-specific members, reports and stocks by navigating existing `/issues/{id}`.

## File Structure

- `backend/.../issue/IssueQueryRepository.java`: native read-only search/count/history queries and projections.
- `backend/.../issue/IssueService.java`: query validation, pagination and anchor-ID behavior.
- `backend/.../issue/IssueController.java`: additive routes.
- `backend/.../issue/dto/IssueHistoryGroupResponse.java`, `IssueOccurrenceResponse.java`: distinct API contracts.
- `backend/src/test/java/io/wikipulse/backend/issue/IssueControllerTest.java`: HTTP contract and invalid-query tests.
- `db/tests/test_issue_history_sql.py`: actual PostgreSQL grouping, filtering, ordering and pagination tests using rollback fixture.
- `frontend/src/data/api/adapters.js`, `client.js`, `frontend/src/data/index.js`, `contracts.js`: validate and expose new API methods.
- `frontend/.env.example`: document the disabled-by-default opt-in without changing an actual deployment environment.
- `frontend/src/data/history.js`: one small feature-flag predicate and display mapping; no cross-snapshot data merge.
- `frontend/src/pages/explore/ExplorePage.jsx`, `frontend/src/pages/explore/explore.css`: grouped search mode, leaving default list intact.
- `frontend/src/pages/event/EventPage.jsx`, `frontend/src/styles/details.css`: detail timeline that links to existing IDs.
- `frontend/tests/history.test.js`, `frontend/e2e-api/issue-history.spec.js`: data and UI regressions.

## Review Focus

1. Literal `%`, `_`, `\` in `q` must not turn into SQL wildcards or return unrelated documents (Task 1 test).
2. Null keys, a changed representative key, and separate live/replay keys must not collapse into one result (Task 1 test).
3. Discarded rows or unfinished snapshots must not appear in counts, results or history (Tasks 1–2 tests).
4. Multiple snapshots on one calendar day must remain separate, and page boundaries must not duplicate/miss records (Task 2 test).
5. An API failure must not remove the existing issue detail; disabled flag must not request new endpoints (Tasks 3–5 tests).

---

### Task 1: Read-only grouped search endpoint

**Files:** Modify `backend/src/main/java/io/wikipulse/backend/issue/{IssueController,IssueService,IssueQueryRepository}.java`; create `backend/src/main/java/io/wikipulse/backend/issue/dto/IssueHistoryGroupResponse.java`; test `backend/src/test/java/io/wikipulse/backend/issue/IssueControllerTest.java`, `db/tests/test_issue_history_sql.py`.

**Interfaces:** Produces `GET /api/v1/issues/history/search?q=&source=&offset=&limit=` → existing `ApiResponse<List<IssueHistoryGroupResponse>>` with `PageMeta.Pagination`. DTO fields: `id` (latest cluster ID), `label`, `source`, `snapshotTs` (latest), `status`, `pulseScore`, `firstSeen`, `occurrenceCount`. FE Task 3 consumes these names.

Start the HTTP test with this exact assertion shape (complete the Mockito stub with the DTO constructor defined in this task):

```java
mvc.perform(get("/api/v1/issues/history/search")
        .param("q", "Odyssey").param("offset", "0").param("limit", "20"))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.data[0].occurrenceCount").value(10))
   .andExpect(jsonPath("$.meta.pagination.total").value(1));
```

Controller entrypoint and service signature:

```java
@GetMapping("/history/search")
public ApiResponse<List<IssueHistoryGroupResponse>> searchHistory(
        @RequestParam String q, @RequestParam(required = false) String source,
        @RequestParam(required = false) Integer offset,
        @RequestParam(required = false) Integer limit) {
    return service.searchHistory(q, source, offset, limit);
}
```

- [ ] **Step 1: Establish baseline.** From `backend`, run `.\gradlew.bat test --tests io.wikipulse.backend.issue.IssueControllerTest`; record any pre-existing failure. From the worktree root, run `python -m pytest db/tests/test_issue_rankings_sql.py -q`; if skipped, record missing test dependency rather than counting skip as pass.
- [ ] **Step 2: Write failing HTTP contract tests.** Add `GET /api/v1/issues/history/search?q=Odyssey&offset=0&limit=20` asserting one result's `id`, `occurrenceCount`, `firstSeen` and `meta.pagination.total`; add blank/201-character q, bad source/limit/offset → 400. Mock the new `service.searchHistory(...)` method.
- [ ] **Step 3: Write failing SQL tests.** Follow `db/tests/test_issue_rankings_sql.py`: extract the new `@Query` text from `IssueQueryRepository` and run it against the rollback fixture. Insert a key twice on different completed dates, one same-label different key, one replay key, two null keys, a discarded row and an unfinished snapshot. Assert group count, latest ID, first/latest timestamps, source separation and stable 1-row pagination. Add labels `100%`, `A_B`, and `C\D`, asserting literal patterns match only the intended group.
- [ ] **Step 4: Run both focused suites red.** Expect compilation/missing-method failure in Java and missing query in Python.
- [ ] **Step 5: Implement minimum read-only repository/service/controller.** Use a CTE that first finds distinct eligible group keys whose `label ILIKE :pattern ESCAPE '\'`, then collects **all eligible occurrences of those keys**; use `row_number() OVER (PARTITION BY group_key ORDER BY snapshot_ts DESC,id DESC)` for the representative and `count(*)`/`min(snapshot_ts)` for metadata. Use `COALESCE(issue_key, 'legacy-id:' || id)` only if its synthetic prefix cannot collide with current `source:wiki:title` keys; keep the null-key SQL test. Separate count query must count groups before `OFFSET/LIMIT`. Require an `EXISTS` match in `cluster_snapshot` on **both source and timestamp**. In `IssueService`, make a literal pattern with `trim()`, `Locale.ROOT`, and `replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")`; return 400 for blank or over-200 q. Reuse `QueryParams.source/offset/limit` and `PageMeta.Pagination.of`.
- [ ] **Step 6: Run tests green.** Run the two focused suites again, then from `backend` run `.\gradlew.bat test --tests 'io.wikipulse.backend.issue.*'`. A skipped PostgreSQL test does **not** satisfy SQL verification; use an isolated PostgreSQL fixture before proceeding to frontend enablement.
- [ ] **Step 7: Commit.** `git add` only Task 1 files; `git diff --cached --check`; `git commit -m "feat: add read-only grouped issue history search"`.

### Task 2: Per-ID occurrence timeline endpoint

**Files:** Modify `backend/src/main/java/io/wikipulse/backend/issue/{IssueController,IssueService,IssueQueryRepository}.java`; create `backend/src/main/java/io/wikipulse/backend/issue/dto/IssueOccurrenceResponse.java`; extend `IssueControllerTest.java` and `db/tests/test_issue_history_sql.py`.

**Interfaces:** Produces `GET /api/v1/issues/{id}/history?offset=&limit=` → `ApiResponse<List<IssueOccurrenceResponse>>` plus pagination. Entry fields: `id`, `snapshotTs`, `status`, `pulseScore`, `memberCount`; Task 3 consumes them. Anchor ID with null key returns only itself; absent/discarded ID returns 404.

Use a route distinct from `/{id}` and the same pagination envelope:

```java
@GetMapping("/{id}/history")
public ApiResponse<List<IssueOccurrenceResponse>> history(
        @PathVariable Long id,
        @RequestParam(required = false) Integer offset,
        @RequestParam(required = false) Integer limit) {
    return service.history(id, offset, limit);
}
```

- [ ] **Step 1: Write failing controller tests.** Mock `service.history(42L, 0, 20)` and assert exact timestamp and pagination; assert missing and discarded anchors yield 404, invalid limit 400.
- [ ] **Step 2: Write failing SQL tests.** Insert one key at two exact timestamps on the same day and a third on a later day; assert all three IDs newest-first and correct second-page result. Assert different source/key, discarded row and unfinished snapshot excluded; null-key anchor yields exactly itself.
- [ ] **Step 3: Run focused tests red.** Use the commands from Task 1 plus a focused Python test selection for the new timeline tests.
- [ ] **Step 4: Implement minimal endpoint.** `IssueService.history(Long id,Integer offset,Integer limit)` loads the anchor via `clusterRepository.findById`, rejects `DISCARDED`, calls native query/count with `anchor.getSource()`, anchor key (nullable), and anchor ID. Query predicate: `(:issueKey IS NOT NULL AND c.issue_key = :issueKey) OR (:issueKey IS NULL AND c.id = :anchorId)`; also require matching source, completed snapshot, non-discarded status. Order `snapshot_ts DESC,id DESC`; count before paging. Reuse `QueryParams`/`PageMeta`.
- [ ] **Step 5: Run focused tests green and commit.** `git diff --check`; commit only Task 2 files as `feat: add issue occurrence timeline API`.

### Task 3: Frontend API contract and default-off guard

**Files:** Modify `frontend/src/data/api/{adapters,client}.js`, `frontend/src/data/{index,contracts}.js`, `frontend/.env.example`; create `frontend/src/data/history.js`, `frontend/tests/history.test.js`.

**Interfaces:** `dataClient.searchIssueHistory(params, options)` and `dataClient.listIssueHistory(id, params, options)` return validated `DataResponse` values from Tasks 1–2. `issueHistoryEnabled(env, dataSource)` returns true only when `env.VITE_ISSUE_HISTORY_ENABLED === "true" && dataSource === "api"`. Tasks 4–5 consume these APIs.

Guard and client methods:

```js
export const issueHistoryEnabled = (env = {}, dataSource) =>
  env.VITE_ISSUE_HISTORY_ENABLED === "true" && dataSource === "api";

searchIssueHistory: (params = {}, options) =>
  list("/issues/history/search", params, options, issueHistoryGroup, true),
listIssueHistory: (id, params = {}, options) =>
  list(`/issues/${pathId(id)}/history`, params, options, issueOccurrence, true),
```

- [ ] **Step 1: Write failing Node tests.** `history.test.js` asserts absent/`false`/mock flag yields false, true+api yields true; adapters reject malformed `snapshotTs`, negative `occurrenceCount`, invalid source/status, missing pagination. Stub fetch to assert exact API paths and encoded ID.
- [ ] **Step 2: Run red.** `cd frontend; node --test tests/history.test.js`; expect missing export/method.
- [ ] **Step 3: Add validators and client delegation.** For groups validate `id`, `label`, `source`, UTC `snapshotTs`/`firstSeen`, status, nonnegative score/count; for occurrences validate `id`, timestamp, status, score, `memberCount`. Use `adaptResponse(...,{list:true,paginated:true,validate})`; add methods to `createApiClient` and `createDataClient` delegation. Keep existing method shapes unchanged. `history.js` exports only flag predicate plus any small pure card mapper needed later. Add `VITE_ISSUE_HISTORY_ENABLED=false` and a short comment to `frontend/.env.example`, not to an actual `.env`.
- [ ] **Step 4: Run green and commit.** `npm run test:data`; `npm run test:contract`; commit Task 3 files as `feat: add issue history frontend API contract`.

### Task 4: Grouped search mode in Explore

**Files:** Modify `frontend/src/pages/explore/ExplorePage.jsx`, `frontend/src/pages/explore/explore.css`; extend `frontend/tests/history.test.js`; create/extend `frontend/e2e-api/issue-history.spec.js`.

**Interfaces:** Consumes `issueHistoryEnabled` and `searchIssueHistory`. Existing `usePageData()` latest list remains the no-query/flag-off path. Search-card title links to `#/issues/{group.id}`; no group bookmark button.

Mode switch must keep the old path untouched:

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

- [ ] **Step 1: Write failing UI/data test.** With flag off, typing filters only existing page and mock fetch receives no history request. With flag on/API mode, typing `Odyssey` calls server once with trimmed q, offset 0, limit 20; shows one group card with occurrence count/first-last/source and links to latest ID. Changing page uses server pagination; clearing q restores old latest list. Search mode hides the current-snapshot status filter and does not apply its old value.
- [ ] **Step 2: Run red.** `cd frontend; npm run test:data` and targeted `npx playwright test --config playwright.api.config.js e2e-api/issue-history.spec.js`.
- [ ] **Step 3: Implement minimum UI.** Keep `filtered` and existing JSX for no-query/flag-off. Add debounced nonempty search (e.g. 250 ms), `searchOffset` state, `useAsyncResource` keyed by q+offset+flag; call `dataClient.searchIssueHistory({q,offset,limit:20},{signal})`. Render a dedicated simple group card; do **not** reuse `EventRow`'s snapshot bookmark semantics. Use new search pagination only in search mode. Show explicit loading/error/empty states; abort stale requests.
- [ ] **Step 4: Run green and commit.** `npm run test:data`, targeted Playwright test, `npm run lint`, `npm run build`; commit Task 4 files as `feat: show grouped historical issue search`.

### Task 5: Snapshot timeline on existing detail

**Files:** Modify `frontend/src/pages/event/EventPage.jsx`, `frontend/src/styles/details.css`; extend `frontend/tests/history.test.js` and `frontend/e2e-api/issue-history.spec.js`.

**Interfaces:** Consumes `listIssueHistory(event.id,{offset:0,limit:100})`; each entry links to `#/issues/{entry.id}`. The selected detail still comes exclusively from existing `getIssue(eventId)`.

The detail data request and history request stay separate:

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

- [ ] **Step 1: Write failing tests.** Flag off: no history request or timeline. Flag on: entries show exact timestamp (including two same-day times), selected ID is marked, click moves to another existing detail ID and its own members/report/stocks. History API failure leaves existing detail visible with an inline retry/error. More than 100 occurrences has a next-page control rather than silently truncating.
- [ ] **Step 2: Run red.** Run focused Node/Playwright tests.
- [ ] **Step 3: Implement minimum timeline.** Use `useAsyncResource` keyed by `eventId` and page offset, but return no-op data when flag off so no new endpoint is called. Render a compact list above the existing tabs; link IDs, not derived issue keys. Keep API detail tabs (`report/overview/evidence`) and existing save action unchanged. Display `source`/representative-document wording, not “one incident.”
- [ ] **Step 4: Run green and commit.** `npm run test:data`, targeted Playwright, `npm run lint`, `npm run build`; commit Task 5 files as `feat: navigate issue snapshots from detail`.

### Task 6: Rollback and regression gate

**Files:** No product file required; record evidence in final report, not AGENTS.md or a second status document.

**Interfaces:** Produces a reproducible verification/rollback report for the MR reviewer. No deployment.

- [ ] **Step 1: Verify default-off.** `npm run build` without flag, run existing `frontend/e2e/issue-view.spec.js` and `frontend/tests/explore.test.js`; confirm old `/issues` and `/issues/{id}` requests/HTML remain unchanged.
- [ ] **Step 2: Verify opt-in.** `VITE_ISSUE_HISTORY_ENABLED=true npm run build` (PowerShell: `$env:VITE_ISSUE_HISTORY_ENABLED='true'; npm run build; Remove-Item Env:VITE_ISSUE_HISTORY_ENABLED`) and run new tests against an isolated API/mock fixture. No production flag change.
- [ ] **Step 3: Verify backend/SQL.** Full backend test and actual PostgreSQL SQL test. If PostgreSQL fixture cannot run, report blocker; do not claim SQL correctness or enable the flag.
- [ ] **Step 4: Read-only sample check.** Query one known repeated representative (Odyssey) through the new endpoints in a non-production or read-only environment, compare counts/timestamps with direct SQL, and click two different IDs. Capture timings; if grouped search is slow, stop and propose a separate index migration rather than silently adding one.
- [ ] **Step 5: Review diff and rollback.** `git diff origin/develop...HEAD --check` and confirm no `db/migrations`, pipeline, existing API response-shape or production config changes. Show commands to disable flag/redeploy and `git revert` this feature's commits. Request frontend-owner review before merge; do not push/deploy without user request.

## Execution handoff

The owner of Explore (#198) was 팀원 4 and that Jira issue is complete as of 2026-09-24. This branch is isolated and additive, but the MR still needs frontend-owner review before merge. The plan does not authorize production activation.
