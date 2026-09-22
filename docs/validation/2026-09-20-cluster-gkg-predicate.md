# 클러스터 → GKG 술어 자동 생성 검증 — Hurricane Milton

- 검증 ID: `VAL-2026-09-20-GKG-01`
- 실행일: 2026-09-20 KST
- 환경: 로컬 Windows + Docker `python:3.11-slim`, EC2·원격 DB 미사용
- 대상: WP-148 (`gkg/predicate.py`)
- 판정: **PASS** — 사람이 손으로 주던 술어를 클러스터 멤버에서 자동으로 뽑고,
  §11 실측의 정답·음성 대조군을 모두 재현했다

## 1. 질문과 수용 기준

명세 §11(요구사항 v0.3 라인 363)이 정답이다.

> GDELT lift, Milton | I=`HURRICANE ∧ florida` 10,707건. FPL 10.5 · Generac 9.3 ·
> Duke 8.4 · Publix 7.0 · United 6.3 · Disney 4.7 · **Nvidia 0.4 · MSFT 0.3** | 2026-09-07

물은 것은 **그 술어를 사람 없이 뽑아낼 수 있는가**다. 수치 자체가 아니라 술어 생성이 대상이다.

## 2. 입력

| 입력 | 값 |
| --- | --- |
| GKG 원본 | `data.gdeltproject.org/gdeltv2/` 2024-10-10 UTC **96/96 슬롯**, 627 MB, 실패 0 |
| 코퍼스 | **160,838 기사** |
| 관측 어휘 | 테마 **9,910 코드** / 지역 **26,605 풀네임** |
| 클러스터 멤버 | `Hurricane Milton`(씨드) · `Effects of Hurricane Milton in Florida`(씨드) · `Florida` · `Tampa` |

⚠️ 멤버는 **손으로 구성한 목록**이다. 실제 `cluster_member` 행에서 읽은 것이 아니다 —
2024-10-10 Milton 클러스터가 DB에 없다. `load_cluster_members()` 의 SQL 경로는 이 검증에
포함되지 않았고 단위 테스트로만 덮여 있다.

## 3. 결과

자동 생성된 술어:

```
테마[HURRICANE] ∧ 지역[florida ∨ tampa]
  - hurricane: 지지도 21,742 (씨드) ← NATURAL_DISASTER_HURRICANE, NATURAL_DISASTER_HURRICANES
  - florida:   지지도 69,477 ← 773개 풀네임
  - tampa:     지지도 11,246 ← 10개 풀네임
```

이슈 기사 **12,910 / 160,838 (8.0%)**.

§11 의 `HURRICANE ∧ florida` 보다 `tampa` 만큼 넓어 12,910 vs 10,707 이다. 같은 자릿수이고,
`tampa` 는 `florida` 의 부분 지역이라 대부분 겹친다.

| 기관 | 이번 lift | §11 |
| --- | --- | --- |
| florida power light co | **12.46** | FPL 10.5 |
| duke energy florida | **12.46** | Duke 8.4 |
| generac holdings | **12.46** | Generac 9.3 |
| publix super markets charities / publix | **12.46 / 8.06** | Publix 7.0 |
| **nvidia** | **0.44** | **0.4** |
| **microsoft** | **0.32** | **0.3** |

🔴 **음성 대조군이 핵심이다.** 정답 기관은 술어가 넓어지면 따라 올라가지만, 무관 기관이
1 아래로 떨어지는 것은 술어가 **실제로 사건을 고르고 있을 때만** 나온다. Nvidia 0.44·
Microsoft 0.32 가 §11(0.4·0.3)과 소수점까지 맞는다.

양성 기관 lift 가 §11 보다 높은 것은 이슈 집합이 달라 분모(`n_issue`)가 다르기 때문이다.
상위권 다수가 **12.46 = 160,838/12,910** 으로 포화돼 있는데, 이는 "이슈 기사에만 나오고
코퍼스 다른 곳엔 없는 기관"의 이론적 최대 lift 다. 하드 필터 + 문서빈도 lift 의 구조적
성질이지 버그가 아니다.

## 4. 이번에 드러난 결함 2건

둘 다 실데이터에서만 보였다. 합성 코퍼스는 통과시켰다.

### 4-1. 일반성 가드 0.25 가 진짜 사건 테마를 죽였다

초기값 `max_corpus_ratio=0.25` 에서 `hurricane`(코퍼스의 30%)이 **거부**돼 술어가 통째로
비었다. 두 축이 AND 로 묶여 교집합은 좁다는 것을 빼먹은 값이다. 큰 사건은 짧은 창에서
코퍼스의 상당 비율을 정당하게 차지한다. → **0.5** 로 고치고 회귀 테스트로 고정했다.

### 4-2. 절대 하한이 큰 코퍼스에서 무의미했다

`min_support=3` 만으로는 `florida` 가 **테마 축에도** 붙었다. 걸린 코드가
`TAX_WORLDREPTILES_FLORIDA_KINGSNAKE` 하나(19건) — **플로리다 왕뱀**이다. 테마는 OR 이라
이런 것이 끼면 술어가 넓어진다. → `min_support_ratio=0.001` 비례 하한을 추가했다
(하루치에서 하한 160, 19 탈락). 작은 창에서는 비례 하한이 0 이 되므로 절대 하한이 받친다.

## 5. 검증되지 않은 것

있는 줄 알고 넘어가면 나중에 비싸게 드러난다.

- ~~**`load_cluster_members()` 의 SQL 은 실행된 적이 없다.**~~ → **해소** (§7).
- ~~**Spark 경로(`spark_vocabulary`)는 실행된 적이 없다.**~~ → **해소** (§7).
- **사건 하나뿐이다.** Hormuz·CrowdStrike 등 다른 유형(기업형·지정학형)에서 같은 기본값이
  통하는지 모른다. 특히 지역 축이 없는 이슈(기업 실적 등)는 테마 단독 술어가 되는데 그때
  얼마나 넓어지는지 안 쟀다.
- **두 번째 스캔 비용을 안 쟀다.** 술어 자동 생성은 코퍼스를 한 번 더 푼다.

## 6. 재현

```
docker run --rm -m 4g -v <repo>:/w -w /w/data-pipeline python:3.11-slim \
  bash -c "pip install -q pytest==8.3.4 pgserver==0.1.4 'psycopg[binary]==3.3.5' && cd gkg && python -m pytest -q"
```

gkg 테스트 **70개 통과** (신규 17개).

## 7. 후속 — 실제 DB·Spark 관통 (2026-09-20, 같은 날 추가)

§5 의 미검증 두 항목을 닫았다. 로컬 PostgreSQL 에 Milton 클러스터를 실제 행으로 심고
(`issue_cluster` 1 + `cluster_member` 4), `docker/spark/Dockerfile` 이미지에서 드라이버를
끝까지 돌렸다.

```
슬롯: 존재 96 / 결손 0
술어 생성: 멤버 4건, 어휘 스캔 96/96 슬롯
술어: 테마[HURRICANE] ∧ 지역[florida ∨ tampa]
이슈 기사 12,910 / 코퍼스 160,838 / 기관 40건
cluster_org_mention 에 40건 저장(cluster_id=1)
```

- **`load_cluster_members()`** — 손으로 만든 목록이 아니라 `cluster_member` ⋈ `wiki_page`
  에서 4건을 읽어 술어를 만들었다. ✅
- **`spark_vocabulary`** — Spark Stage 0(어휘)·Stage 1(집계) 두 패스가 각각 8 태스크로
  돌았다. `binaryFiles` → `map` → `reduce` 배선 확인. ✅
- **티커 조인** — 2026-09-20 적재한 종목 마스터 5,396건과 붙어 `DUK`(Duke Energy) 가
  매칭됐다. §11 정답 중 하나다. ✅

### 🔴 실행 명령이 틀려 있었다

모듈 docstring 의 `spark-submit gkg/driver.py ...` 는 **동작하지 않는다.** 이 모듈은
상대 임포트(`from .aliases import ...`)를 쓰는데 spark-submit 은 파일을 스크립트로
실행해 패키지 컨텍스트가 없다 — `ImportError: attempted relative import with no known
parent package`. `python -m gkg.driver` 로 고쳤다.

⚠️ **이 명령은 한 번도 실행된 적이 없었다.** `tests/test_driver.py` 가 함수 단위만 덮고
CLI 를 안 돌려서 틀린 채로 남아 있었다. 다른 모듈의 실행 예시도 같은 의심을 해야 한다.

### ⚠️ 티커 오탐 1건

40건 중 티커가 붙은 것은 2건인데 그중 하나가 오탐이다.

| 티커 | 종목명 | 붙은 기관명 | 판정 |
| --- | --- | --- | --- |
| `DUK` | Duke Energy CORP | duke energy florida | 정답 (§11) |
| `MIAX` | MIAMI INTERNATIONAL HOLDINGS | miami international | **오탐** |

허리케인 맥락의 "miami international" 은 거의 확실히 **마이애미 국제공항**이지 옵션
거래소가 아니다. `gkg/aliases.py` 가 `dodge`·`mcdonald` 를 블록리스트에 넣은 것과 같은
유형이다. LLM 검증 단계(WP-68)가 거르도록 설계돼 있어 치명적이진 않지만,
블록리스트 후보로 기록해 둔다.

### 아직 남은 것

- 사건 유형은 여전히 Milton 하나다.
- EC2 에서는 돌리지 않았다 (로컬 PostgreSQL + 로컬 Spark 단일 노드).
- 두 번째 스캔 비용은 이번에도 안 쟀다.
