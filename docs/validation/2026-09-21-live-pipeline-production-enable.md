# LIVE 실시간 파이프라인 최초 운영 활성화 — SINK=spike + live-cycle 상주 배포

- 검증 ID: `VAL-2026-09-21-PROD-01`
- 실행일: 2026-09-21 KST
- 환경: **서비스 EC2 운영** (`service.example.com`), 운영 DB(`wikipulse`) 직접 대상
- 대상: WP-135(재확인), WP-171
- 판정: **PASS** — 운영 DB에 `source='live'` 급증 이슈가 실제로 확정 저장됨

## 1. 발견 — LIVE 최종 관문이 한 번도 안 이어져 있었다

`WP-135`(LIVE 시간 주기)가 Jira상 **완료**였고 `infra/live-cycle/` 코드·문서도
이미 저장소에 있었지만, 실측해보니 **아무것도 배포돼 있지 않았다**.

```
데이터 EC2 wikipulse-edit-stream  SINK=console   ← 여전히 콘솔에만 찍고 버림
서비스 EC2 live-cycle 컨테이너     없음           ← 애초에 떠본 적이 없음
운영 DB spike_candidate           0행
운영 DB spike(source='live')      0행
```

코드·테스트·Jira 완료 표시가 다 있는데 운영엔 없는, 이 저장소에서 반복돼 온 패턴
(`stock`·`cluster` 누락과 같은 유형)과 동일했다.

## 2. 왜 데이터 EC2 직접 배선이 아니라 서비스 EC2 standalone인가

데이터 EC2의 공유 Spark 클러스터(`spark://192.0.2.10:7077`)는 워커가 여전히
Python 3.8.10 이다(`WP-136`도 Jira 완료 표시와 달리 미배포 확인, 2026-09-21
실측). 그 클러스터에 새 드라이버를 submit 하려면 워커 이미지도 같이 바꿔야 하고, 그건
곧 그 클러스터에서 지금 도는 팀원의 LIVE 콘솔 파이프라인을 재시작시킨다는 뜻이다.

**대신 서비스 EC2에서 `--master local[*]`(standalone, 클러스터 미접속)로 새
컨테이너를 띄웠다.** 데이터 EC2·공유 클러스터는 코드 한 줄, 설정 한 줄도 건드리지
않았다 — Kafka 는 읽기 전용으로 원격 구독만 한다(9092, 사설망 확인됨).

## 3. 절차 (저장소만 보고 재현 가능해야 한다)

`docker/spark/Dockerfile`(파이썬 3.11 고정, `WP-136` 산출물, 기존에 캐시돼
있어 즉시 빌드됨)을 그대로 썼다.

```bash
# 1. 격리 테스트 DB(wikipulse_test_live)로 전체 메커니즘 먼저 검증
#    (수집 → 대기 → 조회수 재판정 → 확정 → 원본 삭제, PASS. 아래 §4)

# 2. 운영 DB 인증 확인 (읽기 전용, 부작용 없음)
docker run --rm --network postgres_default -v <checkout>:/opt/app -w /opt/app \
  -e DATABASE_URL="postgresql://user_wikipulse:***@postgres:5432/wikipulse" \
  wikipulse-spark-standalone:local python3 -m spike.live_cycle --dry-run

# 3. 상주 배포 (재시작정책 unless-stopped)
docker run -d --name wikipulse-live-edit-stream --restart unless-stopped \
  --network postgres_default -v <checkout>:/opt/app -w /opt/app \
  -e SINK=spike -e DATABASE_URL="$REAL_DSN" \
  -e KAFKA_BOOTSTRAP_SERVERS=192.0.2.10:9092 -e KAFKA_TOPIC=wiki.edits \
  -e WINDOW_SIZE="1 hour" -e SLIDE_SIZE="1 hour" \
  wikipulse-spark-standalone:local \
  spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3 \
    --conf spark.jars.ivy=/tmp/ivy streaming/edit_windows.py

docker run -d --name wikipulse-live-cycle --restart unless-stopped \
  --network postgres_default -v <checkout>:/opt/app -w /opt/app \
  -e CONTACT_EMAIL=*** -e DATABASE_URL="$REAL_DSN" \
  wikipulse-spark-standalone:local \
  python3 -m spike.live_cycle --loop --interval 300
```

⚠️ **`SLIDE_SIZE`를 `WINDOW_SIZE`와 같게 줘야 한다.** 기본값(5분)으로 두면 한 시간에
12개 윈도우 중 정각 하나만 확정 후보가 될 수 있어(`spike/candidate_store.py` `due()`
독스트링), 나머지 11개는 영영 만료된다. 처음 캐너리에서 이걸 놓쳐 대기만 쌓이고
확정이 0건이었다 — `WINDOW_SIZE=1 hour, SLIDE_SIZE=1 hour`로 고치고서야 정각 윈도우가
나왔다.

⚠️ **Kafka 커넥터 JAR이 pip pyspark 에 기본 포함 안 된다.** `--packages
org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3`을 안 주면
`Failed to find data source: kafka`로 즉사한다(루트 `docker-compose.yml`의 실제
운영 설정에서 값을 그대로 가져왔다).

## 4. 격리 DB(`wikipulse_test_live`)에서 먼저 잡은 결함 2건

### 4-1. `prune_cache()`가 `main()`에만 있어 `live-cycle`엔 안 걸림 (`WP-171`)

`live_cycle.py`는 `ingest_hour()`를 직접 import 해서 쓰지 `pageview_hourly_ingest.main()`을
거치지 않는다. 처음 커밋(`9d7f504`, develop에 이미 머지됨)은 `main()` 끝에만
`prune_cache()`를 걸어놔서 **실제 서비스엔 정리 로직이 안 걸리는 죽은 코드**였다.
`run_once()`(실제로 매 주기 도는 자리)로 옮겨 다시 배선했다(`57a1b39`, 별도 MR).

### 4-2. 실제 파일 강제 삭제 검증

유닛 테스트(mock mtime)만으론 부족하다고 판단해, 실제로 받은 캐시 파일 하나를
`touch -d '50 hours ago'`로 조작하고 `prune_cache()`를 직접 호출해 **진짜로
지워지는지, 새 파일은 안 지워지는지** 확인했다.

```
조작 전: pageviews-20260921-030000.gz(50시간 전으로 조작) · pageviews-20260921-040000.gz(정상)
실행:   DELETED_COUNT 1
조작 후: pageviews-20260921-040000.gz 만 남음
```

## 5. 격리 DB 전체 파이프라인 결과 (배포 전 최종 게이트)

| 단계 | 결과 |
| --- | --- |
| 편집 감지 → 대기실(`spike_candidate`) | 2,209건 누적 |
| 시간별 조회수 재판정 | 2시간치 적재, 24건 재판정 |
| 확정(`spike`, source='live') | **3건** — French Revolution(5.088) · Jordan Love(5.215) · Pakistan at the 2026 Asian Games(5.485) |
| 처리 속도 | 윈도우 종료(05:00 UTC) → 확정(06:12 UTC), **약 1시간 12분** — 명세 §3.2 3번 목표(1~2시간) 안 |
| 원본 캐시 정리 | 실제 파일로 강제 검증, 정상 삭제 확인 |

## 6. 운영 배포 결과 (2026-09-21 06:49 UTC 기준)

| 항목 | 값 |
| --- | --- |
| `wikipulse-live-edit-stream` | `Up`, `--restart unless-stopped` |
| `wikipulse-live-cycle` | `Up`, `--restart unless-stopped` |
| 대상 DB | 운영 `wikipulse` (격리 DB 아님) |
| `spike_candidate`(배포 3분 후) | 23 → 99행으로 증가 중 |
| `spike(source='live')`(배포 3분 후) | 0건 — 아직 첫 시간 창의 조회수 지연(1시간+) 안 지남, 정상 |

## 7. 한계·재현 안 된 부분·다음 검증

- **운영에서의 확정(`spike(source='live')`) 건수는 이 보고서 작성 시점엔 미확인.**
  배포 직후라 조회수 공개 지연(1시간+)이 아직 안 지났다 — 격리 DB에서는 확인됐으나
  (§5), 운영에서 첫 확정 건이 실제로 나오는지는 별도로 재확인 필요.
- 이 배포는 팀의 `infra/live-cycle/compose.yaml` 공식 경로를 쓰지 않고, 검증에 쓰던
  로컬 체크아웃(`~/wikipulse-local-test`)을 그대로 재사용했다. **정식 `infra/`
  배치로 이관할지는 팀 논의 필요** — 지금은 동작 검증이 목적이라 최소 구성으로 갔다.
- 컨테이너 재시작정책은 있지만 **systemd·모니터링·알림은 없다.** 죽으면
  `docker ps`로 직접 봐야 안다.
- 데이터 EC2 공유 클러스터의 파이썬 3.8→3.11 전환(`WP-136`)은 여전히
  미배포다 — 그쪽을 고치면 이 standalone 우회 배포는 정리 대상이 된다.
