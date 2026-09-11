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
| `driver.py` | 실 데이터 소스 배선 — **골격**(아래) | — |

```
pytest cluster/tests        # 19개. Docker 불필요(pgserver 번들 PostgreSQL)
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

## 아직 안 한 것 (driver.py 골격)

실 데이터 소스 어댑터는 선행 산출물이 붙은 뒤 채운다.

- **씨드** — `spike` 테이블 조회 (detector 출력, WP-38 완료)
- **Clickstream 이웃** — 월별 덤프 인제스트 **선행 필요**(아직 이슈 없음)
- **문서 생성일** — `mediawiki_history.page_creation_timestamp`(WP-56 적재본)
- **Wikidata 관계** — `wbgetentities`/SPARQL (선택 — 없으면 clickstream 간선만)
- **이전 first_detected** — `issue_cluster` 에서 `issue_key` 별 `min(snapshot_ts)`

순수 로직·저장·스키마는 완성·검증됐고, 위 소스가 준비되면 `driver.py` 에서
`build_snapshot` 입력으로 변환해 연결한다.
