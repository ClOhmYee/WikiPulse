# db — PostgreSQL 스키마

데이터 모델 v1 (`WP-35`). 명세: [docs/requirements-v0.1.md](../docs/requirements-v0.1.md) §3.2, §5

```
db/
  migrations/V1__initial_schema.sql   Flyway 규칙 이름. 17개 테이블
  tests/test_schema.py                진짜 PostgreSQL 을 띄워서 검증
  requirements-test.txt
```

## 왜 PostgreSQL 하나인가

pgvector 때문에 PG 가 필수다. 그러면 벡터 Top-K 결과에 티커·섹터·재무를 붙이는
조인이 SQL 한 번에 끝난다. 별도 벡터 DB 를 두면 두 번 왕복해야 한다.
기준선·이슈·회원·토론까지 전부 여기 들어간다 — MySQL 을 따로 두지 않는다.

## 설계에서 결정한 것

**위키 문서에 `page_id` 가 없다.** EventStreams recentchange 에 그 필드가 없다
(2026-09-08 실측). 식별자가 `(wiki, title)` 뿐이라 대리키를 두고 그 쌍에
UNIQUE 를 걸었다. 문서 이동이 일어나면 새 행이 생긴다 — MVP 범위에서 감수한다.

**클러스터는 시점의 함수다.** 버블맵에 시간 슬라이더가 있어서 같은 사건이라도
시점마다 구성과 급등도가 다르다. `issue_cluster` 가 `snapshot_ts` 를 갖고,
LIVE 화면은 가장 최근 값을, 리플레이는 사용자가 고른 시점을 읽는다.
`source` 컬럼이 실시간 산출물과 덤프 재계산 산출물을 구분한다.

**상태·등급은 ENUM 이 아니라 TEXT + CHECK 다.** ENUM 은 값을 추가할 때
`ALTER TYPE` 이 필요하고 롤백이 번거롭다. 아직 확정 안 된 값이 많다.

## 테이블

### 위키 신호

| 테이블 | 무엇 |
| --- | --- |
| `wiki_page` | 문서. `(wiki, title)` 이 자연키 |
| `page_edit_window` | Spark 윈도우 집계 출력. **단기 보존** — 슬라이딩이라 편집 1건이 12행에 걸친다 |
| `page_view_hourly` | Pageviews 조회수. 급증 2차 판정용 |
| `page_baseline` | 문서 × 요일·시간대(0~167) 기준선. 28일 EWMA |
| `spike` | 급증 판정 통과분. 편집 급증 **AND** 조회수 급등 |

### 이슈

| 테이블 | 무엇 |
| --- | --- |
| `issue_cluster` | 한 시점의 클러스터 = 버블 하나. `status` 로 3단계 노출 |
| `cluster_member` | 묶인 문서. `weight` 는 Clickstream 이동량, `is_seed` 는 직접 급증 여부 |
| `issue_report` | LLM 요약 |

### 종목

| 테이블 | 무엇 |
| --- | --- |
| `stock` | 약 5,100종목 + `vector(1536)` 임베딩 |
| `stock_price` | yfinance 일봉. 5,100 × 5년 ≈ 640만 행 |
| `cluster_stock` | 매칭 결과. `tier` 로 3등급, `match_path` 로 근거 경로 |
| `cluster_org_mention` | GDELT Organizations 동시 출현 lift. LLM 의 RAG 컨텍스트 |

### 사용자

`member` · `watchlist` · `notification` · `comment_thread` · `thread_comment`

## 함정

**`stock` 마스터를 Wikidata 로 만들지 말 것.** `wdt:P249` 로 티커를 조회하면
**40건**만 나온다. 티커는 `P414`(상장 거래소) 문의 한정어라
`p:P414 → pq:P249` 로 접근해야 15,875건이다. 에러 없이 조용히 0에 수렴한다.
마스터는 SEC `company_tickers.json` + NASDAQ Trader 를 쓴다.

**임베딩 차원을 바꾸면 `vector(1536)` 도 바꿔야 한다.** 지금은
`text-embedding-3-small` 기준이다. 차원이 다르면 INSERT 가 거부된다 —
테스트가 이걸 확인한다.

**`spike.view_ratio` 가 NULL 일 수 있다.** Pageviews API 가 시간 단위라
2차 판정이 최대 1시간 늦는다. NULL = 아직 판정 전이지 판정 실패가 아니다.

**종목이 사라져도 알림·토론은 남는다.** `notification.ticker` 는
`ON DELETE SET NULL` 이다. 상장폐지가 사용자 데이터를 지우면 안 된다.

## 테스트

Docker 없이 돈다. `pgserver` 가 PostgreSQL 바이너리를 번들로 들고 있고
pgvector 도 들어 있다.

```bash
cd db
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-test.txt
.venv/Scripts/python.exe -m pytest
```

서버 기동에 몇 초 걸린다. 테스트마다 롤백해서 서로 간섭하지 않는다.

확인하는 것:

- DDL 이 실제로 실행된다 (문법·타입·제약)
- 명세 §3.2 흐름을 실제 INSERT 로 한 바퀴 돌린다 — 편집 급증 → 조회수 →
  클러스터 → 종목 매칭 → 피드 조회. 중간에 컬럼이 모자라면 걸린다
- CHECK 제약이 오타를 진짜로 막는다 (`CONFIRMD`, `GDELT`, `VIBES`)
- pgvector 코사인 Top-K 가 된다
- 종목을 지워도 알림이 남는다

## 아직 안 한 것

- **마이그레이션 도구 미확정.** 파일 이름만 Flyway 규칙(`V1__`)을 따랐다.
  Spring Boot 쪽에서 Flyway 를 쓸지 Liquibase 를 쓸지는 백엔드 합의 사항이다.
- **인덱스는 최소만.** 실제 질의 패턴을 보고 추가한다. 지금 넣은 건 확실한 것뿐이다.
- **`page_edit_window` 보존 기간 미정.** 운영하면서 정한다.
- **파티셔닝 없음.** `stock_price` 640만 행은 단일 테이블로 충분하다.
