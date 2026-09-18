# MVP 로컬 파이프라인 최종 게이트

- 검증 ID: `VAL-2026-09-18-LOCAL-03`
- 실행일: 2026-09-18 KST
- 환경: 로컬 Windows, EC2·원격 DB 미사용
- 저장소: `docs/mvp-validation-runbook` / `7c3f3e1` 기반의 미커밋 작업 상태
- 판정: **PARTIAL — 추가 탐색 검증을 멈추고 미구현 연결을 구현할 단계**

## 1. 결론

이미 구현된 수집·판정·저장 함수의 회귀에서는 실패가 없었다. 2025-06-12 실제 하루
원본도 `편집 → 생성 시각 → 시간별 조회수 → 재평가`까지 관통했다. 전체 MVP가 아직
이어지지 않는 이유는 데이터 품질을 더 실험해야 해서가 아니라 다음 네 연결이 코드에 없거나
기본 실행 구성에서 꺼져 있기 때문이다.

1. Clickstream 이웃의 historical 생성일 로더와 추가 씨드·재급증 규칙
2. 위키 클러스터를 GKG 테마·지역 검색 술어로 바꾸는 단계
3. `issue_report` 요약 writer와 `DETECTED → VERIFYING → CONFIRMED` 상태 전이
4. Compose의 GATEWAY·후보 생성·검증 워커 환경변수 전달과 실행 데이터 준비

따라서 위 네 항목 구현 전에는 같은 검증을 반복하지 않는다.

## 2. 단계별 판정

| 단계 | 판정 | 증거 또는 막힌 이유 |
| --- | --- | --- |
| EventStreams/GDELT 수집기·파서 | PASS(회귀) | Python 전체 회귀 통과. 외부 상시 폴링은 이번 로컬 게이트에서 실행하지 않음 |
| historical 편집 윈도우·생성 시각 | PASS | 실제 5,501,827행에서 72,632 윈도우 생성. 월 전체 생성 메타데이터 계약 확정 |
| 시간별 pageviews·기준선·재평가 | PASS/PARTIAL | 실제 하루 24파일 재평가 통과. 실제 28일 기준선 품질과 LIVE scheduler는 미검증 |
| spike 저장 | PASS(배치) / BLOCKED(LIVE Compose) | 배치·DB 경로는 통과. Spark 공식 이미지 Python 3.8과 `psycopg 3.3.5`가 맞지 않아 Compose `SINK=spike`는 실행 불가 |
| 클러스터 스냅샷 | PARTIAL | 씨드 단독 회귀는 통과. `cluster/driver.py:load_creation_dates`가 `NotImplementedError`, 추가 씨드·비-seed 재급증 미구현 |
| GDELT GKG lift | PARTIAL | 다운로드·파싱·lift·writer 단위 경로 존재. “클러스터 → 테마·지역 술어” 변환은 미정의 |
| 종목 후보·LLM 검증 | PARTIAL | Backend 단위 회귀 통과. 워커는 기본 OFF이며 Compose가 GATEWAY/워커 환경변수를 backend에 전달하지 않음 |
| 한국어 요약·상태 전이 | **NOT IMPLEMENTED** | production `issue_report` INSERT와 `issue_cluster.status` 전이 코드 없음. demo seed만 존재 |
| API·화면 계약 | PASS(코드) / 실 DB E2E 미실행 | Backend·Frontend 회귀, 계약, API interception, build 통과. 로컬 DB와 Docker 엔진은 꺼져 있었음 |

## 3. 이번 실행 증거

| 검사 | 결과 |
| --- | --- |
| `python -m pytest data-pipeline db/tests -q` | **556 passed, 20 skipped**, 0 failed, 430.47초 |
| Backend Gradle test | **92 passed**, 0 failed |
| Frontend lint | PASS |
| Frontend data tests | **27 passed**, 0 failed |
| Frontend API Playwright | **13 passed**, 0 failed |
| Frontend contract validation | 8 routes·24 schemas·290 responses 검증, PASS |
| Frontend production build | PASS |
| `docker compose config --quiet` | PASS |
| pipeline profile 서비스 | `postgres`, `backend`, `frontend`, `kafka`, `producer`, `spark` |
| 로컬 포트 5432/9092/6379/8080 | 모두 닫힘 — 실제 서비스 E2E 미실행 |

Python skip은 로컬에 `pyspark` 또는 `pgserver`가 없는 테스트와 실행 중 PostgreSQL이 필요한
테스트다. 이 중 DB 관통 핵심 경로는 같은 작업 상태에서 앞선 실제 하루 E2E와 556개 전체
회귀 실행에서 별도로 검증됐다.

로컬에는 target Java 17 대신 Java 21만 있었다. Backend는 저장소를 수정하지 않고 임시
Gradle init script로 Java 21 컴파일러의 `--release 17`을 사용해 검증했다. 따라서 코드의
Java 17 bytecode 호환 회귀는 통과했지만 **Java 17 런타임 자체**는 이번 실행 증거가 아니다.

## 4. MVP 구현 순서

검증 반복보다 아래 순서로 한 개의 실제 replay를 끝까지 연결하는 것이 빠르다.

1. 클러스터 historical 생성일 로더와 추가 씨드·재급증 규칙을 구현한다.
2. 클러스터에서 GKG 검색 술어를 만들고 기존 lift writer까지 자동 호출한다.
3. `issue_report` 멱등 writer와 상태 전이를 구현한다.
4. Compose에 GATEWAY·두 matching worker 설정을 전달하고 종목 임베딩·GKG 입력을 준비한다.
5. 2025-06-12의 대표 이슈 하나를 `spike → cluster → stocks → summary → API`까지 통과시킨다.
6. 그 뒤 LIVE scheduler와 Spark `SINK=spike` 런타임을 연결한다.

## 5. 중단 기준

위 구현 전에는 전체 회귀나 같은 하루 원본을 다시 돌리지 않는다. 각 연결을 구현할 때 해당
단계의 focused test를 추가하고, 5번 실제 replay가 끝난 뒤에만 전체 회귀를 한 번 더 실행한다.
