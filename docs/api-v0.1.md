# API 명세서 — WikiPulse (WikiPulse)

- 버전: **v0.1 (2026-09-08)**
- 정본: 이 파일. 개정은 MR로 한다.
- 상위 문서: [requirements-v0.1.md](requirements-v0.1.md) — 무엇을 만드는가. 이 문서는 **그 화면들이 서버에 무엇을 묻는가**만 적는다.
- 데이터 모델: [erd-v0.1.md](erd-v0.1.md) / `db/migrations/V1__initial_schema.sql`. **응답 필드의 의미와 단위는 그쪽 컬럼 주석이 정본이다.** 여기 다시 적지 않는다.

---

## 0. 이 문서가 정리한 것 — 계약이 두 벌이었다

아래 표는 **2026-09-08 통합 결정 이전 상태**다. 2026-09-09 WP-76에서 BE의 Issue/Stock 경로는 `/api/v1`과 응답 봉투로 변경되었고, 이슈 상세에 `pageId/wiki/title/weight/isSeed/editCount/views`를 가진 `members`가 추가되었다. 펄스맵의 스냅샷 목록·일괄 그래프 조회는 별도 계약이며 WP-74에서 구현한다. [펄스맵 구현·계약](frontend/PULSE_MAP.md)을 참고한다.

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

⚠️ **`frontend/docs/openapi.yaml`은 이 결정 이후 낡았다.** 연동 착수 시 이 문서에 맞춰 갱신한다. 그때까지 FE의 mock 모드는 그대로 돌아간다 (fixture는 API 계약과 무관).

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
- `pulseScore`는 **배수**이지 퍼센트·확률·정확도가 아니다 (명세 §9).
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

🔴 `DISCARDED` 클러스터와 `verified=false` 종목은 **어떤 조회 API로도 나가지 않는다.** LLM 검증에서 떨어진 것이라 화면에 뜨면 안 된다.

---

## 2. 이슈 — 피드 · 버블맵 · 상세

피드와 펄스맵은 이슈를 공유하지만 독립 페이지다. 피드 내부에서 카드/리스트를 전환한다. 펄스맵은 시점별 문서 그래프가 필요하므로 아래 목록 응답 외에 `GET /api/v1/issues/map` 계약을 추가했다(2026-09-09, WP-72·73). [필드·행동 명세](frontend/PULSE_MAP.md), [OpenAPI](../frontend/docs/pulse-openapi.json). 서버 구현은 WP-74의 후속 작업이다.

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
        "weight": 1.0, "isSeed": true, "editCount": 87, "views": 12043 }
    ],
    "relatedStocks": [ ]
  }
}
```

- `summary`는 `issue_report`. 아직 없으면 `null`. 운영 파이프라인의 생성·적재는 WP-119에서 구현한다. 현재 로컬 데모 값은 시드에서 생성한 요약이다.
- `members`는 `weight` 내림차순. `isSeed=false`는 급증을 직접 통과하지 않고 Clickstream·Wikidata 관계로 딸려온 문서다 — 화면에서 구분해 보여줄 수 있게 내보낸다.
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
- 노출 개수 상한은 아직 없다 (WP-22). `limit`으로만 자른다.

---

## 3. 문서 (wiki page)

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

## 5. 회원 · 관심종목 · 알림 · 토론

⚠️ **인증 방식이 아직 미정이다** (명세 §10, `member.password_hash`가 nullable인 이유). 아래는 자체 로그인 + Bearer 토큰을 가정한 형태이며, OAuth로 정하면 `/auth/*`만 갈린다. 나머지 endpoint는 그대로다.

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

**WebSocket**: `/ws/issues/{id}` — 새 댓글 push. `/ws/me` — 알림 push.
⚠️ 실시간이 필수인지 아직 미정이다 (명세 §10). 미정인 동안은 위 REST 폴링으로 화면이 성립한다. WebSocket은 폴링을 대체하는 최적화이지 전제가 아니다.

---

## 6. 통합 검색

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

## 7. 구현 현황 (2026-09-08)

| endpoint | 상태 |
| --- | --- |
| `GET /issues`, `GET /issues/{id}` | **구현됨** — 단 `/api` 경로에 봉투 없음. v0.1에 맞추는 작업 필요 |
| `GET /stocks/{ticker}`, `GET /stocks/{ticker}/issues` | **구현됨** — 위와 같음 |
| 그 외 전부 | 미구현 |

FE는 현재 `VITE_DATA_SOURCE=mock`으로 fixture를 읽는다. api 모드 어댑터(`frontend/src/data/api/adapters.js`)가 이 문서 형태로 갱신되면 붙는다.

---

## 8. 미결

- **인증 방식** (자체 / OAuth) — 정해지면 5절 `/auth/*`만 확정된다
- **노출 개수 상한 N** (WP-22) — 지금은 `limit`으로만 자른다
- **WebSocket 필수 여부** (명세 §10)
- **알림 전달 수단** (명세 §10) — 위 API는 저장·읽음만 다룬다
- `frontend/docs/openapi.yaml` 갱신 — 이 문서 확정 후 기계 판독용 계약을 다시 만든다
