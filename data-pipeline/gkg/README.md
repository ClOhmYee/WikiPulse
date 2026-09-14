# gkg — GDELT GKG 기관명 lift 배치 (WP-65)

`gdelt/` 가 HDFS 에 쌓은 GKG 원본을 Spark 배치로 읽어, 이슈 기간에 뉴스로 함께
등장한 기관명과 **lift** 를 뽑아 `cluster_org_mention` 에 적재한다. 이 산출물이
종목 후보 생성(§6.3 b)과 LLM 검증의 RAG 컨텍스트가 된다.

```
HDFS  YYYY/MM/DD/<ts>.gkg.csv.zip  ──[이 배치]──▶  cluster_org_mention
      (gdelt/ 가 적재)                              (org_name, ticker, lift, ...)
```

명세: [docs/requirements-v0.1.md](../../docs/requirements-v0.1.md) §6.2 (b)·§6.3·§11

## lift

    lift = P(기관 | 이슈 기사) / P(기관 | 전체 기사)

이슈 기사는 같은 기간 GKG 전체(코퍼스)의 부분집합이다 — **이슈 술어**(테마 ∧ 지역)를
통과한 기사. 전체에 고루 퍼진 기관은 lift≈1, 이슈에 몰린 기관은 lift≫1 이다.
lift 는 최대 `코퍼스 수 / 이슈 수` 까지 오른다(그 기관이 이슈 기사에만 나올 때).

## 구성

| 파일 | 역할 | 테스트 |
| --- | --- | --- |
| `parse.py` | GKG 27컬럼 파싱 — 조직명(V1+V2)·테마·지역. Spark 없이 돈다 | `test_parse.py` |
| `lift.py` | 이슈 술어 + 집계·랭킹. 병합 가능(Spark reduce 와 단일프로세스 공유) | `test_lift.py` |
| `match.py` | 기관명 정규화 → 종목 마스터 정확일치 ticker | `test_match.py` |
| `writer.py` | `cluster_org_mention` 멱등 저장(재계산 호환) | `test_writer.py`(pgserver 왕복) |
| `driver.py` | Spark 배선 + CLI — `binaryFiles` 로 zip 분산 파싱 | `test_driver.py` |

```
pytest gkg/tests    # 36개. Docker 불필요(pgserver 번들 PostgreSQL)
```

## 실행

```bash
# 로컬 GKG(gdelt 싱크 레이아웃)에 대해. spark-submit 은 apache/spark 이미지.
spark-submit gkg/driver.py \
    --cluster-id 42 \
    --start 20241010000000 --end 20241010234500 \
    --theme HURRICANE --location florida \
    --min-issue-count 5

# 저장 없이 랭킹만
spark-submit gkg/driver.py --cluster-id 42 --start ... --end ... \
    --theme HURRICANE --location florida --dry-run
```

- `--theme` / `--location` 은 반복 가능(한 차원 안은 OR, 차원끼리는 AND). 부분일치다
  (`HURRICANE` ⊂ 테마코드 `NATURAL_DISASTER_HURRICANE`, `florida` ⊂ 지역 풀네임).
- `--base-dir` 는 `GDELT_LOCAL_DIR`(gdelt 싱크와 같은 `YYYY/MM/DD/<ts>.gkg.csv.zip`).
- `DATABASE_URL` 이 있으면 ticker 를 붙이고 저장한다. 없으면 ticker 전부 NULL·저장 생략.

### 이슈 술어를 왜 인자로 받나

실 파이프라인에서 이슈 클러스터는 위키 문서 묶음이지 GKG 기사 필터가 아니다.
"클러스터 → GKG 술어" 변환은 아직 정의되지 않았다(별도 과제). `cluster/driver.py`
가 골격으로 소스 배선을 기다리듯, 여기서는 이슈 정의를 §11 이 쓴 테마·지역 술어로
받는다. Milton = `--theme HURRICANE --location florida`.

## ticker 매칭 범위

정규화(소문자·구두점 제거·법인격 접미어 제거) 후 **정확 일치**만 붙인다. 부분문자열
매칭은 안 한다 — News Corp·Meta 오탐이 남는다(§10). 못 맞추면 `ticker=NULL` 로
그대로 저장한다 — 미매칭 기관(언론사·정부기관이 절반 넘는다)도 RAG 컨텍스트다.

⚠️ 그래서 지금은 자회사·별칭이 안 붙는다: GKG 의 `florida power light company` 는
종목 마스터의 모회사 `NextEra Energy` 와 정규화가 달라 NULL 이 된다. **별칭 테이블
(WP-47)** 이 붙은 뒤 재조인해 해소한다 — 이슈 노트의 계획대로다.

## 결손 내성 (인수 조건 4)

- `plan_slots` 가 존재하는 슬롯만 골라 넘긴다. GDELT 결손(404, 예 2025-06-13~07-04)은
  `missing` 으로 세고 배치는 멈추지 않는다.
- `from_zip_bytes` 가 손상 zip(HTML 오류 페이지·잘린 파일·빈 아카이브)을 빈 결과로
  흘려 한 파일이 잡 전체를 죽이지 않는다.

## §11 재현 (인수 조건 3) — 실 데이터 실측 2026-09-14

Milton 당일(2024-10-10) GKG 슬롯 16개(90분 간격 표본, 코퍼스 26,448·이슈 2,292)에
`--theme HURRICANE --location florida` 로 이 파이프라인(`parse`+`lift`)을 그대로 돌린 결과:

| 기관 | lift | 이슈/코퍼스 | §11(전일) |
| --- | --- | --- | --- |
| florida power light company | **11.54** | 12/12 | FPL 10.5 |
| duke energy florida | 11.54 | 11/11 | — |
| duke energy | **8.03** | 16/23 | Duke 8.4 |
| nvidia · microsoft | (부재) | <5 | Nvidia 0.4 |

FPL·Duke 가 상위, 무관 Nvidia 는 이슈셋에서 사실상 부재로 §11 방향·수치가 재현됐다.
11.54 는 이 표본의 lift 상한(코퍼스/이슈)이라 FPL 처럼 이슈 기사에만 나오는 기관이
거기 붙고, Duke 는 비이슈 기사에도 나와 8.03 으로 §11 상대순서(FPL>Duke)까지 맞는다.
Generac 은 16슬롯 표본에선 이슈 기사 5건 미만이라 안 떴다 — 전일 96슬롯(§11 조건)이면
드러난다. 실물 컬럼 배치(27컬럼, 조직=13·14)도 이때 확인했다(`parse.py` docstring).

컬럼 인덱스를 문서만 보고 박지 않았다 — GKG 실물로 검증했다(P249 함정 회피, CLAUDE.md).

## 아직 안 한 것

- **EC2 실 HDFS 2노드 실행** — `binaryFiles` 를 `hdfs://` 경로로. 지금은 로컬 싱크
  레이아웃(`file://`)으로 검증. gdelt producer 가 `webhdfs` 로 적재하면 이어붙는다.
- **별칭/자회사 매칭**(WP-47) — 위 ticker 매칭 범위 참조.
- **클러스터 → 이슈 술어 자동 도출** — 지금은 테마·지역 인자. 위키 클러스터에서
  술어를 뽑는 변환은 별도 과제.
