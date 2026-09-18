# LIVE 파이프라인 1차 구축 설계

- 작성일: 2026-09-18
- 대상: 데이터 EC2 `data.example.com`
- 기준 코드: `develop`의 `5d8a31b`
- 범위: Wikipedia EventStreams → Kafka → Spark 편집 윈도우 집계

## 1. 목표와 완료 조건

기존 서비스에 영향을 주지 않고 LIVE 수집·전처리의 첫 구간을 실제 EC2에 상시 실행 가능한 형태로 올린다.

완료 조건은 다음과 같다.

1. EventStreams의 `enwiki`, namespace 0, 비봇 edit/new 이벤트가 Kafka `wiki.edits`에 들어간다.
2. Spark Structured Streaming이 기존 2노드 Spark 클러스터에서 토픽을 읽고 문서별 1시간/5분 슬라이딩 윈도우를 집계한다.
3. Spark 재시작 후 HDFS 체크포인트에서 Kafka offset과 집계 상태를 복구한다.
4. Producer 재시작 후 저장된 SSE `Last-Event-ID`부터 재개한다.
5. 재시작 경계에서 발생 가능한 Kafka 중복 이벤트는 `meta_id`로 제거되어 집계값을 부풀리지 않는다.
6. PostgreSQL, Spring Boot, Nginx와 기존 Kafka·Spark·HDFS 데몬의 설정 및 실행 상태는 바꾸지 않는다.

## 2. 현재 실측 상태

2026-09-18 읽기 전용 점검 결과다.

- 데이터 EC2에서 Kafka 3.9.0, Spark 3.5.3 Master/Worker, HDFS 3.5.0 NameNode/DataNode가 정상 실행 중이다.
- 서비스 EC2의 Spark Worker와 HDFS DataNode도 정상 실행 중이다.
- Spark Worker는 각 2 cores/4 GiB이며 기존 방화벽에 고정 포트가 이미 허용되어 있다.
- Spark 설정에는 Master `spark://192.0.2.10:7077`, Driver `7079`, Driver BlockManager `7080`, Executor BlockManager `7100`이 고정되어 있다.
- HDFS 기본 주소는 `hdfs://192.0.2.10:8020`, 복제 계수는 2다.
- Kafka는 자동 토픽 생성을 끈 상태이며 기본 보존 기간은 7일이다.
- HDFS `/wikipulse`에는 기존 검증 데이터가 있으나 LIVE 스트리밍 체크포인트는 없다.
- 현재 EventStreams Producer와 Spark 스트리밍 Driver는 배포되어 있지 않다.

## 3. 채택 구조

```text
Wikimedia EventStreams
        │ SSE + Last-Event-ID
        ▼
Producer 컨테이너 ──▶ Kafka wiki.edits ──▶ Spark Driver 컨테이너
        │                                      │
        │ cursor 파일                          ├─▶ 기존 Spark Worker 2대
        ▼                                      │
호스트 bind mount                              ▼
                                   HDFS checkpoint (복제 2)
                                   + console sink
```

신규 구성은 데이터 EC2의 `/home/deploy/infra/pipeline`에 별도 Compose 프로젝트로 둔다. 기존 `/home/deploy/infra/kafka`, `/home/deploy/infra/spark`, `/home/deploy/infra/hdfs`의 Compose 파일은 수정하지 않는다.

신규 서비스는 두 개뿐이다.

- `producer`: 저장소의 Python 3.11 Producer 이미지를 빌드하여 EventStreams를 Kafka로 전달한다.
- `edit-stream`: 기존 `apache/spark:3.5.3-python3` 이미지로 `streaming/edit_windows.py`를 제출한다.

두 서비스는 기존 사설 주소에 연결하기 위해 host network를 사용한다. 외부 공개 포트와 UFW 규칙은 추가하지 않는다.

## 4. Producer 재시작 안전성

현재 `SSEClient.last_event_id`는 메모리에만 있어 컨테이너 재시작 시 수집 공백이 생길 수 있다. 배포 전에 다음 최소 변경을 적용한다.

1. SSE parser가 payload와 SSE event ID를 함께 반환한다.
2. Producer는 대상 이벤트를 Kafka에 전송하고 broker acknowledgement를 확인한다.
3. acknowledgement가 확인된 뒤에만 마지막 처리 SSE event ID를 커서 파일에 기록한다.
4. 커서 파일은 같은 디렉터리의 임시 파일에 쓰고 `fsync` 후 `os.replace`하여 원자적으로 교체한다.
5. 시작 시 커서 파일이 있으면 값을 읽어 첫 요청의 `Last-Event-ID` 헤더에 넣는다.
6. 파일이 손상되었거나 기록에 실패하면 조용히 최신 지점으로 넘어가지 않고 Producer를 실패시킨다.

EC2에서는 `SSE_CURSOR_FILE=/var/lib/wikipulse-producer/last-event-id`를 지정하고 `/home/deploy/infra/pipeline/state`를 bind mount한다. `.env`와 커서 파일은 저장소에 커밋하지 않는다.

처리량은 enwiki 약 2 events/s이므로 안전성을 위해 대상 이벤트별 Kafka acknowledgement를 확인하는 단순한 방식을 사용한다. 높은 처리량 최적화는 실제 병목이 확인될 때만 도입한다.

커서를 acknowledgement 이후 기록하므로 강제 종료 시 마지막 일부 이벤트가 다시 들어올 수 있다. 이는 누락을 피하기 위한 의도된 at-least-once 동작이다.

## 5. Spark 중복 제거와 체크포인트

재전송 중복이 윈도우 집계량을 부풀리지 않도록 Kafka JSON을 파싱하고 `event_ts`를 만든 직후 `meta_id` 기준 중복 제거를 수행한다.

- 스트리밍에서만 `dropDuplicatesWithinWatermark(["meta_id"])`를 적용한다.
- watermark는 기존 값인 10분을 사용한다.
- 배치 집계 함수의 의미는 바꾸지 않아 기존 batch/stream parity 계약을 유지한다.
- `meta_id`가 없는 이벤트는 유효한 EventStreams 계약으로 보지 않고 계측 후 제외한다.

Spark 체크포인트는 로컬 `/tmp`가 아니라 HDFS `/wikipulse/checkpoints/edit-windows-v1`을 사용한다. 이 경로에는 Kafka offset, 중복 제거 상태, 집계 상태가 함께 저장되며 HDFS 복제 계수 2가 적용된다.

1차 구축의 sink는 `console`로 고정한다. PostgreSQL 적재는 Python/psycopg 이미지 호환, 조회수 결합, B축 시점 정책이 정리된 뒤 별도 단계에서 연결한다.

## 6. Kafka 토픽

배포 전에 토픽 존재 여부와 설정을 읽는다.

- 이름: `wiki.edits`
- partitions: 1
- replication factor: 1
- retention: 7일 (`604800000 ms`)

토픽이 없을 때만 `--if-not-exists`로 생성한다. 이미 있다면 메시지를 지우거나 토픽을 재생성하지 않고 partitions, replication factor, retention 설정을 검증한다. 이번 단계에서는 토픽 삭제, offset reset, 기존 데이터 정리를 하지 않는다.

## 7. 자원 제한

초기 자원 상한은 다음과 같다.

- Producer: CPU 0.25 core, memory 256 MiB
- Spark Driver: memory 1 GiB
- Spark application: 최대 2 cores, executor당 1 GiB
- Kafka `maxOffsetsPerTrigger`: 50,000
- Spark trigger: 30초
- shuffle partitions: 8
- Docker log rotation: 서비스별 10 MiB × 3 files

기존 Worker 총량은 4 cores/8 GiB다. 1차 잡이 절반 이하만 사용하게 해 웹 서비스와 기존 인프라의 여유를 보존한다.

## 8. 적용 순서

1. 로컬에서 cursor store, acknowledgement 순서, 재시작 중복 제거 테스트를 먼저 작성한다.
2. 관련 Python 테스트와 기존 스트림/배치 parity 테스트를 실행한다.
3. 신규 Compose를 로컬에서 `docker compose config --quiet`로 검증한다.
4. 데이터 EC2의 CPU, RAM, disk, 기존 컨테이너 health와 Kafka 토픽 목록을 다시 읽는다.
5. `/home/deploy/infra/pipeline`에 신규 파일만 배치한다.
6. `CONTACT_EMAIL`은 서버의 `.env`에만 입력하고 출력이나 문서에 노출하지 않는다.
7. `wiki.edits` 토픽을 존재하지 않을 때만 생성한다.
8. Producer만 시작해 3분간 발행률, 오류, 토픽 offset 증가를 확인한다.
9. Spark Driver를 시작해 두 Worker 참여, Kafka 소비, HDFS 체크포인트 생성을 확인한다.
10. 15분 canary 동안 CPU, RAM, disk, consumer lag, malformed count, Spark batch 진행을 관찰한다.
11. Producer 한 번, Spark Driver 한 번을 각각 단독 재시작해 커서와 체크포인트 복구를 확인한다.
12. 모든 조건을 통과한 경우에만 `restart: unless-stopped` 상태로 상시 실행한다.

각 단계가 실패하면 다음 단계로 넘어가지 않는다.

## 9. 중단 기준과 복구

다음 중 하나면 신규 서비스만 즉시 중지한다.

- 기존 Kafka, Spark Master/Worker, HDFS 데몬 중 하나가 unhealthy 또는 종료 상태가 된다.
- 데이터 EC2 메모리 가용량이 2 GiB 아래로 지속 하락한다.
- root filesystem 사용률이 80%를 넘는다.
- Kafka 발행 또는 Spark micro-batch가 5분 이상 진전하지 않는다.
- malformed 이벤트가 지속 증가하거나 정상 이벤트의 `meta_id`가 비어 있다.
- Spark checkpoint 오류, executor 반복 재시작, 처리되지 않은 Kafka delivery error가 발생한다.

복구는 `producer`와 `edit-stream`만 중지하는 것으로 시작한다. 기존 인프라 컨테이너는 재시작하지 않는다. 신규 파일, Kafka 토픽, HDFS 체크포인트도 원인 분석 전에는 삭제하지 않는다. 삭제가 필요하면 대상과 복구 가능성을 별도로 보고하고 승인을 받는다.

## 10. 검증 증거와 운영 인계

실행 결과는 `docs/validation/2026-09-18-live-pipeline-phase1.md`에 남긴다.

반드시 기록할 항목은 다음과 같다.

- 적용한 git commit과 이미지 식별자
- 시작·종료 시각과 실행 명령
- 토픽 설정 및 시작/종료 offset
- Producer 수신·발행·skip·malformed 수치
- Spark application ID, 참여 Worker, micro-batch 진행 수치
- HDFS checkpoint 경로와 복제 상태
- 재시작 전후 커서, offset, 중복 제거 검증 결과
- canary 전후 CPU, RAM, disk
- 실패와 우회가 있었다면 원인, 남은 위험, 인프라 담당 전달 사항

## 11. 이번 단계에서 하지 않는 것

- Spring Boot, PostgreSQL, Nginx 수정
- `SINK=spike` 또는 운영 DB 적재
- GDELT, 시간별 pageviews, Clickstream 수집기 상시화
- 자동 급증 판정, 클러스터링, 요약, 종목 매칭 실행
- Kafka/HDFS 기존 데이터 삭제 또는 offset reset
- UFW, 기존 Compose, 기존 컨테이너 restart 정책 변경
- 모니터링 스택, Kafka UI, Airflow, Redis 추가

이 범위 밖의 변경이 필요해지면 작업을 멈추고 변경 이유, 대상, 영향, 복구 방법을 먼저 보고한다.
