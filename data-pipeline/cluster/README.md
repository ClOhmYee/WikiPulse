# cluster — 시점별 클러스터·문서 그래프 생산 (WP-75)

급증 문서를 이슈 클러스터로 묶고, 문서 쌍 간선과 시점별 지표를 생산해
PostgreSQL 에 저장한다. 버블맵 조회 API(WP-74)가 이 산출물을 읽는다.

계약: [`docs/frontend/PULSE_MAP.md`](../../docs/frontend/PULSE_MAP.md) ·
[`frontend/docs/pulse-openapi.json`](../../frontend/docs/pulse-openapi.json)
저장 스키마: [`db/migrations/V2__pulse_snapshot_graph.sql`](../../db/migrations/V2__pulse_snapshot_graph.sql)

## 구성

| 파일 | 역할 | 테스트 |
| --- | --- | --- |
| `snapshot.py` | 순수 생산 로직 — 게이트·멤버·간선·issue_key. Spark·DB 없이 돈다 | `tests/test_snapshot.py` |
| `score.py` | 공통 sizeScore 0~1 + `SCORE_VERSION` | (snapshot 테스트에 포함) |
| `writer.py` | 스냅샷을 PostgreSQL 에 멱등 저장(재계산 호환) | `tests/test_writer.py`(pgserver 왕복) |
| `driver.py` | 실 데이터 소스 배선 + CLI — **씨드 경로 배선됨**(아래) | `tests/test_driver_seeds.py` · `tests/test_driver_pg.py` · `tests/test_driver.py` |

```
pytest cluster/tests        # 42개. Docker 불필요(pgserver 번들 PostgreSQL)
```

## 클러스터링 게이트 (WP-51 확정, 명세 §3.2 4번·§11)

- **씨드**(`is_seed=true`) = 급증 판정(`spike/detector.py`)을 직접 통과한 문서. 각 씨드가 한 클러스터를 연다.
- **비-씨드** = 씨드의 Clickstream 이웃(월별 덤프, `n>=10`) 중 **문서 생성일이 씨드 사건일 ±창(기본 30일) 안**인 문서. 생성일 근접이 곧 시간 동시성.
- Clickstream 값에 별도 문턱 없음 — 절대 이동량으로는 사건/배경이 안 갈린다(§11: Hormuz 배경 문서가 사건 문서보다 30배 더 클릭). 포함은 생성일 창이 정하고 `n` 은 `weight` 로만.
- Wikidata 는 게이트에서 빠짐(속성 5종 전수 검사 실패). 화면 근거 점선 간선으로만 그린다.
- ⚠️ 기존 문서가 사건으로 재조명되는 비-씨드(예: `Mojtaba_Khamenei`)는 생성일 창으로 못 잡는다 — **WP-77 로 분리.** 이 모듈 범위 밖.

## 점수

- `size_score = s/(s+5)` (`s`=spike_score), 0~1 절대 척도. 매 시점 최댓값 정규화 아님 — 시점 간 버블 크기가 비교돼야 한다. 비-씨드는 원시 점수가 없어 `None`(화면은 작은 점선 노드, 0과 구분).
- `pulse_score` = 씨드 급등도 최댓값. 문서 수가 아니라 가장 강한 급증이 이슈 세기를 대표.
- 산식·상수를 바꾸면 `SCORE_VERSION` 을 올리고 `cluster_snapshot.score_version` 으로 시점과 함께 저장한다.

## 시점 간 추적

`issue_key = "{source}:{wiki}:{title}"`(씨드 자연키) — `id` 는 스냅샷마다 새로 생기지만
씨드 문서는 사건 내내 유지되므로 시간축을 잇는다. `first_detected_at` 은 이 `issue_key`
가 과거에 처음 잡힌 시각(없으면 이번 스냅샷). NEW 배지는
`0 <= snapshot_ts - first_detected_at < new_window_hours`(기본 24h).

## LIVE / 리플레이

둘 다 `build_snapshot(...)` 하나를 쓴다. LIVE 는 현재 시각을, 리플레이(Spark 배치)는
과거 시점을 `snapshot_ts` 로 넣어 같은 로직을 과거 덤프에 돌린다. `persist_snapshot` 은
`(source, snapshot_ts)` 단위로 멱등이라 재계산이 중복을 쌓지 않는다. 클러스터 0개
스냅샷도 `cluster_snapshot` 에 등록해 "완료된 빈 스냅샷"을 미저장 시점과 구분한다.

## 실행 — spike → issue_cluster (WP-99 · -102)

```bash
python -m cluster.driver --dsn "$DATABASE_URL" --source replay
python -m cluster.driver --dsn "$DATABASE_URL" --source live
python -m cluster.driver --dsn ... --source replay --snapshot-ts 2024-10-07T14:00:00Z
python -m cluster.driver --dsn ... --source live --dry-run
```

`spike`(WP-94 런타임 출력) → 씨드 → `build_snapshot` → `persist_snapshot`.
로직·점수·게이트는 이 파일이 정하지 않는다 — 전부 위 `snapshot.py`·`score.py` 자산이다.

**스냅샷 시점은 `spike.detected_at` 의 고유값 하나당 하나다.** 새 문턱이나 lookback 창을
만들지 않으려고 이렇게 했다 — 기존 행을 다시 묶기만 한다.

🔴 **`--source` 는 산출물 라벨이 아니라 입력 필터다** (~~`replay` 전용, -99~~ →
`live`·`replay` 둘 다, WP-102 · 2026-09-16).

-99 가 `replay` 하나로 묶어 둔 이유는 `spike` 에 출처 컬럼이 **없었기** 때문이다 —
리플레이 행을 읽어 `issue_cluster.source='live'` 로 저장하는 거짓 라벨링이 가능했고,
API·화면은 그걸 실시간 이슈로 그리는데 **에러는 안 났다.** V5(`db/migrations/V5__spike_source.sql`)가
`spike.source` 를 만들면서 전제가 사라졌고, -102 가 그 가드를 걷었다.

**가드를 걷는 조건은 "조회에 source 를 건다" 이지 "라벨을 자유롭게 받는다" 가 아니다.**
`source` 를 출력 라벨로만 쓰고 입력 질의에 안 걸면 -99 가 막던 거짓 라벨링이 그대로
돌아온다. 그래서:

| 자리 | -102 계약 |
| --- | --- |
| `SELECT_SEEDS_SQL` | `WHERE s.source = %s AND s.detected_at = %s` |
| `SELECT_SNAPSHOT_TIMES_SQL` | `WHERE s.source = %s AND …` |
| `load_seeds_from_spike(conn, ts, source)` | `source` **필수**, 기본값 없음 |
| `load_snapshot_times(conn, source, …)` | `source` **필수** |
| `require_spike_source` | `spike_sink.SPIKE_SOURCES` 두 개만. 그 외 `ValueError` |
| CLI `--source` | **required**. 기본값 없음, `choices` 로 오타 거절 |

⚠️ **같은 `detected_at` 에 replay 행과 live 행이 공존한다.** V5 가 UNIQUE 키에
`source` 를 넣어 두 출처가 같은 `(page_id, window_start)` 를 각각 갖기 때문이다 —
시각만으로 시점을 고르면 두 출처가 한 스냅샷에 섞인다. 시점 목록부터 출처별로 뽑는다.

🔴 **없는 `source` 를 관용하지 않는 이유.** `'LIVE'` 같은 대소문자 어긋남을 통과시키면
조회가 **0행**이 되고, 씨드가 비어 클러스터 0개 스냅샷이 저장된다. 그건 writer 계약상
"완료된 빈 스냅샷" 이라 에러가 안 나고, 화면에는 "이 시점엔 이슈가 없다" 로 보인다.
CLI 기본값을 없앤 것도 같은 이유다 — `--source` 를 빠뜨린 LIVE 운영이 조용히
리플레이 스냅샷을 다시 만든다.

산출물 쪽 격리는 이미 서 있었다: `issue_key_of` 가 `{source}:{wiki}:{title}` 라 두
출처의 키가 겹치지 않고, `persist_snapshot` 의 삭제·재적재 단위가 `(source, snapshot_ts)`
라 한쪽을 다시 돌려도 다른 쪽이 안 지워진다.

🔴 **오름차순 처리라야 `first_detected_at` 이 멱등이다.** 앞 시점이 먼저 저장돼 있어야
`load_prior_first_detected` 가 맞는 최초 시각을 준다. 내림차순으로 돌리면 뒤 시점이
'최초'가 되고 재실행마다 값이 바뀐다 — 에러 없이 NEW 배지가 흔들린다.

### Milton 실측 (2026-09-15)

`spike` 6행(enwiki / `Hurricane Milton` / page_id 398) → 스냅샷 6 · 클러스터 6 ·
멤버 6(전부 `is_seed=true`) · 간선 0. `issue_key` 는 6시점 모두
`replay:enwiki:Hurricane Milton` 하나, `first_detected_at` 은 전부 최초 시점
`2024-10-07T14:00:00Z`. 두 번 돌려도 행 수·키·최초 시각 불변.
백엔드 무수정으로 `/api/v1/issues?snapshotTs=…&source=replay` · `/issues/map` ·
`/issues/{id}` 가 그대로 읽는다.

⚠️ **`hot` 이 z 경로 클러스터에서는 사실상 안 켜진다.** 위 6건 중 `hot=true` 는 신규 문서
경로 1건(pulse 42.3)뿐이고 z 경로 5건은 1.4~1.7 이라 `DEFAULT_HOT_SPIKE_THRESHOLD=5.0`
근처에도 못 간다. 임계가 틀린 게 아니라 **두 경로의 `spike_score` 척도가 다르다** —
`detector._detect_new_page` 는 `edit_count × √editor_count`, 기존 문서 경로는 `log1p(z)`
압축이다. 여기서 임계를 만지면 안 되고(WP-38 자산) 점수 쪽에서 풀어야 한다.

### LIVE / replay 공존 실측 (2026-09-16, WP-102)

한 DB 에 두 출처를 같이 넣고 `--source` 별로 돌렸다. 입력은 둘 다 **공식 적재 경로**다 —
replay 는 실 Milton 덤프(`spike.replay --edits …/out/enwiki/2024-10 --dsn`), live 는 실
Spark 윈도우(`streaming.live_spike.process_batch`). spike 를 손으로 INSERT 하지 않았다.

| | replay | live |
| --- | --- | --- |
| `spike` | 48행, 2024-10-06T20Z ~ 10-12T23Z | 2행, 2026-09-16T05Z |
| `load_snapshot_times` | 48시점 | 1시점 (2024년이 안 섞인다) |
| `issue_cluster` | 48 (`replay:enwiki:Hurricane Milton`) | 2 (`live:enwiki:Live Issue Alpha`·`Bravo`) |
| `cluster_member` | 48, 전부 `is_seed=true` | 2, 전부 `is_seed=true` |
| `cluster_snapshot` | 48 | 1 (`cluster_count=2`) |
| `cluster_edge` | 0 | 0 (씨드 단독 계약) |

혼입 검사 — 각 클러스터 멤버를 `spike(source=클러스터 출처, detected_at=snapshot_ts)` 와
조인했더니 replay 48/48 · live 2/2 가 **같은 출처에서** 매칭됐다. 교차 0건.
두 `--source` 를 각각 2회씩 돌린 뒤 `(cluster, member, snapshot)` = `(50, 50, 49)` 불변,
`issue_key`·`first_detected_at` 전부 동일.

⚠️ **이 실측의 replay 숫자를 위 "Milton 실측(2026-09-15)" 6행과 비교하지 말 것.**
여기서는 `page_baseline` 을 적재하지 않아 272 윈도우가 전부 "기준선 없음(absent)"
경로로 갔다 — 그래서 48건이 잡히고 `hot` 이 전부 켜졌다. -99 의 6행은 기준선이 있는
z 경로다. 판정이 달라진 게 아니라 **입력 조건이 다르다**(`spike/runtime.py` 상단 ⚠️).

### 백엔드 무수정 확인 (2026-09-16, 실 HTTP)

위 DB 를 그대로 물린 `bootRun` 에 붙었다. 백엔드 코드는 **한 줄도 안 고쳤다.**

| 요청 | 결과 |
| --- | --- |
| `GET /api/v1/issues` (무인자) | 200 · LIVE 2건 (`id` 149·150, `source":"live"`, `memberCount":1`, `meta.snapshotTs":"2026-09-16T05:00:00Z"`) |
| `GET /api/v1/issues?source=live` | 200 · 같은 2건 |
| `GET /api/v1/issues?snapshotTs=2024-10-07T22:00:00Z&source=replay` | 200 · Milton 1건 (pulse 176.0) |
| `GET /api/v1/issues/map` | 200 · `issueKey` `live:enwiki:Live Issue Alpha`·`Bravo`, `edgeCount":0` |
| `GET /api/v1/issues/snapshots?source=live` | 200 · 1건 (`clusterCount":2`) |
| `GET /api/v1/issues/149` | 200 · `members` 1건(`isSeed":true`), `relatedStocks":[]` |

무인자 피드가 LIVE 를 잡는 경로는 `IssueClusterRepository` 다 —
~~`findLatestLiveSnapshot` (`SELECT max(snapshot_ts) FROM issue_cluster WHERE source='live'`)~~
→ `findLatestSnapshot(source)` (`cluster_snapshot` 에서 LIVE 우선, 아래 항목).
LIVE 가 있는 위 표의 결과는 그대로다.

~~⚠️ `?source=replay` 를 시각 없이 주면 빈 목록이 온다 (`total:0`, `meta.snapshotTs` 는
LIVE 시각). `IssueService.feed` 가 시각 미지정 시 최신 LIVE 스냅샷을 먼저 고르고 그
시각에 `source=replay` 를 거는 구조라서다.~~ → **고쳤다** (2026-09-17, WP-106).

시각 미지정이면 이제 `IssueClusterRepository.findLatestSnapshot(source)` 가 **요청한
출처의 최신 완료 스냅샷**을 고른다. 출처도 없으면 최신 LIVE, LIVE 가 없으면 최신
replay — `/issues/map` 의 `PulseMapRepository.findLatestSnapshot` 과 같은 규칙·같은
SQL 이다. 두 endpoint 는 같은 데이터를 카드/버블로만 다르게 그리므로 시각 미지정에서
서로 다른 시점을 고르면 두 화면이 조용히 어긋난다. 고친 계기는 **replay 만 적재된
DB(이 README 의 Milton 6행)에서 `GET /api/v1/issues` 가 에러 없이 빈 피드를 낸 것**이다.

⚠️ **pgserver 로는 백엔드를 못 띄운다.** 번들 postgres 에 timezone DB
(`share/postgresql/timezone`)가 없어 JDBC 가 보내는 `TimeZone` 파라미터를 전부 거절한다
(`Asia/Seoul`·`UTC` 둘 다 `FATAL: invalid value`). `GMT` 만 통과한다 —
위 확인은 `-Duser.timezone=GMT` 로 돌린 것이다. 실 PostgreSQL(docker compose)에는
없는 문제다(CLAUDE.md). 팀 기본 경로는 `docker compose up -d postgres` 다.

## 배선됨 (WP-115, 2026-09-17)

~~Clickstream 이웃·문서 생성일·`load_pages_by_title` 셋 다 미배선~~ → 전부 이어졌다.

```
python -m cluster.driver --dsn "$DATABASE_URL" --source replay     --clickstream-root ./data/clickstream --clickstream-month-rule event     --creation-index ./data/page-creation/enwiki/2024-09_2024-10
```

- **Clickstream 이웃** — `MonthlyNeighborSource` 가 월 덤프를 **월당 한 번** 훑는다.
  시점이 1,400개가 넘어 시점마다 읽으면 끝나지 않는다.
- **문서 생성일** — `batch/page_creation` 이 mediawiki_history 의
  `page_creation_timestamp` 로 `title → 생성일` 인덱스를 만든다. `wiki_page` 에도
  `-56` edit_event 15필드에도 `-58` 윈도우 샤드에도 그 값이 없어서 덤프가 유일한 소스다.
- **`load_pages_by_title`** — 이웃 제목 → `page_id`. 🔴 **없는 문서를 등록한다.**
  사건 직후 생긴 비-씨드 문서는 `wiki_page` 에 없고(그 테이블은 warm-up 기준선과 급증
  문서로만 채워진다), 등록을 안 하면 진짜 멤버가 조용히 전부 사라진다.
- 🔴 **게이트는 한 곳에만 있다.** driver 는 `snapshot._within_creation_window` 를 그대로
  부른다 — 같은 조건을 driver 에 다시 쓰면 규칙이 두 벌이 되고 한쪽만 바뀌어도
  에러 없이 결과가 갈린다.
### 근거 월은 출처마다 다르다 (2026-09-17 확정)

`--clickstream-month-rule` 은 **필수**다. `--source` 를 `required` 로 둔 것과 같은
이유 — 기본값이 있으면 빠뜨린 실행이 에러 없이 다른 근거로 산출물을 만든다.

| 출처 | 규칙 | 왜 |
| --- | --- | --- |
| **historical replay** | `event` (스냅샷이 속한 달) | 과거 재생이라 그 달 덤프가 이미 나와 있다 |
| **LIVE** | `event` 를 **쓸 수 없다** | 당월 덤프는 그 달이 끝나야 나온다 |

🔴 **리플레이가 사건월을 쓴다고 해서 LIVE-equivalent 가 아니다.** 두 경로가 가진
근거의 시간 범위가 구조적으로 다르다. **LIVE 가 무엇을 쓸지는 정해지지 않았고 별도
후속 과제다** — `previous` 가 LIVE 가 구할 수 있는 최신 덤프지만, 그것으로 충분한지는
측정된 바 없다. 두 출처의 산출물을 비교할 때 이 비대칭을 먼저 확인한다.

replay 에서 `event` 를 고른 근거 (61일 2024-09~10, `-109` 데이터 전량 실측):

| | `event` | `previous` |
| --- | --- | --- |
| 씨드 덤프 적중 | **83.7%** | 66.6% |
| 2+ 멤버 클러스터 | **34.1%** | 17.7% |
| edge | **20,161** | 6,134 |
| Milton·Helene·Yagi | 멤버 10·18·11 | **전부 이웃 0개** |

대표 사건이 `previous` 에서 0인 이유는 씨드 문서(생성일 2024-10-05·09-23·09-01)가
직전 달 덤프에 **아직 존재하지 않아서**다. 신규 사건 문서일수록 이 문제가 커진다.

## 아직 안 한 것

- **Wikidata 점선 간선** — 선택. 없으면 안 그린다.
- 🔴 **비-씨드 판정 규칙(기존 문서 재조명)** — WP-77. 명세 §3.2·§10 에
  확정 규칙(재급증 비율 ≥ 5 AND 절대 편집 ≥ 20)이 적혀 있지만 **코드에는 없다**
  (2026-09-17 확인). 지금 비-씨드가 되는 경로는 생성일 창(-51) 하나뿐이라
  `Mojtaba_Khamenei` 류는 멤버가 되지 않는다.
