# data-pipeline — 실시간 수집·집계

Wikipedia EventStreams 를 Kafka 로 옮기고, Spark Structured Streaming 이
문서별 편집량을 윈도우 집계한다.

- `WP-30` EventStreams SSE → Kafka `wiki.edits` Producer
- `WP-31` Spark Structured Streaming 골격 — 문서별 편집 윈도우 집계
- `WP-32` GDELT GKG 15분 폴링 → HDFS 적재 Producer — [gdelt/README.md](gdelt/README.md)
- `WP-65` GDELT GKG 기관명 lift 집계 → `cluster_org_mention` Spark 배치 — [gkg/README.md](gkg/README.md)

명세: [docs/requirements-v0.3.md](../docs/requirements-v0.3.md) §3

> 이 폴더엔 서로 다른 잡이 산다. 위 두 개는 위키 편집 실시간 경로(Kafka·Spark),
> `gdelt/` 는 뉴스 원본을 HDFS 에 쌓는 별도 배치성 수집기다. 각각 따로 뜬다.

```
EventStreams (SSE)              Kafka                    Spark Structured Streaming
  recentchange        ──▶   wiki.edits        ──▶   문서별 편집 윈도우 집계
  약 31 events/s            보존 7일                 (wiki, title, window)
  enwiki 약 2/s             키 = wiki:title           → edit_count, editor_count
```

## 왜 Kafka 를 거치나

처리량 때문이 아니다. enwiki 는 초당 2건, 이벤트 하나가 1.5 KB다.

1. **EventStreams 는 SSE(HTTP)라 Spark 가 직접 못 읽는다.** 프로듀서가 Kafka 토픽으로 옮겨야 붙는다.
2. **Spark 재시작 중 유실을 막는다.** 토픽 보존 기간(7일) 안에서는 오프셋을 되감아 재처리할 수 있다.

발표에서 "실시간 대용량 처리를 위해 Kafka"라고 하면 초당 2건 앞에서 무너진다.

## 빠른 시작

### 1. 파이썬 환경

🔴 **Python 3.11 을 쓴다.** PySpark 3.5 가 지원하는 건 3.8~3.11 이다. 그보다 높은
버전에서는 executor 가 `Python worker exited unexpectedly (crashed)` 로 죽는데,
스택트레이스에 버전 얘기가 없어서 원인 찾기 어렵다. 2026-09-08 에 3.13.12 로
만든 venv 에서 실제로 겪었다.

⚠️ **시스템 기본 파이썬으로 venv 를 만들면 이 함정에 걸린다.** 이 프로젝트를
확인한 PC 는 `python` 이 3.14.6, conda 가 3.13.12 였다. 둘 다 못 쓴다.
아래처럼 3.11 을 명시해서 만든다.

```bash
cd data-pipeline
uv venv --python 3.11 .venv          # uv 가 없으면 py -3.11 -m venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
cp .env.example .env                 # CONTACT_EMAIL 채우기
```

`CONTACT_EMAIL` 은 필수다. Wikimedia 는 연락처 없는 User-Agent 를 차단한다.

### 2. Kafka 띄우기

```bash
docker compose up -d kafka
docker compose --profile ui up -d    # Kafka UI 가 필요하면 (localhost:8080)
```

### 3. 프로듀서

```bash
.venv/Scripts/python.exe -m producer.wiki_edits
```

30초마다 처리량을 찍는다. `발행 2.1/s` 정도면 정상이다 (enwiki 기준).

### 4. Spark 잡

```bash
docker compose run --rm spark
```

첫 실행은 Kafka 커넥터 의존성을 내려받느라 몇 분 걸린다. ivy 캐시가 볼륨에
남아 두 번째부터는 건너뛴다.

## 설정

전부 환경 변수다. 기본값은 [.env.example](.env.example) 참고.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `CONTACT_EMAIL` | (필수) | User-Agent 에 넣을 연락처 |
| `WIKIS` | `enwiki` | 쉼표로 여러 개. `*` 면 전 위키 |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | 컨테이너 안에서는 `kafka:29092` |
| `KAFKA_TOPIC` | `wiki.edits` | |
| `SSE_CURSOR_FILE` | (빈 값) | Kafka 확인 완료 뒤 저장할 EventStreams cursor 파일. 빈 값이면 로컬 임시 동작 유지 |
| `WINDOW_SIZE` / `SLIDE_SIZE` | `1 hour` / `5 minutes` | 현재 집계 구현값. 현행 v0.3에서는 편집 횟수 임계가 아니라 조회수 검사 후보를 내는 주기를 결정하며 WP-118에서 재검토 |
| `STARTING_OFFSETS` | `latest` | 처음부터 읽으려면 `earliest` |
| `SINK` | `console` | `spike` 면 판정까지 가서 `spike(source='live')` 에 적재 (WP-100) |
| `DATABASE_URL` | (없음) | `SINK=spike` 에 필수. 없으면 기동 때 멈춘다 — 조용히 콘솔로 안 떨어진다 |

### 재시작 상태

producer는 Kafka가 이벤트 전달을 확인한 뒤에만 `SSE_CURSOR_FILE`을 갱신한다. 전달 실패나
확인 timeout에서는 cursor를 진행시키지 않으며, 재연결 때 저장된 값을 `Last-Event-ID`로
보낸다. 로컬에서 `SSE_CURSOR_FILE`을 비워 두면 cursor를 디스크에 저장하지 않는다.

Spark의 로컬 기본 checkpoint는 `/tmp/wikipulse-checkpoint`지만 운영 Compose는
`CHECKPOINT_DIR=hdfs://192.0.2.10:8020/wikipulse/checkpoints/edit-windows-v1`을 사용한다. 이 HDFS 경로에는
streaming offset과 상태가 있으므로 재시작·복구 때 삭제하거나 다른 실행과 공유하지 않는다.

### LIVE 적재 경로 (`SINK=spike`, WP-100)

```
EventStreams ──producer/wiki_edits.py──▶ Kafka wiki.edits
                                             │
                        streaming/edit_windows.py  (윈도우 집계)
                                             │ foreachBatch
                          streaming/live_spike.py  (epoch → PageWindow)
                                             │
                                   spike/runtime.py  SpikeRuntime
                                             │ page_baseline 조회 → detect()
                                             ▼
                                spike (source='live')
                                             │
                  cluster/driver.py --source live   (WP-102, 별도 실행)
                                             ▼
                     issue_cluster(source='live') + cluster_member/cluster_snapshot
```

- 🔴 **타임스탬프는 epoch 초로 건넌다.** PySpark 의 `TimestampType` → 파이썬 변환은
  **드라이버 로컬 시간대의 naive datetime** 을 낸다. KST 장비 실측(2026-09-15):
  UTC `2024-10-06T19:00:00` → `datetime(2024, 10, 7, 4, 0)`, `tzinfo=None`.
  9시간 밀린 값이라 `require_utc` 가 막지만, 거기에 tzinfo 만 붙여 "고치면" 그때부터
  조용히 틀린다. `F.unix_timestamp` 는 세션 시간대 설정에도 안 걸린다.
- **조회수는 `None`(미수집)이다.** `wiki.edits` 에 조회수 필드가 없다 — 0 으로 꾸미면
  "진짜 0회" 와 구분이 안 된다. `detect()` 는 `None` 이면 편집만으로 1차 판정한다.
- **멱등하다.** `UNIQUE (source, page_id, window_start)`(V5) 라 같은 마이크로배치를
  재처리해도 행이 안 는다. 실 Kafka 재처리로 확인함 (2026-09-15).
- ⚠️ **슬라이딩 윈도우라 한 문서가 한 시간에 여러 행을 낸다.** `SLIDE_SIZE` 가 5분이면
  겹치는 윈도우가 최대 12개고, `window_start` 가 달라 전부 별개 행이다. 정각 tumbling
  만 원하면 `SLIDE_SIZE` 를 `WINDOW_SIZE` 와 같게 준다.
- ⚠️ **compose 의 `spark` 서비스로는 아직 못 돌린다** — 이미지 파이썬이 3.8.10 이라
  못박은 psycopg 3.3.5 가 안 깔린다(2026-09-15 실측). 근거와 대안은 `docker-compose.yml`
  의 spark 서비스 주석.
- ⚠️ **클러스터 생산은 이 스트리밍 잡 안에서 돌지 않는다** (WP-102). `spike` 를
  사이에 둔 별도 실행(`python -m cluster.driver --dsn … --source live`)이다. 아직
  스케줄러가 없어 사람이 돌린다 — 상시 LIVE 운영은 후속 과제.

## edit_event 스키마

프로듀서가 내보내고 Spark 가 읽는 형태. `producer/normalize.py` 와
`streaming/edit_windows.py` 의 `EDIT_EVENT_SCHEMA` 가 **1:1로 맞아야 한다.**
`from_json` 은 스키마가 어긋나도 예외를 던지지 않고 조용히 null 을 채운다 —
집계가 전부 0이 되는데 에러는 안 난다. `test_스키마_필드가_정규화_출력_키와_정확히_같다`
가 이걸 잡는다.

```json
{
  "wiki": "enwiki",
  "domain": "en.wikipedia.org",
  "title": "Hurricane Milton",
  "event_type": "edit",
  "rev_id": 1373797378,
  "rev_parent_id": 1372610131,
  "byte_delta": 2972,
  "new_length": 27706,
  "user": "Fundsmoney",
  "is_bot": false,
  "is_minor": false,
  "event_ts": "2026-09-08T00:28:36.250Z",
  "event_ts_ms": 1788827316250,
  "source": "eventstreams",
  "meta_id": "11d28510-7f5e-49e6-98cc-856cdf71befa"
}
```

`source` 는 리플레이 경로(`mediawiki_history` 덤프)가 붙을 자리다. 실시간과
리플레이가 같은 형태로 들어와야 급증 탐지 로직을 한 벌만 짠다. 명세 §3.2.

## 운영·리플레이 계약 (2026-09-17 확정)

- 과거 MVP 구간은 **2026-07-17~2026-09-17**로 고정하고, 이후 LIVE 데이터를 계속 누적한다.
- 과거와 LIVE는 정규화·감지·클러스터링·요약·종목 매칭 계약을 공유한다. 과거는 미리
  계산한 스냅샷, LIVE는 같은 계약의 최신 스냅샷이다.
- 조회수 최종 관문은 약 1시간 늦게 오는 `other/pageviews` 시간별 덤프다.
  `pageview_complete` 일별 `agent=user` 덤프는 품질 검증용으로 함께 보존하며,
  AQS 일별 API는 LIVE 최종 관문에 쓰지 않는다.
- 목표 지연은 사건 발생 후 통상 1~2시간, 시간별 원본 도착 후 내부 처리 15분 이내다.
  조회수 미도착은 후보 대기이고 빈 정상 결과가 아니다.
- 고정 2개월의 편집·시간별 조회수·일별 user 조회수·GDELT·Clickstream 원본은 실제
  공통 파이프라인 재생과 API·화면 검증이 끝나기 전에 삭제하지 않는다.
- 버블 점수·멤버는 시점별 스냅샷, 요약·검증 종목은 `issue_key` 단위 결과다. 과거 조회에는
  선택 시점까지 완료된 결과만 보여야 하며 미래 결과를 소급하지 않는다.
- GATEWAY·GDELT 실패는 재시도/처리 중이다. 모든 보강 작업 완료 후 통과 종목이 없을 때만
  정상 0건으로 확정한다.

🔴 **`title` 은 공백형이 canonical 이다** (`Hurricane Milton`). 덤프는 밑줄형
(`Hurricane_Milton`)으로 오는데, 그대로 두면 같은 문서가 `(wiki, title)` 두 개로
갈라진다. historical baseline 조회에서 LIVE 제목이 miss 하면 **기존 문서가 신규
문서로 잘못 판정**되는데 예외는 안 난다. 변환은 `producer/normalize.py` 의
`canonical_title()` **한 곳**이다 — 경로마다 따로 구현하지 않는다.
규칙·근거·비적용 항목은 그 함수 docstring 과 명세 §5.1 (WP-79).

이 함수를 쓰는 경로 (2026-09-15): `producer/normalize.py`(LIVE) ·
`batch/normalize_dump.py`(mediawiki_history) · `batch/pageview.py`(pageview_complete).
⚠️ `batch/clickstream.py` 만 아직 자체 구현(`replace("_", " ")`)이라 연속 축약·trim 이
없다 — 후속 통합 대상. 적용 시점은 **필터 뒤·집계 키 앞**이다(§5.1).

## 원본 스키마에서 알게 된 것 (2026-09-08 실측)

recentchange 이벤트를 실제로 받아 확인한 것들이다.

- **`page_id` 가 없다.** 페이지 식별자는 `(wiki, title)` 뿐이다. 문서 이동이
  일어나면 키가 바뀌지만 MVP 범위에서는 감수한다.
- **`categorize` 이벤트가 절반이다.** enwiki ns0 12초 표본에서
  edit 28 · new 7 · **categorize 25** · log 1. 분류 자동 갱신이라 편집량 신호가
  아니다. 안 거르면 편집 수가 부풀려진다.
- **이벤트 시각은 `meta.dt` 를 쓴다.** 최상위 `timestamp` 는 초 단위라 같은 초의
  편집을 구분하지 못한다. `meta.dt` 는 ms 정밀도다.
- **`type=new` 는 `length.old` · `revision.old` 가 없다.** 증분 계산 경로가 다르다.
- **봇 비중이 낮지 않다.** enwiki 41건 중 11건이 봇이었다.

## 테스트

```bash
.venv/Scripts/python.exe -m pytest
```

Kafka·Docker 없이 돈다. Spark 테스트는 로컬 `local[2]` 로 실제 집계를 돌려
스키마와 결과를 검증한다. pyspark 가 없으면 그 파일만 건너뛴다.

## 아직 안 한 것

- **v0.3 최종 이슈 판정 계약 적용** — 편집 발생을 후보 관문으로만 쓰고, 문서 생성일부터
  현재까지(최대 28일) 조회수 급등으로 최종 판정하는 경로는 `WP-118`에서 구현한다.
  운영 입력은 `other/pageviews` 시간별 덤프이며 미도착 후보 재평가와 내부 15분 SLA 계측도
  포함한다. 현재 `spike/detector.py`의 편집 임계·신규 문서 별도 식은 이전 계약이다.
- **클러스터 멤버 역할 적용** — 루트 씨드 외 Clickstream 이웃에 대해 생성 시각 동시성
  추가 씨드와 `재급증 비율 >= 5 AND 사건기간 편집 수 >= 20` 비-seed를 저장하는 실행 경로가
  아직 없다. Wikidata는 멤버 편입 관문이 아니다.
- **시점별 AI 산출물 연결과 상태 정합성** — 같은 `issue_key`의 각 스냅샷 클러스터에
  선택 시점까지 완료된 리포트·검증 종목을 연결하고 `DETECTED -> VERIFYING -> CONFIRMED`
  상태를 실제 실행 단계와 맞춘다. GATEWAY·GDELT 실패와 정상 0건도 구분한다. 실제 2개월 원본으로
  1,112개 데모 시드를 교체하는 검증까지 `WP-119`·`WP-120` 범위다.
- **실제 종목 가격 공급** — `stock_price` 실데이터 적재와 백엔드·프론트 조회 경로가 없다.
  종목 상세 MVP 완료 전에 `WP-124`에서 실데이터·가격 API·그래프를 연결한다.
- **되돌리기 판정** — 서로 다른 편집자 2명 이상 관문은 구현됐지만, identity revert 필드는
  아직 급증 판정에서 사용하지 않는다.
- **EC2 구성의 저장소 재현성** — Kafka(`WP-26`)와 Spark 2노드
  (`WP-27`) 설치·분산 실행은 2026-09-17 완료했다. 다만 EC2의 `~/infra/*`
  compose·설정은 저장소에 없고, Spark 3.5.3 기본 Python 3.8에서는 고정한
  `psycopg 3.3.5`를 설치할 수 없어 `SINK=spike` 운영 경로가 아직 막혀 있다.
  루트 `docker-compose.yml`은 로컬 개발용이며 운영 구성과 같지 않다.
