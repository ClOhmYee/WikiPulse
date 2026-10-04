# API 명세서 v1 — WikiPulse

- 기준: 2026-09-27 문서화, `develop` 커밋 `d082303`의 Spring 컨트롤러·DTO·SQL
- Base path: `/api/v1`. 아래 경로는 모두 이 접두부에 상대적이다.
- 연결 문서: [요구사항](requirements-v1.md) · [기술](tech-spec-v1.md) · [ERD](erd-v1.md)
- `frontend/docs/openapi.yaml`은 이슈·종목의 일부 경로만 반영한다. 계정·기록 경로는 이 문서와 컨트롤러를 대조해야 한다.

## 1. 공통 규약

조회 성공은 `{"data": ...}`이며 endpoint별 부가 정보가 있으면 `meta`를 더한다. 목록의 빈 결과는 `[]`, 없는 단건은 404다. 오류는 `{"error":{"code":"...","message":"..."}}` 형식이다. 주된 코드는 `INVALID_QUERY`(400), `UNAUTHORIZED`(401), `NOT_FOUND`(404), `INTERNAL`(500)이고 로그인·CSRF·중복 이메일에는 각각 401·403·409가 적용된다. 페이지 번호가 아닌 `offset`/`limit`을 쓰며 일반 목록 기본값은 0/50, 최대 100이다. 계정 보관함 목록 기본 limit은 20이다. 페이지네이션 응답은 `meta.pagination={offset,limit,total,hasMore}`다.

시각은 UTC ISO 8601로 전달한다. `pulseScore`는 단위 없는 급등 점수이며 수익률·발생 확률이 아니다. `source`는 `live|replay`; 이슈 `status`는 `DETECTED|VERIFYING|CONFIRMED|DISCARDED`; 멤버 `completeness`는 `complete|pending|unavailable`이다. 결측 수치를 0으로 치환하지 않는다. 기본 피드는 `DISCARDED`를 제외하고 종목 응답에는 검증 통과분만 포함한다.

시점별 버블 점수·멤버·조회수·편집수는 해당 클러스터에 고정된 값을 읽는다. 요약·후보·검증 결과 재사용은 원본 `snapshot_ts <=` 대상 `snapshot_ts`인 결과만 허용한다. 처리 시각 `generated_at`·`verified_at`은 이 사건 시점 비교에 사용하지 않는다.

## 2. 이슈 조회

| Method·path | 입력 | 주요 결과·의미 |
| --- | --- | --- |
| `GET /issues` | `snapshotTs?`, `status?`, `source?`, `offset?`, `limit?` | 선택한 완료 스냅샷의 이슈 카드. 미지정 시 최신 시점. `pulseScore` 내림차순·ID 오름차순. `meta.snapshotTs`와 페이지네이션 |
| `GET /issues/snapshots` | `from?`, `to?`, `source?` | 완료 시점 목록. `clusterCount=0`인 시점도 포함 |
| `GET /issues/map` | `snapshotTs?`, `source?` | 한 시점의 `clusters[]`, 각 클러스터의 `nodes[]`·`edges[]`, `meta`. 없는 시점 404 |
| `GET /issues/{id}` | 클러스터 ID | 이슈 상세, 스냅샷 멤버, 검증 종목 상위 5개, 저장된 경우 섹션형 `report` |
| `GET /issues/{id}/stocks` | `limit?` | 검증된 관련 종목. `tier`, `matchPath`, `similarity`, `gdeltLift`, `rationale` 포함 |
| `GET /issues/rankings` | 없음 | 최근 30일·Asia/Seoul 기준 최근 1년 각각 `pulseScore` 최고 이슈 상위 10건 |
| `GET /issues/history/groups` | `q?`, `status?`, `source?`, `offset?`, `limit?` | 완료·비폐기 시점의 대표 문서별 기록 묶음. LIVE와 replay를 함께 탐색 |
| `GET /issues/{id}/history/reports` | `offset?`, `limit?` | 같은 대표 문서에서 `issue_report`가 저장된 시점. 최신순 |

`/issues/{id}`의 핵심 응답은 다음과 같다. 실제 필드의 nullable 여부는 DTO를 따른다.

```json
{
  "data": {
    "id": 42, "label": null, "pulseScore": 8.4,
    "status": "VERIFYING", "source": "replay",
    "snapshotTs": "2026-08-02T19:00:00Z",
    "summary": null, "summaryModel": null,
    "members": [{
      "pageId": 901, "wiki": "enwiki", "title": "Strait of Hormuz",
      "titleKo": "호르무즈 해협",
      "weight": 1.0, "isSeed": true, "editCount": 87,
      "views": 12043, "completeness": "complete"
    }],
    "relatedStocks": []
  }
}
```

`title`은 식별·위키 링크용 영문 원문이다. 표시 우선순위는 `titleKo` → `titleKoFallback` → `title`이고 기계 번역은 ko.wikipedia 제목이 아니다. 상세 DTO는 없는 선택 표시명을 필드째 생략할 수 있다. 지도 `nodes[]`는 편집·조회수·기준선·급등 점수·집계 창·`completeness`를 내보낸다. `meta`에는 실제 `snapshotTs`, `source`, `scoreVersion`, `clusterCount`, `nodeCount`, `edgeCount`, `truncated` 등이 들어간다. `cluster_snapshot`에 기록된 완료 0건 시점은 빈 지도이며 존재하지 않는 시점과 구별한다.

섹션형 리포트가 저장돼 있으면 상세에 다음 객체가 추가된다. 저장값이 없거나 유효한 섹션이 없으면 `report` 필드 자체가 생략된다. 요약만 있다고 `report`가 생기지 않는다.

```json
{"report": {
  "status": "ready", "model": "claude-sonnet-4-5-20250929 (report_v1)",
  "generatedAt": "2026-09-24T05:00:00Z",
  "snapshotTs": "2026-08-02T19:00:00Z",
  "sections": [{"id":"overview","title":"이슈 개요","body":"...","evidenceIds":["901"]}]
}}
```

`evidenceIds`는 해당 이슈 멤버의 `pageId` 문자열이다. 현행 저장 경로는 시연 이슈용 일회성 생성 도구이며 자동 리포트 워커는 없다. 기록 그룹의 `occurrenceCount`는 같은 대표 문서의 기록 수, `defaultReportId`는 우선 선택할 보고서 ID다. 같은 대표 제목은 같은 현실 사건의 증명이 아니고 제목 이동도 자동 합쳐지지 않는다. `/issues/{id}/history/reports`는 요약만 있는 `issue_report` 행도 반환한다.

순위 API는 `data={asOf,monthFrom,yearFrom,monthly:[...],yearly:[...]}`이다. 같은 `issue_key`는 각 기간의 최고 점수 한 건을 남긴다. `label`이 없을 수 있다.

## 3. 종목 조회

| Method·path | 입력 | 주요 결과·의미 |
| --- | --- | --- |
| `GET /stocks` | `q?`, `sector?`, `exchange?`, `hasIssues?`, `offset?`, `limit?` | 종목 카드. `ticker`, `name`, `exchange`, `sector`, `issueCount`, `lastClose`(일봉 없으면 null) |
| `GET /stocks/{ticker}` | 티커 | 종목 설명과 상세 정보. 없는 티커 404 |
| `GET /stocks/{ticker}/issues` | 티커 | 해당 종목의 검증된 이슈 카드 |
| `GET /stocks/{ticker}/prices` | `from?`, `to?` (`YYYY-MM-DD`, 기본 최근 1년) | 거래일별 `{tradeDate,open,high,low,close,volume}` 오름차순 |

휴장일은 가격 점이 없으며 보간하지 않는다. 유효한 빈 구간은 200과 빈 배열, 잘못된 날짜는 400이다. 이슈 마커는 프론트가 `/stocks/{ticker}/issues`의 시점을 가격 차트에 겹친다. `lastClose`는 최신 보유 거래일 종가이며 실시간 시세가 아니다.

## 4. 회원·보관함

인증은 Bearer 응답이 아니라 HttpOnly 쿠키의 서버 세션과 CSRF다. 변경 요청 전에 `GET /auth/csrf`가 준 `headerName`·`token`을 헤더에 넣는다. 로그인 후 세션 ID와 CSRF 토큰이 교체되므로 새 토큰을 사용한다.

| Method·path | 요청·응답 |
| --- | --- |
| `GET /auth/csrf` | `{token,headerName}` |
| `POST /auth/signup` | `{email,password,displayName}` → 회원 정보, 201 |
| `POST /auth/login` | `{email,password}` → `{member}`, 세션 쿠키 |
| `POST /auth/logout` | 세션 무효화, 204 |
| `GET /me` | 인증된 회원 정보 |
| `GET /me/saved-state` | `{issueIds:string[],tickers:string[]}` |
| `GET /me/bookmarks` / `GET /me/watchlist` | 저장한 이슈·종목 카드. `q`, `offset`, `limit`; 저장 시각 내림차순 |
| `PUT`·`DELETE /me/bookmarks/{clusterId}` | 이슈 스냅샷 저장·해제, 멱등 204 |
| `PUT`·`DELETE /me/watchlist/{ticker}` | 종목 저장·해제, 멱등 204 |

보관함 항목은 특정 `clusterId`를 저장한다. 재클러스터링으로 대상이 삭제되면 FK에 따라 북마크도 삭제될 수 있다. 상세 검증·세션 규칙은 [계정·보관함 계약](backend/ACCOUNT_BOOKMARKS.md)을 따른다.

## 5. 현재 제공하지 않는 경로

`/pages/*`, `/search`, 알림(`/me/notifications*`), 댓글(`/issues/{id}/comments`, `/comments/{id}`), WebSocket 초안은 Spring 컨트롤러에 없다. 기존 v0.3 문서의 미래 초안을 현재 구현 API로 해석하지 않는다. 계정·북마크·관심종목은 구현됐고 이 미구현 목록에 포함되지 않는다.
