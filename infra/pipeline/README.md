# LIVE pipeline deployment

`wikipulse-pipeline`이라는 독립 Compose 프로젝트로 Wikipedia producer와 Spark
edit stream만 실행한다. 기존 EC2 인프라 Compose와 UFW 설정은 수정하거나 재시작하지
않으며, 두 서비스 모두 호스트 포트를 게시하지 않는다.

서버 경로는 `/home/deploy/infra/pipeline`이고 저장소 경로도 같은 이름으로 맞췄다
(~~`deploy/live-pipeline`~~ → `infra/pipeline`, 2026-09-19). EC2 compose의 정본을
`infra/*`에 둔다는 WP-133 규칙을 따른 것이다.

🔴 **Spark driver 이미지는 Worker와 같은 파이썬이어야 한다.** 여기 `edit-stream`은
Worker와 같은 `apache/spark:3.5.3-python3`(파이썬 3.8)을 쓴다. `infra/README.md`가
예고한 대로 Worker를 `docker/spark/Dockerfile`(파이썬 3.11)로 바꾸는 순간 이 서비스도
같이 바꿔야 한다 — 버전이 갈리면 파이썬 워커가 뜨는 순간 executor가 죽는다.

## 준비

- 저장소의 `data-pipeline` 체크아웃 경로를 `PIPELINE_APP_DIR`로 지정한다.
- 기존 Spark/Hadoop 설정 디렉터리를 `SPARK_INFRA_DIR`로 지정한다.
- 기존 Kafka, Spark master, HDFS가 각 환경 변수의 주소에서 접근 가능해야 한다.

```bash
cd infra/pipeline
cp .env.example .env
chmod 0600 .env
unset RESTART_POLICY
PIPELINE_IVY_PATH="$(sed -n 's/^PIPELINE_IVY_DIR=//p' .env)"
test -n "$PIPELINE_IVY_PATH"
sudo install -d -m 0775 -o 185 -g 185 -- "$PIPELINE_IVY_PATH"
test "$(stat -c '%u:%g:%a' "$PIPELINE_IVY_PATH")" = "185:185:775"
```

운영 `.env`는 반드시 mode `0600`을 유지하고 실제 `CONTACT_EMAIL`과 서버 경로·주소를
채운다. `.env`와 자격 증명은 Git에 커밋하지 않는다. 저장소 체크아웃에서는 예제의
`PIPELINE_APP_DIR=../../data-pipeline`이 그대로 렌더링된다.

Spark 이미지는 UID/GID `185:185`로 실행한다. 위 preflight는 전용
`PIPELINE_IVY_DIR`을 그 계정이 쓸 수 있게 만들고 소유권과 mode를 검사한다. 이 검사가
통과하지 않으면 `--packages` 의존성 다운로드 전에 중단한다.

## 사전 확인과 canary 시작

컨테이너를 시작하기 전에 구성을 렌더링한다. `.env`의 `RESTART_POLICY=no`가 canary
기본값이므로 프로세스가 실패해도 무한 재시작하지 않는다.

```bash
grep -qx 'RESTART_POLICY=no' .env
sudo docker compose --env-file .env config --quiet
```

producer를 먼저 시작해 Kafka 발행과 cursor 저장을 확인한 뒤 edit-stream을 시작한다.

```bash
sudo docker compose --env-file .env up -d --build producer
sudo docker compose --env-file .env logs --since 3m producer
sudo docker compose --env-file .env up -d edit-stream
sudo docker compose --env-file .env logs --since 5m edit-stream
```

초기 로그 확인 뒤에도 `RESTART_POLICY=no`를 유지한다. 15분 canary와 producer/Spark
복구 검증에서는 정책을 바꾸지 않고 아래처럼 대상 서비스만 명시적으로 재시작한다.

```bash
sudo docker compose --env-file .env restart producer
sudo docker compose --env-file .env restart edit-stream
```

15분 canary, 두 재시작 복구 검증, 기존 서비스 상태 재확인까지 모든 Task 7 gate가
통과한 뒤에만 운영 재시작 정책을 활성화한다. 변경된 정책은 producer, edit-stream
순서로 적용한다.

```bash
sed -i 's/^RESTART_POLICY=no$/RESTART_POLICY=unless-stopped/' .env
grep -qx 'RESTART_POLICY=unless-stopped' .env
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env up -d producer
sudo docker compose --env-file .env up -d edit-stream
```

## 로그 취급

현재 `SINK=console`은 검증용으로 batch마다 집계 행을 최대 20개 출력한다. 집계 행에는
공개 Wikipedia `title`, wiki, window와 편집 집계값이 포함되며, 호스트 관리자는 Docker
로그로 열람할 수 있다. 두 서비스 로그는 `json-file`의 `max-size=10m`, `max-file=3`으로
제한된다. 집계 schema에는 원시 사용자명·meta ID·이벤트 본문·producer cursor·연락처
환경변수가 포함되지 않는다.

운영자가 `docker compose logs` 출력을 외부에 공유할 때는 공개 문서 제목과 시각·집계값이
포함된다는 점을 고려한다. PostgreSQL 적재 sink로 전환하기 전까지 console sink는 영구
결과 저장소가 아니라 동작 확인 수단이다.

## 중지와 복구

롤백 때는 이 독립 프로젝트의 `edit-stream`, `producer` 두 서비스만 중지한다. 기존
Kafka/Spark/HDFS 서비스나 기존 EC2 인프라 Compose/UFW는 중지하거나 변경하지 않는다.

```bash
sudo docker compose --env-file .env stop edit-stream producer
```

복구할 때도 사전 확인 후 producer, edit-stream 순서로 위 시작 명령을 다시 실행한다.
producer cursor는 `PIPELINE_STATE_DIR`, Spark streaming 상태는 HDFS의
`/wikipulse/checkpoints/edit-windows-v1`에 유지된다. 복구를 이유로 Kafka 토픽이나 HDFS
checkpoint를 삭제해서는 안 된다.
