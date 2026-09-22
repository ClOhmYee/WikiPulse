# API 명세서 — WikiPulse (WikiPulse)

- 버전: **v0.3 (2026-09-18 개정)**
- v0.3 변경: 과거 상세·버블맵의 멤버 수치를 스냅샷에 고정하고 미래 원시 지표로 보충하지 않는 계약을 확정했다.
- 정본: 이 파일. 개정은 MR로 한다.
- 상위 문서: [requirements-v0.3.md](requirements-v0.3.md) — 무엇을 만드는가. 이 문서는 **그 화면들이 서버에 무엇을 묻는가**만 적는다.
- 데이터 모델: [erd-v0.1.md](erd-v0.1.md) / `db/migrations/V1__initial_schema.sql`부터 `V9__spike_revision_evidence.sql`까지의 누적 스키마. **응답 필드의 의미와 단위는 해당 마이그레이션 컬럼 주석이 정본이다.** 여기 다시 적지 않는다.

---

## 0. 이 문서가 정리한 것 — 계약이 두 벌이었다

아래 표는 **2026-09-08 통합 결정 이전 상태**다. 2026-09-09 WP-76에서 BE의 Issue/Stock 경로는 `/api/v1`과 응답 봉투로 변경되었고, 이슈 상세에 `pageId/wiki/title/weight/isSeed/editCount/views`를 가진 `members`가 추가되었다. 펄스맵의 스냅샷 목록·일괄 그래프 조회도 WP-74에서 구현되었다. [펄스맵 구현·계약](frontend/PULSE_MAP.md)을 참고한다.

| | FE 제안 (`frontend/docs/openapi.yaml`, `0.2.0-proposal`) | BE 구현 (`backend/`, WP-36) |
| --- | --- | --- |
| 경로 | `/api/v1/events`, `/entities`, `/stocks` | `/api/issues`, `/api/stocks` |
| 식별자 | slug (`eventId`, `entityId`) | `id`(BIGINT), `ticker` |
| 응답 | `{data, included, meta}` 봉투 + 오류 코드 | raw 배열/객체 |
| 데이터 | fixture 6건, "구현된 서버 아님" 명시 | DB 스키마 연결 |

**v0.1은 이렇게 합친다** (2026-09-08 결정):

- **경로·어휘·식별자는 BE·DB 쪽을 쓴다.** `event`가 아니라 `issue`, `entity`가 아니라 `page`. DB가 `issue_cluster`·`cluster_member`이고 명세 §3.2도 "클러스터 = 이슈"라, API만 다른 말을 쓰면 세 곳을 머릿속에서 번역해야 한다.
- **봉투·페이지네이션·오류 규약은 FE 제안 쪽을 쓴다.** 이미 설계돼 있고 프론트 조회 계층이 그 형태를 기대한다. BE의 적용은 WP-76에 포함되었다.
- base path는 `/api/v1`. ~~`/api`~~ → 버전 없는 경로는 계약이 바뀔 때 갈아탈 자리가 없다.

~~`frontend/docs/openapi.yaml`은 이 결정 이후 낡았다~~ → **현재 OpenAPI는 Spring 컨트롤러의 8개 GET 경로와 DTO를 반영했다** (2026-09-15, WP-95·97). 구현되지 않은 미래 API는 OpenAPI에 넣지 않는다. FE mock과 실제 API의 통합 실행 여부는 별도 검증 기록으로 구분한다.

---

## 1. 공통 규약

### 1.1 봉투

성공:

```json
{
  "data": {},
  "meta": { "snapshotTs": "2026-09-08T04:00:00Z" }
}
```

- 목록은 `data`가 배열, 단건은 객체. 결과 없음은 `[]`이지 `null`이 아니다.
- 없는 단건은 404다. `data: null`을 쓰지 않는다.
- `meta`는 해당 endpoint가 정의한 것만 담는다. 없으면 `meta` 자체를 생략한다.

오류:

```json
{ "error": { "code": "NOT_FOUND", "message": "issue 42 not found" } }
```

| code | HTTP | 언제 |
| --- | --- | --- |
| `INVALID_QUERY` | 400 | enum 밖의 값, 범위 밖 숫자, 정의 안 된 쿼리 키 |
| `UNAUTHORIZED` | 401 | 로그인 필요 endpoint에 토큰 없음·만료 |
| `NOT_FOUND` | 404 | 경로의 식별자가 없음 |
| `INTERNAL` | 500 | 그 외 |

유효한 문자열 필터가 아무것도 못 맞히는 경우(없는 섹터명 등)는 **오류가 아니라 200 + `[]`**다.

`message`는 개발자용 영문이다. 사용자에게 보여줄 한국어 문구는 FE가 `code`로 고른다.

### 1.2 페이지네이션

목록 endpoint에만 붙는다.

```json
"meta": { "pagination": { "offset": 0, "limit": 50, "total": 137, "hasMore": true } }
```

- `offset` ≥ 0 (기본 0), `limit` 1~100 (기본 50). 범위 밖은 `INVALID_QUERY`.
- `total`은 자르기 **이전** 조건 일치 개수. `hasMore` = `offset + data.length < total`.
- `offset >= total`이면 200 + `[]`.

### 1.3 시각·숫자

- 모든 시각은 **ISO 8601 UTC (`2026-09-08T04:00:00Z`)**다. 표시용 시간대 변환은 FE가 한다.
  ⚠️ FE 제안 계약은 `+09:00` 오프셋이었다. DB가 `TIMESTAMPTZ`, JPA가 `time_zone: UTC`라 UTC로 맞춘다.
- `pulseScore`는 **단위 없는 급등 점수**다. 배수·퍼센트·확률·정확도·수익률로 해석하지 않는다. 조회수 중심의 새 점수식은 WP-118 구현·회귀 검증 대상이다.
- `similarity`는 코사인(0~1), `gdeltLift`는 배수. 둘 다 `null` 가능 — 그 경로로 안 들어온 후보다.
- 결측을 `0`으로 치환하지 않는다. 차트 중간 날짜가 없으면 그 포인트를 생략하고 보간하지 않는다.

### 1.4 enum

DB `CHECK` 제약과 **같은 값을 그대로** 쓴다. 번역하지 않는다.

| 필드 | 값 | 화면 표기 |
| --- | --- | --- |
| `status` | `DETECTED` / `VERIFYING` / `CONFIRMED` / `DISCARDED` | 감지됨 / 검증 중 / 확정 / (노출 안 함) |
| `source` | `live` / `replay` | — |
| `tier` | `BOTH` / `GDELT_ONLY` / `EMBEDDING_ONLY` | — |
| `matchPath` | `DIRECT_MENTION` / `PRODUCT_INDUSTRY` / `SUPPLY_CHAIN` / `REGION` | 직접 언급 / 제품·산업 / 공급망 / 지역 노출 |
| `completeness` | `complete` / `pending` / `unavailable` | 확정 / 입력 대기 / 원본 없음 |

🔴 `DISCARDED` 클러스터와 `verified=false` 종목은 **어떤 조회 API로도 나가지 않는다.** LLM 검증에서 떨어진 것이라 화면에 뜨면 안 된다.

`status`는 이슈 판정 단계가 아니라 판정 후 AI 보강 상태다. `DETECTED`는 요약·종목 검증 전, `VERIFYING`은 처리 중, `CONFIRMED`는 요약 생성과 종목 검증 작업이 끝난 상태다. 조회수 미도착은 아직 이슈가 아닌 후보 대기이며, GATEWAY·GDELT 실패는 재시도/`VERIFYING`으로 남긴다. 모든 작업이 끝난 뒤 검증 통과 종목이 없는 `CONFIRMED`만 정상 0건이다. 미처리·장애 데이터를 시연 편의로 `CONFIRMED`에 올리면 안 된다.

과거 스냅샷을 조회할 때 버블 점수·멤버·편집수·조회수·기준선은 해당 `cluster_id`의 `cluster_member` 고정값을 사용한다. 일반 이슈 상세도 최신 `page_edit_window`나 `page_view_hourly` 행으로 이를 보충하지 않는다. 이 멤버 수치 계약은 WP-129로 구현됐다. 요약·검증 종목은 `issue_key` 단위 결과를 재사용하되, 요약은 `issue_report.generated_at <= snapshotTs`, 종목은 `cluster_stock.check_state='DONE' AND verified=true AND verified_at IS NOT NULL AND verified_at <= snapshotTs`인 결과만 노출한다. 재사용 결과를 다른 `cluster_id` 행으로 복사할 때도 원 결과의 `generated_at`·`verified_at`을 보존하며 복사 시각으로 덮지 않는다. 미래에 생성된 원문·수치·요약·종목 결과를 같은 `issue_key`의 과거 화면에 소급 노출하지 않는다. 현재 요약·종목 재사용 조회는 대상 스냅샷 상한 없이 가장 최근 결과를 선택하고 요약 복사 시각을 새 `generated_at`으로 기록하므로 이 as-of 계약은 아직 만족하지 못한다(WP-119·120).

---

## 2. 이슈 — 피드 · 버블맵 · 상세

피드와 펄스맵은 이슈를 공유하지만 독립 페이지다. 피드 내부에서 카드/리스트를 전환한다. 펄스맵은 시점별 문서 그래프가 필요하므로 아래 목록 응답 외에 `GET /api/v1/issues/map` 계약을 추가했고 서버 구현까지 완료했다(2026-09-15, WP-74·95). [필드·행동 명세](frontend/PULSE_MAP.md), [통합 OpenAPI](../frontend/docs/openapi.yaml)를 참고한다.

### `GET /api/v1/issues`

| 쿼리 | 값 | 기본 |
| --- | --- | --- |
| `snapshotTs` | ISO 8601. 리플레이 시점 | 생략 시 가장 최근 스냅샷 |
| `status` | 위 enum, 쉼표로 여러 개 | `DETECTED,VERIFYING,CONFIRMED` |
| `source` | `live` / `replay` | 둘 다 |
| `offset` `limit` | 1.2 | |

정렬은 `pulseScore` 내림차순 고정. 동률은 `id` 오름차순 (동일 `snapshotTs` 안에서 순서가 흔들리면 버블맵이 매 폴링마다 튄다).

```json
{
  "data": [
    { "id": 42, "label": "Strait of Hormuz tension",
      "pulseScore": 8.4, "status": "CONFIRMED",
      "source": "live", "snapshotTs": "2026-09-08T04:00:00Z",
      "memberCount": 5, "stockCount": 3 }
  ],
  "meta": { "snapshotTs": "2026-09-08T04:00:00Z", "pagination": { } }
}
```

- `label`은 LLM이 붙이기 전 `null`이다. FE는 그때 대표 문서명(`GET /issues/{id}`의 `members[0].title`)을 쓴다.
- `memberCount`·`stockCount`는 버블 크기·배지용 집계다. 목록에서 상세를 N번 부르지 않게 하려고 넣었다.

### `GET /api/v1/issues/snapshots`

리플레이 시간 슬라이더가 고를 수 있는 시점 목록. 슬라이더가 임의 시각을 보내면 대부분 빈 결과가 나온다 — 스냅샷은 이산적이다.

```json
{ "data": [ { "snapshotTs": "2026-09-08T04:00:00Z", "source": "live", "clusterCount": 23 } ] }
```

쿼리 `from`·`to`(ISO 8601), `source`.

### `GET /api/v1/issues/{id}`

```json
{
  "data": {
    "id": 42, "label": "Strait of Hormuz tension",
    "pulseScore": 8.4, "status": "CONFIRMED", "source": "live",
    "snapshotTs": "2026-09-08T04:00:00Z",
    "summary": "…", "summaryModel": "claude-…",
    "members": [
      { "pageId": 901, "wiki": "enwiki", "title": "Strait of Hormuz",
        "weight": 1.0, "isSeed": true, "editCount": 87, "views": 12043,
        "completeness": "complete" }
    ],
    "relatedStocks": [ ]
  }
}
```

- `summary`는 `issue_report`. 아직 없으면 `null`. 운영 writer와 상태 전이는 WP-119로 구현됐지만 worker는 기본값이 꺼져 있고 실제 GATEWAY·EC2 실행은 하지 않았다. 현재 로컬 데모 값은 시드에서 생성한 요약이다.
- `members`는 `weight` 내림차순. `isSeed=true`는 최종 급증 관문을 직접 통과한 루트 문서 또는 생성 시각 동시성으로 편입된 새 사건 문서다. `isSeed=false`는 Clickstream 이웃 중 사건기간 편집 재급증 기준을 통과한 기존 문서다. Wikidata 관계는 멤버 편입 사유가 아니다.
- `members[].editCount/views`는 이 `cluster_id`가 가리키는 스냅샷에서 판정에 사용한 고정값(`cluster_member`)이다. 아직 판정 입력이 없거나 원본이 없어서 `null`일 수 있지만, 최신 원시 테이블 값으로 대체하지 않는다. ~~최신 `page_edit_window`·`page_view_hourly` 한 행을 끌어왔다~~ → 고정값으로 전환 (2026-09-18, WP-129). 과거 스냅샷에 그 뒤의 수치가 붙던 결함이다.
- `members[].completeness`는 그 `null`이 무슨 뜻인지 말한다 — `complete`(판정 끝) / `pending`(입력 대기) / `unavailable`(원본 없음). 지도 노드와 같은 어휘다. 둘 다 빈칸으로 보이면 사용자는 서비스가 고장 난 줄 안다.
- `relatedStocks`는 아래 endpoint와 **같은 객체**이며, 상세 진입 시 왕복을 줄이려고 상위 5개만 미리 담는다. 전체는 아래로 부른다.

### `GET /api/v1/issues/{id}/stocks`

```json
{
  "data": [
    { "ticker": "FANG", "name": "Diamondback Energy", "exchange": "NASDAQ",
      "sector": "Energy", "tier": "BOTH",
      "matchPath": "SUPPLY_CHAIN", "similarity": 0.28, "gdeltLift": 6.1,
      "rationale": "호르무즈 해협 봉쇄는 …" }
  ]
}
```

- **`verified=true`만 나간다.** 필터가 아니라 규칙이다.
- 정렬: `tier` (`BOTH` → `GDELT_ONLY` → `EMBEDDING_ONLY`) → `gdeltLift` 내림차순 → `similarity` 내림차순. 명세 §6.3의 검증 우선순위와 같은 순서다.
- `rationale`이 **연관 근거다.** 상관계수가 아니다 (명세 §9).
- 제품 정책상 노출 개수 상한은 두지 않기로 확정했다(WP-22). `limit`은 전송 응답 크기만 제한한다.

---

### 기간별 이슈 Top 10 (WP-198)

`GET /api/v1/issues/rankings` — 별도 쿼리 인자 없이 최근 30일과 최근 1년의 순위를 함께 반환한다.

- 조회 시각 `asOf`를 한 번 고정한다. `monthFrom`은 30일 전, `yearFrom`은 Asia/Seoul 기준 1년 전 같은 시각(윤일은 전년 2월 말일)이며 양 끝 시각을 포함한다.
- 각 기간의 완료 스냅샷(`cluster_snapshot`)에 속한 `DETECTED`, `VERIFYING`, `CONFIRMED` 이슈를 집계한다. 목록의 분석 상태 필터와 페이지 번호는 순위에 영향을 주지 않는다.
- 같은 `issue_key`는 기간 내 최고 급증점수 한 건만 남긴다. 키가 없으면 개별 ID로 구분한다. 동점은 최신 스냅샷, 낮은 ID 순이며 최종 상위 10건까지 반환한다.
- 항목은 `{id, label, pulseScore}`이며 `id`는 최고점을 기록한 시점의 상세 ID다. 제목이 없으면 `label`은 null/생략 가능하다.
- 응답: `{data: {asOf, monthFrom, yearFrom, monthly: [...], yearly: [...]}}`. 데이터가 없는 기간은 빈 배열이다. 프론트는 제목·점수와 상세 링크만 표시한다.
- 이슈 목록은 기존 단일 스냅샷 API와 프론트 병합 로직을 유지한다. 연간 순위를 만들기 위해 브라우저가 모든 스냅샷을 개별 조회하지 않는다.

## 3. 문서 (wiki page) — MVP 제외·미구현

단일 위키 문서 상세 화면은 MVP에서 제외했다. 아래 계약은 향후 기능 참고용이며 현재 Spring 컨트롤러와 통합 OpenAPI에는 없다. MVP 클라이언트가 호출해서는 안 된다.

이슈의 근거 문서 화면용.

### `GET /api/v1/pages/{id}`

```json
{
  "data": { "id": 901, "wiki": "enwiki", "title": "Strait of Hormuz",
            "url": "https://en.wikipedia.org/wiki/Strait_of_Hormuz",
            "firstSeen": "…", "lastSeen": "…" }
}
```

### `GET /api/v1/pages/{id}/metrics`

편집·조회수 시계열 + 기준선. 문서 상세 차트.

| 쿼리 | 값 |
| --- | --- |
| `from` `to` | ISO 8601. 기본 최근 7일 |
| `metric` | `edits` / `views` / `both` (기본 `both`) |

```json
{
  "data": {
    "edits": [ { "windowStart": "2026-09-08T03:00:00Z", "editCount": 87, "editorCount": 12 } ],
    "views": [ { "tsHour": "2026-09-08T03:00:00Z", "views": 12043 } ],
    "baseline": [ { "hourOfDay": 3, "editEwma": 2.1, "editStddev": 1.4, "viewEwma": 380.0 } ],
    "spikes": [ { "detectedAt": "…", "windowStart": "…", "editZ": 11.2, "viewRatio": 2.6, "spikeScore": 8.4 } ]
  }
}
```

- `baseline`은 시간대(0~23, UTC) 기준이라 시계열과 축이 다르다. 차트에 겹칠 때 FE가 시각→`hourOfDay`로 접어서 매핑한다. ~~요일·시간대(0~167)·`hourOfWeek`~~ → 2026-09-15 변경 (WP-84).
- 새 판정 계약(WP-118)에서는 조회수 2차 관문을 통과한 문서만 `spikes`에 들어가므로 LIVE 응답의 `viewRatio`는 판정 근거를 가져야 한다. `null`은 과거 스키마·리플레이 호환 값이며 신규 LIVE 이슈의 정상 상태로 사용하지 않는다.

~~Wiki Intelligence 화면의 MVP 포함 여부 확인 필요~~ → 단일 위키 문서 상세는 페이지 구성에서 제외했다(2026-09-09, [페이지 구성 정본](frontend/PAGES.md)). 위 문서 데이터 API 제안은 이번 페이지 정리에서 변경하지 않는다. 화면 제거를 데이터 모델이나 endpoint 삭제로 해석하지 않는다.

---

## 4. 종목

### `GET /api/v1/stocks`

쿼리: `q`(회사명·티커 부분 일치, 대소문자 무시), `sector`, `exchange`, `hasIssues`(boolean — 이슈가 걸린 종목만), `offset`, `limit`.

```json
{ "data": [ { "ticker": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ",
              "sector": "Technology", "issueCount": 2 } ] }
```

`businessSummary`는 목록에 넣지 않는다 — 종목당 수천 자라 5,100건 목록이 수 MB가 된다.

### `GET /api/v1/stocks/{ticker}`

`ticker`는 대소문자를 구분하지 않는다. 응답은 마스터의 대문자 표기다.

```json
{ "data": { "ticker": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ",
            "cik": "0001045810", "sector": "Technology", "businessSummary": "…" } }
```

`embedding`은 내보내지 않는다. 1,536차원 벡터는 화면이 쓸 일이 없다.

### `GET /api/v1/stocks/{ticker}/issues`

이 종목이 걸린 이슈 목록. 응답은 2절 카드와 같은 형태 + `tier`·`matchPath`·`rationale`. `verified=true`만.

### `GET /api/v1/stocks/{ticker}/prices`

쿼리 `from`·`to` (`YYYY-MM-DD`, 기본 최근 1년).

```json
{ "data": [ { "tradeDate": "2026-09-05", "open": 178.2, "high": 181.0,
              "low": 177.4, "close": 180.6, "volume": 41203300 } ] }
```

거래일만 있다. 휴장일은 포인트가 없고 보간하지 않는다. 차트 위 이슈 발생 시점 표시는 `/stocks/{ticker}/issues`의 `snapshotTs`로 FE가 겹친다 — 서버가 합쳐 내리지 않는다.

---

## 5. 회원 · 관심종목 · 알림 · 토론 — MVP 제외·미구현

~~MVP 인증·관심종목·알림·토론 API~~ → **전부 MVP 범위에서 제외** (2026-09-17, WP-104). 아래는 v0.1 당시의 미래 기능 초안이며 현재 Spring 컨트롤러와 통합 OpenAPI에는 없다. 인증 방식·알림 수단·WebSocket 여부도 이번 MVP에서 결정하지 않는다.

| endpoint | 하는 일 |
| --- | --- |
| `POST /api/v1/auth/signup` | `{email, password, displayName}` |
| `POST /api/v1/auth/login` | → `{token, member}` |
| `GET /api/v1/me` | 내 정보 |
| `GET /api/v1/me/watchlist` | 관심종목 목록 (종목 요약 + `addedAt`) |
| `PUT /api/v1/me/watchlist/{ticker}` | 추가 (멱등) |
| `DELETE /api/v1/me/watchlist/{ticker}` | 해제 |
| `GET /api/v1/me/notifications` | 쿼리 `unreadOnly`. `{id, body, issue, stock, readAt, createdAt}` |
| `PATCH /api/v1/me/notifications/{id}` | `{"readAt": "…"}` 읽음 처리 |

`PUT`으로 관심종목을 넣는 이유: 같은 종목을 두 번 눌러도 409가 아니라 200이어야 한다. `watchlist` PK가 `(member_id, ticker)`라 서버도 중복을 만들 수 없다.

알림의 `issue`·`stock`은 `null`일 수 있다 — 상장폐지·클러스터 삭제 시 FK가 `SET NULL`이고 **알림 본문은 남긴다**.

### 토론

| endpoint | 하는 일 |
| --- | --- |
| `GET /api/v1/issues/{id}/comments` | 이슈별 댓글. `deleted_at IS NULL`만 |
| `POST /api/v1/issues/{id}/comments` | `{body}`. 스레드가 없으면 서버가 만든다 (클러스터당 1개) |
| `DELETE /api/v1/comments/{commentId}` | 본인 것만. soft delete |

```json
{ "data": [ { "id": 7, "body": "…", "author": { "id": 3, "displayName": "…" },
              "createdAt": "…" } ] }
```

`author`가 `null`이면 탈퇴한 사용자다 — FE는 "삭제된 사용자"로 표시한다.

**과거 초안의 WebSocket**: `/ws/issues/{id}` — 새 댓글 push. `/ws/me` — 알림 push. MVP에서는 구현하지 않는다.

---

## 6. 통합 검색 — 미래 계약·미구현

통합 검색은 현재 MVP 핵심 루프와 Spring 컨트롤러에 없다. 아래 계약은 향후 기능 참고용이며 통합 OpenAPI에는 포함하지 않는다.

### `GET /api/v1/search?q=`

FE 공통 헤더용. 이슈·문서·종목을 한 번에.

```json
{ "data": { "issues": [ ], "pages": [ ], "stocks": [ ] },
  "meta": { "limitPerType": 5 } }
```

- 각 타입 상위 5개(쿼리 `limitPerType`, 1~20). 페이지네이션 없다.
- 단순 부분 일치다. 형태소 분석·의미 검색·자동완성이 아니다.
- `q`가 비었거나 공백뿐이면 200 + 전부 `[]`. 최대 200자.

---

## 7. 구현 현황 (2026-09-18)

| endpoint | 상태 |
| --- | --- |
| `GET /api/v1/issues`, `/issues/{id}`, `/issues/{id}/stocks` | **구현됨** — 상세 members는 WP-129부터 `cluster_member` 고정값과 `completeness`를 읽음. 로컬 회귀 테스트 완료, EC2·실데이터 API 재검증은 하지 않음 |
| `GET /api/v1/issues/snapshots`, `/issues/map` | **구현됨** — 완료 스냅샷 목록과 원자적 그래프. map은 `cluster_member` 고정값을 읽음 |
| `GET /api/v1/stocks`, `/stocks/{ticker}`, `/stocks/{ticker}/issues` | **구현됨 / as-of 재사용 미완료** — 응답 봉투 적용. 요약·검증 재사용 조회에 대상 스냅샷 상한이 없어 과거 backfill에 미래 결과가 섞일 수 있음 |
| `GET /api/v1/stocks/{ticker}/prices` | **구현됨** (WP-124). 거래일 일봉, 없는 티커 404·빈 구간 200 빈 data·잘못된 날짜 400. 로컬 실데이터·프론트 차트·마커 연결까지 검증(2026-09-18) |
| `/pages/*`, `/search`, 5절 기능 | 미구현. 문서 상세·회원·관심종목·알림·토론은 MVP 제외 |

기계 판독 정본은 `frontend/docs/openapi.yaml`이다. 8개 GET 경로를 Spring 컨트롤러·DTO와 대조했고, 2026-09-18 canary에서 실제 PostgreSQL → Spring API → Frontend dev proxy까지 200 응답과 동일 이슈·요약·BA 종목을 확인했다. canary 당시 GKG와 요약·상태 전이는 수동 bridge였고 과거 상세 수치·historical 대표 텍스트의 시점 정합성은 미통과였다. 이후 요약 writer·상태 전이(WP-119)와 historical 도입부·고정 멤버 수치·상세 조회(WP-129)를 구현했지만 동일 canary 재실행과 EC2 검증은 하지 않았다. [1일 E2E canary](validation/2026-09-18-one-day-e2e-canary.md)는 당시의 부분 통과 근거이며 OpenAPI나 코드 존재만으로 배포 완료로 보지 않는다.

---

## 8. 남은 MVP API 작업

- ~~`GET /api/v1/stocks/{ticker}/prices` — 아직 컨트롤러·OpenAPI에 없고 로컬 `stock_price`도 0건~~ → **완료** (WP-124, 2026-09-18). 컨트롤러·서비스·리포지토리·OpenAPI 추가, 로컬 PostgreSQL에 시연 44종목(verified 3 + 정답셋) 일봉 적재(55,176행), 프론트 종목 상세 차트를 실 API에 연결하고 연관 이슈 시점 마커를 겹쳤다. 전 종목(5,100×5년) 적재는 시연 범위 밖.
- ~~`/issues/{id}`의 members 쿼리를 `cluster_member.edit_count/views`로 전환하고, 과거 스냅샷 뒤에 들어온 원시 행이 응답을 바꾸지 않는 회귀 테스트를 추가한다(WP-120).~~ → **완료** (2026-09-18, WP-129). 회귀는 `db/tests/test_issue_detail_sql.py`가 실 PostgreSQL로 고정한다.
- 운영 이슈 요약 worker를 활성화해 실제 GATEWAY로 요약·상태 전이를 실행하고, GKG·종목 매칭 자동 배선(WP-120)이 실제 데이터를 채운 뒤 8개 GET의 실데이터 응답을 다시 검증한다. 같은 `issue_key`의 요약·종목 재사용에는 대상 스냅샷 상한과 원 유효 시각 보존을 추가한다. 한 종목 canary 통과나 writer 코드 존재는 이 자동화·as-of·EC2 검증 완료를 뜻하지 않는다.
- 2026-07-17~09-17 로컬 시드는 모든 스냅샷을 `CONFIRMED`로 고정하고 요약·종목을 이슈별 마지막 `cluster_id`에만 연결한다. 이 시드는 API 형태·시간 슬라이더 시연용이며 상태 전이, 과거 시점 보강 데이터, 실제 매칭 E2E 검증 근거가 아니다.
- 관련 종목의 **제품 노출 상한은 두지 않기로 확정**했다(WP-22). 다만 현재 `/issues/{id}/stocks`의 전송 `limit` 기본 50·최대 100은 API 응답 크기 보호용이며 제품 정책상 노출 상한과 다른 값이다.
