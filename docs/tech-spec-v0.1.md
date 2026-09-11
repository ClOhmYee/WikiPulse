# 기술 명세서 — WikiPulse (WikiPulse)

- 버전: **v0.1 (2026-09-08)**
- 상위 문서: [requirements-v0.1.md](requirements-v0.1.md) — **왜 이 컴포넌트가 있는가는 §3.1이 정본이다.** 여기 다시 적지 않는다.
- 이 문서가 다루는 것: **무엇이 어느 버전으로, 어느 서버 어느 포트에서, 어떻게 뜨는가.**
- API는 [api-v0.1.md](api-v0.1.md), 데이터 모델은 [erd-v0.1.md](erd-v0.1.md).

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
| Python | **3.11** (팀 표준) | 저장소 스크립트에 버전 표기는 아직 없다 |
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
| PostgreSQL | **미정** | 아직 설치 전 (WP-29). pgvector가 붙는 버전으로 고른다 |
| pgvector | 차원 **1536** 고정 | `vector(1536)` — `text-embedding-3-small` 기준. 모델을 바꾸면 DDL도 바꿔야 한다 |
| Hadoop / HDFS | **미정** | 아직 설치 전 (WP-28). 프로젝트 안내는 3.5.0 SingleCluster 가이드 |
| Spark (EC2) | **미정** | 아직 설치 전 (WP-27). 로컬 3.5.3과 맞추는 편이 안전 |
| Kafka (EC2) | **미정** | 아직 설치 전 (WP-26) |
| Redis | **채택 여부 미정** | CLAUDE.md 인프라 절에 이름만 있고 명세 §3.1 컴포넌트 표에는 없다. 지금 필요한 캐시가 무엇인지부터 정할 것 |
| Nginx / Jenkins | **미정** | 배포 방식 미정 |

### 외부 의존

| | 무엇 | 주의 |
| --- | --- | --- |
| 프로젝트 GATEWAY | `https://llm-gateway.example.com/{원래 호스트}/…` 프록시 | 🔴 키는 저장소에 넣지 않는다. 각자 `.env`. |
| OpenAI 임베딩 | `text-embedding-3-small` (1536차원) | GATEWAY 경유. `Authorization: Bearer` |
| Anthropic | `/v1/messages` + `web_search_20250305` | GATEWAY 경유. `x-api-key`. 중계 실동작 확인 (2026-09-07) |
| Wikimedia | EventStreams SSE, Pageviews API, 덤프, Clickstream | ⚠️ **연락처 없는 User-Agent는 차단된다.** `CONTACT_EMAIL` 필수 |
| GDELT 2.0 GKG | 15분 파일 | 2025-06-13~07-04 전 구간 404 (결손) |
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

HDFS·Spark 포트는 설치 전이라 적지 않는다 — 깔고 나서 실측 날짜와 함께 채운다.

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
| `backend` | `DATABASE_URL`, `DB_USER`, `DB_PASSWORD` |
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
| 급증 판정 | 편집 z ≥ 3 **AND** 절대 편집수 ≥ 10. 신규 문서(baseline 없음)는 절대 편집수만 | 명세 §11 — Hormuz 평상시 최대 z 1.9 / 사건 최소 z 11.2 |
| 조회수 2차 판정 | z ≥ 3 **AND** 2배 이상 | 같은 곳 |
| 기준선 | 28일, 문서 × 요일·시간대(0~167) EWMA | `page_baseline` |
| 종목 임베딩 텍스트 | `{회사명}. {섹터} — {산업}. {longBusinessSummary}`, 2,000자 상한 | 명세 §6.1 |
| 이슈 대표 텍스트 | `{문서 제목}: {도입부 앞 N문장}` 나열. N = 문서 1개면 6, 2~3개면 4, 4개↑면 2. 2,000자 상한 | 명세 §6.2 |
| 🔴 파이프라인 내부 텍스트 | **영어** | 한국어로 만들면 코사인이 절반 (0.160 → 0.081) |
| 후보 우선순위 | `BOTH` → `GDELT_ONLY` → `EMBEDDING_ONLY` | 명세 §6.3 |

---

## 6. 미정 (정해지면 실측 날짜와 함께 이 문서에 적는다)

**설치·버전**

- PostgreSQL·Hadoop·Spark·Kafka의 EC2 설치 버전 (-26 ~ -29)
- Node 버전 고정
- 마이그레이션 도구 (Flyway / Liquibase)
- Redis를 쓰는가 — 쓴다면 무엇을 캐시하는가
- 배포 방식 (Jenkins / Docker Compose / 수동), Nginx 설정, HTTPS

**설계**

- 인증 방식 (자체 로그인 / OAuth) — `member.password_hash`가 nullable인 이유
- WebSocket 필수 여부, 알림 전달 수단 (명세 §10)
- Top-K의 K, 3등급 검증 발동 기준 N, 노출 개수 상한 (-22)
- 이슈 임베딩 저장 위치 (-49, ERD §4)
- 클러스터링 파라미터 — Clickstream 엣지 최소 이동량, Wikidata 관계 종류 (-51)
- LIVE 2차 판정 소스: 시간별 덤프(빠름·봇 미구분) vs 일별 API(느림·정확)

**운영**

- 2노드 RAM 배분, t3 CPU 크레딧 실측
- `page_edit_window` 보존 기간, GDELT·리플레이 덤프 보존 기간
- GATEWAY 키 서비스별 사용 조건 확인갱신 절차 (-52)
