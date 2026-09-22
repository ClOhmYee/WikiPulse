# 기술 명세서 — WikiPulse (WikiPulse)

- 버전: **v0.3 (2026-09-22 정합성 갱신)**
- v0.3 변경: 1일 실제 원본 E2E 결과와 historical 대표 텍스트·스냅샷 증거·상세 API의 시점 계약을 반영했다.
- 2026-09-22 정합성 갱신: 운영 배포·DB V14·파이썬 런타임·HDFS/Kafka 상태를 재실측 값으로 교체했다.
- 상위 문서: [requirements-v0.3.md](requirements-v0.3.md) — **왜 이 컴포넌트가 있는가는 §3.1이 정본이다.** 여기 다시 적지 않는다.
- 이 문서가 다루는 것: **무엇이 어느 버전으로, 어느 서버 어느 포트에서, 어떻게 뜨는가.**
- API는 [api-v0.3.md](api-v0.3.md), 데이터 모델은 [erd-v0.1.md](erd-v0.1.md).
- 구현·검증 순서는 [MVP 구현·검증 실행서](mvp-validation-runbook.md), 2026-09-17 서버 실측·변경 흔적은 [프로젝트 문서](https://github.com/ClOhmYee/WikiPulse)를 따른다.

⚠️ 아래 표에서 **(저장소)** 는 저장소 파일에서 읽은 확정 값, **(계획)** 은 아직 안 깔아본 값이다. 계획값을 실측값처럼 인용하지 말 것.

---

## 1. 스택

### 서비스

| | 버전 | 출처 |
| --- | --- | --- |
| Java | **17** (toolchain) | `backend/build.gradle` (저장소) |
| Spring Boot | **3.5.16** | 같은 파일 (저장소). ~~4.1.1~~ → 3.5.16 다운그레이드 (WP-36) |
| 빌드 | Gradle wrapper | `backend/gradlew` |
| JPA | `spring-boot-starter-data-jpa`, `ddl-auto: validate` | `application.yml` (저장소) |
| React | **19.2.8** / react-dom 19.2.8 | `frontend/package.json` (저장소) |
| 번들러 | **Vite 8.2.2** | 같은 파일 |
| 3D·아이콘 | three 0.185.1, @react-three/fiber 9.7.0, lucide-react 1.37.0 | 같은 파일 — 버블맵용 |
| FE 테스트 | Playwright 1.62.1, axe-core 4.13.0 | 같은 파일 |
| Node | **미정** | `package.json`에 `engines` 없음. Vite 8이 요구하는 하한을 확인하고 고정할 것 |

🔴 **스키마는 백엔드가 소유하지 않는다.** `db/migrations/`가 정본이고 JPA는 `validate`만 한다. 엔티티가 실제 테이블과 어긋나면 기동에서 걸린다.

### 데이터 파이프라인

| | 버전 | 출처 |
| --- | --- | --- |
| Python | 일반 파이프라인·서비스 Spark **3.11.16**, 추가 EC2 edit-stream **3.8.10** | 저장소의 일반 파이프라인은 `python:3.11-slim`, Spark는 `wikipulse-spark:py311` 자체 이미지다. 기본 EC2 `live-cycle`·Spark worker는 3.11.16, 추가 EC2의 공식 Spark 이미지 기반 edit-stream driver만 3.8.10이며 Spark worker는 3.11.16이다 (2026-09-22 실측). `SINK=spike` 경로는 기본 EC2의 3.11 이미지로 구성됐다 |
| Kafka | **3.9.0** (`apache/kafka:3.9.0`) | `data-pipeline/docker-compose.yml` (저장소) — **로컬 개발용** |
| Spark | **3.5.3** (`apache/spark:3.5.3-python3`) | 같은 파일 (저장소) — **로컬 개발용** |
| Kafka 커넥터 | `spark-sql-kafka-0-10_2.12:3.5.3` | 같은 파일 |
| Producer | `confluent-kafka==2.6.1`, `requests==2.32.3` | `data-pipeline/requirements.txt` |
| 종목 적재 | `yfinance==1.7.0`, `psycopg[binary]==3.3.5` | `data-pipeline/stock/requirements.txt` — ~~0.2.51~~ → 1.7.0 (2026-09-10, WP-64). 0.2.51 은 `.history()` 가 현재 Yahoo 에서 깨져 전 종목 0행이 조용히 나온다. 1.7.0 은 `.history()`·`.info` 둘 다 실측 정상 |
| 스키마 테스트 | `pgserver==0.1.4` | `db/requirements-test.txt` — Docker 없이 PG를 띄운다 |
| 테스트 | `pytest==8.3.4` (전 모듈 동일) | |

### 저장·인프라

| | 버전 | 상태 |
| --- | --- | --- |
| PostgreSQL | **17.11** (`pgvector/pgvector:0.8.6-pg17-bookworm`) | 누적 스키마 **V1~V14**가 기본 EC2에 적용됐고 schema version 최댓값 14를 확인했다. Spring Backend가 이 DB에 연결되어 서비스 중이다 (2026-09-22 실측). 테이블별 현재 역할과 상태는 [ERD](erd-v0.1.md)가 정본이다 |
| pgvector | **0.8.6**, 차원 **1536** 고정 | 같은 이미지 (2026-09-17 실측). `vector(1536)` — `text-embedding-3-small` 기준. 모델을 바꾸면 DDL도 바꿔야 한다 |
| Hadoop / HDFS | **3.5.0** (`apache/hadoop:3.5.0`) | NameNode 1 + DataNode 2, 복제 2. `/wikipulse`는 논리 약 1.7 GiB·복제 포함 약 3.5 GiB이며 `mediawiki_history`와 `pageview_complete` 원본이 있다. 고정 MVP 2개월 원본은 아직 완성되지 않았다 (2026-09-22 실측) |
| Spark (EC2) | **3.5.3** (`apache/spark:3.5.3-python3`) | Standalone 2노드, client 모드. 제한 2코어 작업에서 Worker 2대 참여·HDFS Parquet 20행 왕복 통과 (2026-09-17 18:26 KST) |
| Kafka (EC2) | **3.9.0** (`apache/kafka:3.9.0`) | 추가 EC2 KRaft 단일 broker + controller. `wiki.edits` 3파티션과 EventStreams producer·edit-stream 잡이 기동 상태다 (2026-09-22 실측) |
| Redis | **채택 여부 미정** | CLAUDE.md 인프라 절에 이름만 있고 명세 §3.1 컴포넌트 표에는 없다. 지금 필요한 캐시가 무엇인지부터 정할 것 |
| Nginx / 배포 | Nginx **1.30.5** / GitLab CI | Nginx·Frontend·Spring Backend가 기본 EC2에 배포됐다. HTTPS 루트와 snapshots·map·rankings·stocks API가 모두 200을 반환했다 (2026-09-22 실측). 현재 자동 배포 정본은 `.gitlab-ci.yml`이며 Jenkins는 배포 경로가 아니다 |

⚠️ **로컬 개발 스택의 Hadoop 은 3.4.1, EC2 는 3.5.0 이다** (2026-09-17 확인). 서로 다른 환경이라 그 자체로 불일치는 아니지만, 한쪽만 보고 다른 쪽을 "고치지" 말 것. 맞출지 여부는 결정된 바 없다. Kafka(3.9.0)·Spark(3.5.3)는 양쪽이 같다.

### 외부 의존

| | 무엇 | 주의 |
| --- | --- | --- |
| 프로젝트 GATEWAY | `https://llm-gateway.example.com/{원래 호스트}/…` 프록시 | 🔴 키는 저장소에 넣지 않는다. 각자 `.env`. |
| OpenAI 임베딩 | `text-embedding-3-small` (1536차원) | GATEWAY 경유. `Authorization: Bearer` |
| Anthropic | `/v1/messages` + `web_search_20250305` | GATEWAY 경유. `x-api-key`. 중계 실동작 확인 (2026-09-07) |
| Wikimedia | EventStreams SSE, `other/pageviews` 시간별 덤프, `pageview_complete` 일별 user 덤프, Clickstream | 운영 조회수 최종 관문은 시간별 덤프. 일별 user는 품질 검증. AQS 일별 API는 PoC용만. ⚠️ **연락처 없는 User-Agent는 차단된다.** `CONTACT_EMAIL` 필수 |
| GDELT 2.0 GKG | 15분 파일 | ~~2025-06-13~07-04~~ → **2025-06-14 18:00~07-02 02:00 UTC 결손**(경계 이분 탐색 재확인, 2026-09-16, `docs/requirements-v0.3.md` §11) |
| yfinance | `longBusinessSummary`, 일봉 | 비공식 API. 스로틀·스키마 변경 리스크 |
| SEC / NASDAQ Trader | 종목 마스터 | ⚠️ Wikidata로 티커를 받지 말 것 (`wdt:P249` 40건 함정) |

---

## 2. 저장소 레이아웃

```
backend/        Spring Boot. REST API (io.wikipulse.backend)
frontend/       React + Vite. 버블맵·피드·종목 상세
db/             PostgreSQL 스키마 정본 + pgserver 기반 스키마 테스트
data-pipeline/  producer/  EventStreams SSE → Kafka
                streaming/ Spark Structured Streaming (윈도우 집계)
                spike/     급증 판정 수식 + 28일 기준선
                stock/     종목 마스터·설명·임베딩 적재
                docker-compose.yml  로컬 Kafka + Spark
ai/             AI 파트 실험 코드 (issue-text-poc, stock-text-poc)
docs/           명세·API·ERD·기술·협업 규칙
```

모듈 경계는 **실행 단위**다. `backend`는 JVM 한 덩이, `data-pipeline` 하위는 각각 따로 뜨는 파이썬 잡, `db`는 아무것도 실행하지 않는 스키마 소유자다. `ai/`는 서비스 코드가 아니라 명세 근거를 만든 실험이다 — 파이프라인이 여기를 import하지 않는다.

---

## 3. 배포 토폴로지

두 대 다 HDFS DataNode + Spark Worker다 (명세 §7).

```
service.example.com   (기본, 서비스)      data.example.com  (추가, 데이터)
  Nginx                                    Kafka broker
  Spring Boot                              Spark Master
  PostgreSQL + pgvector                    HDFS NameNode
  HDFS DataNode / Spark Worker             HDFS DataNode / Spark Worker
```

각 대 4 vCPU / 16 GB / 309 GB, Ubuntu 24.04 (2026-09-04 SSH 실측).

⚠️ **RAM 16 GB에 데몬을 다 올리면 Spark executor 몫은 8 GB 안팎이다.** 두 대의 배분 기준은 아직 안 정했다 (명세 §10).
⚠️ **t3는 버스트형이다.** Streaming을 24시간 돌리면 CPU 크레딧이 소진되고 코어당 40%로 떨어진다. 올린 뒤 하루 CPU 그래프를 본다.
🔴 **`ufw`는 항상 enable** (프로젝트 지시). 포트는 `ufw allow`로 개별 개방한다.

### 포트

| 포트 | 무엇 | |
| --- | --- | --- |
| 5432 | PostgreSQL | (계획) 기본 EC2. 외부 비공개 |
| 8080 | Spring Boot | (계획) Nginx 뒤 |
| 9092 / 29092 | Kafka (호스트 / 컨테이너 내부) | (저장소) 로컬 compose 기준 |
| 9093 | Kafka KRaft controller | (저장소) |
| 5174 / 4174 | Vite dev / preview | (저장소) `package.json` |

⚠️ **로컬에서 Kafka UI(8080)와 Spring Boot(8080)가 부딪힌다.** compose의 `ui` 프로파일은 기본으로 안 뜨지만, 둘을 같이 띄우려면 한쪽 포트를 바꿔야 한다.

#### HDFS·Spark (EC2 실물, 2026-09-17 실측)

| 포트 | 무엇 | 어디 | 인바운드 허용 |
| --- | --- | --- | --- |
| 8020 | HDFS NameNode RPC | 추가 EC2 | 기본 → 추가 |
| 9866 / 9867 | DataNode 전송 / IPC | 양쪽 | 서로 |
| 9870 / 9864 | NameNode / DataNode 웹 UI | 각 서버 | 외부 차단 |
| 7077 | Spark Master RPC | 추가 EC2 | 기본 → 추가 |
| 7078 | Spark Worker RPC | 양쪽 | Master 쪽 → 각 Worker |
| 7079 / 7080 | Driver RPC / BlockManager | 추가 EC2 (Driver 위치) | 기본 → 추가 |
| 7100 | Executor BlockManager | 양쪽 | 서로 |
| 18080 / 18081 / 4040 | Master UI / Worker UI / 앱 UI | 각 서버 | 외부 차단. SSH 터널로 접근 |

⚠️ **executor 의 RPC 포트는 임의 포트지만 인바운드로 열 필요가 없다** (2026-09-17 실측). Netty RPC 가 executor → Driver 로 먼저 맺은 연결을 되쓴다. 기본 EC2 Worker 는 **7078·7100 두 개만** 열린 상태에서 2노드 분산 실행이 통과했다. 넓게 열지 말 것.

🔴 **Driver 는 추가 EC2 에서만 돈다.** 기본 EC2 에 7079·7080·4040 을 똑같이 열지 않는다.

⚠️ **18080 을 Master UI 로 쓰고 있다.** History Server 기본 포트와 같아 나중에 충돌한다.

⚠️ **동시 Spark 애플리케이션 1개 기준이다.** 고정 포트 + `spark.port.maxRetries 0` 이라 병렬 제출은 충돌한다.

---

## 4. 실행

⚠️ **개인 절대경로를 여기 박지 말 것.** 팀원마다 파이썬·도구 설치 위치가 다르다. 아래는 전부 저장소 루트 기준 상대경로다.

```bash
# 백엔드
cd backend && ./gradlew bootRun          # DATABASE_URL / DB_USER / DB_PASSWORD 환경변수
cd backend && ./gradlew test

# 프론트엔드
cd frontend && npm ci && npm run dev     # http://127.0.0.1:5174
cd frontend && npm run test:e2e          # Playwright

# 스키마 (Docker 불필요 — pgserver 가 PG 를 번들로 띄운다)
cd db
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-test.txt
.venv/Scripts/python.exe -m pytest

# 파이프라인 (로컬 Kafka + Spark)
cd data-pipeline
cp .env.example .env                     # CONTACT_EMAIL 필수
docker compose up -d kafka
python -m producer.wiki_edits            # SSE → Kafka
docker compose run --rm spark            # 윈도우 집계 잡
```

`.venv/Scripts/`는 Windows 경로다. macOS·Linux는 `.venv/bin/`.

### 환경변수

`.env`는 gitignore 대상이다. 각 모듈의 `.env.example`이 목록의 정본이다.

| 어디 | 무엇 |
| --- | --- |
| `backend` | `DATABASE_URL`, `DB_USER`, `DB_PASSWORD`, `LLM_GATEWAY_KEY`, `WIKIPULSE_MATCHING_SCHEDULER_ENABLED`, `WIKIPULSE_MATCHING_VERIFICATION_ENABLED` |
| `frontend` | `VITE_DATA_SOURCE` (`mock`/`api`), `VITE_API_BASE_URL` |
| `data-pipeline` | `CONTACT_EMAIL`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC`, `WIKIS`, `WINDOW_SIZE`, `SLIDE_SIZE`, `STARTING_OFFSETS` |
| GATEWAY 쓰는 곳 | GATEWAY API 키 — 🔴 저장소에 넣지 않는다 |

---

## 5. 확정된 파라미터

명세 §6·§11에서 실측으로 확정된 것만. 나머지는 6절.

| | 값 | 근거 |
| --- | --- | --- |
| Kafka 토픽 | `wiki.edits`, 보존 **168시간(7일)** | 명세 §5 재처리 창 |
| 대상 위키 | `enwiki` (namespace 0) | 전 위키는 초당 31건, enwiki 2건 |
| 편집 윈도우 | 1시간 / 5분 슬라이드 (기본값) | 실데이터 붙은 뒤 튜닝 |
| 이슈 1차 관문 | `enwiki` namespace 0에서 봇이 아닌 편집 **1건 이상** | 팀 결정 2026-09-17, WP-118 |
| 조회수 2차·최종 관문 | 생성 28일 이상: 직전 28일 대비 z ≥ 3 **AND** 2배 이상 **AND** 100회 이상. 생성 28일 미만: 생성 이후 자료를 즉시 사용하며 통계 산출 불가/기준 0이면 100회 이상 | 명세 §3.2 |
| 운영 조회수 소스 | `other/pageviews` 시간별 덤프. `pageview_complete` 일별 `agent=user`는 품질 검증용 병행 보존. AQS 일별 API는 LIVE 최종 관문에서 제외 | ~~약 1시간~~ → **약 2시간**(윈도우 끝 기준 125~153분 실측) 지연을 받아들이고 품질 우선 |
| 처리 지연 목표 | 사건 발생 후 통상 1~2시간 이내 최종 노출, 시간별 원본 도착 후 내부 처리 15분 이내 | 지연 상한이 아니라 MVP 운영 목표. 미도착은 후보 대기 |
| 조회수 기준선 | 생성 28일 이상은 직전 28일, 미만은 생성 시각부터 현재 직전까지 | `page_baseline`; 짧은 표본 구현은 WP-118 |
| 문서 생성 기준 시각 | 리플레이: snapshot/month 전체를 보강한 뒤 `page_first_edit_timestamp` 우선, 결측이면 미래가 아닌 `page_creation_timestamp`. 현재 API backfill 금지. LIVE: MediaWiki 최초 리비전 시각(`prop=revisions`, `rvdir=newer`, `rvlimit=1`). `wiki_page.first_seen`으로 대체 금지 | 호환 컬럼 `wiki_page.page_created_at`·덤프/API 추출·멱등 sink와 실제 2025-06-12 로컬 E2E 완료. 당일 대기 73 → 월 전체 60, [전수 감사](validation/2026-09-18-creation-pending-audit.md). 운영 호출 스케줄링은 미연결 |
| 🔴 운영 재실행 가드 | `persist_snapshot` 은 downstream(`issue_report`·`cluster_stock`·`cluster_org_mention`·`issue_summary_attempt`·`comment_thread`)이 있으면 **기본 중단**. `--allow-downstream-delete` 명시해야 진행, `--dry-run` 은 삭제 예정 규모만 세고 쓰지 않는다 | WP-161. `DELETE FROM issue_cluster` 가 CASCADE 로 GATEWAY·GDELT 산출물까지 지운다. 중단 시 종료 코드 3 + 전체 롤백 |
| 🔴 클러스터링 정본 1단계 (ROOT SELECTION) | `spike` 후보 → `views` DESC(NULL 뒤, 동점은 `page_id` ASC) 로 **시점당 20**, 같은 `page_id` 는 **24h 되돌아보는 창** 안에서 재선택 금지. 쿨다운에 걸리면 자리를 비우지 않고 다음 후보가 채운다 | WP-137 `cluster/root_selection.py`. 🔴 정렬에 `spike_score` 금지 — 경로마다 단위가 달라 통계 통과 369건이 미검증 162,406건 아래로 밀린다. 🔴 이 단계가 없으면 CORE 가 giant 를 만든다(전량 162,775 root → max 63 · 20+ giant 59, 2026-09-22 실측) |
| 🔴 클러스터링 정본 2단계 (CORE) | 같은 스냅샷 root + strict as-of direct link(wikitext 리터럴 `[[...]]`, 한 방향) → connected component → sym focus **τ=0.005** → **D2**(떼어 낼 조각 2개 이상일 때만) directional bridge 억제. component 자체가 issue cluster, 그 안의 root 가 cluster_member | WP-161, 2026-09-22 확정. `cluster/rootgraph.py`. 고정 2개월 실측: 스냅샷 1,104 · root 22,080 · component 19,432 (1:17,569 / 2:1,461 / 3~4:322 / 5~7:57 / 8~12:20 / 13+:3 / max 16 / 20+ giant 0) |
| CORE as-of 링크 앵커 | `spike.max_rev_id`(V9) → `action=parse&oldid=…&prop=wikitext`. replay·LIVE 동일 계약. 캐시는 `page_asof_links`(V12), revision 단위라 만료 없음 | 🔴 `parse.links` 금지 — 옛 revision 을 렌더해도 템플릿은 현재 판이라 navbox 링크가 누수된다. `max_rev_id` 없으면 현재 판 폴백 금지, singleton |
| CORE 링크 비교 정규화 | `cluster.asof_links.link_key` = 밑줄→공백·연속 축약·trim **+ 첫 글자 대문자** | 🔴 `producer.normalize.canonical_title` 과 다르다. 링크 타깃은 사람이 쓴 문자열이라 MediaWiki 가 첫 글자를 대문자로 해석한다(`[[eBay]]`→`EBay`). 비교 양쪽에 같은 함수를 걸어야 하며, 저장 제목은 계속 `canonical_title` 계약 |
| 멤버 확장 레이어 | **기본 OFF** (`build_snapshot(expansion=False)`). 켜면 CORE component 의 각 root 에 Clickstream 이웃이 붙는다 | 보존만 한다. 켜면 위 분포가 보장되지 않고, non-root 멤버는 `window_start/end` 가 없어 펄스맵 계약(`contract.js` metric window)에 걸린다 — 2026-09-22 preview 에서 baseline 5,120 클러스터 렌더 탈락 실측 |
| 클러스터 멤버 역할 | 루트 씨드=최종 급증 통과 문서, 추가 씨드=Clickstream 이웃 중 생성일 시간 동시성 통과 새 사건 문서, 비-seed=기존 문서 중 재급증 비율 ≥5 AND 사건기간 편집 ≥20. 공통으로 UTC 실제 생성 시각 `<= snapshot_ts` | WP-51·77. 현재 `cluster/snapshot.py`는 시점 상한은 적용하지만 추가 씨드 승격·비-seed 재급증은 미구현 |
| Clickstream 관계 가중치 | `n` 100%. 스냅샷 월보다 앞선 검증 완료본 중 직전 월 우선, 없으면 가장 최근 검증 완료 월(통상 전전월). 서로 다른 월을 합산하지 않음 | 당월·미래 데이터 기간은 제외하며 로컬 적재 시각은 event-time 상한이 아님. 생성일·재급증 조건은 멤버 편입 관문이고 가중치에 혼합하지 않음. Wikidata 보조 간선은 `observed_at <= snapshot_ts`. 새 덤프는 다운로드·스키마·매니페스트 검증 후 교체 |
| 종목 임베딩 텍스트 | `{회사명}. {섹터} — {산업}. {longBusinessSummary}`, 2,000자 상한 | 명세 §6.1 |
| 이슈 대표 텍스트 | `{문서 제목}: {도입부 앞 N문장}` 나열. N = 문서 1개면 6, 2~3개면 4, 4개↑면 2. 2,000자 상한. LIVE=현재 API, replay=`snapshot_ts` 이하 revision 고정 | 현재 API의 historical 폴백 금지, 명세 §6.2 |
| 🔴 파이프라인 내부 텍스트 | **영어** | 한국어로 만들면 코사인이 절반 (0.160 → 0.081) |
| 후보 우선순위 | `BOTH` → `GDELT_ONLY` → `EMBEDDING_ONLY` | 명세 §6.3 |
| 과거/LIVE 범위 | 과거 2026-07-17~09-17 고정, 이후 LIVE 계속 누적. 정규화부터 종목 매칭까지 같은 계약 | 과거=미리 계산한 스냅샷, LIVE=최신 스냅샷 |
| 시점별 재사용 | 점수·멤버는 시점별 스냅샷. 요약·검증 종목은 `issue_key` 단위로 재사용하되 조회 시각까지 완료된 결과만 노출 | 미래 결과의 과거 소급 노출 금지, WP-119·120 |
| 멤버 증거 고정 | `edit_count/views/edit_baseline/view_baseline/spike_score/size_score/window_start/end`를 판정 시점에 `cluster_member`로 복사 | API는 최신 원시 지표로 보충하지 않음, 명세 §5.2 |
| `completeness` | `complete`=최종 조회수 판정 완료, `pending`=입력 대기, `unavailable`=원본 없음 | `view_ratio IS NULL`만으로 판정 금지. 신규 문서 기준선 0 경로도 완료되면 `complete` |
| 처리 실패 의미 | 조회수 미도착=후보 대기, GATEWAY/GDELT 실패=재시도/처리 중, 전체 완료 뒤 통과 종목 없음=정상 0건 | 빈 배열로 장애를 숨기지 않음 |
| Spark Worker 자원 | 2 코어 · 4 g × 2대. `spark.cores.max 4` · `executor.cores 2` · `executor.memory 2g` | 2026-09-17 기동값 |
| Spark HDFS 기본 경로 | `/wikipulse/spark` | WP-27 |

---

## 6. 결정 현황 (남은 항목은 실측 날짜와 함께 갱신한다)

**설치·버전**

- ~~PostgreSQL·Hadoop·Spark·Kafka의 EC2 설치 버전 (-26 ~ -29)~~ → **전부 확정** (2026-09-17, §1)
- Nginx·Jenkins·HTTPS·배포 방식 — 기본 EC2 서비스 스택 미설치
- Node 버전 고정
- 마이그레이션 도구 (Flyway / Liquibase)
- Redis를 쓰는가 — 쓴다면 무엇을 캐시하는가
- 배포 방식 (Jenkins / Docker Compose / 수동), Nginx 설정, HTTPS

**확정된 설계 변경**

- ~~인증 방식·WebSocket·알림 전달 수단~~ → 회원·관심종목·알림·토론과 함께 MVP 범위에서 제외 (2026-09-17, WP-104)
- ~~Top-K의 K, 3등급 검증 발동 기준 N, 노출 개수 상한~~ → **K=20/10, N=2, 제품 노출 상한 없음으로 확정** (2026-09-14, WP-22)
- ~~이슈 임베딩 저장 위치~~ → **저장하지 않고 후보 생성 시 계산하며, 판정 결과는 `(issue_key, ticker, prompt_version)`으로 재사용** (2026-09-16, WP-49)
- ~~Clickstream 엣지 최소 이동량·Wikidata 관계 종류~~ → **별도 Clickstream 문턱 없음, Wikidata 멤버 편입 관문 폐기** (2026-09-09, WP-51). 포함 여부는 생성일 시간 동시성·사건기간 편집 재급증으로 판정. 이미 포함된 멤버 사이 Wikidata 화면 보조 간선 계약은 남지만 소스 배선은 없음
- ~~Clickstream 70% + 실시간 관계 신호 30% 혼합~~ → **사용하지 않고 이동량 `n` 100%로 확정** (2026-09-17). 직전 월 완료본 우선, 미공개·검증 실패 시 최신 검증 완료 월 유지, 월간 합산 없음
- ~~LIVE 조회수 최종 관문 소스~~ → **`other/pageviews` 시간별 덤프**로 확정. `pageview_complete` 일별 user는 품질 검증, AQS 일별 API는 운영 관문에서 제외 (2026-09-17, WP-118)
- ~~리플레이 범위·MVP 원본 보존~~ → **2026-07-17~09-17 고정 2개월**, 실제 공통 파이프라인 재생·E2E 검증 완료 전 편집·시간별/일별 조회수·GDELT·Clickstream 원본 삭제 금지
- ~~replay 대표 텍스트를 현재 Wikipedia 도입부로 읽음~~ → **`page_intro`에서 `snapshot_ts` 이하 마지막 revision을 읽도록 구현** (2026-09-18, WP-129, V8). 현재 도입부 폴백은 금지하며 EC2·실제 replay 재검증은 하지 않음
- ~~spike 조회수·기준선이 `cluster_member`에 전달되지 않고 상세 API가 최신 원시 행을 읽음~~ → **판정 수치 전달·`completeness` 결정·상세 고정값 조회 구현** (2026-09-18, WP-129, V7). `max_rev_id`·`last_edit_ts` 감사 필드도 V9로 추가. 로컬 회귀 테스트만 완료하고 EC2에서는 검증하지 않음
- ~~실시간 이슈 요약 writer·상태 전이 미구현~~ → **백엔드 구현·EC2 실제 GATEWAY 실행 완료** (WP-119). 현재 워커는 꺼져 있고 재클러스터링 뒤 `issue_report`는 0건 (2026-09-22)
- ~~화면이 영문 raw title만 표시~~ → **ko.wikipedia 표시명 구현** (2026-09-22, WP-205, V15). `wiki_page.title_ko`를 `cluster_member` 편입 enwiki 문서에 한해 `prop=langlinks&lllang=ko`로 1회 조회(50개/요청)해 채우고, `title`(영문)은 그대로 둔다. LIVE·replay 공통. 워커 `wikipulse.page-title.enabled` 기본 꺼짐이라 켜기 전에는 전량 영문이며 EC2 실행은 0회임. 리다이렉트 제목은 ko를 붙이지 않고 영문 폴백(정밀 매핑은 후속)

**남은 설계·검증**

- 문서 최초 revision 시각의 LIVE 수집 배선(WP-118). 저장 필드는 구현 완료했으며 `first_seen`은 시스템 최초 관측 시각이라 대체할 수 없음
- 시간별 조회수 원본 미도착 후보 보관·재평가와 원본 도착 후 15분 이내 처리 계측(WP-118)
- ~~Docker Compose에서 GATEWAY 키·후보 생성/검증 워커 설정 전달~~ → **완료** (2026-09-20, WP-142)
- 클러스터 → GKG 검색 술어는 구현됨(WP-148). GKG lift 집계 자동 실행은 남아 있음
- 요약 worker의 실제 GATEWAY·상태 전이는 EC2에서 실행했다. 반복 거절 방지와 일일 호출 상한도 적용했지만 현재 워커는 운영 안전을 위해 꺼져 있음
- ~~같은 `issue_key` 결과 재사용이 미래 스냅샷을 과거에 복사할 수 있었음~~ → 요약·후보·검증 재사용과 비용 상한 면제를 원본 `snapshot_ts <=` 대상 `snapshot_ts`로 제한하고 순서 역전 회귀 테스트를 추가함(WP-208). `generated_at`·`verified_at`은 backfill 처리 시각이라 event-time 상한으로 사용하지 않음
- 2026-07-17~09-17 실제 원본 공통 리플레이로 1,112개 수작업 시드를 교체하고 이후 LIVE 누적까지 연결(WP-120)
- ~~종목 상세 가격 API·FE 연결~~ → **완료** (2026-09-18, WP-124). 시연 44종목 55,176행을 적재하고 차트·이슈 마커 E2E를 검증함

**운영**

- 2노드 RAM 배분, t3 CPU 크레딧 실측
- `page_edit_window`와 2026-09-18 이후 LIVE 원본의 장기 보존 기간. 고정 MVP 2개월 원본은 실제 재생 검증 전 삭제 금지로 확정
