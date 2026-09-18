# LIVE 파이프라인 1차 배포 검증

- 검증 ID: `VAL-2026-09-18-LIVE-01`
- 실행일: 2026-09-18 KST
- 배포 대상: 데이터 EC2 `data.example.com`
- 서비스 EC2: 읽기 전용 기준선·최종 상태 확인만 수행
- 배포 커밋: `2d00cdb963c52f8aa69b0b12369b497a3f7506a1`
- 판정: **PASS — EventStreams → Kafka → 2-node Spark → HDFS checkpoint 지속 실행과 재시작 복구 확인**

## 1. 결론

추적된 `data-pipeline/`과 `deploy/live-pipeline/`만 버전 고정 아카이브로 배포했다.
기존 `.env`, Producer state·cursor, Ivy cache, Kafka topic, HDFS checkpoint는 덮거나
삭제하지 않았다. 실패한 옛 Spark 실행이 정상 commit한 checkpoint batch 0에서 새 코드가
batch 1로 재개됐으며, 15분 canary와 Producer·Spark 명시적 재시작을 모두 통과했다.

최종 상태는 다음과 같다.

| 항목 | 최종 상태 |
| --- | --- |
| `wikipulse-producer` | running, OOM 없음, `restart=unless-stopped`, image `sha256:d449ee94beff27c993abdad386103b7fb7d086fc43c27802dd78dbf7c0c884e0` |
| `wikipulse-edit-stream` | running, OOM 없음, `restart=unless-stopped` |
| Spark application | `app-20260918083122-0014`, `wikipulse-edit-windows` |
| worker 참여 | 데이터 EC2와 서비스 EC2 worker가 각각 1 core·1024 MiB executor 담당 |
| HDFS checkpoint | `hdfs://192.0.2.10:8020/wikipulse/checkpoints/edit-windows-v1`, 정책 승격 시 batch 57·최종 읽기 전용 확인 시 batch 309 |
| 기존 인프라 | 데이터 EC2 Kafka·Spark master/worker·HDFS NameNode/DataNode 정상, UFW active |

## 2. 배포 무결성과 보호 대상

아카이브는 clean exact HEAD에서 생성했다.

| 항목 | 값 |
| --- | --- |
| 파일 | `wikipulse-live-phase1-2d00cdb.tar.gz` |
| 범위 | tracked `data-pipeline/`, tracked `deploy/live-pipeline/` |
| 크기 | 263,937 bytes |
| SHA256 | `1f4a306dfd2af672254ddf3bfb8bbc740592663de19828a94eff5a4d415f5017` |
| 원격 해시 | 로컬과 일치 |
| 설치 경로 | `/home/deploy/infra/pipeline/app`, `/home/deploy/infra/pipeline/compose.yaml`, `/home/deploy/infra/pipeline/README.md` |

갱신 전후 inode·권한·mtime 검사를 통해 `.env`, `state/`, `ivy/`,
`state/last-event-id`가 배포 파일 복사로 바뀌지 않았음을 확인했다. `.env`는 배포와 정책
승격 후 모두 mode `0600`이었다. cursor 내용과 연락처 환경변수는 조회·출력·문서화하지
않았다.

사용한 비밀 없는 핵심 명령은 다음과 같다.

```bash
git archive --format=tar.gz --output=wikipulse-live-phase1-2d00cdb.tar.gz 2d00cdb963c52f8aa69b0b12369b497a3f7506a1 data-pipeline deploy/live-pipeline
sha256sum wikipulse-live-phase1-2d00cdb.tar.gz
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env up -d --no-deps --force-recreate edit-stream
sudo docker compose --env-file .env restart producer
sudo docker compose --env-file .env restart edit-stream
sudo docker exec hdfs-namenode-1 hdfs fsck hdfs://192.0.2.10:8020/wikipulse/checkpoints/edit-windows-v1 -files -blocks
```

## 3. checkpoint 재개와 분산 실행

이전 실패 실행은 batch 0의 `offsets/0`, `commits/0`, state를 정상 기록한 뒤 이중
watermark 계획 오류로 종료됐었다. checkpoint는 삭제하지 않았다. `2d00cdb` 코드를 적용해
종료된 `edit-stream`만 재생성하자 다음과 같이 이어졌다.

| 시각(UTC) | 증거 |
| --- | --- |
| 08:05:30 | 새 `edit-stream` 시작, `restart=no` |
| 시작 후 20초 | `offsets/1`, 기존 `commits/0` |
| 이후 | batch 1, 2, 3 순서로 출력·commit; checkpoint 호환성·동시 query 오류 0 |

Spark Master는 `wikipulse-edit-windows` 한 개를 active application으로 표시했다. 두 worker
호스트 `192.0.2.10`, `192.0.2.20`가 각각 1 core·1024 MiB executor를 받았다. worker가
반복적으로 executor를 잃은 흔적은 없었다.

console sink는 batch마다 집계 행을 최대 20개 출력한다. batch 1~6과 명시적 재시작 후
batch 45~48은 각각 20행이었다. 관측한 schema는 다음과 같다.

```text
window_start, window_end, wiki, title, edit_count, editor_count,
byte_delta_sum, last_edit_ts, max_rev_id
```

이 집계 행에는 공개 Wikipedia `title`과 wiki, window, 집계값이 포함되며 Docker의 bounded
`json-file` 로그(`max-size=10m`, `max-file=3`)에 보존되어 호스트 관리자에게 노출된다.
원시 `user`·meta ID·이벤트 본문·cursor·연락처 환경변수는 이 sink가 출력하거나 문서에
기록하지 않았다.

## 4. 15분 canary

- 엄격 관찰 시작: `2026-09-18T08:09:59Z`
- 900초 관찰 종료 표본: `2026-09-18T08:24:59Z`
- 관찰 루프 종료: `2026-09-18T08:25:14Z`
- 간격: 60초, 총 16개 표본

| 지표 | 시작 | 종료 |
| --- | ---: | ---: |
| Spark checkpoint commit batch | 10 | 40 |
| checkpoint 크기 | 7,360,171 B | 16,729,792 B |
| Producer CPU / memory | 1.59% / 20.77 MiB | 1.81% / 20.95 MiB |
| Spark driver CPU / memory | 51.33% / 696.6 MiB | 83.88% / 756.8 MiB |
| 호스트 가용 메모리 | 10,427 MiB | 10,255 MiB |
| 루트 디스크 | 4% | 4% |
| stream 오류 | 0 | 0 |

Spark checkpoint에 기록된 Kafka source offset은 세 파티션 모두 전진했다.

| 파티션 | batch 10 | batch 40 | 증가 |
| --- | ---: | ---: | ---: |
| 0 | 2,471 | 2,685 | 214 |
| 1 | 2,594 | 2,816 | 222 |
| 2 | 2,406 | 2,644 | 238 |

Producer 누적 통계는 첫 표본 `수신 256,658 / 발행 7,484 / 건너뜀 249,174 /
파싱실패 0`에서 마지막 표본 `수신 293,730 / 발행 8,193 / 건너뜀 285,537 /
파싱실패 0`으로 증가했다. 발행 증가는 709건이며 마지막 관측 속도는 0.9건/초였다.

Kafka 관리 CLI의 end-offset 조회는 canary 중 8~20초 제한 안에 응답하지 않았다. 따라서
위 값은 broker CLI 결과가 아니라 Spark가 각 batch에 commit한 Kafka source offset이다.
이 값은 실제 소비 진행을 증명하지만 broker의 순간 최신 end offset과 동일하다고 주장하지
않는다.

### 후속 broker–checkpoint 오프셋 대조

canary 종료 후 Kafka `AdminClient.list_offsets(latest)`와 HDFS checkpoint를 읽기 전용으로
두 번 대조했다. consumer group·subscription·offset commit은 만들거나 사용하지 않았다.
broker를 먼저 읽고 이어 checkpoint를 읽었으므로 각 행은 완전히 원자적인 한 시점의
snapshot은 아니다.

| KST | checkpoint batch | P0 broker / checkpoint / lag | P1 broker / checkpoint / lag | P2 broker / checkpoint / lag |
| --- | ---: | ---: | ---: | ---: |
| 19:32:57 | 295 | 4,557 / 4,550 / 7 | 4,935 / 4,930 / 5 | 4,725 / 4,719 / 6 |
| 19:34:16 | 298 | 4,583 / 4,580 / 3 | 4,948 / 4,945 / 3 | 4,746 / 4,742 / 4 |

79초 동안 broker와 checkpoint가 세 파티션 모두 전진했고 관측 lag 합계는 18건에서
10건으로 줄었다. 현재 소비가 broker 최신 위치에 근접해 따라가는 증거다. 이 후속 표본은
canary 시작·종료 시점의 broker end offset을 소급해 증명하지는 않는다.

## 5. 재시작 복구

### Producer

- 시작: `2026-09-18T08:25:55Z`
- 판정 완료: `2026-09-18T08:26:40Z`
- 재시작 정책: 검증 중 `no`
- 결과: running, OOM 없음, `EventStreams 연결됨 (이어받기)` 1회, 연결 실패 0회
- cursor: SHA256 fingerprint와 mtime이 변경됨. 내용은 읽지 않음
- Spark checkpoint: batch 41 → 43
- Kafka source offset: `2693/2826/2654` → `2708/2840/2675`
- 재시작 후 통계: 수신 1,387, 발행 28, 건너뜀 1,359, 파싱실패 0

### Spark

- 시작: `2026-09-18T08:27:20Z`
- 판정 완료: `2026-09-18T08:28:28Z`
- 재시작 정책: 검증 중 `no`
- 재시작 직전: offsets/commits batch 44, source offset `2717/2846/2679`
- 재시작 후: 같은 checkpoint에서 batch 45, 46 commit, source offset `2737/2875/2701`
- 결과: fresh `earliest` 시작이 아닌 다음 batch 재개, 호환성·동시 query·분석 오류 0

## 6. HDFS 건전성

checkpoint에는 `metadata`, `offsets`, `commits`, `sources`, `state`가 모두 존재했다.
post-canary fsck 결과는 다음과 같다.

- `Status: HEALTHY`
- DataNode 2개
- default replication factor 2
- average block replication 2.0
- under-replicated blocks 0
- 검사 시 986개 블록의 `Live_repl=2`

정책 승격 후 최종 checkpoint는 26개 디렉터리, 1,101개 파일, 20,122,367 bytes였고
offsets/commits가 모두 batch 57까지 전진했다.

## 7. 기존 서비스 비교

데이터 EC2의 기존 Kafka, Spark master/worker, HDFS NameNode/DataNode는 시작부터 끝까지
같은 컨테이너로 running/healthy 상태를 유지했다. UFW도 계속 active였다. 기존 Kafka topic,
HDFS daemon, Spark master/worker, UFW, 인프라 Compose는 변경하지 않았다.

서비스 EC2는 읽기 전용으로만 조회했다. 최초 기준선 `08:03:07Z`의 백엔드 image는
`wikipulse-backend:7c97535f`였다. `08:29:25Z`에도 동일했지만, 최종 `08:32:08Z`에는
외부 CI 배포로 보이는 `wikipulse-backend:d77ce0f8`로 바뀌어 있었다. 중간에 CI runner
컨테이너가 나타났다가 사라진 점도 이 해석과 일치한다. 본 작업은 서비스 EC2에서 어떠한
파일·컨테이너·설정도 수정하지 않았다. 최종 백엔드, Nginx, PostgreSQL, Spark worker,
HDFS DataNode는 모두 running이며 건강 검사가 있는 컨테이너는 healthy였다. UFW도 active였다.

## 8. 정책 승격과 최종 상태

모든 gate 통과 후에만 `.env`의 `RESTART_POLICY` 한 줄을 `unless-stopped`로 바꿨다.
환경 파일 내용은 출력하지 않았고 mode `0600`을 유지했다.

1. `sudo docker compose --env-file .env config --quiet`
2. Producer만 적용·running 확인
3. `edit-stream`만 적용·같은 checkpoint에서 다음 batch 확인
4. 두 신규 서비스의 정책만 확인

승격 적용 시각은 Producer `08:30:59.979574922Z`, Spark driver
`08:31:16.286529635Z`다. 적용 과정에서 checkpoint batch 51 → 52가 진행됐고 오류는
0건이었다. 최종 두 서비스는 모두 running, OOM 없음, `restart=unless-stopped`다.

`19:39:27 KST` 최종 읽기 전용 확인에서도 두 신규 서비스는 같은 상태를 유지했고
checkpoint commit은 batch 309까지 전진했다. 데이터 EC2의 Kafka·Spark master/worker·HDFS
NameNode/DataNode와 서비스 EC2의 백엔드·Nginx·PostgreSQL·Spark worker·HDFS DataNode도
running이었으며 건강 검사가 있는 컨테이너는 healthy였다. 두 서버의 UFW는 모두 active였다.

## 9. 실패 이력, 남은 위험, 인프라 인계

이번 배포 전에 발견·수정한 실패는 두 건이다.

1. checkpoint URI에 NameNode authority가 없어 첫 Spark 실행이 실패했다. 현재 URI는
   `hdfs://192.0.2.10:8020/...`로 고정했다.
2. 하나의 stream lineage에서 watermark를 두 번 정의해 batch 0 이후 Spark가 종료됐다.
   `2d00cdb`에서 watermark를 한 번만 정의하고 실제 streaming 2-batch 회귀를 추가했다.

남은 위험과 인계 사항:

- `wiki.edits`는 3 partitions, replication factor 1, retention 7일이다. broker 장애 내성은 없다.
- 이번 단계의 Spark sink는 console이다. PostgreSQL/API 제공 경로는 별도 단계다.
- checkpoint는 약 15분에 7.36 MiB → 16.73 MiB로 증가했다. 장시간 state 크기와 HDFS
  보존 정책을 관찰해야 한다.
- canary 중 Kafka 관리 CLI 조회 지연 원인은 별도로 확인해야 한다. 후속 검증에서는
  읽기 전용 AdminClient 조회가 성공해 현재 broker–checkpoint lag를 보완 기록했다.
- Producer cursor 파일은 root 소유 mode `0644`였으나 지정 state 디렉터리 안에서 저장·재개에
  성공했다. 운영 계정 정책을 정할 때 소유권을 재검토할 수 있다.
- 데이터 EC2 RAM 16 GiB에서 현재 두 신규 서비스는 제한 안에서 안정적이었지만 Kafka,
  Spark, HDFS와 함께 장시간 운영 시 CPU credit과 state 증가를 계속 관찰해야 한다.

롤백 시 기존 topic이나 checkpoint를 삭제하지 않는다. 먼저 정책을 `no`로 되돌리고 Compose
렌더링을 확인한 뒤 `wikipulse-edit-stream`, `wikipulse-producer` 두 신규 서비스만 중지한다.
기존 Kafka·Spark·HDFS·UFW·서비스 EC2는 건드리지 않는다.
