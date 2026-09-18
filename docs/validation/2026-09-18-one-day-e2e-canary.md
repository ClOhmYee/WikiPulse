# 실제 하루 대표 이슈 E2E canary

- 검증 ID: `VAL-2026-09-18-LOCAL-04`
- 실행일: 2026-09-18 KST
- 환경: 로컬 Windows·Docker PostgreSQL, EC2·원격 DB 미사용
- 원본 날짜: 2025-06-12 UTC
- 대표 이슈: `Air India Flight 171`
- 판정: **PASS with 2 manual bridges**
- 기계 판독 결과: [JSON](data/2026-09-18-one-day-e2e-canary.json)

## 1. 결론

EC2 배포 전에 필요한 “하루 데이터가 제품 응답까지 흐르는가”는 확인됐다.

```text
실제 mediawiki_history 편집 윈도우
  → 실제 other/pageviews 24시간 파일
  → 생성 시각·신규 문서 판정
  → spike 15개
  → 시점별 seed-only cluster 15개
  → 종목 임베딩·후보 합집합·LLM 검증
  → 한국어 요약·CONFIRMED
  → Spring API
  → Frontend dev proxy
```

다만 아래 두 단계는 제품 자동화 코드가 없어 canary에서 수동으로 이었다.

1. `cluster → GKG 테마·지역 술어`: Boeing 기관 언급·lift 행을 통제 입력으로 넣었다.
2. `issue_report` 요약 writer·상태 전이: GATEWAY 요약을 직접 적재하고 `CONFIRMED`로 바꿨다.

따라서 **EC2에 기반 스택과 현재 코드를 올려 같은 canary를 재현할 수는 있지만**, 두 bridge를
구현하기 전에는 “무인 자동 파이프라인”이라고 부르면 안 된다.

## 2. 실제 입력과 감지 결과

앞선 전일 upstream 검증은 실제 편집 덤프 5,501,827행에서 72,632개 윈도우를 만들고,
24개 `other/pageviews` 파일을 결합했다. 이번 canary는 그 결과 중 대표 이슈 하나를 새 전용
DB(`wikipulse_canary_20260918`)에 다시 적재해 downstream까지 이어 갔다.

| 항목 | 결과 |
| --- | ---: |
| 문서 생성 시각 | 2025-06-12 08:58:02 UTC |
| 실제 편집 윈도우 | 16개 |
| 조회수 결합 시간 | 16개 |
| 평가 / 대기 | 16 / 0 |
| 저장 spike | 15개 |
| 최초 spike | 09:00 UTC, 편집 126·조회 24,669·점수 5.512 |
| 마지막 spike | 23:00 UTC, 편집 22·조회 25,426·점수 5.542 |

08시 윈도우는 조회 3회라 미탐이고, 09시부터 23시까지 급증으로 저장됐다. 신규 문서라
과거 28일 기준선을 요구하지 않고 생성 이후 관측치와 절대 조회수 하한으로 판정됐다.

## 3. 클러스터·종목·요약 결과

기존 `cluster.driver`를 seed-only 모드로 실행해 spike의 `detected_at`별 스냅샷 15개를
저장했다. 최신 스냅샷은 클러스터 1·멤버 1·간선 0이며 멱등 저장 계약을 그대로 사용했다.

종목은 Boeing(`BA`) 한 건만 넣고 기존 `stock.embed`로 실제 GATEWAY
`text-embedding-3-small` 1,536차원 임베딩을 생성했다. 후보 생성 워커는 현재 Wikipedia
도입부 임베딩 Top-K와 통제 GKG lift를 합쳐 다음 결과를 저장했다.

| 항목 | 결과 |
| --- | --- |
| ticker / tier | `BA` / `BOTH` |
| cosine similarity | 0.3812 |
| GKG lift | 6.0 — **통제값** |
| LLM 판정 | verified=true |
| 근거 / 신뢰도 | `DIRECT_MENTION` / `strong` |
| 상태 | `DONE` |

GATEWAY summary 호출도 성공해 `issue_report`에 한국어 두 문장을 저장했다. 이 호출과
`DETECTED → CONFIRMED` 갱신은 production writer가 없어 canary 스크립트가 직접 수행했다.

⚠️ historical candidate 생성에서 Backend가 현재 Wikipedia 도입부를 조회했다. 실행 경로
연결 증거로는 유효하지만 과거 시점 재현에는 미래 정보가 섞일 수 있다. EC2의 정식 replay는
선택 월/snapshot 당시 대표 텍스트를 저장하거나 입력으로 고정해야 한다.

## 4. API·Frontend 경계

Spring Boot를 canary DB에 연결한 뒤 실제 HTTP로 확인했다.

| 검사 | 결과 |
| --- | --- |
| `/actuator/health` | `UP` |
| replay snapshot 목록 | 15개 |
| 최신 map | cluster 1·node 1·edge 0 |
| `/api/v1/issues/15` | `CONFIRMED`, 요약 있음, 관련 종목 1개 |
| `/api/v1/issues/15/stocks` | `BA`, `DIRECT_MENTION` |
| `/api/v1/stocks/BA/issues` | 역방향 이슈 1개 |
| Frontend HTTP / API proxy | 200 / 동일 이슈·요약·BA 반환 |

## 5. 이번 canary가 발견한 표시 한계

클러스터 멤버의 `views`는 실제 DB에 25,426이 있어도 API에서 `null`이고
`completeness=pending`으로 나왔다. 현재 `spike`가 원 조회수를 저장하지 않고,
신규 문서의 기준선 0 판정은 `view_ratio=NULL`이라 cluster driver가 이를 pending으로
해석하기 때문이다. 감지·종목·요약에는 영향이 없지만 이슈 근거 화면 수치가 비므로 EC2
시연 전 수정 대상이다.

## 6. EC2 구축 순서

다음 순서면 같은 canary를 서버에서 빠르게 재현할 수 있다.

1. PostgreSQL+pgvector에 V1~V7 migration 적용
2. Kafka 3.9와 Python 3.11 데이터 파이프라인 환경 준비
3. 종목 master·사업 설명·임베딩을 **후보 워커보다 먼저** 적재
4. historical 편집·생성 시각·시간별 pageviews·기준선·recheck 실행
5. `cluster.driver --source replay` 실행
6. GKG 원본·기관 lift 적재 후 후보 생성 워커 실행
7. LLM 검증 → 요약 writer → 상태 전이 실행
8. Backend API·Frontend 연결 후 이 보고서의 HTTP 항목 재확인

필수 환경변수는 `DATABASE_URL`, `DB_USER`, `DB_PASSWORD`, `LLM_GATEWAY_KEY`,
`WIKIPULSE_MATCHING_SCHEDULER_ENABLED=true`,
`WIKIPULSE_MATCHING_VERIFICATION_ENABLED=true`, Wikimedia 연락처다.

현재 Compose는 backend에 GATEWAY 키와 두 워커 flag를 전달하지 않는다. 또한 공식 Spark
3.5.3 이미지의 Python 3.8은 `psycopg 3.3.5`와 맞지 않아 LIVE `SINK=spike`가 실행되지
않는다. EC2 배포 전 Compose/env 전달과 Python 3.11 Spark 실행 이미지를 먼저 맞춘다.

## 7. 이관 판정

- **지금 EC2에 구축 가능한 것:** PostgreSQL·Kafka·배치 replay·seed-only cluster·종목
  임베딩·후보 생성·LLM 검증·Backend·Frontend.
- **수동 bridge로만 가능한 것:** GKG 검색 술어 생성, 이슈 요약·상태 전이.
- **LIVE 전에 필요한 것:** Spark Python/psycopg 호환, pageviews scheduler, 위 두 bridge,
  cluster member 조회수·completeness 전달 수정.

이번 실행은 전용 canary DB만 만들었고 기존 로컬 `wikipulse` DB는 수정하지 않았다.
