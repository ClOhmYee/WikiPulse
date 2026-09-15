# data-pipeline — 실시간 수집·집계

Wikipedia EventStreams 를 Kafka 로 옮기고, Spark Structured Streaming 이
문서별 편집량을 윈도우 집계한다.

- `WP-30` EventStreams SSE → Kafka `wiki.edits` Producer
- `WP-31` Spark Structured Streaming 골격 — 문서별 편집 윈도우 집계
- `WP-32` GDELT GKG 15분 폴링 → HDFS 적재 Producer — [gdelt/README.md](gdelt/README.md)
- `WP-65` GDELT GKG 기관명 lift 집계 → `cluster_org_mention` Spark 배치 — [gkg/README.md](gkg/README.md)

명세: [docs/requirements-v0.1.md](../docs/requirements-v0.1.md) §3

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
| `WINDOW_SIZE` / `SLIDE_SIZE` | `1 hour` / `5 minutes` | 급증 판정 수식 확정 전 임시값 (`WP-38`) |
| `STARTING_OFFSETS` | `latest` | 처음부터 읽으려면 `earliest` |

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

- **PostgreSQL 싱크** — 데이터 모델(`WP-35`)이 확정된 뒤에 붙인다. 지금
  스키마를 넣으면 두 번 고치게 된다. 현재 싱크는 콘솔이다.
- **급증 판정** — z-score 임계·조회수 2차 판정 (`WP-38`)
- **클러스터링** — Clickstream + Wikidata
- **1인 반복 편집·되돌리기 필터** — 지금은 봇만 거른다
- **EC2 배포** — `WP-26`(Kafka)·`-27`(Spark). 이 compose 는 로컬 개발용이고
  운영 구성과 다르다 (복제 계수 1, 단일 브로커).
