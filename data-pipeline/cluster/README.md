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

## 실행 — spike → issue_cluster (WP-99)

```bash
python -m cluster.driver --dsn "$DATABASE_URL" --source replay
python -m cluster.driver --dsn ... --source replay --snapshot-ts 2024-10-07T14:00:00Z
python -m cluster.driver --dsn ... --source replay --dry-run
```

`spike`(WP-94 런타임 출력) → 씨드 → `build_snapshot` → `persist_snapshot`.
로직·점수·게이트는 이 파일이 정하지 않는다 — 전부 위 `snapshot.py`·`score.py` 자산이다.

**스냅샷 시점은 `spike.detected_at` 의 고유값 하나당 하나다.** 새 문턱이나 lookback 창을
만들지 않으려고 이렇게 했다 — 기존 행을 다시 묶기만 한다.

🔴 **이 DB 입력 경로는 `--source replay` 전용이다.** `spike` 테이블에 provenance(출처)
컬럼이 없어 어떤 행이 리플레이 산출물이고 어떤 행이 LIVE 산출물인지 **가릴 수 없다.**
그대로 두면 리플레이 spike 를 읽어 `issue_cluster.source='live'` 로 저장하는 거짓 라벨링이
가능한데, API·화면은 그걸 실시간 이슈로 그리고 **에러는 안 난다.** 그래서
`require_spike_source` 가 `replay` 외를 거부하고 CLI `--source` 도 `replay` 만 받는다.
같은 이유로 조회 함수 `load_seeds_from_spike` 는 `source` 를 **아예 받지 않는다** —
인자로 있으면 "이 source 로 거른다"로 오해된다. 라벨은 `build_snapshot_at` 이 붙인다.
**LIVE 연결은 `spike` 에 provenance 컬럼을 두는 계약과 함께 별도 스토리에서 한다**
(스키마 변경이라 WP-99 범위 밖).

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

## 아직 안 한 것

- **Clickstream 이웃(비-씨드)** — `load_clickstream_neighbors` 는 구현돼 있지만
  적재본이 0건이다(-81 코드는 Done, 산출물 없음). 덤프가 생기면 `build_neighbor_inputs`
  결과를 `build_snapshot_at(neighbors=...)` 으로 넘기면 된다 — 계약이 이미 그 형태다.
- **문서 생성일** — `load_creation_dates` 는 골격. **비-씨드 게이트 전용**이라 씨드 단독
  경로에서는 호출되지 않는다. 이웃 배선과 같이 채운다.
- **`load_pages_by_title`** — 이웃 제목 → `page_id` 해석. 같은 이유로 아직 없다.
- **Wikidata 점선 간선** — 선택. 없으면 안 그린다.
- **비-씨드 판정 규칙(기존 문서 재조명)** — WP-77, 이 모듈 범위 밖.
