# cluster — 시점별 클러스터·문서 그래프 생산 (WP-75)

급증 문서를 이슈 클러스터로 묶고, 문서 쌍 간선과 시점별 지표를 생산해
PostgreSQL 에 저장한다. 버블맵 조회 API(WP-74)가 이 산출물을 읽는다.

계약: [`docs/frontend/PULSE_MAP.md`](../../docs/frontend/PULSE_MAP.md) ·
[`frontend/docs/pulse-openapi.json`](../../frontend/docs/pulse-openapi.json)
저장 스키마: [`db/migrations/V2__pulse_snapshot_graph.sql`](../../db/migrations/V2__pulse_snapshot_graph.sql)

## 구성

| 파일 | 역할 | 테스트 |
| --- | --- | --- |
| `root_selection.py` | **정본 1단계** — spike 후보 중 클러스터링에 넣을 root 선택 | `tests/test_root_selection.py` |
| `rootgraph.py` | **정본 2단계(CORE)** — root 를 사건 component 로 묶는 순수 그래프 | `tests/test_rootgraph.py` |
| `asof_links.py` | as-of revision 링크 추출·정규화·수집 + V11 캐시 | `tests/test_asof_links.py` |
| `snapshot.py` | 순수 생산 로직 — CORE 결과 → Cluster/Member, legacy 게이트·간선·issue_key | `tests/test_snapshot_core.py` · `tests/test_snapshot.py` |
| `score.py` | 공통 sizeScore 0~1 + `SCORE_VERSION` | (snapshot 테스트에 포함) |
| `writer.py` | 스냅샷을 PostgreSQL 에 멱등 저장(재계산 호환) | `tests/test_writer.py`(pgserver 왕복) |
| `driver.py` | 실 데이터 소스 배선 + CLI — **씨드 경로 배선됨**(아래) | `tests/test_driver_seeds.py` · `tests/test_driver_pg.py` · `tests/test_driver.py` |

```
pytest cluster/tests        # Docker 불필요(pgserver 번들 PostgreSQL)
```

## 클러스터링 정본 (WP-186, 2026-09-22 확정) — **두 단계**

```
spike 후보
  ↓  1. ROOT SELECTION   root_selection.py   views DESC · 시점당 20 · 24h 쿨다운
20 roots / snapshot
  ↓  2. CORE GROUPING    rootgraph.py
     strict historical as-of direct Wikipedia link (한 방향이라도)
     → connected component → sym focus τ=0.005 → D2 directional bridge 억제
component 자체가 issue cluster, 그 안의 root 가 cluster_member (root-only)
```

🔴 **두 단계가 함께 정본이다.** ROOT SELECTION 없이 `spike` 전량을 CORE 에 넣으면
2026-09-22 실측으로 component 146,988 · **max 63 · 20+ giant 59** 가 나온다.
`giant 0` 은 두 단계가 함께 만드는 성질이다. 1단계 규칙은 `root_selection.py` 참고.

고정 2개월 replay 실측 (`tools/cluster-preview/verify_core_regression.py` 가 매번 대조한다):

| 스냅샷 | root | component | 1 | 2 | 3~4 | 5~7 | 8~12 | 13+ | max | 20+ giant |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 1,104 | 22,080 | 19,432 | 17,569 | 1,461 | 322 | 57 | 20 | 3 | 16 | 0 |

- **앵커는 `spike.max_rev_id`(V9)** — replay 는 과거 판정 시점의 판, LIVE 는 관측 시점의
  판이라 **두 출처가 같은 계약**이다. 코드에 replay/live 분기가 없다.
- 🔴 **`prop=wikitext` 의 리터럴 `[[...]]` 만 쓴다.** `parse.links` 는 옛 revision 을
  렌더해도 템플릿을 현재 판으로 전개해 스냅샷 이후 navbox 링크가 섞인다 — 미래 누수이고
  에러 없이 조용히 틀린다.
- 🔴 **`max_rev_id` 가 없으면 현재 판으로 폴백하지 않는다.** 그 root 는 singleton 이다.
- 🔴 **링크 비교 정규화는 `asof_links.link_key` 다.** `producer.normalize.canonical_title`
  과 달리 **첫 글자를 대문자로 올린다** — 링크 타깃은 사람이 쓴 문자열이고 MediaWiki 가
  그렇게 해석한다(`[[eBay]]` → `EBay`). 양쪽에 같은 함수를 걸어야 하며, 한쪽만 걸면
  간선이 에러 없이 사라진다. 저장 제목은 계속 `canonical_title` 계약이다.
- 채택하지 않은 것: common-neighbor expansion(PoC 7 B1~B4, precision 미달) ·
  Clickstream 을 membership 필수조건으로 · resurgence 를 CORE 생성 규칙으로.

### 링크 캐시 (V11 `page_asof_links`)

revision 단위라 만료가 없다. 대량 재계산 전에 미리 채운다.

```bash
# 캐시만 사용 (기본) — 없는 root 는 singleton 이 되고 경고를 찍는다
python -m cluster.driver --dsn ... --source replay

# 캐시에 없는 것을 받아 채우면서 돌린다. CONTACT_EMAIL 필요
python -m cluster.driver --dsn ... --source replay --fetch-links --link-workers 4
```

⚠️ 리플레이 한 판이 root 수만큼 요청을 낸다(실측 22,080). 그래서 `--fetch-links` 가
**기본이 아니다** — 실수로 켜지면 위키미디어를 그만큼 때린다.

### ~~root 집합이 두 벌이다~~ → 해소 (2026-09-22)

~~`issue_cluster` 의 22,080 root 와 `spike` 의 162,775 행이 서로 다른 실행의 산출물이고,
driver 에 상한도 중복 제거도 없다~~ → **ROOT SELECTION 이 그 자리다.** WP-137 이
만들어 둔 `seed_selection.py` 가 바로 22,080 을 만든 코드였고, 그걸 `root_selection.py`
로 가져와 기본 경로에 넣었다. 같은 DB 의 `spike` 에서 production selector 를 돌리면
`(snapshot_ts, page_id)` 22,080 쌍이 PoC frozen set 과 **정확히 일치**한다
(prod-only 0 · PoC-only 0 · 스냅샷당 20 위반 0 · 24h 쿨다운 위반 0).

## LEGACY 멤버 확장 게이트 — 기본 OFF (제품 계약: WP-51·77, 명세 §3.2 4번·§11)

🔴 **`--expansion` 을 줘야 돈다.** CORE 뒤에 자동으로 다시 적용하지 않는다 — 위 분포가
보장되지 않고, non-root 멤버는 `window_start`·`window_end` 가 없어 프론트 계약
(`contract.js` 의 `metric window`)에 걸려 **펄스맵이 통째로 안 그려진다.**
2026-09-22 preview 에서 baseline 5,120 클러스터가 그 이유로 렌더에서 탈락했다.
아래 서술은 그 레이어의 계약이며 규칙 자체는 -186 에서 바뀌지 않았다.


- **루트 씨드**(`is_seed=true`) = 조회수 최종 관문을 직접 통과한 문서. 각 루트 씨드가 클러스터를 연다.
- **추가 씨드**(`is_seed=true`) = 루트 씨드의 Clickstream 이웃(월별 덤프, `n>=10`) 중 문서 생성일이 사건일 ±창(기본 30일) 안인 새 사건 문서.
- **비-씨드**(`is_seed=false`) = 오래전에 생성된 Clickstream 이웃 중 사건기간 편집 재급증 비율 ≥5 **AND** 사건기간 편집 수 ≥20인 문서(WP-77).
- **시점 정합성 상한** = UTC 기준 실제 생성 시각이 `snapshot_ts` 이후인 문서는 생성일 창 안이어도 제외한다. `clickstream_month`도 스냅샷 월보다 앞선 데이터 기간만 허용하고, Wikidata는 `observed_at <= snapshot_ts`인 보조 간선만 허용한다. 당월에 새로 생긴 LIVE 이슈는 완료 월에 관계가 없으면 씨드 단독일 수 있다. 이 상한은 원본 데이터 기간 기준이므로 과거 원본을 나중에 적재하는 리플레이도 계산할 수 있지만, 사건 당월이나 이후 기간의 근거를 더 이전 지도에 소급하지는 않는다.
- Clickstream 값에 별도 문턱 없음 — 절대 이동량으로는 사건/배경이 안 갈린다(§11: Hormuz 배경 문서가 사건 문서보다 30배 더 클릭). 관계 `weight`는 `n` 100%이며 다른 실시간 신호를 섞지 않는다. 직전 월 검증 완료본을 우선하고, 미공개·검증 실패 시 최신 완료본(통상 전전월)을 유지하며 월간 합산은 하지 않는다.
- Wikidata는 멤버 편입에 쓰지 않는다. 이미 포함된 멤버 사이 화면 보조 점선 간선만 계약에 남아 있으며 실제 소스 배선은 없다.

⚠️ **현재 구현 차이:** `snapshot.py`는 루트 씨드만 `is_seed=true`로 두고 생성일 근접 이웃을 `false`로 저장한다. 재급증 비율·절대 편집 수 입력도 없어 WP-77 규칙을 실행하지 않는다. `driver.py:load_creation_dates`도 미구현이라 실제 E2E는 씨드 단독이다. 아래 테스트는 현재 코드의 회귀 테스트이지 제품 계약 구현 완료 증거가 아니다.

## 점수

- `pulse_score` = component 안 root 들의 `spike_score` **최댓값**, `hot` 은 하나라도 임계를
  넘으면 참. `label`·`issue_key`·`seed_page_id` 는 **lead root**(최대 `spike_score`, 동점이면
  제목 내림차순)에서 나온다 — 입력 순서에 안 흔들린다.
  ⚠️ 같은 사건이 앞뒤 시점에 다른 lead 를 가지면 `issue_key` 도 달라진다.
  temporal episode grouping 후속 과제로 분리했다(2026-09-22).
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
재계산 시에도 해당 `snapshot_ts`까지 존재한 문서·관계와 그보다 앞선 Clickstream 데이터
기간만 사용하므로 미래 기간의 근거가 과거 지도에 소급 반영되지 않는다. 로컬 적재 시각은
이 event-time 상한에 포함하지 않는다.

## 실행 — spike → issue_cluster (WP-99 · -102)

```bash
python -m cluster.driver --dsn "$DATABASE_URL" --source replay
python -m cluster.driver --dsn "$DATABASE_URL" --source live
python -m cluster.driver --dsn ... --source replay --no-root-grouping   # 2단계 끔(비상용)
python -m cluster.driver --dsn ... --source replay     --root-limit-per-snapshot 20 --root-cooldown-hours 24   # 1단계 기본값(명시)
python -m cluster.driver --dsn ... --source replay --root-limit-per-snapshot 0     --root-cooldown-hours 0                                  # 1단계 끔 — 🔴 giant 가 생긴다
python -m cluster.driver --dsn ... --source replay --expansion     --clickstream-root ./data/clickstream --creation-index ./data/page-creation/...
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

## 배선됨 (WP-115, 2026-09-17 · 2026-09-18 정정)

~~Clickstream 이웃·문서 생성일·`load_pages_by_title` 셋 다 미배선~~ → 전부 이어졌다.

```
python -m cluster.driver --dsn "$DATABASE_URL" --source replay \
    --clickstream-root ./data/clickstream \
    --creation-index ./data/page-creation/enwiki/2024-09_2024-10
```

- **Clickstream 이웃** — `MonthlyNeighborSource` 가 월 덤프를 **월당 한 번** 훑는다.
  시점이 1,400개가 넘어 시점마다 읽으면 끝나지 않는다.
- **문서 생성 시각** — `batch/page_creation` 이 mediawiki_history 의
  `page_creation_timestamp` 로 `title → 생성 시각(UTC)` 인덱스를 만든다. `wiki_page` 에도
  `-56` edit_event 15필드에도 `-58` 윈도우 샤드에도 그 값이 없어서 덤프가 유일한 소스다.
  🔴 **timezone-aware UTC 다** (2026-09-18 변경). ~~날짜(`2024-10-05`)~~ → 덤프 정밀도
  그대로(`2024-10-05T14:55:15+00:00`). 자정으로 뭉개면 되돌릴 수 없고, 명세 v0.3
  §3.2 4번의 시점 상한(`실제 생성 시각 <= snapshot_ts`)을 시 단위로 못 따진다.
  `read_index` 는 시간대 없는 옛 적재본을 **거부한다** — 자정 보정은 실제보다 이른
  시각이 되어 통과하면 안 되는 문서를 통과시킨다. 옛 적재본은 다시 만든다.
- **`load_pages_by_title`** — 이웃 제목 → `page_id`. 🔴 **없는 문서를 등록한다.**
  사건 직후 생긴 추가 씨드 문서는 `wiki_page` 에 없고(그 테이블은 warm-up 기준선과 급증
  문서로만 채워진다), 등록을 안 하면 진짜 멤버가 조용히 전부 사라진다.
- 🔴 **게이트는 한 곳에만 있다.** driver 는 `snapshot._within_creation_window` 를 그대로
  부른다 — 같은 조건을 driver 에 다시 쓰면 규칙이 두 벌이 되고 한쪽만 바뀌어도
  에러 없이 결과가 갈린다.
- **멤버 역할** — 생성일 창을 통과한 이웃은 **추가 씨드(`is_seed=true`)** 다
  (2026-09-18 정정, 명세 v0.3 §3.2 4번). ~~`is_seed=false`~~ 였는데, 그 자리는
  **기존 문서 재조명(-77)** 몫이다. 창을 통과했다는 건 사건 때문에 새로 생긴
  문서라는 뜻이라 배경이 아니라 사건의 일부다. 한 값에 섞어 두면 화면도 API 도
  "이 문서가 사건 자체인가, 사건이 끌어온 배경인가" 를 구분할 수 없다.

### 근거 월 — `select_completed_month` 한 벌 (2026-09-18, develop 머지)

**월 선택 규칙은 `batch.clickstream.select_completed_month` 하나다.** 직전 월 우선,
미공개·검증 실패 시 최신 완료본(통상 전전월) 폴백, `_manifest.json` 검증까지 그쪽
계약이다. `MonthlyNeighborSource.month_for(wiki, snapshot_ts)` 가 그 함수만 부른다.

~~`--clickstream-month-rule previous|event`~~ → **제거됨.** -115 브랜치가 develop
머지 전까지 쓰던 로컬 스위치였다. 규칙이 두 벌이면 한쪽만 바뀌어도 에러 없이 결과가
갈린다 — 그래서 예고한 대로 머지 시점에 한 벌로 합쳤다. CLI 인자도 같이 없앴다.

🔴 **리플레이도 완료 월 계약이다.** 명세 v0.3 §3.2 4번: "`clickstream_month` 는
스냅샷 월보다 앞선 데이터 기간이어야 한다 … 이 판단은 원본의 데이터 기간 기준이고
로컬 적재 시각 기준은 아니다. **따라서 과거 원본을 나중에 적재하는 리플레이도 같은
event-time 계약으로 계산할 수 있다.**" §11 도 사건 당월 dump 실측에 "운영 당시에는
사용할 수 없던 당월 덤프를 월 종료 후 분석한 품질 검증이며, 해당 월 스냅샷 입력으로
사용했다는 뜻이 아니다" 를 달아 두었다. "덤프가 이미 나와 있다" 는 **적재 시각
논거**라 이 계약이 명시적으로 배제한다.

이중 방어: 월을 잘못 골라도 `snapshot._is_completed_clickstream_month` 가
스냅샷 당월·미래·형식 오류 근거를 멤버 편입에서 다시 막는다.

#### 배선 regression 실측 (2024-09-01~11-01, 스냅샷 1,426 · 클러스터 6,614)

| | 완료 월 (제품 규칙, 현재 코드) | 사건 당월 (사후 QA upper bound, 옛 로컬 스위치) |
| --- | --- | --- |
| 비-루트 멤버 = edge | **6,134** | 20,161 |
| 2+ 멤버 클러스터 | **17.7%** | 34.1% |
| Milton | **1 멤버**(이웃 0) | 10 |
| Yagi | **1 멤버**(이웃 0) | 11 |
| Helene | **최대 6 멤버** | 18 |

~~"Milton·Helene·Yagi 전부 `previous` 에서 이웃 0개"~~ → **틀린 서술이었다**
(2026-09-18 DB 재확인). Milton(생성 2024-10-05)·Yagi(09-01)는 이웃 0이 맞지만
**Helene 은 6 멤버**다 — 사건일이 09-23 이라 10월 스냅샷의 직전 월(2024-09) 덤프에
이미 행이 있다. 즉 두 규칙의 차이는 품질이 아니라 **"씨드 문서가 직전 월에 이미
존재했는가"** 하나로 갈린다. 존재하지 않았던 경우는 LIVE 도 똑같이 못 봤을 정보다.

🔴 **`event` 수치를 제품 성능으로 인용하지 않는다.** 34.1%·20,161 은 배선이 이론상
최대 몇 멤버까지 붙일 수 있는지 잰 값이지 서비스가 낼 수 있는 값이 아니다.

⚠️ **이 표 전체가 탐지 성능 근거가 아니다.** 기반인 2024-09~10 replay seed 는
조회수를 적재하지 않고 옛 `편집 급증 OR 조회수 급등` detector 로 만든 것이라
WP-109 매니페스트에서 **폐기**됐다(현행 2단계 관문 -126 의 산출물이 아니다).
MVP 탐지 성능으로 인용하면 안 되고, **이웃 배선(-115)이 끝까지 이어지는지 보는
regression 데이터**로만 쓴다. 최종 MVP 리플레이 구간은 2026-07-17~2026-09-17 이다.

## 아직 안 한 것

- **Wikidata 점선 간선** — 선택. 없으면 안 그린다.
- 🔴 **비-씨드 판정 규칙(기존 문서 재조명)** — WP-77. 명세 v0.3 §3.2·§10 에
  확정 규칙(재급증 비율 ≥ 5 AND 절대 편집 ≥ 20)이 적혀 있지만 **코드에는 없다**
  (2026-09-18 재확인). 지금 이웃이 멤버가 되는 경로는 생성일 창(-51) 하나뿐이고 그건
  **추가 씨드**(`is_seed=true`)다. `Mojtaba_Khamenei` 류(2009 생성, 재조명)는
  `is_seed=false` 로 들어와야 하는데 그 경로 자체가 없다 — 재급증 입력도 안 받는다.
- ~~시점 상한(`생성 시각 <= snapshot_ts`)~~ → **통합됨** (develop 머지, 2026-09-18).
  `snapshot._build_cluster` 가 `created_at > snapshot_ts` · 완료 월 · Wikidata
  `observed_at <= snapshot_ts` 를 모두 건다.
- ~~완료 월 폴백~~ → **통합됨.** `batch.clickstream.select_completed_month` 하나가
  근거 월을 고른다. 아래 근거 월 절 참고.
