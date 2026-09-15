# 요구사항 명세서 — WikiPulse (WikiPulse)

- 버전: **v0.1 (2026-09-07 재작성)**
- 정본: 이 파일 (GitLab `docs/`). 개정은 MR로 한다. 노션은 읽기용 미러.
- 수치는 전부 실측이며 날짜를 붙였다 (11번).

---

## 1. 한 줄

위키피디아 편집이 급증한 문서 중 **편집 전후로 조회수도 급등한 문서**를 실시간으로 묶어 **지금 뜨는 이슈 피드**를 만들고, 각 이슈에 **관련 미국 상장 종목**을 LLM 검증을 거쳐 붙인다.

## 2. MVP 범위

**들어간다**

1. **급증 감지·클러스터링** — 위키 편집 급증 감지 → 편집 전후 조회수 급등 확인 → 둘 다 통과한 문서를 이슈 단위로 묶음. 묶는 근거는 Wikipedia Clickstream(문서 간 이동량)과 Wikidata API(항목 간 관계)
2. **버블맵** — 1번 결과의 시각화. 클러스터 = 버블, 크기 = 급등도. **시간 슬라이더로 과거 시점 재생(리플레이)**
3. **이슈 피드** — `/issues` 내부에서 카드/리스트 형식을 전환한다. 펄스맵(`/pulse`)은 독립 페이지이며 지도/목록 토글은 두지 않는다. (2026-09-09 정정, WP-37)
4. **이슈별 관련 미국 주식** — 후보 생성(벡터 유사도) → LLM 검증(근거 경로). 노출 개수 제한은 아직 두지 않는다
5. **종목 상세** — 주가 그래프 + 이슈 발생 시점 표시 + 그 종목이 걸린 이슈 피드
6. **회원** — 관심종목, 알림
7. **토론방** — 이슈별

**들어가지 않는다**

과거 유사 이슈 사례, 이슈 유형 자동 분류.

## 3. 아키텍처

```
 [수집]                    [저장·큐]              [연산]                    [서빙]

 Wikipedia EventStreams ─▶ Kafka ───────────────▶ Spark Structured ──┐
   (SSE, 편집 이벤트)        (토픽: wiki.edits)      Streaming          │
                                                    급증 감지·클러스터링  │
 Wikipedia Pageviews API ─▶ (배치 적재)           ─▶ 28일 기준선        ├─▶ PostgreSQL ─▶ Spring Boot ─▶ React
                                                                        │   + pgvector      REST API      버블맵·피드·
 Clickstream (월) ──────┐                                                │                   WebSocket     종목 상세·
 Wikidata API ──────────┴▶ (클러스터링 근거)                              │                                 토론방
                                                                        │
 GDELT GKG (15분 파일)  ──▶ HDFS (2노드) ────────▶ Spark 배치           │
                                                    종목 근거 추출       │
                                                                        │
 과거 덤프 (리플레이) ───▶ HDFS ─────────────────▶ Spark 배치           │
   mediawiki_history                                과거 시점 클러스터   │
   pageview_complete                                스냅샷 계산          │
                                                                        │
 SEC/NASDAQ 종목 마스터 ──▶ PostgreSQL ──────────▶ 종목 임베딩 (1회)   ─┘
 yfinance 사업 설명·주가                             pgvector 적재
                                                            │
                                                     LLM 검증 (Claude)
                                                     이슈 ↔ 후보 종목 근거 판정
```

### 3.1 컴포넌트별 역할 — 왜 있는가

| 컴포넌트 | 하는 일 | 없으면 |
| --- | --- | --- |
| **Kafka** | EventStreams(SSE)를 Spark가 읽을 수 있는 소스로 변환. 토픽 보존 기간 안에서 오프셋 되감기로 재처리 | Spark가 SSE를 직접 못 붙고, Spark 재시작 중 이벤트가 유실됨. 처리량은 이유가 아니다 — enwiki 초당 2건 |
| **Spark Structured Streaming** | 문서별 편집 윈도우 집계, 28일 기준선 대비 편집 급증 판정, 편집 전후 조회수 급등 확인, 통과 문서를 Clickstream·Wikidata 관계로 클러스터링 | 스트리밍 자체가 안 됨 |
| **Spark 배치** | 28일 기준선 산출(수십억 행), GDELT에서 이슈 관련 기관명·테마 추출, 과거 덤프로 리플레이용 클러스터 스냅샷 계산 | 단일 머신으로는 기준선·덤프 집계 불가 |
| **HDFS (2노드)** | GDELT 원본과 리플레이용 과거 덤프 보관. 두 EC2 디스크에 블록 분산, 복제 2 | 1년 100~230 GB zip이 한 디스크에 안 들어감 |
| **PostgreSQL + pgvector** | 서비스 데이터 전부 — 이슈·클러스터(현재+스냅샷)·기준선·종목 마스터·주가·회원·관심종목·토론. 종목/이슈 임베딩 벡터 저장과 코사인 Top-K | 별도 벡터 DB를 두면 종목 메타 조인이 두 번 왕복 |
| **LLM (Claude)** | 벡터 Top-K 후보 각각에 "왜 관련인가" 근거 경로를 생성할 수 있는지 판정. 통과분만 채택. 이슈 요약 문장 생성 | 임베딩 유사도만으로는 인과(호르무즈 → 유조선주)를 못 잡음 |
| **Spring Boot / React** | REST API + WebSocket(토론방·알림), 버블맵·피드·종목 상세 UI | — |

### 3.2 처리 흐름

1. Producer가 EventStreams SSE를 읽어 `wiki.edits` 토픽에 넣는다 (namespace 0, bot 플래그 유지).
2. Spark Streaming이 토픽을 읽어 문서별 편집 수를 슬라이딩 윈도우로 집계하고, PostgreSQL의 28일 기준선과 비교해 편집 급증 문서를 뽑는다. **기존 문서는 z-score(편집 z ≥ 3) AND 절대 편집수(≥ 10) AND 편집자 수(≥ 2)로, 신규 문서(baseline 없음)는 절대 편집수 AND 편집자 수로** 판정한다. 봇·1인 반복·되돌리기는 여기서 거른다 — **1인 반복(편집자 하한)은 2026-09-15 에 실제로 구현됐다**(WP-85, §11). 그전까지 `editor_count` 는 선언만 되고 판정에 안 쓰였다. 임계 근거는 §6·§11. ⚠️ **기존 문서에서 편집이 유일 관문인 게 맞는지는 재검토 중이다** — 사건 10건 실측에서 기존 문서 편집 탐지가 4/6(2건 미탐·1건 9일 지연)인 반면 조회수는 6/6이었다(2026-09-15, WP-86, §11). 신규 문서 판정은 그대로다(편집 4/4, 조회수는 baseline 이 원리적으로 없어 2/4).
3. 편집 급증 문서에 대해 조회수를 조회해 기준선 대비 급등(조회수 z ≥ 3 AND ≥ 2배)한 문서만 확정한다. 편집만 튀고 조회수가 안 따라오면 편집 전쟁·정리 작업으로 보고 버린다. ⚠️ **조회수는 편집보다 늦게 온다**(§6). 그래서 편집만 통과한 문서는 먼저 **감지됨** 상태로 내보내고, 조회수가 들어오면 **확정**으로 올린다 — 7번의 3단계 상태가 이 지연을 그대로 드러낸다. ⚠️ **기존 문서에 한해 이 AND 를 OR 로 바꾸는 안이 올라와 있다** (2026-09-15, WP-86). 합집합이면 실측 10/10을 잡고 현행 순서는 2건을 영영 못 잡는데, 조회수 오탐 비용은 대조군 434 문서·일에서 3건이었다. 분기 자체는 `detect()` 의 신규/기존 경로에 이미 있어 구조 변경이 아니다. 3단계 상태는 유지되고 **감지됨** 진입 조건만 두 갈래가 된다. 결정·영향 정리는 `ai/signal-order/RESULT.md`, 미결은 §10.
4. 통과 문서들을 **클러스터** = 이슈로 묶는다. ~~Wikidata API로 항목 간 관계를 확인해 약한 엣지를 자른다~~ → **폐기 (2026-09-09 실측, 아래 폐기 절).** Wikidata 카테고리 속성(`P31`·`P361`·`P17`·`P131`·`P276`)은 사건마다 걸리는 속성이 달라 하나로 못 정하고, 넓은 속성(P17·P31)은 무관한 배경 문서까지 다 끌어오고 좁은 속성(P361)은 진짜 관련 문서도 거의 못 잡는다. 신생 사건 문서는 Wikidata 항목 자체가 비어 있는 경우도 흔하다. **대신 급증 판정(1~3번)이 이미 갖고 있는 시간 신호를 쓴다.** 씨드 멤버(`is_seed=true`): 문서 생성일이 seed 사건 발생일 기준 윈도우(±14~30일, 실측 §11) 안이면 같은 이슈로 묶는다 — 신규 문서는 baseline이 없어 §3.2 2번과 같은 경로(절대 편집수 판정)로 이미 급증 판정을 통과하므로, 생성일 근접이 곧 시간 동시성이다. **비-seed 멤버(`is_seed=false`, 기존 문서가 사건으로 재조명되는 경우 — 예: `Mojtaba_Khamenei`, 2009년 생성인데 2026 Iran war 국면에서 Clickstream n=17,499로 최상위)는 아직 기준이 없다.** Clickstream 엣지 존재만으로는(n≥10, 문턱 없음) 후보 230~1,331개가 그대로 다 걸려 §10에서 실측한 "넓어서 못 쓰는" 문제가 그대로 재발한다 — 창 안 씨드 멤버 대비 얼마나 강한 상대적 이동량인지, 혹은 편집 이력 자체의 재급증(생성일이 아니라 최근 편집 밀도) 신호가 더 필요하다. 이동량(n)은 정해지면 `cluster_member.weight`에 쓴다. Wikidata 관계는 게이트에서 빠지고 GDELT처럼 LLM 검증 단계(6번)의 RAG 컨텍스트로 내려간다. 클러스터별 급등도(`pulse_score`)는 편집 급등과 조회수 급등을 합쳐 계산한다.
5. **여기부터(5~7)의 매칭·검증은 Spring 워커가 맡는다** — 급증 판정·클러스터링(2~4)은 Spark, 이슈-종목 매칭·검증은 Spring 후보 생성 워커로 실행 경계가 갈린다 (WP-67, `backend` `io.wikipulse.backend.matching`). 워커는 클러스터 멤버 도입부로 대표 텍스트(§6.2)를 만들어 GATEWAY로 임베딩하고, pgvector에서 종목 임베딩과 코사인 Top-K(a)를 뽑는다. 여기에 GDELT lift 상위 Top-K(`cluster_org_mention`, b, Spark 배치가 산출 — §3.1·WP-65)를 합집합해 `BOTH`/`GDELT_ONLY`/`EMBEDDING_ONLY` tier와 함께 `cluster_stock`에 `verified=false`로 멱등 적재한다(K·컷은 §6.3 확정값 — 임베딩 20 / GDELT 10). ⚠️ 이슈 임베딩은 질의 시점에 만들고 저장하지 않는다 — 저장 위치는 아직 미결(§10, WP-49)이라 거기 묶지 않았다.
6. **(같은 Spring 워커 경계)** LLM이 Top-K 각각에 근거 경로(직접 언급 / 제품·산업 관계 / 공급망·고객·경쟁 / 지역 노출)를 생성할 수 있는지 판정한다. GDELT에서 뽑은 이슈 관련 기관명·테마를 컨텍스트로 준다 (RAG). 통과한 것을 tier 우선(§6.3: BOTH → GDELT_ONLY → EMBEDDING_ONLY)으로 낸다. 노출 개수 제한은 아직 없다. (후보 생성은 5번에서 끝났고, 이 검증 단계가 `cluster_stock`의 `verified`·`match_path`·`rationale`을 채운다 — 후보 재생성이 이 값들을 덮지 않는다.)
7. 이슈 + 종목 + 근거 문장을 PostgreSQL에 쓰고 API가 낸다. 피드 상태는 **감지됨 → 검증 중 → 확정** 3단계 — 2~4번은 초~분 단위, 6번 LLM은 분 단위라 그 차이를 사용자에게 그대로 보여준다.
8. **리플레이**: 과거 덤프(`mediawiki_history`·`pageview_complete`·해당 월 Clickstream)를 HDFS에 올리고 Spark 배치가 2~4번을 과거 시점으로 돌려 `cluster_snapshot(snapshot_ts, …)`을 미리 계산해 PostgreSQL에 넣는다. 버블맵 시간 슬라이더가 이 스냅샷을 읽는다. 원본 덤프는 계산 후 폐기해도 된다.
9. **종목 상세**: yfinance 일봉을 PostgreSQL에 적재. 그래프 위에 그 종목이 걸린 이슈의 발생 시점을 표시하고, 아래에 해당 이슈 피드를 붙인다.
10. **회원·관심종목·알림·토론방**: PostgreSQL 테이블. 관심종목에 새 이슈가 붙으면 알림(수단 미정, 10번). 토론방은 이슈별 WebSocket 채널.

## 4. 데이터 소스

| 구분 | 소스 | 용도 | 실측 (11번) |
| --- | --- | --- | --- |
| 편집 이벤트 | Wikipedia EventStreams `recentchange` | 급증 감지 | 전체 31/s, enwiki 2/s, 1.5 KB/건 |
| 조회수 | Wikipedia Pageviews API(일별) · `other/pageviews` 시간별 덤프 · `pageview_complete` 덤프(일별, 봇 구분) | 28일 기준선, 급증 2차 판정 | 시간별 gz 49.6 MB · 일별 user 677 MB bz2 |
| 문서 간 이동 | **Wikipedia Clickstream** 월별 덤프 | 클러스터링 엣지 가중치 | enwiki 월 471 MB gz |
| 항목 관계 | **Wikidata API** (`wbgetentities`, SPARQL) | 클러스터링 — 문서 간 관계 확인(사건·지역·상위 개념). 티커 조회에는 안 씀 | — |
| 리플레이 원본 | `mediawiki_history` 월 스냅샷, `pageview_complete` 일별 | 과거 시점 클러스터 스냅샷 계산 | 월 520~585 MB · 일 677 MB bz2 |
| 뉴스 메타데이터 | **GDELT 2.0 GKG** 15분 파일 | 이슈 관련 기관명·테마 → LLM 컨텍스트, HDFS 원본 | 일 276~627 MB zip |
| 종목 마스터 | NASDAQ Trader 심볼 디렉터리, SEC `company_tickers.json` | 미국 3대 거래소 보통주 약 5,100 | 2026-09-04 확정 |
| 종목 설명 | yfinance `longBusinessSummary` | 종목 임베딩 입력 | 표본 200종목 보유율 100% |
| 주가 | yfinance 일봉 | 종목 상세 그래프 | 5,100종목 × 5년 ≈ 640만 행, PostgreSQL로 충분 |
| 임베딩 | OpenAI `text-embedding-3-small` (LLM 게이트웨이) | 이슈·종목 벡터 | — |
| 검증 | Anthropic Claude (LLM 게이트웨이) | 근거 경로 판정, 요약 | GATEWAY가 Anthropic + web_search 서버 도구 중계 확인 (2026-09-07) |

제외: 한국 증시(약관), IEX Cloud(종료), Wikidata 티커(P249가 한정어라 조용히 40건만 나옴 — 티커는 SEC 파일이 정확), 위키 링크 그래프로 종목 후보 생성(1-hop 이웃에 상장기업이 없음, 11번).

## 5. 저장

| 데이터 | 어디 | 크기 | 보존 |
| --- | --- | --- | --- |
| 편집 이벤트 원본 | Kafka 토픽 | enwiki 260 MB/일 | 7일 (재처리 창) |
| GDELT GKG 원본 | HDFS | 100~230 GB/년 zip | **기간 미정** (10번). 307 GB × 2 디스크 |
| 28일 기준선 | PostgreSQL | 문서 × 시간대, 수백 MB~수 GB | 롤링 갱신 |
| 종목 임베딩 | PostgreSQL pgvector | 5,100 × 1,536 dim | 마스터 갱신 시 |
| 이슈·클러스터·피드 | PostgreSQL | 작음 | 영구 |
| 클러스터 스냅샷 (리플레이) | PostgreSQL | 시점 × 클러스터. 시연 구간만 | 영구 |
| 리플레이 원본 덤프 | HDFS | 구간당 수십 GB bz2 | 스냅샷 계산 후 폐기 가능 |
| 주가 일봉 | PostgreSQL | ~640만 행 | 영구 |
| 회원·관심종목·알림·토론 | PostgreSQL | 작음 | 영구 |

RDB는 PostgreSQL 하나다. MySQL을 따로 두지 않는다 — pgvector 때문에 PG가 필수이고, 나머지를 분리할 이유가 없다.

## 6. 이슈-종목 매칭

후보 생성과 검증을 나눈다.

### 6.1 종목 임베딩 텍스트 (2026-09-08 확정)

```
{회사명}. {섹터} — {산업}. {yfinance longBusinessSummary}
```

- 입력은 회사명·섹터·산업을 사업 설명 앞에 붙인다. 상한 2,000자(넘으면 뒤를 자른다) — 대부분 2,000자 미만이라 거의 안 걸린다
- 설명이 비어 있는 종목은 임베딩하지 않고 화면에서 제외한다. **회사명만으로 임베딩하지 않는다** — 이름만으로는 사업 정체성이 안 담겨 노이즈에 가깝다. 표본 32종목·200종목 모두 보유율 100%라(4번) 발생 빈도는 낮다
- 사업 설명 끝의 상투 문구("~ was founded in ...", "~ is headquartered in ...")는 **제거하지 않는다.** 있으나 없으나 순위·분리도 차이가 ±0.5순위·±0.006 이내였다 — 정규식 유지보수 비용을 들일 이득이 없다

메타 접두(회사명·섹터·산업)가 사업 설명 단독보다 살짝 낫다 — Hormuz 클러스터 Top-10 정답이 6→7개로 늘었고 다른 곳에서 뒤진 적은 없다. 근거는 `ai/stock-text-poc/RESULT.md`.

⚠️ 표본은 이슈 텍스트 실험과 같은 32종목이다. 200종목 표본 재확인은 WP-34(종목 설명 수집·적재) 착수 시 한다.

### 6.2 이슈 대표 텍스트 (2026-09-08 확정)

클러스터는 문서 여러 개인데 임베딩·LLM 입력은 글 한 덩이여야 한다. 그 변환 규칙:

```
{문서 제목}: {도입부 앞 N문장}
{문서 제목}: {도입부 앞 N문장}
...
```

- N = 클러스터 문서가 1개면 6, 2~3개면 4, 4개 이상이면 2. 전체 상한 2,000자
- 문서 순서는 급등도(`pulse_score`) 내림차순
- 출처는 Wikipedia API `prop=extracts&exintro&explaintext`, 리다이렉트를 따라간다
- 🔴 **텍스트는 영어로 유지한다.** 종목 설명이 영어라 이슈 텍스트를 한국어로 만들면 언어 불일치만으로 코사인이 절반이 된다 (정답 평균 0.160 → 0.081, 11번). 사용자에게 보여줄 한국어 문장은 LLM 검증 단계에서 따로 만든다.

~~LLM 한 번 호출해 이슈를 요약한 뒤 그것을 임베딩~~ → **채택하지 않는다** (2026-09-08). 랭킹 품질이 나열 방식과 동률인데 호출 1회와 4~6초가 붙고, 조용히 틀리는 실패 모드 셋이 실측됐다: ① 프롬프트 언어를 따라가 한국어 요약이 나오면 코사인 반토막 ② 정보가 부족하면 "설명할 수 없다"는 거부 문장이 그대로 임베딩됨 ③ 입력에 없는 사건을 지어냄 ④ 같은 입력으로 4회 돌렸을 때 나열 방식은 값이 동일한데 LLM 요약만 정답 평균순위가 3.3~7.0으로 흔들렸다 — 파라미터 튜닝 효과가 잡음에 묻힌다. 근거는 `ai/issue-text-poc/RESULT.md`.

### 6.3 후보 생성과 검증

- **후보 (recall)** — 두 경로의 합집합:
  - (a) 이슈 임베딩 ↔ 종목 임베딩 코사인 **Top-20**. pgvector 한 쿼리. 설명서에 그 리스크가 적힌 종목을 잡는다 (보험사, 에너지 인프라)
  - (b) GDELT 동시 출현 lift 상위 **Top-10**. 이슈 기간 기사에서 기관명을 뽑아 종목 마스터와 조인. 설명엔 없는 2차 효과를 잡는다 (플로리다 전력, 발전기, 항공 결항)
  - 둘의 교집합은 작다 — Milton K=10에서 1개, K=30에서 3개 (11번). 합집합이 맞다. 다만 **(b)가 주력이고 (a)는 보충**이다: 사건 서술과 사업 설명은 같은 종류의 텍스트가 아니라 임베딩 코사인이 0.2 안팎으로 낮고, 정답(NEE·Lennar·Generac)과 노이즈(Monster Beverage·Intel)가 섞여 나온다. (a)의 몫은 기사에 아직 이름이 안 나온 첫 시간대와 기업 문서 이슈다
- **우선순위 — 교집합 먼저**:
  1. **(a) ∩ (b)** — 두 신호가 일치. 먼저 검증하고 통과하면 최상단. Milton K=10 교집합 NEE, K=30 NEE·Generac·Exxon — K가 커지면 노이즈도 들어오므로 LLM 면제는 아니다
  2. **(b) − (a)** — GDELT 단독. 정답 밀도가 높다
  3. **(a) − (b)** — 임베딩 단독. **1·2등급 통과(LLM 검증 확정)가 2개 미만일 때만** 검증한다. 임베딩 노이즈(Monster Beverage·Intel)가 대부분 여기 있어서 LLM까지 안 간다
- **검증 (precision)**: LLM이 후보마다 근거 경로를 만들 수 있는지 판정. 못 만들면 버린다. 고정 유사도 컷은 두지 않는다. **노출 개수 상한도 두지 않는다** — LLM 검증을 통과한 것만 화면에 나가므로 이미 자연 상한이 걸려 있고, 정답셋 최댓값(Milton 9개)도 스크롤 범위 안이다.
- **컨텍스트 (RAG)**: (b)에서 나온 기관명 상위와 테마를 LLM에 같이 준다. 뉴스 동시 출현이 인과 경로의 근거가 된다.

**확정 (2026-09-14, WP-22)**: 임베딩 K=20 · GDELT K=10 · 3등급 발동 기준 N=2(1·2등급 확정 통과 개수). 근거:
- 임베딩 K는 10~20이면 강한 정답 대부분을 담는다(K=20에서 Milton NEE·ETN·LEN·HD, 은행위기 ZION·SCHW·FITB 포착). K=30까지 키우면 새로 들어오는 후보의 노이즈 비율이 70%→86%로 올라가 LLM 호출만 늘리고 회수가 적다(`ai/candidate-overlap/RESULT.md`)
- GDELT K=10에서 제목 매칭이 되는 사례(CrowdStrike·IBM)는 정답이 다 Top-3 안에 있었다 — 10이면 여유 있게 담는다(같은 문서)
- N=2는 CrowdStrike(등급1 확정 3개)·IBM(등급1 확정 2개) 둘 다 등급3에 정답이 0개였던 실측(`ai/matching-goldset/RESULT.md`)에 맞춘 것 — 확정 통과가 2개 이상이면 이미 정답을 대부분 건진 상태라 등급3 비용을 아낀다. GDELT 신호가 죽는 사례(Milton·2023 은행위기)는 등급1·2 확정이 N 미만이라 그대로 등급3 전수 검증으로 넘어간다 — N 조건이 아니라 GDELT 자체를 GKG 기관명 필드로 되살리는 게 먼저다(WP-47)
- 이 값들은 title-그렙 근사 위에서 나온 방향성 확인이다. WP-47(별칭 테이블)로 GDELT를 GKG 기관명 기반으로 바꾸면 재측정 대상이다

비용: 이슈당 LLM 호출 = |1등급| + |2등급| (+ 3등급 조건부, 등급1·2 확정 통과가 2개 미만일 때 최대 20 추가). 등급1·2 합은 GDELT Top-10을 넘지 않으므로 보통 10회 안팎, 등급3까지 가면 최대 30회. 이슈 수에 비례하고 사용자 수와 무관하다.

임베딩 유사도만으로는 안 되는 이유: `Strait of Hormuz` 임베딩에 가까운 건 `Persian Gulf`·`Iran`이지 `Frontline plc`가 아니다. "해협 봉쇄 → 운임 급등 → 유조선주"는 의미 유사도가 아니라 인과라서 LLM과 뉴스 근거가 필요하다.

GDELT 동시 출현이 실제로 신호가 있는지는 확인했다 — Hurricane Milton(2024-10-10) 기사에서 Florida Power & Light lift 10.5, Generac 9.3, Duke Energy 8.4, Publix 7.0, 무관한 Nvidia 0.4 (11번).

## 7. 인프라 (2026-09-04 SSH 실측)

| | 값 |
| --- | --- |
| 서버 | Lightsail xlarge 2대 (기반 t3.xlarge) — `service.example.com`, `data.example.com` |
| 각 대 | 4 vCPU / 16 GB / 309 GB, Ubuntu 24.04 |
| 초기 상태 | python3만. Java·Docker·Hadoop·Spark·Kafka·PostgreSQL 없음 |
| 구성 | **두 대 모두** HDFS DataNode + Spark Worker. 서비스(Nginx·Spring·PG·Redis)는 1번, Kafka·Spark Master·NameNode는 2번 |
| GPU | `192.0.2.30` jupyter, 계정 `example-account`, **Device 2** |

주의: t3는 버스트형이라 CPU 크레딧 소진 시 코어당 40%로 떨어진다. Streaming을 24시간 돌리고 하루 CPU 그래프를 본다. `ufw`는 프로젝트 지시로 항상 enable — 포트는 `ufw allow`로 개별 개방.

RAM 16 GB에서 Kafka + Spark + HDFS 데몬을 올리면 Spark executor 몫은 8 GB 안팎. HBase·Airflow는 넣지 않는다.

## 8. 팀

| 이름 | 역할 |
| --- | --- |
| 팀원 1 | PM / AI |
| 팀원 2 | BE — Issue/Stock API, 데이터 모델링 |
| 팀원 3 | BE — Wikipedia 수집, 실시간 Issue API |
| 팀원 6 | BE — 뉴스·기업 데이터 연동, AI 파이프라인 API |
| 팀원 4 | FE — 버블맵, 이슈 상세 |
| 팀원 5 | Infra — Kafka/Spark/HDFS 환경, 배포 |

## 9. 포지셔닝 / 면책

위키피디아 활동과 주가의 상관관계는 연구 결과가 엇갈린다. 서비스 문구는 "원인 규명"이 아니라 "참고 컨텍스트"로 유지한다. 화면 노출 문안(발표 PPT p.25에서 가져옴):

> 종목 연결은 자동 매핑 결과이며 정확도가 검증된 것이 아닙니다. 연결 강도는 사업 구조의 직접성을 표현하며 주가 방향이나 수익률을 뜻하지 않습니다. 시세·밸류에이션·투자 기간을 포함하지 않으며 투자 권유가 아닙니다.

## 10. Open Issues

- [x] ~~LLM 게이트웨이가 Claude `web_search`를 중계하는지~~ — **된다** (2026-09-07 실측, 11번). Anthropic `/v1/messages` + `web_search_20250305` 서버 도구가 정상 반환. OpenAI `web_search_preview`도 됨
- [x] ~~급증 판정 수식~~ — **확정 (2026-09-08, §11 실측).** 편집·조회수 임계 z = 3, 절대 편집수 하한 10, 조회수 최소 2배. 기존 문서는 z-score, 신규 문서는 절대 편집수. Strait of Hormuz 조회수로 검증 — 평상시 최대 z 1.9, 사건 최소 z 11.2로 z=3이 오탐 없이 앉는다. 코드: `data-pipeline/spike/detector.py`, 테스트 13개. 남은 튜닝: 윈도우 길이, EWMA 가중, 봇 필터 강도는 실데이터 붙은 뒤
  - ⚠️ **2026-09-14 실편집 덤프 리플레이에서 이 확정이 흔들렸다** (WP-61, §11 "리플레이 회귀 검증" 행). 위 검증은 **조회수**로 한 것이고 편집 분포로는 검증된 적이 없었는데, 실제 편집으로 재생하니 Hormuz 기존 문서 경로가 **전량 미탐**(시간 최대 8편집 < 하한 10)이고 대조군에서 **1인 연속 편집 오탐**이 났다. 또 `hour_of_week` 슬롯은 주 1회라 `sample_days`가 7에 구조적으로 도달 못 해 **z 경로가 실행되지 않는다.** 🔴 임계는 확정 자산이라 임의로 고치지 않았다 — 재개 여부는 팀 결정(WP-84·-85)
- [ ] **조회수 지연 처리** — Pageviews API는 **일 단위, 하루 지연**(시간별 아님, 실측). 시간별은 `other/pageviews` 덤프(약 1시간 지연, 봇 구분 없음)만. "시간별 + 봇 구분"을 동시에 주는 소스가 없다. LIVE 2차 판정을 시간별 덤프(빠름·봇 미구분)로 할지 일별 API(느림·정확)로 할지 결정. 감지됨→확정 지연이 그만큼이다
  - ⚠️ **아래 신호 순서 항목과 같이 결정해야 한다** (2026-09-15, WP-86). 조회수가 기존 문서의 **1차** 신호가 되면 이 소스 선택이 확정 지연이 아니라 **탐지 지연**에 직접 들어온다. 다만 `Strait_of_Hormuz`·`Papal_conclave` 는 편집으로 아예 안 잡히므로, 하루 늦는 것과 못 잡는 것 사이의 선택이다
- [ ] **편집·조회수 신호 순서 (기존 문서)** — 실측은 끝났고 **팀 결정 대기**다 (2026-09-15, WP-86, §11). 사건 10건에서 두 신호가 서로 다른 문서 유형을 맡는 게 드러났다: 기존 문서는 조회수 6/6·편집 4/6, 신규 문서는 편집 4/4·조회수 2/4(신규는 조회수 baseline 이 **원리적으로** 없다). **권고: 신규 문서는 현행 편집 단독 유지, 기존 문서만 AND → OR.** 조회수를 전면 1차로 뒤집는 안(선택지 1)은 신규 문서를 통째로 놓쳐 채택 불가다. 근거·영향 정리는 `ai/signal-order/RESULT.md`
- [ ] **조회수 절대 하한(`MIN_ABSOLUTE_VIEWS`) 신설** — 편집에는 `MIN_ABSOLUTE_EDITS=10` 이 있는데 조회수에는 대응물이 없다. 평소 1~3회/일인 `Hurricane_Helene` 이 **8회**로 `z 8.1·8.9배` 통과했다(2026-09-15 실측, §11). 하한 100~500 구간에서 나머지 9건 결과가 동일. 🔴 임계는 WP-38 확정 자산이라 임의로 안 넣었다 — 값·도입 여부는 팀 결정
- [ ] **관측이 드문 기존 문서가 z 경로에 못 간다** — `Boeing_787_Dreamliner`(2011년 생성, 월 ~100편집)가 `is_new_page=True` 로 판정됐다. `hour_of_day` 슬롯 28일 창에 관측이 7일치도 안 모여서다. -84 가 `hour_of_week`(최대 4관측) 문제를 고쳤지만 편집이 24개 슬롯에 흩어지는 문서는 여전히 `is_thin` 이다 (2026-09-15, WP-86). -84 후속
- [x] ~~클러스터링 파라미터 — Clickstream 엣지 최소 이동량~~ — **문턱값 없음으로 확정 (2026-09-09 실측, WP-51).** 과거 사건 3건(Hormuz 2025-06·Milton 2024-10·Iran 2026-08, 사건 당시 월 dump)에서 실제 엣지 값을 봤더니 절대 이동량으로는 "같은 이슈"와 "배경 지식"을 못 가른다 — Hormuz는 진짜 사건 문서(`2025_Iran_threat_of_Strait_of_Hormuz_closure`, n=383)보다 무관한 지리 배경 문서(`Choke_point`, n=11,778)가 30배 더 클릭됐고, 반대로 Iran은 같은 사건 하위 문서(`Kuwait_in_the_2026_Iran_war` 등)가 덤프 최하단(n=10)까지 깔려 있다. 문턱을 어디 잡든 한쪽은 잘못 거른다. **결론: 덤프 자체 하한(n≥10)만 쓰고 별도 문턱을 얹지 않는다. Clickstream 값은 §3.2 4번대로 `cluster_member.weight`에만 쓰고, 포함 여부(엣지를 자르는 일)는 전적으로 아래 Wikidata 관계 확인이 맡는다.**
- [x] ~~클러스터링 파라미터 — Wikidata 관계 종류~~ — **Wikidata 카테고리 속성 접근 자체를 폐기 (2026-09-09 실측 전체, WP-51).** 후보 5개(`P31`·`P361`·`P17`·`P131`·`P276`)를 사건 3건의 클릭스트림 이웃 전체(231·421·1,331개)에 SPARQL로 돌려본 결과 — `P17`(국가)은 Milton 421개 중 205개, Iran 1,331개 중 389개가 매치될 만큼 넓다. 매치된 문서가 `Atlanta_Motor_Speedway`·`Air_Force_One`·NBA 시즌 문서·`2003_Bam_earthquake` 등 사건과 무관 — "같은 나라"일 뿐 "같은 이슈"가 아니다. (처음엔 Iran↔`2026_Iran_war` 단일 쌍만 보고 "P17이 잘 맞는다"고 잘못 판단했었다 — 전체 후보군 검증 전이었다.) `P31`도 마찬가지로 넓다(다른 해협·다른 태풍 다 걸림). `P361`은 좁아서 안전하지만 Milton 2개·Iran 1개·Hormuz 0개로 진짜 관련 문서도 거의 못 잡는다. **결론: 5개 속성 다 못 쓴다. 대신 급증 판정의 시간 동시성(같은/인접 시간창에 함께 스파이크)을 클러스터링 게이트로 쓴다 — §3.2 4번.** Wikidata는 게이트에서 빠지고 LLM 검증 단계 RAG 컨텍스트로 내려간다
- [x] ~~클러스터 최소·최대 크기~~ — **생성일 윈도우 기준 씨드 멤버로 실측 (2026-09-09, WP-51).** Hormuz(±30일) 2개·Milton(±14일) 6개·Iran(±30일) 14개, 다 검증해도 사건 무관 문서는 안 섞임 (§11 "생성일 시간 동시성" 행). 씨드 멤버만 기준으로는 최소 2 ~ 최대 14 정도. ⚠️ 비-seed 멤버(아래 항목)가 정해지면 실제 클러스터 크기는 더 커진다 — 이 숫자는 하한선이다
- [ ] 비-seed 클러스터 멤버 기준 — 기존 문서가 사건으로 재조명될 때(예: `Mojtaba_Khamenei`) 딸려 들어갈 조건. Clickstream 존재만으로는 후보가 너무 넓음(§3.2 4번 참조). **편집 재급증 비율(사건기간 편집 수 / 동일 길이 직전 기준기간 편집 수) 예비 검증** — `Mojtaba_Khamenei` 17.9배(재조명, 포함돼야 함) vs `Saffir–Simpson_scale` 6.1배(Milton과 무관, 태풍 시즌 전체가 겹쳐 편집이 몰린 계절성 오염 — 배제돼야 함) vs `Hurricane_Katrina` 1.0배·`Persian_Gulf` 0.7배(배경, 정상 배제). 신호는 있으나 6.1배와 17.9배 사이 어디서 끊을지는 표본 4~5개로는 못 정한다. 후속 이슈로 분리(WP-77) — 근거는 §11 "편집 재급증 비율, 예비 표본" 행
- [ ] 리플레이 시연 구간 — 어느 사건·며칠. GDELT 결손(2025-06-13~07-04) 밖에서
- [x] ~~Top-K의 K (임베딩·GDELT 각각), 3등급 검증 발동 기준 N, 노출 개수 상한~~ — **확정 (2026-09-14, WP-22).** 임베딩 K=20 · GDELT K=10 · 3등급 발동 N=2(1·2등급 확정 통과 개수). 노출 상한은 두지 않는다(검증 통과분만 노출되어 자연 상한). `-39`·`-48` 실측 위에서 결정 — 근거·수치는 §6.3
- [x] ~~임베딩 교집합 재측정~~ — **재측정 완료 (2026-09-10, WP-48).** 확정 이슈 텍스트 규칙(§6.2 D) + `text-embedding-3-small` + 정답셋 5사례로 S&P 500 대상 재측정. 임베딩∩GDELT 겹침은 K=10에서 0~2개(합집합이 맞다는 §6.3 재확인), 임베딩 단독 후보는 70~100%가 노이즈(3등급 조건부 검증의 근거), GDELT는 임베딩이 못 잡는 2차 효과 정답(CrowdStrike의 DAL, IBM의 MU)을 데려옴. 단 GDELT 제목-그렙 근사는 "회사=2차 영향"인 사건(Milton·은행위기)에서 죽음 — 실제 파이프라인의 GKG 기관명 필드로는 재측정 필요. 근거: `ai/candidate-overlap/RESULT.md`, §11
- [ ] GDELT 기관명 → 종목 정규화 — 부분문자열 매칭은 News Corp·Meta 같은 오탐이 남. 별칭 테이블 필요
- [ ] 알림 수단 — 웹 내 배지 / 브라우저 푸시 / 이메일
- [ ] 토론방 — 실시간(WebSocket) 필수인지, 모더레이션
- [ ] GDELT·리플레이 덤프 보존 기간 — 디스크 307 GB × 2, GDELT 1년 zip 100~230 GB
- [ ] 2노드 RAM 배분 — 서비스 박스에 DataNode·Worker를 얹을 때 Spring·PG와 나누는 기준
- [x] ~~매칭 정확도 정답셋~~ — **확정 (2026-09-10, WP-39).** 사건형 3(Milton·CrowdStrike·2023 은행위기) + 기업형 2(IBM 실적 경고·PayPal 인수 무산) = 5건, 정답 20종목에 근거 기사를 달았다. 등급(§6.3) 채점 결과 CrowdStrike·IBM은 정답이 등급1(교집합)에서 다 잡히고 등급3(임베딩 단독)엔 정답이 0개 — §6.3 우선순위가 실측으로 확인됐다. 자세한 결과·GDELT 방식의 한계는 `ai/matching-goldset/RESULT.md`
- [ ] 면책 문구 법적 검토

## 11. 근거 수치 (실측)

| 항목 | 값 | 날짜 |
| --- | --- | --- |
| EventStreams 처리량 | 전체 31 events/s, enwiki 2/s, 1.5 KB/건 (15초 표본) | 2026-09-04 |
| GDELT GKG 하루 | 2026-03-01 66,338건 276 MB zip / 862 MB · 2024-10-10 160,838건 627 MB / 1.9 GB | 2026-09-07 |
| GDELT 결손 | 2025-06-13 ~ 07-04 전부 404 | 2026-09-07 |
| GDELT lift, Milton | I=`HURRICANE ∧ florida` 10,707건. FPL 10.5 · Generac 9.3 · Duke 8.4 · Publix 7.0 · United 6.3 · Disney 4.7 · Nvidia 0.4 · MSFT 0.3 | 2026-09-07 |
| GDELT lift, Iran | I=`iran` 35% → 석유 메이저 0.5 / I=`iran ∧ ENV_OIL` 6% → Chevron 3.6 · Exxon 2.6 | 2026-09-07 |
| 임베딩 vs GDELT 후보 교집합 | 풀 S&P 500, 이슈=위키 intro. **`text-embedding-3-small`(GATEWAY)**: Milton K=10/20/30 → 1/1/3개, Iran+Hormuz → 2/4/5개, Jaccard ≤0.11. 로컬 MiniLM도 같은 범위(0/1/3, 1/3/3). 임베딩 Top-20에 NEE·Home Depot·Lennar·Eaton·Generac(정답)과 Monster Beverage·Intel·Nike(노이즈)가 섞임, 코사인 0.17~0.30. GDELT Top-20은 NEE·Duke·Generac·Mosaic·Progressive·Allstate·United·Disney — 정답 밀도 높음 | 2026-09-07 |
| 임베딩 vs GDELT 후보 교집합, 확정 규칙 재측정 | S&P 500(504종목), 이슈=§6.2 확정 규칙(D), 정답셋 5사례(§39). 임베딩∩GDELT K=10에서 Milton 0·CrowdStrike 2·은행위기 0·IBM 1·PayPal 1개 (K=30까지 키워도 1~4개 — 합집합이 맞다). 임베딩 단독 후보 노이즈율 K=10에서 70~100%(3등급 조건부 검증의 근거). GDELT가 임베딩이 못 잡은 정답 데려옴: CrowdStrike DAL·IBM MU. ⚠️ GDELT를 DOC API 제목-그렙으로 근사 → Milton·은행위기(회사가 2차 영향)는 제목에 회사명이 안 실려 신호 0. 실제 파이프라인 GKG 기관명 필드로는 재측정 필요 | 2026-09-10 |
| 이슈 대표 텍스트 방식 비교 | 클러스터 3건(Milton·Hormuz·Nvidia) × 종목 32개(정답 20 + 노이즈 12). 대표문서 도입부 / 제목+요약 나열 / LLM 요약 / 문서수 적응 나열의 정답 평균순위가 각각 10.6·10.5·11.0·10.5(Milton), 6.6·7.8·6.9·7.8(Hormuz), 4.0·5.0·3.3·4.0(Nvidia)로 **사실상 동률**. LLM 요약은 한국어로 생성 시 정답 평균 코사인 0.160 → 0.081로 반토막, 단일 문서에서 거부 응답이 그대로 임베딩됨. 정답-노이즈 분리도는 사건형 +0.05~0.15 / 기업형 +0.26 — 임베딩 단독이 사건형에 약하다는 §6 전제와 일치 | 2026-09-08 |
| 매칭 정답셋 등급 채점 | 5사례(사건형 3+기업형 2) K=10. CrowdStrike 등급1 정답 3/3(노이즈57%)·등급3 정답 0. IBM 등급1 정답 2/2(노이즈75%)·등급2에서 MU(이슈 본문엔 없는 인과 후보) 발견. Milton·2023은행위기는 GDELT 제목-그렙 근사가 "회사=사건 당사자"가 아닌 사례에서 신호 0(방법론 한계, 실제 파이프라인의 GKG 기관명 추출과 다름) | 2026-09-10 |
| 위키 링크 그래프 → 상장기업 | Hormuz 1,358 이웃 중 0 · Milton 3 · Iran 4 · Nvidia 507(목록 문서 노이즈) | 2026-09-04 |
| Wikidata 티커 | `wdt:P249` 40건 / `p:P414 → pq:P249` 15,875건 / NYSE+NASDAQ 3,905 | 2026-09-04 |
| Wikimedia 덤프 | pageview_complete 일 user 677 MB bz2 · mediawiki_history enwiki 월 ~~520~585 MB(추정)~~ → **실측 515,334,641 B(2025-06) · 596,614,108 B(2024-10)** (HEAD Content-Length, 2026-09-10) · clickstream enwiki 월 471 MB | 2026-09-04 (덤프 크기 2026-09-10 정정) |
| 급증 임계 (Strait of Hormuz 조회수 2025-06) | 사건 전 18일 391±55, z 범위 −1.3~+1.9. 사건 첫날 6/12 z=11.2(2.6배), 정점 6/22 z=5311(746배). **z=3이 평상시 최대와 사건 최소 사이에 오탐 없이 앉음** | 2026-09-08 |
| Pageviews 입도 | AQS API는 일별만(hourly 400 에러). 시간별 문서 조회수는 `other/pageviews` 덤프뿐, 봇 구분 없음 | 2026-09-08 |
| 편집 곡선 (Hurricane Milton) | 신규 문서. 생성 당일(10-05) 40편집, 시간 최대 44/h. baseline 없어 z 불가 → 절대 편집수로 판정 | 2026-09-08 |
| 리플레이 회귀 검증, 실편집 덤프 (WP-61) | 실덤프(`2026-08.enwiki.2025-06` 5,501,827행→3,361,013 event / `2024-10` 6,646,918행→3,654,769 event)를 1시간 윈도우로 재생해 `detect()` 실행. **Milton 2024-10(신규 문서 경로) 통과** — 272 윈도우 중 48건 급증, 최초 탐지 `2024-10-06T19:00Z` 편집 10·편집자 7·`is_new_page=True`·`spike_score` 26.46, `edit_z`는 baseline 없어 `None`. **Hormuz 2025-06(기존 문서 경로) 전량 미탐** — `Strait_of_Hormuz` 38 윈도우·총 71편집·시간 최대 **8**, `2025_Iran_threat_of_Strait_of_Hormuz_closure` 8 윈도우·총 17편집·시간 최대 6. 둘 다 `MIN_ABSOLUTE_EDITS=10`을 한 번도 안 넘어 급증 판정 0건. 조회수는 746배 폭증한 구간인데 **편집은 거의 안 늘었다** — 사건 유형에 따라 편집·조회 반응이 자릿수로 다르다. **대조군 오탐 1건** — `Association_football` `2024-10-27T01:00Z` 편집 12·**편집자 1명**·`score` 12.0 이 급증으로 통과(1인 연속 편집). `Association_football`(2025-06) 3 윈도우·`Cat`(2025-06) 0 윈도우는 오탐 없음. ⚠️ `hour_of_week` 슬롯은 주 1회라 28일 창 관측이 **최대 4개** → `sample_days ≤ 4 < MIN_BASELINE_SAMPLE_DAYS=7` 이라 **기존 문서도 항상 `is_thin`** → `EDIT_Z_THRESHOLD`(z≥3) 경로가 한 번도 실행되지 않는다. 🔴 임계·수식은 WP-38 확정 자산이라 여기서 고치지 않았다 — 별건 이슈 | 2026-09-14 |
| 편집자 하한 게이트 (WP-85) | 실덤프 **4개월**(`2025-05`·`2025-06`·`2024-09`·`2024-10`, 1.9 GB)을 1시간 윈도우로 재생. 대상 사건 **12건**(Air_India_Flight_171 · June_2025_Israeli_strikes_on_Iran · June_2025_LA_protests · 2025_shootings_of_Minnesota_legislators · American_strikes_on_Iranian_nuclear_sites · Strait_of_Hormuz · 2025_Iran_threat_of_…_closure · Hurricane_Milton · Liam_Payne · Ratan_Tata · October_2024_Iranian_strikes_against_Israel · Hurricane_Helene) / 대조군 **14건**(상시 편집이 많은 비사건 문서 — `List_of_people_named_Peter`·`Deaths_in_2025`·`Timeline_of_science_fiction`·TV 시즌 등). **현재 설정: 재현율 10/12, 대조군 오탐 395건·14/14 문서.** `editor_count >= 2` 추가 → 오탐 **101건**(74%↓), 재현율 불변. 슬롯을 `hour_of_day` 로도 바꾸면 **57건**(86%↓). 6시간 창까지 가면 재현율 11/12·오탐 40건, `editor>=3` 이면 20건. ⚠️ 창 길이는 스트리밍 `WINDOW_SIZE` 와 같이 움직여야 해 WP-83 선행(이번엔 1시간 유지). 🔴 탐지 240여 건이 **전부 신규 문서 경로**이고 z 경로 탐지는 0건 — 사건 문서는 대개 그 시점에 생성돼 baseline 이 없다. `EDIT_Z_THRESHOLD` 는 사건 탐지가 아니라 상시 편집 문서 오탐에만 관여한다. 스트리밍 `approx_count_distinct` 는 편집자 1~10명에서 정확값과 불일치 0건(게이트로 안전) | 2026-09-15 |
| 편집·조회수 신호 시차 (WP-86) | 사건 **10건**(기존 문서 6·신규 문서 4, 로컬 덤프 4개월 범위 내). 편집은 `detect()` 그대로 1시간 윈도우, 조회수는 AQS per-article 일별 `agent=user` 에 detector 조회수 규칙(z≥3 AND ≥2배). **기존 문서: 조회수 6/6 탐지, 편집 4/6**(`Strait_of_Hormuz`·`Papal_conclave` 미탐, `Hassan_Nasrallah` 조회수 9/19 → 편집 9/28 로 **+9일**). **신규 문서: 편집 4/4 탐지, 조회수 2/4**(`Hurricane_Milton`·`Air_India_Flight_171` 미탐 — 문서가 사건 당일 생겨 **조회수 baseline 이 원리적으로 없다**). 합집합이면 10/10. 같은 날 잡힌 4건은 전부 배수 16~518배의 대형 사건. **대조군 조회수 오탐**: 비사건 문서 14개 × 31일 = 434 문서·일에서 하한 없음 4건 / 하한 100 이상 3건 — 그중 `India` 5/7 은 실제 교전 개시라 오탐 아님. ⚠️ 조회수 절대 하한 부재 확인: `Hurricane_Helene` 이 평소 1~3회/일에서 **8회**로 `z 8.1·8.9배` 통과(진짜 폭증은 9/25 719회부터). 하한 100~500 구간은 나머지 9건 결과가 동일. ⚠️ 편집 baseline 은 월 덤프 경계에서 잘려 신규 문서 경로(더 무른 판정)로 빠지는 쪽 — 편집에 유리하게 잰 값이다. ⚠️ 대조군 목록은 -85 가 쓴 14개와 다르다(그 목록이 저장소에 안 남아 성격만 따라 새로 고름). 근거: `ai/signal-order/RESULT.md` | 2026-09-15 |
| 서버 | t3.xlarge × 2, 4 vCPU / 16 GB / 309 GB | 2026-09-04 |
| GATEWAY 게이트웨이 | `https://llm-gateway.example.com/{원래 호스트}/…` 경로 프록시. OpenAI 임베딩·responses, **Anthropic messages + web_search 서버 도구** 전부 HTTP 200 | 2026-09-07 |
| Clickstream 엣지, 사건 당시(월 dump) | Hormuz(2025-06): 상위는 `Choke_point` n=11,778·`Musandam_Governorate` 9,175 등 배경 지리 문서, 진짜 사건 문서 `2025_Iran_threat_of_Strait_of_Hormuz_closure`는 n=383(264개 중 54위)로 30배 낮음. Milton(2024-10): `2024_Atlantic_hurricane_season` 200,669, 사건 하위 `Tornadoes_of_2024` 8,555. Iran(2026-08): `2026_Iran_war` 3,022~4,226(1,623개 중 3·8위)이나 같은 사건 하위 문서(`Kuwait_in_the_2026_Iran_war` 등)는 n=10까지 깔림. 절대 이동량으로 "같은 이슈"와 "배경 지식"이 안 갈림 — §10 결론 참조 | 2026-09-09 |
| Wikidata 관계 속성, 후보 전수 검사 | 클릭스트림 이웃 전체(Hormuz 231·Milton 421·Iran 1,331개)에 `P31`·`P361`·`P17`·`P131`·`P276` SPARQL 대조. `P17`(국가) 매치 Milton 205/421·Iran 389/1,331 — `Atlanta_Motor_Speedway`·`2003_Bam_earthquake` 등 사건 무관 문서 다수 포함, 오탐률 높음. `P31`도 다른 해협·다른 태풍이 걸려 넓음. `P361`은 Milton 2·Iran 1·Hormuz 0개로 좁아서 안전하나 회수율 바닥. Hormuz 진짜 사건 문서 `2025_Iran_threat_of_Strait_of_Hormuz_closure`는 `claims: {}` — Wikidata 항목이 아직 안 채워짐. 5개 속성 다 게이트로 부적합 → 클러스터링은 급증 동시성으로 전환(§3.2 4번) | 2026-09-09 |
| 생성일 시간 동시성, 후보 전수 검사 | 클릭스트림 이웃(Hormuz 202/230·Milton 366/421·Iran 939/1,331 생성일 조회 성공)을 seed 사건일 기준 윈도우로 필터. Hormuz(±30일, 사건일 06-12): 2개 — `2025_Iran_threat_of_Strait_of_Hormuz_closure`(+11일)·`2025_Iranian_strikes_on_Al_Udeid_Air_Base`(+11일), 둘 다 진짜 같은 사건. Milton(±14일, 사건일 10-05): 6개 — `Hurricane_Helene`(-12)·`Hurricane_Kirk`(-4)·`Tropical_Storm_Nadine`(+14) 등 같은 시즌 동시 발생 태풍, 무관 문서 없음. Iran(±30일, 사건일 02-28): 14개 — `List_of_attacks_during_the_2026_Iran_war`·`2026_Strait_of_Hormuz_crisis`·`Sinking_of_IRIS_Dena` 등 전부 같은 전쟁 관련, 무관 문서 없음. **세 사건 다 창 밖(200·360·925개)에 배경 문서가, 창 안에 사건 관련 문서만 걸림 — Wikidata·Clickstream 절대값보다 훨씬 깨끗함.** 단, 사건 전 생성된 기존 문서가 사건으로 재조명되는 경우(`Mojtaba_Khamenei`, 2009년 생성, Iran과 Clickstream n=17,499)는 이 방법으로 못 잡음 | 2026-09-09 |
| 편집 재급증 비율, 예비 표본 | 사건기간 편집 수 / 동일 길이 직전 기준기간 편집 수. `Mojtaba_Khamenei`(Iran 재조명 예상) 500+ vs 28 = **17.9배**. `Saffir–Simpson_scale`(Milton과 무관 예상) 49 vs 8 = **6.1배**(태풍 시즌 전체가 겹쳐 편집이 몰린 계절성 오염 — 배제 실패 위험). `Hurricane_Katrina` 23 vs 24 = 1.0배·`Persian_Gulf` 21 vs 30 = 0.7배(둘 다 정상 배제). 표본 4개로는 6.1배와 17.9배 사이 문턱값을 못 정함, Wikipedia API rate limit으로 표본 확대 중단. 후속: WP-77 | 2026-09-09 |
| mediawiki_history 적재, enwiki 2025-06 | 원본 `2026-08.enwiki.2025-06.tsv.bz2` 515,334,641 B → rows_read 5,501,827 / events_written 3,361,013 / shard **7**(`shard_records` 500,000) / 산출물 전체(shard + `_manifest.json`) **152,362,627 B** / 변환 **771.1s**. HDFS `/wikipulse/raw/mediawiki_history/wiki=enwiki/year=2025/month=06/` — logical 152,362,627 B(로컬 산출물과 바이트 일치) · physical(replication=2) 304,725,254 B · `fsck` HEALTHY · average block replication 2.0 · under-replicated·missing·corrupt 0. 검증 사례 Strait of Hormuz 2025-06 | 2026-09-10 |
| mediawiki_history 적재, enwiki 2024-10 | 원본 `2026-08.enwiki.2024-10.tsv.bz2` 596,614,108 B → rows_read 6,646,918 / revision 행 5,944,825 / events_written 3,654,769 / shard **8**(`shard_records` 500,000) / 산출물 전체(shard + `_manifest.json`) **164,092,141 B** / 변환 **476.8s** — ⚠️ **직전 다운로드·sha256 검증으로 OS page cache 가 올라간 warm-cache 조건이다. 2025-06 의 771.1s 와 성능을 직접 비교하지 않는다.** HDFS `/wikipulse/raw/mediawiki_history/wiki=enwiki/year=2024/month=10/` — logical 164,092,141 B(로컬 산출물과 바이트 일치) · physical(replication=2) 328,184,282 B · `fsck` HEALTHY · average block replication 2.0 · under-replicated·missing·corrupt 0. 검증 사례 `Hurricane_Milton` ns0 **1,430 events**, event_type **edit 1,430 / new 0**. 관찰: 그중 1,428건이 2024-10-06T18:31:30Z 문서 이동 이후의 본문 문서이고, 나머지 2건은 같은 ns0 제목을 먼저 쓰다 삭제된 별도 단명 문서다 — `(wiki, title)` 계약에서 함께 집계된다 | 2026-09-10 |
| HDFS 환경 | Hadoop **3.5.0**, NameNode 1 + DataNode **2**, `dfs.replication=2`, block size **128 MiB**, Docker 컨테이너로 운영. `dfsadmin` DFS Remaining 603.91 GB — ⚠️ **두 DataNode 물리 여유의 합이다. replication=2 이므로 사용자 관점 논리 저장 가능량은 대략 그 절반(약 302 GB)이다** | 2026-09-10 |

재현 스크립트는 아직 대부분 저장소 밖에 있다 (WP-53). 이슈 대표 텍스트 비교는 `ai/issue-text-poc/`, 신호 시차 측정은 `ai/signal-order/`(+ `data-pipeline/spike/signal_lag.py`)에 들어와 있다.

⚠️ historical 덤프(`Hurricane_Milton`)와 LIVE EventStreams(`Hurricane Milton`)의 문서 제목 표기가 다르다 — `(wiki, title)` canonical 규칙 통일은 **WP-79** 로 분리했다.

## 12. 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v0.1 | 2026-09-07 | 재작성. 노션 판(v0.1~v0.3) 폐기. MVP = 급증(편집+조회수) 클러스터링 → 버블맵(리플레이 포함)·이슈 피드 → LLM 검증 관련 주식 → 종목 상세·회원·관심종목·알림·토론방. 클러스터링은 Clickstream + Wikidata. Kafka·Spark·HDFS·PostgreSQL+pgvector·Claude로 스택 확정. 알고리즘 9종·MapReduce·레이어A/B·HBase·Airflow·MySQL·과거 유사 사례·이슈 유형 분류 제거. 정본을 노션 → GitLab으로 |
