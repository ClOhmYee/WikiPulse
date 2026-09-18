# db — PostgreSQL 스키마

데이터 모델은 V1(`WP-35`)에서 시작해 **V9(2026-09-18)**까지 누적됐다. 명세: [docs/requirements-v0.3.md](../docs/requirements-v0.3.md) §3.2, §5

```
db/
  migrations/
    V1__initial_schema.sql            초기 17개 테이블
    V2__pulse_snapshot_graph.sql      시점별 지도 스냅샷·간선
    V3__baseline_hour_of_day.sql      UTC 시간대 기준선
    V4__baseline_view_stddev.sql      조회수 표준편차
    V5__spike_source.sql              LIVE/replay 출처·유일키
    V6__cluster_stock_reuse.sql       종목 판정 재사용·재시도 상태
    V7__spike_view_metrics.sql        판정 조회수·기준선 고정
    V8__page_intro.sql                historical revision 도입부
    V9__spike_revision_evidence.sql   revision 시점 감사 필드
  tests/
    test_schema*.py                   V1~V9 마이그레이션·제약 검증
    test_*_sql.py                     writer·상세 조회 SQL 회귀 검증
  requirements-test.txt
```

🔴 저장소 스키마의 정본은 V1 하나가 아니라 **V1부터 V9까지 순서대로 적용한 결과**다. EC2는 V1~V6까지만 확인했으며 V7~V9 적용 여부는 [기술 명세](../docs/tech-spec-v0.3.md)에서 별도로 추적한다.

## 왜 PostgreSQL 하나인가

pgvector 때문에 PG 가 필수다. 그러면 벡터 Top-K 결과에 티커·섹터·재무를 붙이는
조인이 SQL 한 번에 끝난다. 별도 벡터 DB 를 두면 두 번 왕복해야 한다.
기준선·이슈·회원·토론까지 전부 여기 들어간다 — MySQL 을 따로 두지 않는다.

## 설계에서 결정한 것

**위키 문서에 `page_id` 가 없다.** EventStreams recentchange 에 그 필드가 없다
(2026-09-08 실측). 식별자가 `(wiki, title)` 뿐이라 대리키를 두고 그 쌍에
UNIQUE 를 걸었다. 문서 이동이 일어나면 새 행이 생긴다 — MVP 범위에서 감수한다.

🔴 **`title` 은 공백형 canonical 만 넣는다** (`Hurricane Milton`). 자연키라서
표기가 흔들리면 한 문서가 두 행이 된다 — 덤프가 주는 밑줄형(`Hurricane_Milton`)이
그대로 들어오면 그렇게 된다. 적재 쪽에서 `producer/normalize.py` 의
`canonical_title()` 로 맞춰 보낸다. DDL 에 제약을 걸지는 않았다(정규화 규칙을
CHECK 로 옮기면 규칙이 두 곳에 생긴다). 규칙과 근거는 명세 §5.1 (WP-79).

**지금 이 보장이 어디까지인가** (2026-09-15 확인). `wiki_page` 에 쓰는 코드는
`spike/baseline_sink.py` 의 `RESOLVE_PAGE_SQL` UPSERT **하나뿐**이다. 그 title 은
-58 Historical Window 샤드의 `row["title"]` 을 그대로 쓰고, 그 샤드는
`batch/normalize_dump.py` 가 `canonical_title` 로 맞춘 값이다 — 즉 **DB 경계에
닿기 전에 이미 canonical 이다.** `baseline_sink` 자체는 정규화하지 않는다.

⚠️ **단, 그건 WP-79 이후에 만든 샤드에만 해당한다** (2026-09-15 정정,
WP-92). 그 전에 만든 `-56` 편집 샤드는 밑줄형이고 두 세대가 섞여 돈다.
`batch/historical_windows.py` 가 **읽는 지점에서** `canonical_title` 을 통과시켜
흡수한다 — 안 그러면 편집·조회수 join 이 한 건도 안 맞아 같은 문서가 두 행으로
쪼개지고, 밑줄 title 이 그대로 `wiki_page` 에 들어간다. 에러는 안 난다.
title 로 `wiki_page` 를 조회하는 코드는 **아직 없다**(`cluster/driver.py` 의
`load_pages_by_title` 은 docstring 속 의사코드이고 실제 함수가 없다).

🔴 **새 write path 를 추가하는 사람의 책임**: canonical 을 DB 직전에 부르지 말고,
**소스를 읽어 들이는 지점에서** 이미 canonical 인 샤드를 쓰거나 `canonical_title` 을
통과시킨다. 집계·그룹핑이 끝난 뒤에 문자열만 바꾸면 키가 이미 갈라진 뒤다 — 명세 §5.1.

**표시용 제목을 따로 두지 않는다.** 공백형이 곧 MediaWiki 의 표시 제목이라
(`Hurricane Milton`·`EBay`) 내부 식별용과 표시용이 같은 문자열이다. 나누면 두 값이
갈라질 위험만 생긴다. 백엔드는 `page_id` 로 조인하고 `title` 은 표시용으로만 읽는다.

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
| `page_view_hourly` | Pageviews 조회수. 편집 발생 후 2차·최종 판정용 |
| `page_baseline` | 조회수 기준선. 생성 28일 이상은 직전 28일, 미만은 생성 이후 자료 |
| `page_intro` | 리플레이 대표 텍스트의 시점별 도입부. `(page_id, rev_id)`로 고정하고 `rev_ts <= snapshot_ts` 중 마지막 revision을 읽음(V8) |
| `spike` | 사람 편집 1건 이상 **AND** 조회수 급등 통과분(WP-118). V7의 `views`·`view_baseline`과 V9의 `max_rev_id`·`last_edit_ts`가 판정값과 시점 감사 근거를 보존 |

### 이슈

| 테이블 | 무엇 |
| --- | --- |
| `issue_cluster` | 한 시점의 클러스터 = 버블 하나. `status` 로 3단계 노출 |
| `cluster_member` | 묶인 문서. `weight`는 Clickstream 이동량. `is_seed=true`는 루트 급증 문서 또는 생성일 동시성으로 편입된 새 사건 문서, `false`는 재급증 기준으로 편입된 기존 문서. Wikidata는 멤버십을 만들지 않음 |
| `issue_report` | LLM 요약. 운영 writer·상태 전이는 WP-119로 구현됐지만 worker 기본값은 꺼져 있고 실제 GATEWAY·EC2 실행은 미검증 |

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

~~`spike.view_ratio`가 NULL이면 조회수 도착 전 감지 상태~~ → **아니다.** V7부터 조회수 도착 여부는 `spike.views`로 판단한다(WP-129). `view_ratio`는 기준선 표본이 없는 신규 문서가 절대 하한으로 확정될 때도 정상적으로 NULL이며, V7 이전 행도 NULL일 수 있다. `cluster_member.completeness`를 `view_ratio`만으로 결정하지 않는다. 조회수 원본이 늦으면 `spike`를 만들지 않고 후보 대기에 남긴다.

**V6 재사용 인덱스가 as-of를 보장하지는 않는다.** 같은 `issue_key`의 최근 완료 요약·종목 판정을 찾는 경로는 구현됐지만, 현재 조회에는 원 결과 스냅샷이 대상 `snapshot_ts` 이하인지 확인하는 상한이 없다. 과거 backfill에 미래 결과가 섞이지 않도록 WP-120에서 조회 조건과 원 `generated_at`·`verified_at` 보존을 보완한다.

**회원·관심종목·알림·토론 테이블은 향후 기능용으로만 남아 있다.** MVP에서는 관련
API·UI·운영 적재를 구현하지 않는다(WP-104). 스키마 자체의 삭제 전파 규칙은
그대로이며, `notification.ticker` 는 `ON DELETE SET NULL` 이다.

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
- 명세 §3.2 흐름을 실제 INSERT 로 한 바퀴 돌린다 — 사람 편집 발생 → 조회수 급등 →
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
