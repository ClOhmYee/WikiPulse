# batch — 과거 덤프 적재

`WP-56`. `mediawiki_history` 월 덤프를 실시간과 **같은 `edit_event` 형태**로
바꿔 적재한다. baseline 산출(`-60`)과 리플레이 검증(`-61`)의 원천이다.

명세: [docs/requirements-v0.1.md](../../docs/requirements-v0.1.md) §3.2 8번, §4, §5, §11

```
mediawiki_history TSV.bz2  ──▶  edit_event JSONL.gz (shard)
  78컬럼 · 헤더 없음             15필드 · source="dump"
  ingest.py                      schema.py + normalize_dump.py
```

## 실행

```bash
export CONTACT_EMAIL=you@example.com      # 새로 받을 때만 필요

python -m batch.ingest --wiki enwiki --range 2025-06            # 적재
python -m batch.ingest --wiki enwiki --range 2025-06 --dry-run  # 건수만
python -m batch.ingest --wiki aawiki --range all-time           # 소형 위키
```

시간 범위는 위키마다 다르다 — enwiki·commonswiki·wikidatawiki 는 `YYYY-MM`,
중형 위키는 `YYYY`, 나머지는 `all-time` (덤프 readme 의 분할 규칙).

출력:

```
out/{wiki}/{range}/part-00000.jsonl.gz
                   part-00001.jsonl.gz
                   _manifest.json        ← 이 파일이 있으면 완료된 단위다
```

## 입력 포맷 (2026-09-08 실측)

`2026-08.aawiki.all-time` (440 KB, 12,075행)을 직접 받아 확인했다.

- **헤더 행이 없다.** 78컬럼 TSV, bz2. 컬럼 이름·순서는 wikitech 스키마 문서에서
  받아 실데이터로 정렬을 검증했다 — `schema.py` 참고
- 배포 경로: `/{snapshot}/{wiki}/{snapshot}.{wiki}.{range}.tsv.bz2`. 스냅샷은
  **최근 2개 판만** 보관된다
- 검증 구간 크기 (HEAD 실측): enwiki `2025-06` **491 MB**, `2024-10` **569 MB**

## 함정

**`event_entity` 가 3종이다** — `revision` · `user` · `page`. 표본에서 편집이 아닌
행이 **61%**(12,075 중 7,381)였다. 실시간 경로(recentchange)에는 없는 필터 축이라
가장 먼저 거른다.

🔴 **`_historical` 변종을 쓴다.** 이유는 데이터 유실 회피가 아니라 **시점 정합성**이다 —
revision 이 일어난 그 시점의 namespace·title 을 재현해야 Historical/Replay 데이터가
실시간 경로가 포착했을 값과 같은 시점을 가리킨다. 현재 컬럼은 "지금" 상태라 과거
시점 재현에 쓸 수 없다.

결측률은 위키마다 크게 다르다. **아래 두 수치를 섞지 말 것.**

**[aawiki all-time 표본 — 2026-09-08]**

- 현재 `page_namespace`·`page_title` 결측이 매우 높게 관찰됐다
  (revision 4,694행 중 2,968 / ns0 677행 중 342)
- `_historical` 로는 그 시점의 namespace·title 이 복원됐다
- ⚠️ **소형 위키 all-time 표본 결과다. enwiki 특성으로 일반화하지 않는다** — 아래
  enwiki 실측과 자릿수가 다르다

**[enwiki 2025-06 실측 — 2026-09-09 로컬]**

| 컬럼 | 결측 (revision 4,871,806행 기준) |
| --- | --- |
| `page_namespace` (현재) | 373 (0.008%) |
| `page_title` (현재) | 373 (0.008%) |
| `page_namespace_historical` | **0** |
| `page_title_historical` | **0** |

⚠️ 현재 필드와 `_historical` 사이의 **namespace 이동 차이는 측정하지 않았다.** 위 값은
결측만 센 것이라 "현재 필드를 쓰면 N건이 유실된다"로 읽으면 안 된다.

**타임스탬프가 초 정밀도다.** 표본 전부 `.0` 으로 끝난다. 실시간은 `meta.dt`(ms)를
쓰는데 — 최상위 `timestamp` 가 초 단위라 같은 초의 편집을 구분 못 해서 그랬다
([../README.md](../README.md)) — **덤프에는 그 ms 가 아예 없다.** 리플레이 데이터는
시간 해상도가 구조적으로 낮다. 윈도우 집계에는 영향이 없다.

**증분을 덤프가 직접 준다.** `revision_text_bytes_diff` 는 결측 0, 음수 정상.
실시간처럼 `new - old` 를 계산하지 않는다.

⚠️ **`domain` 과 `meta_id` 는 덤프에 없다** (78컬럼 확인). deterministic 하게 만든다 —
`enwiki` → `en.wikipedia.org`, `dump:{wiki}:{revision_id}`. 기본값 `None` 을 넣지
않는다. 도메인 규칙이 다른 위키(`commonswiki` 등)는 추측하지 않고 `UnsupportedWiki`
로 멈춘다 — 조용히 틀린 도메인을 만드는 것보다 낫다.

## ⚠️ event_type(edit/new)은 파생 규칙이다

덤프의 `event_type` 은 `event_entity="revision"` 행에서 **전부 `create`** 라
실시간의 `edit`/`new` 구분을 주지 않는다. 현재 규칙:

```
page_first_edit_timestamp 가 있고 == event_timestamp  ->  "new"
그 외 (결측 포함)                                     ->  "edit"
```

🔴 **이것은 EventStreams 의 `type` 을 복원한 값이 아니다.** live `edit_event` 계약에
맞추기 위한 파생 규칙이다 (2026-09-08 팀 결정).

`revision_parent_id` 를 주 신호로 쓰지 않는 이유: 표본 ns0 677행 중 583행(86%)이
결측·0 이라 "부모 없음"이 아니라 사실상 "미상"이다. 같은 표본에서
`event_timestamp == page_first_edit_timestamp` 는 43행이었다.

**enwiki 2025-06 sanity check (2026-09-09 로컬 실측).** 세 신호를 비교했다.

| 신호 | 건수 |
| --- | --- |
| 현재 규칙 (`event_ts == page_first_edit_ts`) | 53,596 |
| `event_ts == page_creation_ts` | 52,231 |
| `page_creation_ts` 가 해당 월인 고유 `page_id` | 55,709 |

세 값이 약 4% 이내로 모였다 — **큰 이상이 발견되지 않았다는 정도**이지 파생 규칙이
정확하다는 증명이 아니다. new 비율은 1.59% (53,596 / 3,361,013) 였다.

앞으로도 비율이 비정상으로 보이면 이 로직을 바로 고치지 말고 **별도 이슈로 올린다.**

다운스트림 영향은 작다 — `event_type` 으로 분기하는 코드가 없다. `EDIT_TYPES`
필터를 통과하면 되고, `edit_windows.py` 는 `count(*)` 만 세며, detector 의
`is_new_page` 는 baseline 두께에서 나온다.

## 재실행 안전성

1. **다운로드** — 받은 덤프는 캐시(`./dumps`)에 남는다. `.part` 로 받아 완료 후
   이름을 바꾸므로 끊긴 파일을 완성본으로 착각하지 않는다. 다시 돌리면 HTTP Range
   로 이어받는다 (491 MB 를 처음부터 다시 받지 않는다). 캐시에 있으면 네트워크를
   타지 않아 `CONTACT_EMAIL` 없이도 재실행·dry-run 이 된다
2. **정규화** — 임시 디렉터리에 쓴 뒤 통째로 옮기고 마지막에 매니페스트를 남긴다.
   매니페스트가 있으면 그 `(wiki, range)` 는 건너뛴다(`--force` 로 무시). 절반만
   남은 출력이 완료본으로 보이는 상태가 생기지 않는다

## shard

한 달치를 gzip 하나로 만들면 Spark 가 분할해 읽지 못해 태스크 1개로 직렬화된다.
`--shard-records` 로 나눈다.

⚠️ **기본값 500,000 은 잠정값이다 — 최적값으로 확정된 것이 아니다.**

enwiki 2025-06 로컬 실측에서 3,361,013 events → **7 shard**, 압축 크기 median 21.6 MiB
(min 15.8 / max 21.8) 로 정상 동작하는 것까지만 확인했다. gzip 은 분할이 안 돼서
shard 개수가 곧 Spark 태스크 수의 상한인데, **실제 Spark 실행 결과가 아직 없다.**
`WP-58` 에서 실 태스크 수·executor 활용률·처리 시간을 재고 필요하면 조정한다.

## 출력 위치

지금은 **로컬 파일시스템만** 쓴다. HDFS 2노드(`WP-28`)가 아직 없어서,
여기에 HDFS 클라이언트를 박아 두면 인프라 없이는 파싱·정규화·테스트조차 못 돈다.
출력 경로를 만드는 곳이 `ShardWriter` 한 군데뿐이라 HDFS 가 서면 그 자리만 잇는다.

## 테스트

```bash
cd data-pipeline/batch
../.venv/Scripts/python.exe -m pytest       # 62개 (mediawiki + clickstream), 네트워크 없이
```

확인하는 것:

- **덤프 출력 키 == 실시간 `normalize()` 출력 키** — pyspark 없이도 돈다.
  갈라지면 Spark `from_json` 이 조용히 null 을 채워 집계가 0이 된다
- 같은 검사를 `EDIT_EVENT_SCHEMA` 에 직접 (`test_edit_event_schema.py`,
  pyspark 있을 때만). 1차 검사를 같은 파일에 두면 pyspark 없는 환경에서 함께
  skip 되어 계약이 깨져도 아무도 모른다
- 컬럼이 78개가 아니면 멈추는지 — 위치가 하나만 밀려도 전부 틀린 값이 된다
- 네임스페이스·제목·봇 판정이 **과거 값**으로 되는지
- 두 번 돌려도 이벤트가 늘지 않는지, 반쪽 출력이 완료본으로 안 보이는지
- dry-run 이 파일을 안 만드는지, shard 가 이벤트를 잃지 않는지

## enwiki 2025-06 로컬 실측 (2026-09-09)

🔴 **로컬 파일시스템 실측이다. HDFS 실측이 아니다.** HDFS 적재 수치는
`WP-28` 완료 후 따로 잰다.

| 항목 | 값 |
| --- | --- |
| 입력 | `2026-08.enwiki.2025-06.tsv.bz2` — 515,334,641 bytes |
| 읽은 행 | 5,501,827 |
| 출력 event | 3,361,013 |
| 파싱 오류 | **0** |
| 출력 크기 | 145.3 MiB (원본의 29.6%) |
| shard | **7** — 500,000 × 6 + 361,013 |
| shard 압축 크기 | median 21.6 MiB (min 15.8 / max 21.8) |
| 처리 시간 | 12분 51초 |
| peak memory | **31 MB** |
| 재실행 | manifest 를 보고 skip. shard 개수·바이트 동일, 중복 생성 없음 |

peak 31 MB 는 491 MB bz2 를 줄 단위로 흘리는 설계가 실제로 동작한다는 뜻이다.

명세 §11 은 아직 갱신하지 않았다 — HDFS 적재까지 끝난 뒤 한 번에 적는다.

## 아직 안 한 것

- **HDFS 적재** — `WP-28` 완료 후 같은 스토리에서 잇는다.
  `hdfs dfs -du` 검증과 실측 크기·소요시간 기록(명세 §11)도 그때
- **조회수 덤프** — `pageview_complete` 는 별도 스토리
- **Spark 에서의 실제 읽기** — shard 개수가 태스크 수에 어떻게 걸리는지는
  `WP-58` 에서 잰다. 위 로컬 수치만으로 shard 기본값을 확정하지 않는다

---

# Clickstream 적재 (WP-81)

`clickstream.py` + `clickstream_ingest.py`. Wikipedia Clickstream 월별 덤프를 받아
문서 간 이동(`link`)만 `(prev, curr, n)` 로 적재한다. 펄스맵 클러스터링
(`data-pipeline/cluster`, `WP-75`)의 이웃 후보·간선·가중치 원천이다.

```
clickstream-{wiki}-{YYYY-MM}.tsv.gz  ──▶  (prev, curr, n) JSONL.gz (shard)
  prev curr type n · 헤더 없음            link 행만 · 제목 공백 정규화
  n>=10 (덤프 자체 하한)                   clickstream_ingest.py
```

## 실행

```bash
export CONTACT_EMAIL=you@example.com      # 새로 받을 때만 필요

python -m batch.clickstream_ingest --wiki enwiki --month 2025-06            # 적재
python -m batch.clickstream_ingest --wiki enwiki --month 2025-06 --dry-run  # 건수만
```

출력: `data/clickstream/{wiki}/{month}/part-*.jsonl.gz` + `_manifest.json`.
다운로드·shard·매니페스트 장치는 위 mediawiki 적재와 같은 것을 재사용한다
(`ShardWriter`·`download`·재실행 skip).

## 무엇을 남기나

- **`type='link'` 만.** `external`(검색·외부 유입)·`other`(같은 문서)는 문서 간
  이동이 아니라 이웃 신호가 아니다.
- **문턱 없음.** 위키미디어가 이미 `n>=10` 만 공개한다. `n` 은 `cluster_member.weight`
  로만 쓰고, 클러스터 포함 여부는 생성일 창이 정한다 (명세 §3.2 4번·§10 폐기 절).
- **제목 정규화.** Clickstream 밑줄 → `wiki_page` 공백. ⚠️ 두 소스 canonical 통일은
  `WP-79` — 확정되면 `canonical_title` 을 그 규칙으로 교체한다.

## 이웃 조회

`clickstream.neighbors_for(rows, seeds)` 가 덤프를 **한 번** 훑어 씨드별 이웃을 모은다.
씨드가 `prev` 면 나가는 이웃, `curr` 면 들어오는 이웃이고, 양방향은 `n` 을 합쳐
동시 열람 강도 하나로 본다. `cluster/driver.py` 가 이걸 읽어
`cluster.snapshot.Neighbor`(+ `wiki_page` page_id·`mediawiki_history` 생성일)로 만든다.

## 아직 안 한 것

- **실 덤프 적재·HDFS** — `WP-28` 완료 후. enwiki 월 ~471 MB gz, 실측 크기·
  건수는 그때 명세 §11 에 적는다. 위 오프라인 스모크(가짜 덤프)로 CLI 흐름만 검증했다.
- **page_id·생성일 조인** — `driver.build_neighbor_inputs` 가 자리는 잡았고, `wiki_page`
  조회와 `mediawiki_history`(`WP-56`) 생성일 어댑터가 붙으면 실데이터로 흐른다.
