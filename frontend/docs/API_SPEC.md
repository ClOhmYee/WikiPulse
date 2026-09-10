# WikiPulse 프론트엔드 API 계약 제안

작성 기준: 2026-09-07 · 프론트 조회 구현 갱신: 2026-09-10 · 계약 버전: `0.2.0-proposal` · 현재 데모 기준일: `2026-09-10`

> 2026-09-10: 아래 날짜·숫자·단일 Event JSON은 이전 계약 설명용 예시다. 현재 mock 카탈로그는 [연간 목데이터](../../docs/frontend/MOCK_HISTORY.md)로 교체했다. `meta.asOf`는 목록의 2026-09-10 또는 상세 리포트의 해당 날짜이고 `availableRange`는 2025-09-01~2026-09-10이다. 이 문서의 과거 예시를 현재 데이터 개수·종목 목록·활동 수치로 사용하지 않는다.

페이지 구성 갱신: 2026-09-09. 페이지 URL은 [PAGES.md](../../docs/frontend/PAGES.md), 향후 통합 API는 [저장소 API 명세](../../docs/api-v0.1.md)가 정본이다. 이 문서와 `openapi.yaml`은 현재 FE 클라이언트가 사용하는 이전 제안 계약을 설명하며, `/events`·`/entities` HTTP 계약을 이번 페이지 변경에서 갱신한 것은 아니다.

이 문서는 **완성된 프론트엔드 화면에 데이터를 제공하기 위한 제안 계약**이다. 아래 API는 구현된 서버 엔드포인트가 아니다. 현재 페이지는 공통 비동기 조회 계층을 사용한다. `frontend/.env`의 mock 모드에서는 fixture를, api 모드에서는 이 제안 계약에 맞춘 HTTP 클라이언트를 사용한다. 실제 백엔드 연동은 아직 검증하지 않았다. 로그인, 데이터 수집, 분석 처리, 데이터베이스, 배포 방식은 이 문서의 범위에 포함하지 않는다.

기계 판독용 계약은 [openapi.yaml](./openapi.yaml)에 있다. HTTP 응답 봉투, 페이지네이션과 HTTP 오류는 연동 시 사용할 제안이다. 현재 화면에는 페이지 나누기 UI가 없다. API 목록은 전체 페이지를 수집하여 기존 로컬 필터에 제공하며, 조회 오류에는 수동 재시도를 제공한다.

## 1. 현재 화면과 데이터의 범위

| 화면 | 브라우저 경로 | 현재 제공하는 동작 |
|---|---|---|
| 온보딩 | `#/` | Track → Cluster → Match 소개, 탐색 진입 |
| Pulse Map | `#/pulse` | 날짜·시점 선택, 문서 그래프·HOT/NEW·근거 패널. 별도 [Pulse 계약](pulse-openapi.json)과 [행동 명세](../../docs/frontend/PULSE_MAP.md) 사용 |
| 이슈 탐색 | `#/issues` | 이슈 검색·주제 필터, Pulse/시작 시점/문서 수 정렬 |
| 이슈 상세 = 리포트 | `#/issues/{issueId}` | 개요·타임라인·관련 소식·근거 문서·토론 탭, 차트 범위·기준선, 문서 선택, 이슈 저장 |
| 종목 탐색 | `#/stocks` | 종목 검색·산업 필터·관심 종목 필터, 관련 사건 수/티커 정렬 |
| 연관주식 | `#/issues/{issueId}/stocks` | 해당 이슈 종목, 산업·연결 유형·관심 종목 필터, 연결 설명 |
| 종목 상세 | `#/stocks/{symbol}` | 관련 사건과 연결 경로, 연결 유형 필터, 예시 가격 차트, 관심 종목 저장 |
| 보관함 | `#/saved` | 저장 사건/관심 종목 탭, 보관함 내부 검색·저장 해제 |
| 마이페이지 | `#/mypage` | 준비 안내, 보관함·로그인·회원가입 이동 |
| 로그인 | `#/login` | 준비 안내, 실제 인증 요청 없음 |
| 회원가입 | `#/signup` | 준비 안내, 실제 계정 생성 요청 없음 |
| 전체 검색 | 공통 헤더 | 조회 결과에서 이슈·종목만 페이지 이동 대상으로 표시, 키보드 선택 |

이슈 상세의 키워드 링크는 `#/issues?q={인코딩된 키워드}`로 이동해 검색어를 초기화한다. URL query는 화면 상태이며 API 요청을 이미 보냈다는 의미가 아니다. 단일 문서 화면은 제거했고, 리포트의 문서 정보는 유지하며 원문 링크를 제공한다.

현재 공통 이슈 카테고리는 10개이며 기본 카탈로그는 사건 6개, 문서 14개, 종목 8개로 구성된다. 모든 수치·편집자·편집 내역·소식 제목과 시각·가격·연결 관계는 합성 fixture다. 뉴스 카드의 외부 URL은 주제를 읽는 참고 링크이며 예시 제목과 요약을 뒷받침하는 기사 출처가 아니다.

토론은 사건별 예시 글과 브라우저에 입력한 글을 보여 준다. 작성·답글·공감은 현재 브라우저에만 반영되며 다른 사용자에게 전송되지 않는다. 예시 작성자와 실제 서비스 사용자를 혼동하지 않는다.

## 2. 공통 요청·응답 규칙

### 2.1 주소와 식별자

- 제안 base path: `/api/v1`. 실제 서버 주소는 정하지 않는다.
- 조회 메서드는 `GET`이며 본문은 없다. 토론 작성·답글·공감에 대한 `POST`/`PUT` **제안**은 11절에 별도로 정의한다. JSON 요청·응답의 형식은 `application/json; charset=utf-8`이다.
- `eventId`는 사건 slug, `entityId`는 문서 slug다. 영문 Wikipedia 제목 자체를 `entityId`로 사용하지 않는다.
- `symbol`은 `NVDA`, `012450.KS`와 같은 종목 식별자다. 응답은 fixture의 대문자 표기를 사용한다. 종목 단건 조회의 입력은 대소문자를 구분하지 않는다.
- 모든 동적 path segment에는 `encodeURIComponent(value)`를 적용한다. `encodeURIComponent('012450.KS')`는 `012450.KS`이며, 마침표와 거래소 suffix를 제거하지 않는다.
- 쿼리는 `URLSearchParams`로 인코딩한다. 예: `q=호르무즈`의 전송값은 `q=%ED%98%B8%EB%A5%B4%EB%AC%B4%EC%A6%88`다. 화면의 `#/...` 경로를 API 경로에 그대로 붙이지 않는다.

```js
const url = `/api/v1/events/${encodeURIComponent(eventId)}`;
const query = new URLSearchParams({ q: '호르무즈', category: 'world', window: '3d' });
const listUrl = `/api/v1/events?${query.toString()}`;
```

### 2.2 성공 응답

```json
{
  "data": [],
  "included": { "entities": [] },
  "meta": {
    "dataMode": "mock",
    "asOf": "2025-06-24",
    "timezone": "Asia/Seoul",
    "availableRange": { "from": "2025-06-01", "to": "2025-06-24", "interval": "day" },
    "window": "24h",
    "pagination": { "offset": 0, "limit": 50, "total": 0, "hasMore": false }
  }
}
```

| 필드 | 규칙 |
|---|---|
| `data` | 목록은 배열, 단건은 객체. 검색 결과가 없으면 `[]`. 존재하지 않는 단건은 `data: null`이 아닌 404 |
| `included` | 해당 응답에서 ID로 참조하는 화면용 요약 객체. endpoint별로 정한 키를 사용하며 대상이 없으면 `[]`. 관계의 실제 증거를 의미하지 않음 |
| `meta.dataMode` | 이 계약의 값은 `mock` 고정. 실제 수집·실시간 데이터를 의미하는 값을 임의로 사용하지 않음 |
| `meta.asOf` | 현재 fixture 기준일 `2026-09-10`. 과거 리포트/연결 종목 조회에서는 해당 리포트 날짜. 요청한 오늘 날짜가 아님 |
| `meta.timezone` | 날짜와 일 단위 집계의 해석 기준 `Asia/Seoul` |
| `meta.availableRange` | 차트에 실제로 들어 있는 전체 날짜 범위. 현재 24개의 **달력 날짜별** 포인트이며 거래일 시계열이 아님 |
| `meta.window` | 응답 주요 편집 지표의 집계 기간. 사건 목록의 `window` 요청만 `3d`/`7d` 가능. 그 외는 `24h` |
| `meta.pagination` | 페이지네이션 목록 endpoint에만 포함. 단건·주제 목록·전체 검색에는 없음 |

`included`는 현재 JavaScript의 `getEntity`, `getEvent`, `getStock` 참조를 네트워크 응답으로 옮기기 위한 **응답 구조 제안**이다. 현재 fixture 자체에는 `included`나 `meta` 필드가 없다. 동일한 ID의 객체는 응답 안에서 한 번만 담는다.

### 2.3 페이지네이션과 검색

- 페이지네이션 대상: 사건 목록, 문서 목록, 종목 목록, 사건 소식 목록, 문서 변경 내역 목록.
- `offset`: 0 이상 정수, 기본값 0. `limit`: 1~100 정수, 기본값 50.
- 순서: 해당 endpoint의 전체 집합 → 검색·필터 → 정렬 → `slice(offset, offset + limit)`.
- `total`은 페이지 자르기 **이전**의 조건 일치 개수다. `hasMore`는 `offset + data.length < total`이다.
- `offset >= total`이면 200과 빈 배열. 조건 변경 시 클라이언트는 `offset=0`부터 다시 시작한다.
- 하나의 `asOf` 안에서 정렬 순서는 일관되어야 한다. 별도 tie-break가 없는 사건 정렬의 동률은 기본 카탈로그 순서를 유지한다. 현재 카탈로그 순서는 fixture 배열 순서다.
- `q`는 일반 문자열 부분 일치다. 정규식·형태소 분석·의미 검색·자동완성을 주장하지 않는다. 검색 대상은 endpoint별로 명시한다. 계약상 앞뒤 공백을 제거하고 대소문자를 구분하지 않는다. 내부 공백은 유지한다.
- `q` 생략 또는 공백만 있는 경우: 일반 목록은 검색 제한 없음, 전체 검색은 빈 결과. `q` 최대 길이는 200자라는 **전송 계약 제안**이다. 현재 UI 입력란에 이 길이 제한이 구현되어 있다는 뜻은 아니다.
- 잘못된 enum, 범위를 벗어난 숫자, 중복된 단일 쿼리 키, 정의하지 않은 쿼리 키는 400 `INVALID_QUERY`로 처리하는 계약을 제안한다. 없는 산업 이름 등 유효한 문자열 필터가 매칭되지 않는 경우는 200과 빈 배열이다.

현재 화면은 조회한 전체 목록을 대상으로 로컬 필터링하며 페이지 나누기 UI는 없다. API 모드는 필요한 모든 페이지와 included를 합친다. 보관함은 저장된 ID별 단건 조회를 사용하며 404만 표시에서 제외한다.

### 2.4 날짜·단위·빈 값

| 데이터 | 의미와 형식 |
|---|---|
| `date`, 차트 `date` | `YYYY-MM-DD`, 일 단위. 현재 목데이터 범위는 2025-09-01~2026-09-10. 아래 2025-06 JSON은 계약 형식 예시로 보존 |
| `startAt`, `updatedAt`, `time`, `publishedAt` | ISO 8601 offset 포함. 예: `2025-06-24T11:42:00+09:00`. 프론트 표시 시 같은 시간대로 변환해야 함 |
| `edits` | 편집 횟수, 0 이상 정수. 사건은 포함 문서 값의 합 |
| `baseline` | 같은 기간에 대응하는 비교용 편집 횟수, 현재 fixture는 양수. 실제 28일 평균에서 산출한 데이터가 아님 |
| `pulse` | `round(edits / baseline, 1)`인 **배수**, `%` 아님. 우선순위·확률·정확도·주가 방향 점수 아님 |
| `pageviews` | 조회 횟수, 0 이상 정수. 실제 방문자 수와 다름 |
| 문서 `editors` | 해당 문서의 기준일 편집자 수 예시 |
| 사건 `editors` | 연결 문서의 편집자 수를 단순 합산한 예시. 문서 간 중복 제거 인원 아님. 3일·7일 고유 편집자 수로 재해석하지 않음 |
| `delta` | 편집에 따른 글자 수 증감의 예시 정수. 음수 허용. `before`/`after`는 발췌 설명이므로 두 문자열 길이 차이와 일치하지 않음. bytes 값으로 바꾸면 현재 `자` 표시와 맞지 않음 |
| `price` | `currency` 단위의 예시 가격. OHLC·실시간 가격·실제 종가 아님 |
| `change` | 이전 예시 가격 포인트 대비 변동률, **퍼센트 값**. `1.26`은 `1.26%`, `0.0126`이 아님 |
| 주가 차트 `price` | 날짜별 단일 예시 가격. 수정주가·거래량 필드 없음 |

현재 숫자 fixture는 모두 유효한 값이다. 필수 편집 지표와 차트 포인트에 `null`, `NaN`, `Infinity`, 숫자 문자열을 보내지 않는다. 결측을 `0`으로 치환하지 않는다. 데이터가 없는 차트는 `[]`, 중간 날짜가 없으면 그 날짜의 포인트를 생략하고 보간하지 않는다. 기준선이 0이거나 없는 실데이터를 표현하려면 별도의 결측 처리 계약과 UI 대응을 먼저 정해야 한다.

UI가 빈 상태를 지원하는 필드만 다음과 같이 허용한다.

- `news.url`: URL 문자열 또는 `null`. `null`이면 외부 링크를 표시하지 않는다.
- `timeline.entityId`: 문서 ID 또는 `null`. `null`이면 연결 문서 링크를 표시하지 않는다.
- `stock.price`, `stock.change`: 숫자 또는 `null`. `null`이면 `—` 표시. 현재 예시 데이터에는 이 경우가 없으므로 별도의 실제 데이터 검증을 했다는 의미는 아니다.
- `before`, `after`: 문자열. `""`는 각각 새 내용 추가/내용 삭제를 표현할 수 있다. 누락이나 `null` 대신 빈 문자열을 사용한다.
- 배열 필드는 대상이 없으면 `[]`이며 생략하거나 `null`로 보내지 않는다.

### 2.5 오류 응답

```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "window 값은 24h, 3d, 7d 중 하나여야 합니다.",
    "details": [{ "field": "window", "reason": "unsupported_value" }]
  }
}
```

| HTTP | `error.code` | 표시 동작 제안 |
|---|---|---|
| 400 | `INVALID_QUERY` | 입력값을 확인하도록 안내. 올바르지 않은 조건을 조용히 다른 값으로 바꾸지 않음 |
| 400 | `INVALID_BODY` | 토론·답글의 공백 입력, 길이 또는 공감 요청의 타입 확인 |
| 400 | `LIMIT_REACHED` | 현재 데모의 사건당 토론/토론당 답글 200개 한도 안내 |
| 404 | `NOT_FOUND` | 현재 각 상세 페이지의 찾을 수 없음 화면과 탐색 복귀 링크 |
| 500 | `INTERNAL_ERROR` | 불러오기 실패와 다시 시도 동작. 현재 공통 조회 훅에서 수동 재시도 제공 |

`details`는 항상 배열이며 일반 오류에는 `[]`를 사용한다. 시스템 내부 정보나 stack trace를 사용자 메시지에 넣지 않는다. HTTP 오류는 데이터 조회 경계에서 처리하며, 렌더링 오류 경계 및 lazy import 로딩과 구분한다.

## 3. 공통 데이터 모델

아래 필드는 `src/data/mock/fixtures/catalog.js`에 실제 존재한다. `Summary` 모델은 명시한 무거운 배열만 제외하는 응답 projection 제안이며, 별도 계산 알고리즘을 뜻하지 않는다.

### Category

`{ id: string, label: string, color: string }`

| id | 화면 이름 |
|---|---|
| `politics` | 정치 |
| `world` | 국제 |
| `society` | 사회 |
| `economy` | 경제 |
| `technology` | 기술 |
| `science` | 과학 |
| `culture` | 문화 |
| `sports` | 스포츠 |
| `environment` | 환경 |
| `other` | 기타 |

`color`는 `#RRGGBB` 표현용 색상이다. `all`은 UI/쿼리의 전체 선택 값이며 데이터의 `category` 값이 아니다.

### EventSummary / Event

| 필드 | 형식 | 화면 용도 |
|---|---|---|
| `id`, `title`, `summary` | string | URL, 제목, 사건 설명 |
| `category` | Category ID | 주제 태그·필터 |
| `status` | `rising` / `sustained` / `cooling` | 상승 중 / 관심 지속 / 안정화 |
| `date` | date | 기준일 |
| `startAt`, `updatedAt` | date-time | 사건 시작 정렬과 데이터 시각. `updatedAt`은 현재 주된 화면 지표로 노출되지 않음 |
| `pulse`, `edits`, `baseline`, `editors`, `pageviews` | number/integer | 앞의 단위 규칙 적용 |
| `articleIds` | string[] | 사건에 포함된 문서 ID. `articleIds.length`가 문서 수 |
| `stockSymbols` | string[] | 함께 탐색할 종목 ID |
| `keywords` | string[] | 검색과 주제 이동 |
| `chart` | ActivityPoint[] | 일 단위 활동 추이, 날짜 오름차순 |
| `timeline` | TimelineEntry[] | Event만 포함. 최신 항목부터. 개요는 앞의 3개, 타임라인 탭은 전체 |
| `news` | NewsItem[] | Event만 포함. 최신 항목부터 |
| `insights` | Insight[] | Event만 포함. 작성 순서. 화면의 `AI 해석 예시`; 실제 AI 요청이 수행되는 것이 아님 |

`EventSummary`는 `timeline`, `news`, `insights`를 제외한 모델이다. Pulse Map의 미리보기를 위해 `chart`는 목록에도 포함한다.

### EntitySummary / Entity

| 필드 | 형식 | 설명 |
|---|---|---|
| `id` | string | 예: `strait-of-hormuz` |
| `title` | string | 영문 Wikipedia 제목. 예: `Strait of Hormuz` |
| `name`, `description` | string | 한국어 문서명과 설명 |
| `category` | Category ID | 문서의 주제; 사건의 주제와 다를 수 있음 |
| `edits`, `pulse`, `pageviews`, `editors`, `baseline` | number/integer | 문서 기준일 지표 |
| `eventIds` | string[] | 연결된 사건 |
| `relatedIds` | string[] | 함께 읽을 문서. 현재 관계의 출처·방향·가중치가 아님 |
| `chart` | ActivityPoint[] | Entity만 포함 |
| `changes` | Revision[] | Entity만 포함. 최신 순의 편집 전후 예시 |

`EntitySummary`는 `chart`, `changes`를 제외한다. Wikipedia 링크는 `title`을 인코딩해 UI에서 만든다. 예: `https://en.wikipedia.org/wiki/Strait%20of%20Hormuz`, 역사 링크의 쿼리는 `title=Strait%20of%20Hormuz&action=history`.

### StockSummary / Stock

| 필드 | 형식 | 설명 |
|---|---|---|
| `symbol`, `name` | string | 종목 식별자, 기업명 |
| `market` | `NYSE` / `NASDAQ` / `KRX` | 현재 fixture의 시장 |
| `currency` | `USD` / `KRW` | 가격 표시 통화 |
| `sector`, `description` | string | 산업 필터와 기업 맥락 설명 |
| `price`, `change` | number 또는 null | 예시 가격과 퍼센트 변동률 |
| `eventIds` | string[] | 연결 사건. 길이가 관련 사건 수 |
| `relations` | StockRelation[] | 사건별 연결 설명. 목록에서도 사용 |
| `chart` | PricePoint[] | Stock만 포함. 날짜 오름차순 |

`StockSummary`는 `chart`만 제외한다. 산업은 현재 종목 집합에서 고유한 `sector` 문자열을 추출해 선택지를 만든다. 고정 산업 ID 체계는 구현되어 있지 않다.

### 세부 배열

```text
ActivityPoint = { date, edits, baseline, pageviews }
PricePoint    = { date, price }
TimelineEntry = { id, time, title, body, kind, entityId }
NewsItem      = { id, title, source, publishedAt, type, url, summary }
Insight       = { title, body }
Revision      = { id, time, editor, section, before, after, summary, delta }
StockRelation = { eventId, type, strength, explanation, path }
```

- `TimelineEntry.kind`: `signal`(편집 신호), `news`(관련 소식), `context`(배경).
- `NewsItem.type`: `news`, `official`, `analysis`. `source`의 현재 값은 `데모 뉴스`, `기관 발표 예시`, `데모 분석`이다. `official`인 예시가 실제 기관 발표라는 뜻은 아니다.
- `Revision.editor`: `DemoEditor-01` 같은 가상 편집자 이름. 실제 계정 ID·사용자 신원 정보가 아니다.
- `StockRelation.type`: `direct`(직접 언급), `industry`(산업·기술), `supply`(공급망), `region`(지역 노출). `region`은 UI가 지원하지만 현재 fixture에서는 사용하지 않는다.
- `StockRelation.strength`: `high` 또는 `medium`인 예시 연결 강도. `type`과 다른 축이다. `high`를 직접 거래·직접 노출 또는 검증된 연결로 해석하지 않는다.
- `StockRelation.path`: 화면에서 화살표로 잇는 설명 문자열 배열. 개별 문자열은 문서 ID가 아니므로 URL이나 증거 객체로 취급하지 않는다.

## 4. Endpoint별 계약

### GET `/categories`

쿼리 없음. `data: Category[]`. 현재 6개를 fixture 순서로 반환한다. `included`, 페이지네이션 없음.

### GET `/events`

| 쿼리 | 값 / 기본값 | 의미 |
|---|---|---|
| `q` | string / `""` | `title + summary + keywords.join(' ')` 부분 일치 |
| `category` | `all` 또는 Category ID / `all` | 하나의 주제 선택. 복수 선택 미지원 |
| `window` | `24h`, `3d`, `7d` / `24h` | Pulse Map의 최근 1/3/7일 누적 지표 |
| `sort` | `pulse`, `recent`, `documents` / `pulse` | Pulse 내림차순 / `startAt` 최신 순 / `articleIds.length` 내림차순 |
| `offset`, `limit` | 공통 페이지네이션 | 현재 화면의 페이지 이동 기능과 구분 |

응답은 `data: EventSummary[]`, `included.entities: EntitySummary[]`다. `included.entities`는 반환 사건의 `articleIds`에 해당하는 문서만 중복 없이 포함한다. 사건 목록이나 지도에서 미리보기 문서명을 찾는 용도다.

`window`는 기준일을 포함하는 마지막 1/3/7개 **일 단위 포인트**를 사용한다. 반환 객체의 `edits`, `baseline`, `pageviews`는 선택 구간의 합, `pulse`는 합산 편집량/합산 기준선의 한 자리 반올림 값이다. `editors`는 기준일의 문서별 편집자 수 합계를 유지한다. `status`, `date`, `startAt`, `updatedAt`, ID 배열, `keywords`를 기간 선택 때문에 다시 만들지 않는다. `chart`는 전체 가용 날짜의 원래 일별 데이터를 유지한다.

위 `window`는 기존 사건 목록 API 계약이다. 이슈 탐색은 기본 `24h`를 사용한다. 펄스맵의 24h/3d/7d 누적 전환은 2026-09-09 제거하고 실제 스냅샷 날짜·시각 선택으로 교체했다. 펄스맵은 이 이벤트 목록·차트에서 과거 그래프를 재구성하지 않는다.

### GET `/events/{eventId}`

쿼리 없음. `data: Event`, `included.entities: EntitySummary[]`, `included.stocks: StockSummary[]`. 기본 기준일 지표(`24h`)와 전체 차트·타임라인·소식·해석을 반환한다. 목록에서 3일을 보다가 상세로 들어와도 이 endpoint의 기본 지표를 3일 값으로 간주하지 않는다.

탭 변경, 기준선 체크, 7일/전체 차트 선택, 문서 네트워크 선택은 받은 데이터의 로컬 표시 변경이다. 별도 AI 생성·클러스터 계산·차트 계산 endpoint를 정의하지 않는다. 개별 문서를 열면 `/entities/{entityId}`, 기업을 열면 `/stocks/{symbol}`로 대응한다.

### GET `/events/{eventId}/news`

`q`, `type`, `offset`, `limit`을 받는다. `type`은 `all`(기본), `news`, `official`, `analysis`. `q` 검색 대상은 `title + source + summary`. 게시 시각 내림차순의 `data: NewsItem[]`를 반환한다. `included` 없음.

이 endpoint는 관련 소식 탭의 목록을 분리해 가져오는 계약이다. 현재 화면은 `Event.news`를 로컬로 필터링한다. 단건 사건 안의 `news`와 동일한 ID·필드·순서를 유지한다. 소식 유형 칩의 개수는 검색·유형 필터 전 전체 `Event.news` 기준이고, 결과 개수는 필터 후 기준이다. 외부 참고 링크 열기는 우리 API에 대한 조회가 아니다.

### GET `/entities`

아래 `/entities` 계열은 기존 데이터 계약으로 보존한다. 단일 위키 문서 상세 페이지는 2026-09-09에 제외했다. 목록·상세 클라이언트의 존재가 해당 페이지나 편집 비교 UI의 존재를 의미하지 않는다.

`q`, `offset`, `limit`을 받는다. `q`는 `name + title`에 대한 부분 일치. 기본 순서는 fixture 문서 순서. 응답 `data: EntitySummary[]`, `included` 없음.

현재 독립적인 문서 목록 화면은 없다. 이 endpoint는 기존 전체 검색의 문서 조회 부분이나 문서 참조 획득에 사용할 수 있는 **연동 제안**이다. 문서별 주제·기간·인기 정렬 같은 새 화면 기능을 뜻하지 않는다. 현재 헤더의 실제 검색 동작을 한 번에 대체하려면 아래 `/search`를 사용한다.

### GET `/entities/{entityId}`

쿼리 없음. `data: Entity`, `included.entities: EntitySummary[]`는 `relatedIds`, `included.events: EventSummary[]`는 `eventIds`를 해석한 결과다. 같은 참조는 같은 fixture ID를 유지한다.

제거된 문서 상세 화면에서는 차트 범위 7/14/전체, 조회수/편집량 전환, 편집 기준선 토글을 제공했다. 이 문장의 화면 동작은 이전 구현 기록이다. 문서 fixture의 24일 차트 데이터와 계약은 유지하며, 관련 문서 네트워크를 실제 링크·이동량 증거로 보장하는 필드는 없다.

### GET `/entities/{entityId}/changes`

`q`, `offset`, `limit`을 받는다. `q` 검색 대상은 `section + summary`다. 편집자·편집 전후 본문에 대한 검색은 현재 UI에 없다. 최신 순의 `data: Revision[]`, `included` 없음.

현재는 `Entity.changes`를 로컬로 필터링하고 선택한 항목의 `before`/`after`를 함께 보여 준다. 각 내역에 비교 문자열이 이미 포함되므로 별도의 diff 생성 endpoint가 필요하지 않다. 실제 Wikipedia revision ID는 현재 모델에 없으며 예시 `id`를 Wikipedia `oldid`로 사용하면 안 된다. 외부 `action=history` 링크는 실제 문서의 역사로 이동할 뿐 이 예시 revision을 여는 링크가 아니다.

### GET `/stocks`

| 쿼리 | 값 / 기본값 | 의미 |
|---|---|---|
| `q` | string / `""` | `symbol + name + sector + description` 부분 일치 |
| `sector` | `all` 또는 산업 문자열 / `all` | `sector` 정확히 일치 |
| `eventId` | 사건 ID / 생략 | 특정 사건의 종목 집합. 해당 사건이 없으면 404 |
| `relationType` | `all`, `direct`, `industry`, `supply`, `region` / `all` | 지정 사건과의 연결 유형. `eventId`가 있을 때만 사용 |
| `sort` | `events`, `name` / `events` | 관련 사건 수 내림차순 후 티커 오름차순 / 티커 오름차순 |
| `offset`, `limit` | 공통 페이지네이션 | 검색·필터·정렬 후 페이지 적용 |

응답 `data: StockSummary[]`, `included.events: EventSummary[]`. `eventId`를 지정한 집합은 `stock.eventIds`에 사건이 있거나 사건의 `stockSymbols`에 종목이 있는 항목이다. 현재 fixture는 양쪽 참조가 일치한다. `relationType` 검사에는 반드시 같은 `eventId`의 relation을 사용한다. `eventId` 없이 `relationType`을 지정하면 400으로 처리하는 제안이다. 일반 종목 목록에는 연결 유형 선택 UI가 없다.

산업 필터 선택지는 사건 범위를 적용한 **전체 종목 집합**의 고유 산업이다. `q`나 산업 필터 자체에 따라 선택지를 계속 제거하지 않는다. 현재 목록은 전체 fixture를 이미 가지고 있으므로 이를 직접 만든다. API 페이지네이션으로 이 정보가 필요해질 경우 전체 대상 집합을 확보해야 하며 첫 페이지에서만 선택지를 만들지 않는다.

`savedOnly`는 API 쿼리가 아니다. 관심 종목 필터는 브라우저 보관 목록과 교집합을 취한다. 해당 필터를 쓰기 전에 대상 페이지를 전부 확보하거나 이미 확보한 종목 카탈로그를 사용한다. 저장 상태·사용자 ID·인증 관련 필드를 이 endpoint에 추가하지 않는다.

### GET `/stocks/{symbol}`

쿼리 없음. `data: Stock`, `included.events: EventSummary[]`는 `eventIds`에 대응한다. 관련 사건은 `date` 최신 순이고 같은 날짜의 순서는 기본 사건 순서다. 유형 선택은 `Stock.relations[].type`의 고유 값으로 만든다. 종목 상세의 유형 필터와 가격 차트 기간 선택은 로컬 동작이다.

가격 차트의 범위 값은 `7`, `14`, `all`이며 각각 마지막 7/14/전체 포인트를 표시한다. 현재 전체는 24개 일별 포인트다. `Stock.chart`에 없는 날짜를 생성하지 않는다. 세로축은 예시 가격의 범위에 맞춰 확대되며 0에서 시작하는 절대 크기 비교 차트가 아니다. 가격과 사건 연결을 같은 시점에 표시한다고 두 값 사이의 인과관계가 성립하지 않는다.

### GET `/search`

`q`와 `limit`을 받는다. `limit`은 1~7, 기본 7. offset·페이지네이션 없음. `q`가 비어 있으면 `data: []`. 응답은 다음 DTO 배열이다.

```json
{
  "kind": "entity",
  "id": "strait-of-hormuz",
  "title": "호르무즈 해협",
  "detail": "Strait of Hormuz"
}
```

`kind`는 `event`, `entity`, `stock`. 이 DTO는 기존 헤더가 만드는 검색 항목의 **전송 형태 제안**이다. 현재 UI의 React icon, DOM 결과 ID, `href`를 서버 필드로 요구하지 않는다.

| kind | title | detail | 검색 문자열 |
|---|---|---|---|
| event | `event.title` | `사건` | 제목 + `사건` + keywords |
| entity | `entity.name` | `entity.title` | 한국어 이름 + 영문 제목 |
| stock | `stock.name` | `stock.symbol` | 기업명 + 티커 |

순서는 사건 카탈로그 → 문서 카탈로그 → 종목 카탈로그이며 각 묶음의 기본 순서를 유지한다. 검색 후 앞에서 최대 `limit`개만 반환한다. 현재 의미 기반 관련도 정렬은 없다. 전체 검색은 사건의 `summary`, 종목의 `description`이나 `sector`를 검색하지 않으므로 개별 목록 검색과 결과가 다를 수 있다. 결과 선택 시 클라이언트가 `kind`에 따라 기존 hash URL을 만든다.

## 5. 실제 fixture와 일치하는 예시

호르무즈 사건의 기준일 요약은 다음 값이다. 아래 JSON은 필드 확인용 발췌이며 `EventSummary`의 모든 필드를 담은 완전한 응답은 아니다.

```json
{
  "id": "iran-hormuz-2025",
  "title": "호르무즈 해협, 에너지 공급망으로 번지는 관심",
  "category": "world",
  "status": "rising",
  "date": "2025-06-24",
  "startAt": "2025-06-18T08:40:00+09:00",
  "updatedAt": "2025-06-24T11:42:00+09:00",
  "edits": 824,
  "baseline": 98,
  "pulse": 8.4,
  "editors": 190,
  "pageviews": 501830,
  "articleIds": ["strait-of-hormuz", "iran", "petroleum"],
  "stockSymbols": ["XOM"],
  "keywords": ["호르무즈 해협", "해상 운송", "원유", "공급망"]
}
```

편집량은 `412 + 248 + 164 = 824`, 기준선은 `34 + 31 + 33 = 98`, 편집자 예시 합계는 `86 + 63 + 41 = 190`이다. 마지막 차트 포인트는 `{ "date": "2025-06-24", "edits": 824, "baseline": 98, "pageviews": 501830 }`이다. `window=3d`/`7d` 응답의 합산 지표는 마지막 한 포인트와 일치할 필요가 없으며 전체 응답의 `meta.window`로 구분한다.

실제 종목 fixture의 연결 객체 예시:

```json
{
  "eventId": "ai-chip-controls",
  "type": "direct",
  "strength": "high",
  "explanation": "사건에 엔비디아 기업 문서가 직접 포함되어 있습니다. 직접 연결은 문서의 포함 여부이며 규제 적용이나 가격 영향을 판정한 결과가 아닙니다.",
  "path": ["AI 반도체", "가속 컴퓨팅", "엔비디아 문서", "엔비디아"]
}
```

NVDA의 예시 `price`는 `143.72`, `change`는 `2.14`, `currency`는 `USD`다. 실제 시세를 대조하거나 검증한 값이 아니다.

## 6. 사용자 동작과 조회 연결표

| 동작 | 연동 시 조회 | 현재 구현 |
|---|---|---|
| 온보딩 진행·지도 이동/확대/초기화 | 없음 | 브라우저 로컬 UI 상태 |
| Pulse Map 진입·시각 선택 | `/issues/snapshots`, `/issues/map` | 같은 계약의 합성 snapshot/HTTP 클라이언트 |
| 지도 검색·주제·이슈·문서 선택 | 추가 조회 불필요 | 로드한 스냅샷의 노드·간선·요약 표시 |
| 사건 상세 이동 | `/events/{eventId}` | `getEvent`와 참조 helper |
| 상세 탭·차트·기준선·문서 선택 | 추가 조회 불필요 | 받은 필드의 표시 변경 |
| 소식 검색·유형 변경 | 필요 시 `/events/{eventId}/news` | `event.news`를 로컬 필터 |
| 근거 문서 원문 이동 | 우리 API 추가 조회 없음 | 위키백과 원문을 새 탭으로 열기 |
| 이전 문서 상세·편집 검색·비교 | `/entities/{entityId}`, `/entities/{entityId}/changes` 계약 보존 | 해당 독립 화면은 2026-09-09 제거. 리포트의 문서 참조 데이터는 유지 |
| 전체 종목 탐색 | `/stocks` | 전체 stocks 필터 |
| 특정 사건의 종목 탐색 | `/stocks?eventId=...` | 양쪽 사건·종목 참조로 집합 선택 |
| 기업 상세 이동 | `/stocks/{symbol}` | `getStock`와 관련 events |
| 기업 상세 연결 유형·가격 차트 | 추가 조회 불필요 | 관계 필터와 배열 자르기 |
| 공통 헤더 검색 | `/search?q=...` | 공통 searchWorkspace 비동기 호출·250ms 입력 지연, 화면에는 이슈·종목만 표시 |
| 저장·저장 해제·보관함 검색 | 저장은 API 없음; 표시는 ID별 단건 조회 | React 상태 + localStorage, 표시 데이터는 공통 조회 |
| 토론 목록·최신순/공감순 | 향후 `/events/{eventId}/discussions` | 예시와 브라우저 저장 글 정렬 |
| 토론·답글 등록·공감 | 11절의 향후 POST/PUT 계약 | 브라우저 로컬 상태만 변경, 외부 전송 없음 |
| Wikipedia 원문·역사·소식 참고 링크 | 외부 사이트 직접 이동 | 새 탭 링크 |

## 7. 보관함은 현재 로컬 기능

현재 저장 키와 값:

```json
{
  "wikipulse.savedEvents": ["iran-hormuz-2025"],
  "wikipulse.savedStocks": ["NVDA", "373220.KS"]
}
```

각 키에는 배열을 `JSON.stringify`한 문자열을 별도로 저장한다. 로드 시 배열인지 검사하고 문자열 ID의 형식을 검사하고 중복을 제거한다. 조회 전 모르는 ID를 삭제하지 않으며, 서버의 404 응답은 표시에서만 제외한다. 같은 항목을 다시 누르면 저장 해제한다. localStorage 쓰기에 실패하면 현재 React 상태에는 반영하고 새로고침 후 유지되지 않을 수 있다는 안내를 표시한다.

보관함의 사건 검색은 제목+요약, 종목 검색은 티커+기업명이다. 표시는 저장 ID 배열의 순서를 따르며, 서버 조회 결과에서 확인된 404 항목은 제외한다. 탭을 바꾸면 검색어가 초기화된다. 다른 기기·브라우저·탭 사이의 동기화나 사용자 계정 저장을 제공하지 않는다.

이 문서와 OpenAPI에는 `POST /bookmarks`, `DELETE /bookmarks`, 로그인·사용자 API를 넣지 않는다. 현재 요구 기능을 위해 서버 저장 계약을 가정하지 않는다.

## 8. 실제 근거를 제공하는 API로 전환할 때 필요한 별도 확장

현재 모델의 `articleIds`, `relatedIds`, `relations[].path`는 **연결을 설명하는 목데이터**다. SVG에 보이는 선과 점의 위치는 UI가 만든 시각적 구성이다. 이 모델에는 실제 Wikipedia 내부 링크, Clickstream 수치, 원문 revision ID, 종목 연결 근거 URL, 관계 검증 결과가 없다. 따라서 지금의 경로 문자열이나 뉴스 URL을 실제 관계의 증거로 반환하면 안 된다.

향후 실데이터 API에서 관계를 근거와 함께 제공하려면 최소한 다음 정보를 담는 별도 `evidence` 구조와 UI 표시를 추가해야 한다. 아래는 **미구현 확장 항목**이며 현재 fixture나 이 문서의 기본 OpenAPI 모델에 존재하지 않는다.

| 확장 정보 | 사용자에게 필요한 의미 |
|---|---|
| `evidence.id` | 원문 근거를 다시 찾는 안정적인 식별자 |
| `evidence.sourceType` | Wikipedia 문서/변경 내역/뉴스/공식 자료/분석 중 무엇인지 |
| `evidence.sourceUrl`, `sourceTitle` | 실제 해당 연결 주장을 뒷받침하는 원문 주소와 제목 |
| `evidence.observedAt`, `retrievedAt` | 원문 사건·관측 시각과 가져온 시각의 구분; 모르는 관측 시각은 명시적으로 null |
| `evidence.subjectIds` | 이 근거가 설명하는 정확한 문서·사건·종목 ID |
| `evidence.claim`, `excerpt` | 어떤 연결을 지지하는지에 대한 범위와 원문 발췌. 전체 페이지 일반 링크만으로 대신하지 않음 |
| `evidence.basis` | 관측된 관계인지, 사람이 작성한 해석인지, AI 해석인지, 데모인지 |

실제 데이터로 바꿀 때는 기간 기준선의 정의, 편집자 중복 처리, 가격의 기준 시점·통화·조정 여부, 데이터 결측도 함께 명시해야 한다. 이는 사용자에게 보이는 값의 의미를 정하는 요구사항이며 수집 방식이나 계산 로직의 설계가 아니다.

## 9. 코드 기준 확인 지점

- `src/data/mock/fixtures/catalog.js`: 실제 필드·fixture·ID·날짜·단위.
- `src/app/App.jsx`, `src/app/RouteContent.jsx`: 앱 조립과 라우트.
- `src/features/`: 전체 검색과 로컬 저장.
- `src/data/`: mock/API 공통 조회, 응답 어댑터, 페이지 데이터 로딩.
- `src/pages/explore/ExplorePage.jsx`: 이슈 검색·정렬·카드/리스트 표시 전환.
- `src/pages/pulse/PulsePage.jsx`: 독립된 스냅샷 조회와 문서 그래프. [펄스맵 계약](pulse-openapi.json)을 사용한다.
- `src/pages/event/EventPage.jsx`: 상세 탭, 뉴스 필터, 차트와 문서 참조.
- `src/pages/account/AccountPage.jsx`: 독립된 마이페이지·로그인·회원가입 준비 안내. 기존 `EntityPage.jsx`는 제거했다.
- `src/lib/wiki.js`: 리포트와 펄스맵에서 사용하는 위키백과 원문 링크.
- `src/pages/stocks/StocksPage.jsx`: 종목 검색·산업·연결 필터와 예시 가격.
- `src/pages/saved/SavedPage.jsx`: 보관함 검색과 저장 항목 표시.
- `src/pages/event/EventDiscussion.jsx`: 예시 토론, 로컬 글·답글·공감과 저장 검증.

기본 데이터 모델은 실제 필드와 일치하도록 작성했다. HTTP 봉투, 전송 DTO projection, pagination, HTTP 오류, 독립 목록 endpoint는 모두 향후 연동용 제안이다. 현재 구현으로 확인한 범위는 프론트엔드 목데이터 경험이다.

## 10. 계약 검증 재현

저장소 루트에서:

```sh
node frontend/scripts/validate-contract.mjs
```

`frontend` 디렉터리에서:

```sh
node scripts/validate-contract.mjs
```

파일 경로는 스크립트 위치를 기준으로 계산한다. `js-yaml`로 YAML을 읽고 `ajv`로 데이터 스키마를 검증한다. 실패 시 오류 위치와 내용을 출력하고 종료 코드 1을 반환한다.

현재 검증 대상은 내부 참조 138개, 중복 없는 operation ID 14개, 필수 path parameter, fixture 객체 34개와 연결 ID, 스키마 예시 3개, 오류 응답 예시 5개, 요청 본문 예시 3개다. OpenAPI의 전체 Event 예시는 실제 fixture와 중첩 필드까지 정확하게 비교한다. 이 검증은 실행 중인 HTTP 서버나 실제 데이터의 정확성을 검증하지 않는다.

## 11. 사건 토론: 현재 로컬 동작과 향후 계약

### 현재 구현

Event Brief의 개요 하단과 `토론` 탭에서 글 작성, 답글 작성·접기/펼치기, 글 공감·취소, 최신순/공감순 정렬을 할 수 있다. 두 위치에서 같은 브라우저 저장 내용을 보여 준다. 답글에는 공감 버튼이 없고 대댓글·편집·삭제·신고·작성자 검색은 구현하지 않았다.

사건마다 토론 3개가 기본 예시로 제공되고 첫 글에는 답글 1개가 있다. 예시 작성자는 `리서처 A/B/C`이고 공감 수는 4/2/1이다. 새로 작성하는 사람의 고정 표시명은 `나 (데모)`다. 이는 계정 정보나 로그인 상태가 아니다.

저장 키는 `wikipulse.discussion.${event.id}`이며 값은 다음 객체를 JSON 문자열로 저장한다.

```text
{ version: 1, threads: DiscussionThread[] }
```

처음 열거나 유효한 저장 값이 없으면 예시로 시작한다. 저장 내용을 읽을 수 없거나 구조가 올바르지 않으면 안내 후 예시를 사용한다. 저장 공간을 사용할 수 없을 때는 페이지를 사용하는 동안 메모리에 반영되지만 새로고침하면 입력한 값이 사라질 수 있다. 다른 브라우저·사용자에게 공유되지 않는다.

### 실제 로컬 모델

```text
DiscussionReply = {
  id: string,
  author: string,
  body: string,
  createdAt: ISO8601,
  isOwn: boolean,
  isSeed: boolean
}

DiscussionThread = {
  ...DiscussionReply,
  likes: integer >= 0,
  liked: boolean,
  replies: DiscussionReply[]
}
```

`id`는 글과 답글의 문자열 ID이며 최대 120자, `author`는 최대 80자다. 사용자 작성 ID는 브라우저가 생성한다. `isOwn`은 내 브라우저에서 작성한 글의 표시, `isSeed`는 예시 표시용이다. 권한이나 검증된 작성자 신원으로 사용하지 않는다. `liked`는 이 브라우저에서 공감했는지, `likes`는 예시 수치에 로컬 공감 여부를 반영한 값이다.

`body`는 앞뒤 공백을 제거한 뒤 1~1,000자여야 한다. 현재 입력 제한은 JavaScript 문자열 길이(UTF-16 code unit) 기준이므로 일부 이모지는 2자로 계산된다. OpenAPI의 `maxLength`와 함께 이 기준을 적용해야 하며 공백만 있는 문자열은 허용하지 않는다. 표시할 때 HTML로 해석하지 않는 일반 텍스트다.

토론은 사건별 최대 200개(예시 포함), 답글은 글마다 최대 200개다. `latest`는 `createdAt` 내림차순, `popular`는 `likes` 내림차순 후 `createdAt` 내림차순이다. 동일 조건의 항목은 기존 순서를 유지한다. 답글은 배열에 추가된 순서로 표시한다.

예시 글의 시각은 리포트의 `startAt`~`updatedAt` 구간에 맞춘다(2026-09-10 변경). 사용자가 새로 작성한 글은 브라우저의 현재 시각을 `new Date().toISOString()`으로 기록한다. 따라서 토론의 `createdAt`이 사건 데이터의 `meta.asOf`보다 늦을 수 있다. `asOf`를 토론의 작성 가능 시점이나 마지막 갱신 시각으로 해석하지 않는다.

### GET `/events/{eventId}/discussions`

유일한 쿼리는 `sort=latest|popular`이고 기본값은 `latest`다. 현재 UI에는 토론 검색이나 페이지 이동이 없다. 제안 응답은 `data: DiscussionThread[]`, `meta: Meta`이며 `pagination`, `included`가 없다. 최대 200개를 반환하고 답글도 각 글의 `replies`에 포함한다. 펼치기는 별도 네트워크 요청 없이 받은 답글을 표시한다.

### POST `/events/{eventId}/discussions`

요청 본문:

```json
{ "body": "어떤 문서의 변화가 사건 연결을 설명하나요?" }
```

제안 성공 응답은 201, `data: DiscussionThread`, `meta: Meta`. 새 글은 `author: "나 (데모)"`, `isOwn: true`, `isSeed: false`, `likes: 0`, `liked: false`, `replies: []`인 **데모 사용자 맥락**이다. 본문에 `author`, `isOwn`, `likes` 등을 보내지 않는다. 이 고정 사용자 표현으로 실제 다중 사용자 식별 방식을 정하는 것은 아니다.

현재 화면은 로컬 배열 앞에 글을 추가하고 입력란을 비운 뒤 정렬을 `latest`로 바꾼다. 실제 POST 요청은 보내지 않는다.

### POST `/events/{eventId}/discussions/{threadId}/replies`

요청은 `{ "body": "편집 전후의 설명과 참고 문서를 함께 비교해 보겠습니다." }`. 성공 제안은 201, `data: DiscussionReply`, `meta: Meta`. 고정 작성자와 두 표시 flag는 새 토론과 같다. 새 답글은 해당 글의 `replies` 끝에 추가되고 그 답글 입력란만 비워진다. 다른 글을 참조하거나 중첩 답글을 생성하는 필드는 없다.

### PUT `/events/{eventId}/discussions/{threadId}/like`

요청은 `{ "liked": true }` 또는 `{ "liked": false }`다. 성공 제안은 200, `data: DiscussionThread`, `meta: Meta`로 갱신된 글을 반환한다. 원하는 최종 상태를 전달하는 계약이므로 같은 값을 반복해 보내도 공감 수를 반복 증가시키지 않는다. 현재 UI는 false→true일 때 1 증가, true→false일 때 1 감소시키는 로컬 토글이다. 공감 수는 음수가 될 수 없다.

세 쓰기 계약 모두 잘못된 본문이면 400 `INVALID_BODY`, 작성 한도 초과면 400 `LIMIT_REACHED`, 존재하지 않는 사건·글이면 404 `NOT_FOUND`를 제안한다. like에는 작성 한도가 적용되지 않는다. 현재 UI의 알림과 HTTP 오류를 혼동하지 않는다. 이 endpoint들은 API 명세에만 존재하며 실제 다른 사용자에게 글이나 알림을 전송하는 기능은 구현하지 않았다.
