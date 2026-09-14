# spike — 급증 판정

`WP-38`. 편집·조회수 급증을 판정하는 수식과 기준선 산출.

명세: [docs/requirements-v0.1.md](../../docs/requirements-v0.1.md) §3.2, §6, §11

```
28일 기준선 (baseline.py, Spark 배치)
   문서 × 요일·시간대(0..167) EWMA
        │
        ▼
급증 판정 (detector.py, 순수 함수)
   기존 문서: 편집 z≥3 AND ≥10건  →  조회수 z≥3 AND ≥2배
   신규 문서: 절대 편집수 ≥10 (baseline 없음)
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

## 조회수는 편집보다 늦게 온다

⚠️ 실측: Pageviews API는 **일 단위, 하루 지연**이다 (시간별은 400 에러). 시간별
문서 조회수는 `other/pageviews` 덤프뿐이고 봇 구분이 없다. "시간별 + 봇 구분"을
동시에 주는 소스가 없다.

그래서 2차 판정(조회수)이 1차(편집)보다 반드시 늦다. `detect()`는 조회수가
아직 없으면(`views=None`) 편집만으로 **감지됨** 상태를 내보내고, 조회수가
들어오면 **확정**으로 올린다. 명세 §3.2 7번의 3단계 상태가 이 지연을 그대로
드러낸다.

## 검증

```bash
cd data-pipeline/spike
python -m pytest        # 35개 (detector + ewma + baseline), Spark·DB 없이
```

- 평상시 조회수가 z 임계 아래인지 (오탐)
- 사건 첫날부터 임계를 넘는지 (미탐)
- 편집만 튀고 조회수가 안 따라오면 확정 안 되는지 (편집 전쟁 걸러내기)
- 얇은 baseline이 절대 하한에 막히는지
- 신규 문서가 절대 편집수로 잡히는지
- 극단값(z=5311)이 점수를 지배하지 않는지 (log 압축)

## EWMA 가중치 (WP-59)

기준선은 슬롯(문서×요일·시간대)마다 지난 28일 관측치(≈4주)를 **최근에 더 무게** 두어
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
(wiki,title,window_start,hour_of_week,edit_count,views)   ← -58 산출물
        │  baseline_rows.py  — 28일 창 · ewma.py 가중 · sample_days
        ▼
(wiki,title,hour_of_week, edit_ewma, edit_stddev, view_ewma, sample_days)
        │  baseline_sink.py  — (wiki,title) → wiki_page.id · upsert
        ▼
page_baseline  PK (page_id, hour_of_week)
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

### 두 판이 있다 — 값이 갈리면 안 된다

| 경로 | 파일 | 상태 |
| --- | --- | --- |
| 순수 파이썬 | `baseline_rows.py` + `baseline_sink.py` | 테스트로 검증됨 |
| Spark 배치 | `baseline.py` (`build_baseline`) | ⚠️ **로컬 미검증** |

Spark 판은 PySpark 워커가 3.12+ 에서 죽어(`tests/conftest.py`) 개발 PC 에서 못 돌리고,
Spark 2노드(`WP-27`)·HDFS(`-28`)도 아직 없다. 같은 수식을 쓰되 분산은 **2-pass**
(평균을 join 해 되돌림)로 냈다 — 1-pass `sum(wv²)/sum(w)−mean²` 가 싸지만 소거 오차로
순수 판과 값이 갈린다. 실행은 `cd data-pipeline && PYTHONPATH=. spark-submit spike/baseline.py`
(spark-submit 이 스크립트로 실행해 상대 임포트가 깨지므로 절대 임포트 + PYTHONPATH).

⚠️ **`baseline.py` 의 `SINK` 로는 `page_baseline` 을 채우지 않는다.** `wiki_page.id` 해석과
upsert 가 필요해 `baseline_sink.py` 가 맡는다. 거기 `SINK` 는 진단 출력이다.

## 아직 안 한 것

- 🔴 **실 PostgreSQL upsert 멱등성 미검증.** SQL 구조·파라미터·해석 캐시는 테스트로
  고정했지만, "같은 입력 두 번에 행이 안 늘어난다" 를 실 DB 로 확인한 기록은 없다
  (`WP-29` PostgreSQL 기동 후, 또는 저장소 `docker-compose.yml` 로).
- 🔴 **결측 실측 미수집.** 실데이터에서 `edit_stddev` NULL 비율·`sample_days<7` 비율을
  재서 백엔드·프론트에 넘기는 건 실덤프(`-56`·`-57`) 적재 뒤다. `--dry-run` 이 두 수치를
  찍는다. `frontend/docs/API_SPEC.md` L108 결측 계약의 입력이 이 값이다.
- **baseline.py Spark 실행** — 위 표 참고.
- **Streaming 연결.** `streaming/edit_windows.py` 가 윈도우 집계까지 하고,
  거기에 `detect()` 를 붙여 spike 테이블에 쓰는 건 데이터 모델(-35)·기준선
  적재가 develop 에 들어간 뒤다.
- **윈도우 길이·봇 필터 강도** 는 실데이터로 튜닝. 지금 임계는 Strait of Hormuz 한
  사건 기준이라 여러 사건으로 넓혀야 한다. (EWMA 반감기는 위 -59 참조.)
