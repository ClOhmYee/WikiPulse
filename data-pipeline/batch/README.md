# batch — 과거 덤프 적재

`WP-56`. `mediawiki_history` 월 덤프를 실시간과 **같은 `edit_event` 형태**로
바꿔 적재한다. baseline 산출(`-60`)과 리플레이 검증(`-61`)의 원천이다.

명세: [docs/requirements-v0.2.md](../../docs/requirements-v0.2.md) §3.2 8번, §4, §5, §11

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
../.venv/Scripts/python.exe -m pytest       # 104개 (mediawiki + clickstream + pageview + historical-window), 네트워크 없이
```

확인하는 것:

- **덤프 출력 키 == 실시간 `normalize()` 출력 키** — pyspark 없이도 돈다.
  갈라지면 Spark `from_json` 이 조용히 null 을 채워 집계가 0이 된다
- 같은 검사를 `EDIT_EVENT_SCHEMA` 에 직접 (`test_edit_event_schema.py`,
  pyspark 있을 때만). 1차 검사를 같은 파일에 두면 pyspark 없는 환경에서 함께
  skip 되어 계약이 깨져도 아무도 모른다
- 컬럼이 78개가 아니면 멈추는지 — 위치가 하나만 밀려도 전부 틀린 값이 된다
- 네임스페이스·제목·봇 판정이 **과거 값**으로 되는지
- **덤프 밑줄 제목과 실시간 공백 제목이 같은 `(wiki, title)`·같은 파티션 키가
  되는지** (WP-79). 갈라지면 baseline 조회가 조용히 miss 한다
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
- **제목 정규화.** Clickstream 밑줄 → `wiki_page` 공백. ~~두 소스 canonical 통일은
  `WP-79`~~ → **공백형으로 확정** (2026-09-13, 명세 §5.1). ⚠️ **공통 함수
  (`producer/normalize.py`)로 통합하는 것은 아직 안 했다** — 이 파일만 남았다
  (`pageview.py` 는 2026-09-15 적용 완료). ~~결과는 같다~~ → **같지 않다**: 이 파일의
  자체 `canonical_title` 은 `replace("_", " ")` 뿐이라 **연속 축약·trim 이 없다.**
  `Hurricane__Milton` 이 공통 함수로는 `Hurricane Milton`, 여기서는 `Hurricane  Milton`
  (공백 2개)이 되어 같은 문서가 두 키로 갈라진다. 덤프에서 연속 밑줄을 본 적은 없어
  지금 틀린 결과를 내고 있진 않지만, "결과 동일"은 근거 없는 서술이었다.

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

---

# 조회수 적재 (WP-57)

`pageview.py` + `pageview_ingest.py`. Wikipedia `pageview_complete` 일별 덤프를 받아
시간별 조회수를 `(wiki, title, ts_hour, agent, views)` 로 적재한다. baseline `view_ewma`
(WP-58/-60)와 급증 2차 판정(조회수) 입력이다.

```
pageviews-{YYYYMMDD}-{agent}.bz2  ──▶  (wiki, title, ts_hour, agent, views) JSONL.gz (shard)
  project title page_id access daily hourly     대상 project·ns0 만 · access·page_id 가로질러 합산
  희소 시간 인코딩 A=0시…X=23시                   pageview_ingest.py
```

## 실행

```bash
export CONTACT_EMAIL=you@example.com      # 새로 받을 때만 필요

python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12            # 적재
python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12 --dry-run  # 건수만
python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12 --agents user,automated
```

출력: `data/pageview/{wiki}/{date}/part-*.jsonl.gz` + `_manifest.json`(존재·결손 agent 기록).

## 함정 (2026-09-09 실측, 스펙 기준)

- **agent 는 파일명에** 있고 시기마다 구성이 다르다 — 2019 user·spider / 2020 +automated /
  2025 user·automated(spider 404). 🔴 하드코딩하지 않고 후보를 순회해 **있는 것만** 적재,
  404 는 결손으로 매니페스트에 남긴다. agent 끼리 합치거나 없는 agent 를 0 으로 채우지 않는다.
- **dump page_id 를 키로 쓰지 않는다.** `-` title 337,394행이 제각각 page_id 로 뭉쳐 있고,
  정상 ns0 문서도 page_id 가 수십 개로 갈린다(null 10.56%). `(wiki, title, ts_hour, agent)`
  로만 합산한다.
- **위키 코드가 다르다** — 덤프는 `en.wikipedia`, mediawiki_history 는 `enwiki`. `project_for`
  가 역매핑하고, 미등록 위키는 `UnsupportedWiki` 로 멈춘다(조용히 틀린 위키 방지).
- **`:` 단순 필터 금지.** 정상 제목에 콜론이 들어간다. 알려진 namespace prefix 집합만 제외한다.
- **시간별 합 != daily_total 이면 `SchemaMismatch`.** 형식 손상·인코딩 오류를 조용히 넘기지 않는다.
- **canonical 적용 시점이 `is_content_title` 뒤·합산 앞이다** (WP-79, 2026-09-15).
  덤프 밑줄 제목을 공통 `canonical_title` 로 공백형에 맞춘다 — 편집 경로와 같은 함수다.
  ⚠️ 순서를 옮기면 조용히 틀린다: 앞으로 당기면 prefix 목록이 `User_talk` 라 `User talk` 와
  일치하지 않아 namespace 문서가 새어 들어오고, 뒤로 미루면 `acc` 가 이미 원래 표기로
  그룹을 갈라 놓아 `Hurricane_Milton` 과 `Hurricane__Milton` 이 별개 키가 된다.
  회귀는 `test_canonical_이_namespace_필터보다_뒤에_걸린다`·`test_표기만_다른_같은_문서가_한_키로_합산된다`.
- **제목에 리터럴 공백은 못 온다.** 6컬럼을 `" "` 로 자르는 형식이라 공백이 든 제목은 7필드가
  되어 `SchemaMismatch` 다. 그래서 "공백형 제목이 덤프에 섞이는" 경우는 테스트하지 않는다 —
  덤프 안에서 실제로 흔들릴 수 있는 건 밑줄 표기(연속·앞뒤)뿐이다.

## 메모리

`aggregate()` 는 한 agent-일 파일을 dict 로 누적한다. 전체 enwiki 는 Spark 경로(WP-58)가
맡고, 이 CLI 는 **검증 슬라이스**(Hormuz 2025-06·Milton 2024-10 등)용이다.

## 아직 안 한 것

- **실 덤프 적재·HDFS** — WP-28 완료 후. 하루 user 542 MiB + automated 706 MiB ≈ 1.2 GiB
  (스펙 실측). 실측 크기·소요는 그때 명세 §11 에. 위 오프라인 테스트로 파싱·필터·합산·CLI 배선만 검증했다.
- **`wiki_page.id` 해석** — 스펙대로 `(wiki, title)` 로만 적재. id 해석은 후속 적재 단계 책임.
  title 은 이 단계에서 이미 canonical 이라, 해석 단계가 다시 정규화할 필요는 없다 (§5.1).
- **기존 산출물 재생성** — 여기까지 적재된 JSONL 은 canonical 도입 **전** 산출물이라 밑줄
  제목을 담고 있다. 논리적으로 재생성 대상이며, 읽을 때 밑줄을 바꾸는 우회는 쓰지 않는다
  (두 표기가 공존하는 게 이 규칙이 없애려는 실패 모드다). -56 산출물과 묶어 후속 이슈로 — 명세 §5.1.

월 단위는 `--month YYYY-MM` 로 하루씩 순회한다(일별 매니페스트로 이어받기, 결손일 기록, 다 되면
요약 출력). `SchemaMismatch` 는 전체 실행을 멈춘다(형식 손상은 하루 문제가 아니다).

---

# Historical Window 집계 (WP-58)

`historical_windows.py` + `historical_windows_ingest.py`. 편집 적재본(WP-56)과
조회수 적재본(WP-57)을 읽어 baseline(`spike/baseline.py`)이 읽을 **문서 × 시간
윈도우** 데이터셋을 만든다. 이 형태가 없어 baseline 배치가 통째로 no-op 이던 걸 채운다.

```
edit_event JSONL.gz (-56) ┐
                          ├─▶ (wiki, title, window_start, hour_of_day, edit_count, editor_count, views) JSONL.gz
pageview JSONL.gz  (-57) ┘        1시간 윈도우 · 봇 제외 편집 · agent 가로질러 조회 합산
```

## 실행

```bash
python -m batch.historical_windows_ingest \
    --edits ./out/enwiki/2025-06 \
    --views ./data/pageview/enwiki \
    --out ./data/baseline-input/enwiki/2025-06

... --agents user,automated    # baseline 에 쓸 agent 만 합산 (기본: 전부)
... --dry-run                   # 행 수만
```

출력: `{out}/part-*.jsonl.gz` + `_manifest.json`.

## 🔴 집계 계약은 스트리밍과 한 벌이어야 한다

`streaming/edit_windows.py`(실시간)와 정의가 갈리면 `edit_z` 가 에러 없이 조용히 틀린다.

- **윈도우 = 1시간.** 스트리밍 `WINDOW_SIZE` 와 맞춘다. baseline 은 24 슬롯(`hour_of_day`)이라
  1시간이 자연스러운 정합값이다.
- **봇 필터 = `is_bot` 참 편집 제외.** 스트리밍 `~coalesce(is_bot, False)` 와 같은 판정.
- **`editor_count` 를 함께 센다** (WP-85). 급증 판정의 편집자 하한이 이 값을 본다.
  🔴 스트리밍은 `approx_count_distinct`(근사), 배치는 정확값이라 **두 값이 갈린다.**
  ~~편집자 1~10명 구간에서 불일치 0건~~ → 표본을 200,000 events 로 키우니 **21건 불일치**,
  그중 13건이 `2 → 1` 로 편집자 하한을 뒤집었다 (2026-09-15, WP-83).
  `rsd=0.01` 이면 0건 — `streaming.EDITOR_COUNT_RSD` 주석 참고.
- **문서 키 = `(wiki, title)`, title 은 canonical 공백형.** -56·-57 과 같다. dump page_id 는
  안 쓴다 — `wiki_page.id` 해석은 적재(WP-60) 책임.
  🔴 **읽는 지점에서 `canonical_title` 을 통과시킨다** (WP-92). -79 이전에 만든
  편집 샤드가 밑줄형이라 세대가 섞이는데, 안 맞추면 편집·조회수 join 이 **한 건도 안 맞고**
  같은 문서·같은 시각이 `views=0` 행과 `edit_count=0` 행 둘로 쪼개진다. 멱등이라 신세대
  샤드에는 무영향이다.
  ⚠️ **스트리밍은 이 보정을 안 한다** — `producer/normalize.py` 가 Kafka 에 넣기 전에 이미
  맞춘다. 규칙을 Spark 표현식으로 또 구현하면 파이썬 판과 갈릴 수 있어서 한 곳에만 둔다.
  이 비대칭은 `tests/test_stream_batch_parity.py` 가 명시적으로 고정한다.
- **`hour_of_day` 정의(UTC 시 0~23)는 `spike/baseline.py` 의 Spark 판과 같아야 한다.**
  Python `weekday()` 월=0 == Spark `(dayofweek+5)%7` 월=0. 테스트로 알려진 날짜를 고정했다.
- 편집·조회는 `(wiki,title,hour)` 기준 **full outer join** — 한쪽만 있는 시간도 0 으로 남긴다
  (baseline 이 `edit_z`·`view_ewma` 를 둘 다 잡는다).

### 대조 실측 (WP-83, 2026-09-15)

선언만으로는 갈린 걸 못 잡는다. 같은 표본을 두 경로에 넣어 확인했다.

```bash
cd data-pipeline && python -m pytest tests/test_stream_batch_parity.py   # 12개
```

실덤프 **200,000 events**(enwiki 2025-06 shard 0) 대조 결과:

| 항목 | 결과 |
| --- | --- |
| 윈도우 수 | 118,521 — **키 집합 완전 일치** (한쪽에만 있는 키 0) |
| `edit_count` | **불일치 0건** |
| `editor_count` | 🔴 **21건 불일치** — 전부 과소 계수 `{2→1: 13, 3→2: 4, 4→3: 1, 5→4: 3}` |

`2 → 1` 13건은 **편집자 하한을 뒤집어 진짜 급증을 떨어뜨린다**(정확 editor≥2 윈도우 5,427의
0.240%). `rsd=0.01`·`rsd=0.005`·정확 `count_distinct` 는 전부 불일치 0건이었다.

✅ **`EDITOR_COUNT_RSD = 0.01` 로 확정** (2026-09-15, WP-89). 같은 표본을 다시 돌려
`edit_count`·`editor_count` 둘 다 **불일치 0건**을 확인했다. 정확 `count_distinct` 도 0건이지만
윈도우마다 편집자 집합을 통째로 들고 있어야 해 안 골랐다.

**무엇을 "같다"고 보는가.** 스트리밍은 1시간/5분 **슬라이딩**, 배치는 정각 **tumbling** 이다.
슬라이드가 창 길이를 나누므로 **정각에서 시작하는 윈도우**가 항상 있고 그게 배치와 같은
구간이다. 대조는 그 윈도우만 본다 — 나머지 슬라이딩 윈도우는 배치에 대응물이 없다.

⚠️ **`collect()` 는 timestamp 를 드라이버 로컬 시간대(KST)의 naive datetime 으로 준다.**
`spark.sql.session.timeZone=UTC` 로도 안 막힌다 — 대조 테스트가 처음에 전부 9시간 밀려
실패했다. 시각 포맷·필터를 **Spark SQL 안에서** 끝내야 한다
(`date_format`·`F.minute`). 이미 알려진 입력 쪽 함정(naive datetime 을 `createDataFrame`
에 주면 밀린다)의 **출력판**이고, 역시 에러가 안 난다.

## ⚠️ API_SPEC §2.4 의 baseline·pulse 와 다른 값이다

여기 산출물은 시간대별 편집·조회 원자료다. `frontend/docs/API_SPEC.md` §2.4 의 `baseline`
(일 단위 편집 횟수)·`pulse`(배수)와 **이름만 같고 정의가 다르다.** 화면용 일 단위 baseline
유도는 별건(백엔드·프론트 합의).

## 아직 안 한 것

- **Spark parquet 출력·"배치 == 스트리밍" 표본 대조** — 지금은 형제 적재(-56·-57)와 같은
  순수 파이썬·JSONL.gz 경로다. 집계 semantics 는 순수 함수로 한 벌 고정해 두었으니 Spark
  판이 같은 계약을 부르게 한다. 실규모 실행은 Spark 2노드(WP-27)·HDFS
  (WP-28)가 서면 잇는다.
  - ~~venv 3.14 에서 PySpark 워커가 죽어 로컬 실행 불가~~ → **로컬에서 돈다** (2026-09-14
    정정, WP-82). venv 는 **3.11.15** 로 PySpark 3.5 지원 범위(3.8~3.11) 안이다 —
    시스템 파이썬(3.14)을 보고 venv 도 그럴 것이라 단정한 서술이었다. 워커가 죽은 실제
    원인은 버전이 아니라 `PYSPARK_PYTHON` 미설정이고, 증상은 `CreateProcess error=2`
    (워커로 띄울 파이썬 **경로**를 못 찾음)다. `conftest.py` 가 그걸 고정하면 실제로 돈다 —
    WP-60 이 로컬 Spark 로 `build_baseline` 을 돌려 순수 판과 값 일치를 확인했다
    (`spike/tests/test_baseline_spark.py`).
  - ⚠️ **자체 `pytest.ini` 를 쓰는 패키지는 바깥 `conftest.py` 가 로드되지 않는다.** rootdir 이
    그 패키지로 잡혀서다. `spike/` 가 그래서 `spike/tests/conftest.py` 를 따로 둔다. 여기
    `batch/` 도 자체 `pytest.ini` 가 있으니 Spark 를 쓰는 테스트를 추가하면 같은 게 필요하다.
  - ⚠️ **naive `datetime` 을 `createDataFrame` 에 주면 드라이버 로컬 시간대(KST)로 해석돼
    9시간 밀린다.** 세션 `timeZone=UTC` 로도 안 막힌다. `hour_of_day` 가 통째로 어긋나는데
    **에러가 안 난다** — 타임스탬프는 tz-aware 로 넘긴다 (2026-09-14 실제로 겪음).
  - 🔴 "배치 == 스트리밍" 대조 자체는 이 README 정정 범위 밖이다 — 별건 이슈다.
- **실데이터 규모 집계** — Hormuz 2025-06·Milton 2024-10 실적재는 -56·-57 실덤프 뒤. `aggregate_*`
  가 dict 누적이라 검증 슬라이스용이다(전체 enwiki 는 Spark).
