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
3. **이슈 피드** — 카드/리스트 형식. 버블맵과 토글로 전환
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
2. Spark Streaming이 토픽을 읽어 문서별 편집 수를 슬라이딩 윈도우로 집계하고, PostgreSQL의 28일 기준선과 비교해 편집 급증 문서를 뽑는다. 봇·1인 반복·되돌리기는 여기서 거른다.
3. 편집 급증 문서에 대해 Pageviews API로 **편집 전후 조회수**를 조회하고, 기준선 대비 급등한 문서만 통과시킨다. 편집만 튀고 조회수가 안 튀면 편집 전쟁·봇·정리 작업으로 보고 버린다.
4. 통과 문서들을 **클러스터** = 이슈로 묶는다. 묶는 근거 둘: Wikipedia Clickstream(전월 문서 간 이동량 — 사용자가 A에서 B로 실제로 넘어간 횟수)으로 엣지 가중치를 주고, Wikidata API로 항목 간 관계(같은 사건·같은 지역·상위 개념)를 확인해 약한 엣지를 자른다. 클러스터별 급등도(`pulse_score`)는 편집 급등과 조회수 급등을 합쳐 계산한다.
5. 클러스터를 텍스트로 요약해 임베딩하고, pgvector에서 종목 임베딩과 코사인 Top-K를 뽑는다.
6. LLM이 Top-K 각각에 근거 경로(직접 언급 / 제품·산업 관계 / 공급망·고객·경쟁 / 지역 노출)를 생성할 수 있는지 판정한다. GDELT에서 뽑은 이슈 관련 기관명·테마를 컨텍스트로 준다 (RAG). 통과한 것을 유사도 순으로 낸다. 노출 개수 제한은 아직 없다.
7. 이슈 + 종목 + 근거 문장을 PostgreSQL에 쓰고 API가 낸다. 피드 상태는 **감지됨 → 검증 중 → 확정** 3단계 — 2~4번은 초~분 단위, 6번 LLM은 분 단위라 그 차이를 사용자에게 그대로 보여준다.
8. **리플레이**: 과거 덤프(`mediawiki_history`·`pageview_complete`·해당 월 Clickstream)를 HDFS에 올리고 Spark 배치가 2~4번을 과거 시점으로 돌려 `cluster_snapshot(snapshot_ts, …)`을 미리 계산해 PostgreSQL에 넣는다. 버블맵 시간 슬라이더가 이 스냅샷을 읽는다. 원본 덤프는 계산 후 폐기해도 된다.
9. **종목 상세**: yfinance 일봉을 PostgreSQL에 적재. 그래프 위에 그 종목이 걸린 이슈의 발생 시점을 표시하고, 아래에 해당 이슈 피드를 붙인다.
10. **회원·관심종목·알림·토론방**: PostgreSQL 테이블. 관심종목에 새 이슈가 붙으면 알림(수단 미정, 10번). 토론방은 이슈별 WebSocket 채널.

## 4. 데이터 소스

| 구분 | 소스 | 용도 | 실측 (11번) |
| --- | --- | --- | --- |
| 편집 이벤트 | Wikipedia EventStreams `recentchange` | 급증 감지 | 전체 31/s, enwiki 2/s, 1.5 KB/건 |
| 조회수 | Wikipedia Pageviews API / `pageview_complete` 덤프 | 28일 기준선, **편집 급증의 2차 판정** (편집 전후 조회수 급등) | 일별 user 677 MB bz2 |
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

### 6.1 이슈 대표 텍스트 (2026-09-08 확정)

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

~~LLM 한 번 호출해 이슈를 요약한 뒤 그것을 임베딩~~ → **채택하지 않는다** (2026-09-08). 랭킹 품질이 나열 방식과 동률인데 호출 1회와 4~6초가 붙고, 조용히 틀리는 실패 모드 셋이 실측됐다: ① 프롬프트 언어를 따라가 한국어 요약이 나오면 코사인 반토막 ② 정보가 부족하면 "설명할 수 없다"는 거부 문장이 그대로 임베딩됨 ③ 입력에 없는 사건을 지어냄. 근거는 `test/issue-text-poc/RESULT.md`.

### 6.2 후보 생성과 검증

- **후보 (recall)** — 두 경로의 합집합:
  - (a) 이슈 임베딩 ↔ 종목 임베딩 코사인 Top-K. pgvector 한 쿼리. 설명서에 그 리스크가 적힌 종목을 잡는다 (보험사, 에너지 인프라)
  - (b) GDELT 동시 출현 lift 상위. 이슈 기간 기사에서 기관명을 뽑아 종목 마스터와 조인. 설명엔 없는 2차 효과를 잡는다 (플로리다 전력, 발전기, 항공 결항)
  - 둘의 교집합은 작다 — Milton K=10에서 1개, K=30에서 3개 (11번). 합집합이 맞다. 다만 **(b)가 주력이고 (a)는 보충**이다: 사건 서술과 사업 설명은 같은 종류의 텍스트가 아니라 임베딩 코사인이 0.2 안팎으로 낮고, 정답(NEE·Lennar·Generac)과 노이즈(Monster Beverage·Intel)가 섞여 나온다. (a)의 몫은 기사에 아직 이름이 안 나온 첫 시간대와 기업 문서 이슈다
- **우선순위 — 교집합 먼저**:
  1. **(a) ∩ (b)** — 두 신호가 일치. 먼저 검증하고 통과하면 최상단. Milton K=10 교집합 NEE, K=30 NEE·Generac·Exxon — K가 커지면 노이즈도 들어오므로 LLM 면제는 아니다
  2. **(b) − (a)** — GDELT 단독. 정답 밀도가 높다
  3. **(a) − (b)** — 임베딩 단독. **1·2등급 통과가 N개 미만일 때만** 검증한다. 임베딩 노이즈(Monster Beverage·Intel)가 대부분 여기 있어서 LLM까지 안 간다
- **검증 (precision)**: LLM이 후보마다 근거 경로를 만들 수 있는지 판정. 못 만들면 버린다. 고정 유사도 컷도, 노출 개수 상한도 아직 없다. N은 미정 (10번).
- **컨텍스트 (RAG)**: (b)에서 나온 기관명 상위와 테마를 LLM에 같이 준다. 뉴스 동시 출현이 인과 경로의 근거가 된다.

비용: 이슈당 LLM 호출 = |1등급| + |2등급| (+ 3등급 조건부). K를 10씩 잡으면 최대 20회, 보통 10회 안팎. 이슈 수에 비례하고 사용자 수와 무관하다.

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
- [ ] 급증 판정 수식 — 편집: 윈도우 길이, 기준선 산출법(동시간대 EWMA?), 임계치(z-score + 최소 절대 편집수). 조회수: "편집 전후"의 창 길이(전 N시간 / 후 M시간), 급등 임계치. Pageviews API는 시간 단위라 지연이 최대 1시간 — 2차 판정 시점을 언제로 잡을지
- [ ] 클러스터링 파라미터 — Clickstream 엣지 최소 이동량, Wikidata 관계 종류(어느 속성을 "같은 사건"으로 볼지), 클러스터 최소·최대 크기
- [ ] 리플레이 시연 구간 — 어느 사건·며칠. GDELT 결손(2025-06-13~07-04) 밖에서
- [ ] Top-K의 K (임베딩·GDELT 각각), 3등급 검증 발동 기준 N, 노출 개수 상한 — 지금은 없음. 정답셋 결과 보고
- [ ] 임베딩 교집합 재측정 — 로컬 MiniLM이 아니라 실제 쓸 `text-embedding-3-small`로, 이슈 텍스트는 실시간 클러스터 요약으로
- [ ] GDELT 기관명 → 종목 정규화 — 부분문자열 매칭은 News Corp·Meta 같은 오탐이 남. 별칭 테이블 필요
- [ ] 알림 수단 — 웹 내 배지 / 브라우저 푸시 / 이메일
- [ ] 토론방 — 실시간(WebSocket) 필수인지, 모더레이션
- [ ] GDELT·리플레이 덤프 보존 기간 — 디스크 307 GB × 2, GDELT 1년 zip 100~230 GB
- [ ] 2노드 RAM 배분 — 서비스 박스에 DataNode·Worker를 얹을 때 Spring·PG와 나누는 기준
- [ ] 매칭 정확도 정답셋 — 기업 문서(IBM 07-14, PayPal 08-28)뿐 아니라 사건 문서 최소 1건 (Hurricane Milton 2024-10-10 후보)
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
| 이슈 대표 텍스트 방식 비교 | 클러스터 3건(Milton·Hormuz·Nvidia) × 종목 32개(정답 20 + 노이즈 12). 대표문서 도입부 / 제목+요약 나열 / LLM 요약 / 문서수 적응 나열의 정답 평균순위가 각각 10.6·10.5·11.0·10.5(Milton), 6.6·7.8·6.9·7.8(Hormuz), 4.0·5.0·3.3·4.0(Nvidia)로 **사실상 동률**. LLM 요약은 한국어로 생성 시 정답 평균 코사인 0.160 → 0.081로 반토막, 단일 문서에서 거부 응답이 그대로 임베딩됨. 정답-노이즈 분리도는 사건형 +0.05~0.15 / 기업형 +0.26 — 임베딩 단독이 사건형에 약하다는 §6 전제와 일치 | 2026-09-08 |
| 위키 링크 그래프 → 상장기업 | Hormuz 1,358 이웃 중 0 · Milton 3 · Iran 4 · Nvidia 507(목록 문서 노이즈) | 2026-09-04 |
| Wikidata 티커 | `wdt:P249` 40건 / `p:P414 → pq:P249` 15,875건 / NYSE+NASDAQ 3,905 | 2026-09-04 |
| Wikimedia 덤프 | pageview_complete 일 user 677 MB bz2 · mediawiki_history enwiki 월 520~585 MB · clickstream enwiki 월 471 MB | 2026-09-04 |
| 서버 | t3.xlarge × 2, 4 vCPU / 16 GB / 309 GB | 2026-09-04 |
| GATEWAY 게이트웨이 | `https://llm-gateway.example.com/{원래 호스트}/…` 경로 프록시. OpenAI 임베딩·responses, **Anthropic messages + web_search 서버 도구** 전부 HTTP 200 | 2026-09-07 |

재현 스크립트는 아직 대부분 저장소 밖에 있다 (WP-53). 이슈 대표 텍스트 비교만 `test/issue-text-poc/`에 들어와 있다.

## 12. 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v0.1 | 2026-09-07 | 재작성. 노션 판(v0.1~v0.3) 폐기. MVP = 급증(편집+조회수) 클러스터링 → 버블맵(리플레이 포함)·이슈 피드 → LLM 검증 관련 주식 → 종목 상세·회원·관심종목·알림·토론방. 클러스터링은 Clickstream + Wikidata. Kafka·Spark·HDFS·PostgreSQL+pgvector·Claude로 스택 확정. 알고리즘 9종·MapReduce·레이어A/B·HBase·Airflow·MySQL·과거 유사 사례·이슈 유형 분류 제거. 정본을 노션 → GitLab으로 |
