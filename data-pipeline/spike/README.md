# spike — 급증 판정

`WP-38`. 편집·조회수 급증을 판정하는 수식과 기준선 산출.

명세: [docs/requirements-v0.1.md](../../docs/requirements-v0.1.md) §3.2, §6, §11

```
28일 기준선 (baseline.py, Spark 배치)
   문서 × 시간대(0..23, UTC) EWMA
        │
        ▼
급증 판정 (detector.py, 순수 함수)
   기존 문서: (편집 z≥3 AND ≥10건 AND 편집자≥2)  OR  (조회수 z≥3 AND ≥2배 AND ≥100회)
   신규 문서: 절대 편집수 ≥10 AND 편집자≥2 (baseline 없음)
```

## 수식을 이렇게 정한 근거 (실측 2026-09-08)

**Strait of Hormuz 조회수, 2025-06** (per-article API):

| 구간 | 조회수 | z |
| --- | --- | --- |
| 사건 전 18일 | 391 ± 55 | −1.3 ~ **+1.9** |
| 사건 첫날 6/12 | 1,007 (2.6배) | **11.2** |
| 정점 6/22 | 291,824 (746배) | 5,311 |

**z = 3이 평상시 최대(1.9)와 사건 최소(11.2) 사이에 깨끗이 앉는다.** 오탐 없이
사건을 다 잡는다. 배수로는 6/12의 2.6배가 최저 신호라 조회수 최소 2배도 건다.

**절대 하한(편집 ≥ 10)이 왜 필요한가.** 평소 편집이 0~1건인 문서는 표준편차가
작아 2건만 돼도 z가 폭발한다. z만으로는 얇은 baseline이 오탐을 낸다.

**급증에는 두 종류가 있다.** Hurricane Milton은 사건 당일 새로 생긴 문서라
baseline이 없다 — z를 못 낸다. 신규 문서는 절대 편집수로만 판정한다
(생성 당일 40편집).

## 편집자 하한 (WP-85, 2026-09-15 실측)

편집 수만으로는 **한 사람이 몰아서 정리한 것**과 **여러 사람이 사건을 고치는 것**이 구분되지
않는다. `MIN_DISTINCT_EDITORS = 2` 로 앞쪽을 뺀다.

실덤프 4개월(`2025-05`·`2025-06`·`2024-09`·`2024-10`, 총 1.9 GB)로 사건 12건·대조군 14건을
재생한 결과:

| 설정 | 재현율 | 대조군 오탐 |
| --- | --- | --- |
| 편집자 하한 없음 (기존) | 10/12 | **395건 · 14/14 문서** |
| `editor_count >= 2` | 10/12 (변화 없음) | **101건** (74% 감소) |
| + 슬롯을 `hour_of_day` 로 | 10/12 | 57건 (86% 감소) |

오탐을 내던 대조군은 `List_of_people_named_Peter`(시간 최대 82편집 — Milton 의 44 보다 많다)·
`Deaths_in_2025`·`Timeline_of_science_fiction`·TV 시즌 문서처럼 **상시 편집이 많은 비사건
문서**다. 명세 §3.2 2번의 "1인 반복 편집은 거른다"가 여태 코드에 없었다.

🔴 **임계는 안 건드렸다.** `EDIT_Z_THRESHOLD`(3)·`MIN_ABSOLUTE_EDITS`(10)·
`MIN_BASELINE_SAMPLE_DAYS`(7)는 WP-38 확정 자산 그대로다.

⚠️ 남은 후속: **6시간 창**
(재현율 92%·오탐 40건). 창 길이는 스트리밍 `WINDOW_SIZE` 와 함께 움직여야 해서
**WP-83 이 선행**이다 — 배치만 바꾸면 `edit_z` 가 에러 없이 어긋난다.


## 슬롯 폭 — 재봤고, 안 바꿨다 (WP-88, 2026-09-15)

`hour_of_day`(24) 를 6시간 4슬롯으로 넓히는 안을 실측하고 **보류**했다.
전문·스크립트는 [`ai/slot-width/RESULT.md`](../../ai/slot-width/RESULT.md).

**얇은 건 맞다.** 슬롯당 `sample_days>=7` 도달률(월 20편집 이상, 28일 창):

| 1h (24) | 3h (8) | 6h (4) | 일 (1) |
| --- | --- | --- | --- |
| **1.5%** | 5.4% | 13.0% | 58.1% |

월 편집 수 구간별(1h): 20~49편집 **0.8%** · 100~299 39.9% · 300~999 83.3%.
→ **24슬롯 z 경로는 사실상 월 300편집 이상 문서 전용이다.**

**넓히면 도달률은 오른다.** 판정 대상 윈도우 기준 z 경로 가능 23% → 81%, 겹치는
구간에서 임계 판정 97.9% 일치.

🔴 **그런데 좋아지는 게 없었다.** 실제로 바꿔 -85 회귀를 돌린 결과:

| | 1h | 6h |
| --- | --- | --- |
| 재현율 | 10/12 | 10/12 |
| 대조군 오탐 | 49건 | 49건 |

폭 2·3·4·6·12h sweep 도 42~51 범위 잡음이다. 원인은 `Deaths_in_2024` 오탐 23건 중
**21건이 z 를 통과**한다는 것 — 상시 편집 목록 문서는 자기 기준선 대비로도 진짜 튄다.
오탐 원인은 "z 가 죽어서" 가 아니었다.

발단이던 `Boeing_787_Dreamliner` 도 사건 전 28일 편집일이 **5일**이라 일 단위
슬롯으로도 미달이다 — 슬롯 폭 문제가 아니라 그 문서가 평소에 거의 안 고쳐져서다.

⚠️ **다음 사람이 빠질 함정**: `EDIT_Z_THRESHOLD = 3` 은 선언돼 있지만 판정 대상
윈도우의 **23%** 에서만 돈다. 튜닝해도 변화가 없는 게 정상이다.

구현은 `feature/WP-88-slot-width`(MR !56, 미머지)에 남겨 뒀다. 오탐의 남은
지렛대는 -88 선택지 4번 — 신규 문서 경로를 "진짜 신규" 와 "관측이 드문 기존 문서" 로
쪼개는 것이고, 그때 슬롯 의미를 같이 정한다(마이그레이션 두 번보다 한 번).

## 조회수 **데이터**는 늦게 온다 (신호가 늦다는 뜻이 아니다)

⚠️ 실측: Pageviews API는 **일 단위, 하루 지연**이다 (시간별은 400 에러). 시간별
문서 조회수는 `other/pageviews` 덤프뿐이고 봇 구분이 없다. "시간별 + 봇 구분"을
동시에 주는 소스가 없다.

그래서 2차 판정(조회수)이 1차(편집)보다 반드시 늦다. `detect()`는 조회수가
아직 없으면(`views=None`) 편집만으로 **감지됨** 상태를 내보내고, 조회수가
들어오면 **확정**으로 올린다. 명세 §3.2 7번의 3단계 상태가 이 지연을 그대로
드러낸다.

⚠️ **여기서 말하는 지연은 데이터 도착 지연이다.** 사건에 대한 **반응 시점**은 오히려 조회수가
빠른 경우가 많다 — 아래 "신호 시차" 절. 둘은 다른 사실이라 섞으면 안 된다.

## 신호 시차 — 조회수가 먼저 반응하는 문서가 있다 (WP-86, 2026-09-15 실측)

`signal_lag.py` 가 두 신호의 **최초 임계 통과일**을 각각 구해 차를 낸다. 임계는
`detector.py` 것을 import 해서 쓴다 — 여기서 새로 정하지 않는다.

```bash
python -m spike.signal_lag --edits ./out/enwiki/2025-05 --edits ./out/enwiki/2025-06 \
    --event-date 2025-06-12 --title Strait_of_Hormuz --title Air_India_Flight_171
```

사건 10건 결과 (전문·원자료는 `ai/signal-order/RESULT.md`):

| 문서 유형 | 조회수 탐지 | 편집 탐지 |
| --- | --- | --- |
| 기존 문서 6건 | **6/6** | 4/6 (`Strait_of_Hormuz`·`Papal_conclave` 미탐, `Hassan_Nasrallah` **+9일**) |
| 신규 문서 4건 | 2/4 | **4/4** |
| 합집합 | — | **10/10** |

**두 신호가 서로 다른 문서 유형을 맡는다.**

- 기존 문서는 사람들이 **읽으러** 온다. `Strait_of_Hormuz` 는 사건 정점에도 시간당 최대
  8편집이라 `MIN_ABSOLUTE_EDITS=10` 에 걸려 영영 안 잡힌다.
- 신규 문서는 **조회수 baseline 이 원리적으로 없다.** 문서가 사건 당일 생겨 이전 관측이
  아예 없다 — `Hurricane_Milton`·`Air_India_Flight_171` 의 조회수 미탐은 임계 문제가 아니다.

그래서 **조회수를 전면 1차로 뒤집는 안은 채택 불가**다(신규 문서를 통째로 놓친다).
✅ **기존 문서 경로만 AND → OR 로 확정** (2026-09-15, WP-90).

전환하며 `page_baseline.view_stddev` 를 새로 만들었다(`V4`). 조회수가 단독 트리거가 되는데
z 를 못 내면 "평소의 2배"만으로 발동해서다 — 여태 `VIEW_Z_THRESHOLD` 는 선언만 되고
쓰이지 않았다. `view_stddev` 가 NULL 인 행(마이그레이션 직후)은 조회수 단독 발동을 안 한다.

⚠️ **잃은 것**: "편집만 튀고 조회수가 안 따라오면 버린다"는 컷. 그 일은 편집자 하한이
맡는다(위 절) — 다만 그 대체는 **리플레이로 확인이 안 된다**(편집 덤프에 조회수가 없다).
실덤프 4개월 재생 결과는 전환 전후 **완전 동일**했고(재현율 10/12), 그건 `views=None` 이라
편집 쪽이 안 변하는 게 맞기 때문이다. 조회수가 붙은 실환경에서 재확인이 필요하다.

⚠️ **덤프 한 달만 주면 기존 문서도 `is_thin` 이 된다.** 월초 사건은 28일 창을 못 채워
신규 문서 경로로 빠진다. `--edits` 를 두 번 줘서 전월을 같이 읽힌다.

✅ **조회수 절대 하한 `MIN_ABSOLUTE_VIEWS = 100`** (2026-09-15, WP-87).
~~조회수 판정에 절대 하한이 없다~~ → 걸었다. 평소 1~3회/일인 `Hurricane_Helene` 이 **8회**로
`z 8.1·8.9배`를 통과했었다(진짜 폭증은 9/25 719회부터). 사건 10건 sweep 에서 100·500 결과가
같고 1000 부터 진짜 신호가 깎여서(Hormuz 6/12 → 6/13) 평평한 구간의 아래쪽 끝을 골랐다.

`signal_lag` 의 `--min-views` 기본값은 이 상수를 그대로 따라간다 — 측정 도구가 detector 와
다른 답을 내면 §11 수치가 조용히 어긋난다. sweep 할 때만 다른 값을 준다.

## 검증

```bash
cd data-pipeline/spike
python -m pytest        # 95개는 Spark·DB 없이, 15개는 실 PostgreSQL
                        # (test_baseline_spark.py 는 pyspark 가 있어야 돈다 — 없으면 skip)
```

측정 2026-09-15 (WP-94): psycopg 있는 venv 에서 `110 passed, 1 skipped`
(skip 은 pyspark 없는 `test_baseline_spark.py`), psycopg 없는 venv 에서 `95 passed, 3 skipped`.

- 평상시 조회수가 z 임계 아래인지 (오탐)
- 사건 첫날부터 임계를 넘는지 (미탐)
- 편집만 튀고 조회수가 안 따라오면 확정 안 되는지 (편집 전쟁 걸러내기)
- 얇은 baseline이 절대 하한에 막히는지
- 신규 문서가 절대 편집수로 잡히는지
- 극단값(z=5311)이 점수를 지배하지 않는지 (log 압축)

## EWMA 가중치 (WP-59)

기준선은 슬롯(문서×시간대)마다 지난 28일 관측치(최대 28개)를 **최근에 더 무게** 두어
평균·표준편차를 낸다. 가중 방식·감쇠는 `ewma.py` 가 정한다:

```
weight = 0.5 ** (age_days / 반감기)      # 반감기 H일 → H일 전 관측치 무게 절반
```

- 반감기가 크면 단순평균에 수렴하고, 작으면 최근값이 지배한다. 후보 `7 / 14 / 28`일.
- 🔴 **잠정 기본값 `DEFAULT_HALFLIFE_DAYS = 14`.** 실측 확정 아님. 실덤프(-56·-57)·
  HDFS(-28)가 서면 `ewma_compare.py` 로 -58 산출물에 후보를 돌려 고르고, 근거를
  명세 §11 에 날짜와 함께 기록한다.
- 판정 임계(z≥3 등, WP-38 확정)는 -59 에서 바꾸지 않는다. 확정 반감기가 -38
  판정을 뒤집으면 임의로 고치지 말고 팀에 올린다.
- 실제 EWMA 구현·`page_baseline` 적재는 WP-60 이 `ewma.py` 를 불러 `build_baseline`
  에 넣는다. 지금 `build_baseline` 은 아직 산술평균 골격이다.

```bash
python -m spike.ewma_compare --input ./data/baseline-input/enwiki/2025-06   # 후보 비교
```

## 기준선 산출·적재 (WP-60)

Historical Window 산출물(WP-58)에서 `page_baseline` 행을 만들어 적재한다.

```
(wiki,title,window_start,hour_of_day,edit_count,editor_count,views)   ← -58 산출물
        │  baseline_rows.py  — 28일 창 · ewma.py 가중 · sample_days
        ▼
(wiki,title,hour_of_day, edit_ewma, edit_stddev, view_ewma, sample_days)
        │  baseline_sink.py  — (wiki,title) → wiki_page.id · upsert
        ▼
page_baseline  PK (page_id, hour_of_day)
```

```bash
python -m spike.baseline_sink --input ./data/baseline-input/enwiki/2025-06 --dry-run
python -m spike.baseline_sink --input ... --as-of 2025-06-30 --dsn "$DATABASE_URL"
```

- **28일 경계.** 창은 `(as_of-28일, as_of]`. 골격엔 기간 필터가 없어 소스 전체를 집계했다.
- **창 안에 관측이 없는 슬롯은 행을 안 낸다.** 기준선 없음과 기준선 0 은 다른 뜻이다 —
  `detect()` 는 baseline `None` 을 신규 문서 경로로 보낸다.
- **`sample_days` = 관측이 있었던 고유 날짜 수.** 0 편집인 날을 채우지 않는다. 채우면
  표본이 두꺼워 보여 `is_thin(<7)` 이 안 걸리고 오탐이 난다.
- **문서 키는 `(wiki, title)`.** `wiki_page.id` 해석은 적재 시점에만 한다. 없는 문서는
  만들어 준다(`ON CONFLICT (wiki,title) DO UPDATE ... RETURNING id` — `DO NOTHING` 이면
  충돌 시 id 를 못 받는다).
- **가중치는 여기서 정하지 않는다.** `ewma.py`(WP-59)에서만 온다.

### 두 판이 있다 — 값이 갈리면 안 된다 (2026-09-14 대조 실측)

| 경로 | 파일 | 쓰임 |
| --- | --- | --- |
| 순수 파이썬 | `baseline_rows.py` + `baseline_sink.py` | 적재 경로 |
| Spark 배치 | `baseline.py` (`build_baseline`) | 대량 처리 |

같은 입력에 같은 값이 나오는지 `tests/test_baseline_spark.py` 가 고정한다 — `edit_ewma`·
`edit_stddev`·`view_ewma`·`sample_days`·28일 경계까지, **로컬 Spark 로 실제 통과**한다.
분산은 양쪽 다 **2-pass**(평균을 join 해 되돌림)다. 1-pass `sum(wv²)/sum(w)−mean²` 가
싸지만 소거 오차로 값이 갈린다.

실행: `cd data-pipeline && PYTHONPATH=. spark-submit spike/baseline.py`
(spark-submit 이 스크립트로 실행해 상대 임포트가 깨지므로 절대 임포트 + PYTHONPATH.)

⚠️ **`baseline.py` 의 `SINK` 로는 `page_baseline` 을 채우지 않는다.** `wiki_page.id` 해석과
upsert 가 필요해 `baseline_sink.py` 가 맡는다. 거기 `SINK` 는 진단 출력이다.

## 판정 런타임 — `page_baseline` 조회 → `detect()` → `spike` (WP-94)

여태 `page_baseline` 을 **쓰는** 코드만 있고 **읽는** 코드가 없었고, `detect()` 결과는
`replay.py` 의 stdout 으로 끝났다. 그래서 `Historical Window → 기준선 → 판정 → 저장` 이
한 번도 이어지지 않았고 `cluster/driver.py` 의 씨드 조회는 입력 자체가 없었다.

```
page_baseline ──BaselineRepository──▶ detector.Baseline
                                            │
PageWindow (wiki,title,window_start,edit_count,editor_count,views)
                                            │
                                     detect()  ← detector.py 그대로
                                            │  급증만
                                       SpikeSink
                                            ▼
                                spike  PK id · UNIQUE (page_id, window_start)
```

| 파일 | 역할 |
| --- | --- |
| `baseline_repository.py` | `(wiki, title, hour_of_day)` → `Baseline`. 문서당 24슬롯 한 번에 읽어 캐시 |
| `spike_sink.py` | `SpikeDecision` → `spike` 행. `(page_id, window_start)` 멱등 upsert |
| `runtime.py` | `PageWindow` 한 건을 판정하고 급증이면 저장. **LIVE·리플레이 공용** |

- 🔴 **리플레이 전용이 아니다.** 입력이 `PageWindow` 한 건이라 `streaming/edit_windows.py`
  의 윈도우 집계가 같은 `SpikeRuntime` 을 부를 수 있다. 붙일 때 고치는 건 여기가 아니라
  `PageWindow` 를 만드는 쪽이다 — 집계 계약이 이미 같다(`batch/historical_windows.py` §AC).
- **조회는 문서를 만들지 않는다.** `baseline_sink.resolve_page_ids` 는 없는 문서를
  만들어 주는데(적재 경로에는 맞다), 조회가 그걸 쓰면 판정만 해도 `wiki_page` 가 분다.
  `baseline_repository` 는 순수 `SELECT`, `spike_sink` 는 그 resolve 를 **import 해서** 쓴다
  (규칙을 두 벌 만들면 한쪽만 고쳐졌을 때 같은 문서가 두 행으로 갈린다).
- **`detected_at` 은 윈도우 끝이다. `now()` 가 아니다.** 리플레이가 `now()` 를 찍으면
  2024년 급증이 전부 2026년에 감지된 것으로 남아, 뒤에 붙을 클러스터 스냅샷의 시간축이
  조용히 무너진다. 결정적이라 재실행해도 값이 안 흔들린다.
  윈도우 끝은 **소스가 주면 그 값을 쓴다** — `streaming/edit_windows.py` 는
  `F.col("window.end")` 를 이미 내보내고 그 길이는 `WINDOW_SIZE` 환경변수다. -58 행에는
  없으므로(정각 tumbling) 그때만 `WINDOW_HOURS` 로 채운다. 상수로만 계산하면
  `WINDOW_SIZE` 를 바꿨을 때 `detected_at` 이 에러 없이 어긋난다.
- 🔴 **기준선 캐시는 배치 하나만큼 산다.** `BaselineRepository` 는 문서당 24슬롯을 한 번에
  읽어 캐시하고(리플레이 왕복 272 → 문서당 1), `SpikeRuntime.iter_process`/`process_all` 이
  **배치 시작마다 비운다.** 안 비우면 장수명 LIVE 프로세스(`foreachBatch` 가 같은 런타임을
  계속 부르는 구조)가 `page_baseline` 재적재를 영원히 못 읽는데 **에러 없이 z 만 틀린다.**
  윈도우를 `process()` 로 하나씩 넣으면 캐시는 유지된다 — 호출자가 명시적으로 고른 경로다.
- **미탐은 저장하지 않는다.** `spike` 는 "판정을 통과한 문서" 다(V1 테이블 주석).
- **없음 / 얇음 / db** 를 `DetectionOutcome.baseline_source` 로 가른다. `detect()` 는 앞의
  둘을 똑같이 신규 문서 경로로 보내지만 원인이 다르다 — **없음은 적재가 안 된 것**,
  **얇음은 표본이 모자란 것**이다. 안 가르면 기준선을 안 넣고 돌린 실행을 표본 부족으로 오진한다.

### 리플레이 DB 모드

```bash
# 기존(메모리 기준선) — 동작 그대로
python -m spike.replay --edits ./out/enwiki/2024-10 --title Hurricane_Milton --control Milton_Park

# DB 모드 — page_baseline 을 읽어 판정하고 spike 에 적재
python -m spike.baseline_sink --input ./data/baseline-input/enwiki/2024-10 --dsn "$DATABASE_URL"
python -m spike.replay --edits ./out/enwiki/2024-10 --title Hurricane_Milton --dsn "$DATABASE_URL"
```

⚠️ `--dsn` 은 **명시 opt-in** 이다. `baseline_sink` 와 달리 `$DATABASE_URL` 로 기본값을
채우지 않는다 — 여기서는 DSN 유무가 **동작을 바꾸므로**, 환경변수만으로 회귀 검증이
DB 모드로 넘어가면 그게 조용히 틀리는 경로다.

### 🔴 두 모드는 같은 숫자를 내지 않는다 — 버그가 아니라 정의 차이다

| | 메모리 모드 (`--dsn` 없음) | DB 모드 (`--dsn`) |
| --- | --- | --- |
| 기준선 창 | 판정 대상 시점 **직전까지** (매 윈도우 재계산) | `baseline_sink --as-of` 로 **고정** |
| 사건 구간 포함 | 안 됨 (자기 급증이 평소로 희석되지 않게) | 적재 창에 들어 있으면 포함됨 |
| 쓰임 | 임계·수식 **회귀 검증** | 런타임 경로 검증 |

Milton 2024-10 한 달, 같은 편집 적재본·같은 명령 (2026-09-15 실측):

| 모드 | 적재 `--as-of` | 윈도우 | 급증 | spike 적재 | 기준선 출처 |
| --- | --- | --- | --- | --- | --- |
| 메모리 | — | 272 | **48** | — | 매 시점 직전 28일 재계산 |
| DB | 미지정 → `2024-10-31` | 272 | **6** | 6 | db 252 · 얇음 20 · 없음 0 |
| DB | `2024-10-05` (사건 전날) | 272 | **48** | 48 | db 0 · 얇음 0 · **없음 272** |
| 대조군 `Milton Park` | 둘 다 | 7 | **0** | 0 | 얇음 7 |

**`--as-of` 를 사건 전날로 주면 메모리 모드와 숫자가 정확히 같아진다**(272 / 48, 최초
`2024-10-06T19:00Z`, 대조군 0). 문서가 `2024-10-06` 에 처음 편집돼 그 창에 관측이 없고,
메모리 모드의 초기 구간과 똑같이 신규 문서 경로로 가기 때문이다 — 48행 전부 `edit_z IS NULL`.

`--as-of` 를 안 주면 창의 끝이 관측 중 최신일(2024-10-31)이 되어 **사건이 기준선 안에
들어간다.** `Hurricane Milton` 시간 슬롯의 `edit_ewma` 가 3~6 으로 올라가 z 가 깎이고
급증이 6건으로 준다. 임계 문제가 아니라 창 문제다.

🔴 **`--as-of` 를 바꿔 재적재해도 옛 슬롯은 안 지워진다.** `baseline_sink` 는 upsert 만
한다 — 넓은 창으로 한 번 적재한 뒤 좁은 창으로 다시 적재하면 새 창에 없는 슬롯은 **옛 값이
그대로 남아** 두 창이 섞인다. 실제로 위 3행째를 처음 시도했을 때 `page_baseline` 을 안 비워
급증이 6건 그대로였다(2026-09-15). 창을 바꿔 재현할 때는 그 문서의 `page_baseline` 을 먼저
비운다. (이건 WP-60 의 성질이고 이 스토리에서 바꾸지 않았다.)

⚠️ **신규 문서 경로와 기존 문서 경로의 `spike_score` 는 아직 같은 척도가 아니다.**
위 실측에서 z 경로 건은 1.46~1.67, 신규 문서 경로 건은 42.33 이 나왔다
(`edit_count × √editor_count` vs `log1p(z)` 압축). WP-93 은 기존 문서 경로
**안에서** 편집·조회수 단위를 맞춘 것이고 두 경로 사이는 범위 밖이었다. 정렬에 둘을
섞기 전에 별도로 다뤄야 한다 — 이 스토리에서는 건드리지 않았다.

### 검증

```bash
docker compose up -d postgres      # 저장소 루트
cd data-pipeline/spike && python -m pytest tests/test_spike_runtime_pg.py
```

DB 없이 도는 계약 검사는 `tests/test_runtime.py`·`tests/test_baseline_repository.py` 다
(대역 사용). 실 DB 왕복만 `_pg.py` 로 뺐다 — 한 파일에 두면 DB 없는 환경에서 계약 검사까지
함께 skip 되어 깨져도 아무도 모른다(`test_baseline_sink_pg.py` 와 같은 이유).

### ⚠️ 조용히 틀리는 함정 둘 (2026-09-14 실제로 겪음)

**PySpark 워커가 안 뜨는 건 파이썬 버전 문제가 아닐 수 있다.** `CreateProcess error=2`
는 워커로 띄울 파이썬 **경로**를 못 찾은 것이다. `conftest.py` 가 `PYSPARK_PYTHON` 을
현재 인터프리터로 고정한다(spike 는 자체 `pytest.ini` 를 써서 rootdir 이 `spike/` 라
바깥 conftest 가 안 먹는다 — 그래서 `spike/tests/conftest.py` 에도 둔다).
~~"venv 가 3.12+ 라 Spark 를 못 돌린다"~~ → venv 는 3.11 이고 **돈다** (2026-09-14 정정).

**naive datetime 을 `createDataFrame` 에 주면 9시간 밀린다.** 세션
`timeZone=UTC` 는 이걸 막아주지 않는다 — 드라이버의 로컬 시간대(KST)로 해석해 UTC 로
옮긴다. `hour_of_day` 가 0 대신 15 가 되는데 **에러가 안 난다.** 타임스탬프는
tz-aware 로 넘긴다.

## 리플레이 회귀 검증 (WP-61)

편집 적재본(WP-56)을 1시간 윈도우로 재생하고, 각 시점마다 **그 이전 28일**로
기준선을 만들어 `detect()` 를 돌린다. baseline 파라미터를 바꿀 때마다 다시 돌린다.

```bash
python -m spike.replay --edits ./out/enwiki/2025-06 \
    --title Strait_of_Hormuz --control Association_football
```

`--title` 은 잡혀야 하는 문서, `--control` 은 오탐이 나면 안 되는 문서다. 제목은 **밑줄·공백
아무 형태로나** 준다 — `aggregate` 가 요청 제목과 레코드 제목을 둘 다 canonical 로 맞춘다
(WP-91). ~~덤프 원형(밑줄)으로 준다~~ → 덤프 세대가 둘이다: `normalize_dump` 가
WP-79 부터 공백형을 내므로 재생성 전(밑줄)·후(공백) 적재본이 섞여 돈다. 형식이
어긋나면 "관측 없음" 으로 끝나는데 그게 "급증이 없었다" 로 읽힌다. 로직 자체는
`tests/test_replay.py` 가 합성 데이터로 고정한다(실덤프 불필요).

### 🔴 2026-09-14 실덤프 결과 — 확정 임계가 흔들렸다

WP-38 의 임계는 **조회수**로 정한 것이고 편집 분포로는 검증된 적이 없었다.
실덤프로 재생하니 양방향으로 틀렸다. **임계는 확정 자산이라 고치지 않았다 — 이슈로 올렸다.**

| 대상 | 윈도우 | 총 편집 | 시간 최대 | 급증 판정 |
| --- | --- | --- | --- | --- |
| `Hurricane_Milton` (2024-10, 신규) | 272 | 1,405 | 44 | **48건 ✅** |
| `Strait_of_Hormuz` (2025-06, 기존) | 38 | 71 | 8 | **0건 (미탐)** |
| `2025_Iran_threat_..._closure` | 8 | 17 | 6 | **0건 (미탐)** |
| `Association_football` (대조군) | 8 | — | 12 | **1건 (오탐)** |

- **Milton 최초 탐지** `2024-10-06T19:00Z` 편집 10·편집자 7·`is_new_page=True`·score 26.46
- **Hormuz 미탐** — 사건 정점에도 시간당 최대 8편집으로 `MIN_ABSOLUTE_EDITS=10` 미달.
  같은 구간 조회수는 **746배** 폭증했다. 사건 유형에 따라 편집·조회 반응이 자릿수로 다르다
- **대조군 오탐** — 편집 12지만 **편집자 1명**(1인 연속 편집). ~~`editor_count` 는 판정에
  안 쓰이고 점수 계산에만 들어간다~~ → **판정 게이트로 올렸다** (2026-09-15, WP-85).
  위 "편집자 하한" 절 참고
- ⚠️ **`hour_of_week` 슬롯은 주 1회라 28일 창 관측이 최대 4개** → `sample_days ≤ 4 <
  MIN_BASELINE_SAMPLE_DAYS=7` → 기존 문서도 항상 `is_thin` → **z 경로가 한 번도 실행되지 않는다**
  → ✅ **해소됨** (2026-09-15, WP-84). 슬롯을 `hour_of_day`(0~23)로 바꿔 같은 슬롯이
  매일 오므로 28일 창에서 최대 28관측이 된다. `V3__baseline_hour_of_day.sql`
  → ⚠️ **다만 "가능해졌다" 지 "돌고 있다" 가 아니다** (2026-09-15, WP-88 측정).
  24슬롯에서 `sample_days>=7` 에 도달하는 건 슬롯당 **1.5%** 뿐이라 z 경로는 사실상
  월 300편집 이상 문서 전용이다. 넓히면 도달률은 오르지만 재현율·오탐이 안 변해서
  **전환은 보류했다** — 아래 "슬롯 폭" 절

→ **WP-84**(sample_days 구조적 미달)·**WP-85**(임계 재검토). 근거는 명세 §11.

## 실 PostgreSQL 검증 (2026-09-14 통과)

upsert 멱등성은 실 DB 로 확인했다 — `tests/test_baseline_sink_pg.py`.

```bash
docker compose up -d postgres          # 저장소 루트
cd data-pipeline && .venv/Scripts/python.exe -m pytest spike/tests/test_baseline_sink_pg.py
```

확인한 것: 같은 입력 두 번에 행이 안 늘어남 · 재적재가 값과 `updated_at` 을 갱신 ·
`wiki_page` 자연키 중복 없음 · 슬롯당 한 행 · `view_ewma` 결측이 NULL 로 들어감.
`DATABASE_URL` 이 있으면 그걸 쓰고, 없으면 compose 기본 DSN 으로 붙는다. 못 붙으면 skip.

## 아직 안 한 것

- 🔴 **결측 실측 미수집.** 실데이터에서 `edit_stddev` NULL 비율·`sample_days<7` 비율을
  재서 백엔드·프론트에 넘기는 건 실덤프(`-56`·`-57`) 적재 뒤다. `--dry-run` 이 두 수치를
  찍는다. `frontend/docs/API_SPEC.md` L108 결측 계약의 입력이 이 값이다.
- **실규모 Spark 실행** — 위 대조는 로컬 `local[1]` 소표본이다. Spark 2노드
  (`WP-27`)·HDFS(`-28`)에서의 태스크 수·소요 시간은 그때 잰다.

- **Streaming 연결.** ~~`detect()` 를 붙여 spike 테이블에 쓰는 건 데이터 모델(-35)·기준선
  적재가 develop 에 들어간 뒤다~~ → 판정·적재 경로는 `runtime.py` 로 섰다(WP-94).
  남은 건 `streaming/edit_windows.py` 의 집계 출력을 `PageWindow` 로 바꿔 `SpikeRuntime`
  에 넘기는 것뿐이다(`foreachBatch`). 이 스토리 범위 밖.
- **윈도우 길이·봇 필터 강도** 는 실데이터로 튜닝. 지금 임계는 Strait of Hormuz 한
  사건 기준이라 여러 사건으로 넓혀야 한다. (EWMA 반감기는 위 -59 참조.)
