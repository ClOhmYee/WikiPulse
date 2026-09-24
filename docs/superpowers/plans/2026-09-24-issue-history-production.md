# 운영 이슈 탐색 대표 문서·리포트 달력 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 운영 이슈 탐색에서 전체 대표 문서를 한 건씩 찾고 저장된 리포트 날짜를 달력으로 탐색한다.

**Architecture:** 기존 피드·상세·펄스맵은 그대로 둔다. 읽기 전용 그룹/리포트이력 API를 추가하고 프론트는 기본 꺼짐 빌드 플래그 뒤에서 이를 소비한다.

**Tech Stack:** Java 21, Spring Boot/JPA SQL, PostgreSQL, React/Vite, Node test, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-24-issue-history-production-design.md`

## Global Constraints

- 스키마·적재·기존 API 응답 변경 없음. 배포·push 없음.
- 새 화면은 `VITE_ISSUE_HISTORY_ENABLED=true`와 API 모드에서만 동작한다.
- 검색·페이지네이션은 서버 측, 이력 달력에는 리포트 보유 시점만 쓴다.
- 기존 로컬 미리보기와 팀원 코드의 사용자 변경을 보존한다.

## Review Focus

- 검색 특수문자 `%`, `_`, `\`와 공백.
- 같은 제목의 다른 키, 다른 출처, NULL 키.
- 완료되지 않은 스냅샷과 폐기 행.
- 한 날짜의 여러 리포트와 100건 초과 이력.
- 플래그 꺼짐·API 실패 시 기존 화면 보존.

### Task 1: 읽기 전용 서버 API

**Files:** `backend/.../issue/{IssueController,IssueService,IssueQueryRepository}.java`, `backend/.../issue/dto/IssueHistory*.java`, `backend/src/test/.../issue/IssueControllerTest.java`, `db/tests/test_issue_history_sql.py`.

- [ ] 기존 테스트 실행 및 결과 기록.
- [ ] HTTP·PostgreSQL SQL 실패 테스트 작성: 그룹 묶음/검색/페이지, 리포트 보유 이력, 경계 조건.
- [ ] 실패 확인 후 DTO·SQL·서비스·컨트롤러 최소 구현.
- [ ] 집중 테스트·이슈 영역 테스트 통과, 성능 측정.

### Task 2: 프론트 API 계약과 플래그

**Files:** `frontend/src/data/api/{client,adapters}.js`, `frontend/src/data/{index,contracts}.js`, `frontend/tests/history-production.test.js`, `frontend/.env.example`.

- [ ] 새 응답 검증·경로·기본 꺼짐 테스트 작성 후 실패 확인.
- [ ] 두 메서드와 응답 검증·플래그 판정 구현.
- [ ] `npm run test:data`, `npm run test:contract` 통과.

### Task 3: 운영 목록·상세 연결

**Files:** `frontend/src/pages/{explore,event}/...`, 달력 컴포넌트/스타일, `frontend/e2e-api/issue-history.spec.js`.

- [ ] 플래그 양쪽·대표 검색·리포트 달력·이력 API 오류 화면 테스트 작성 후 실패 확인.
- [ ] 기존 스타일로 그룹 목록을 그리고, 기존 상세 탭 앞에 리포트 달력을 추가. 다른 날짜는 기존 상세 ID로 이동.
- [ ] `npm run test:data`, `npm run lint`, `npm run build`, 화면 테스트 통과.

### Task 4: 최종 안전 검증

- [ ] PostgreSQL 실제 SQL 테스트와 실데이터 읽기 전용 검색/이력 비교.
- [ ] 기존 `/issues`, `/issues/{id}`, 펄스맵 회귀, 플래그 꺼짐/켜짐 빌드 확인.
- [ ] 변경 범위·롤백 절차 보고. push·MR·배포는 사용자 결정 전 보류.
