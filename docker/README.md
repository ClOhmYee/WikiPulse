# 로컬 개발 스택 (Docker Compose)

`WP-63`. 팀원마다 파이썬·JDK·PostgreSQL 설치가 달라 생기는 의존성
문제를 컨테이너로 없앤다. `docker compose up` 하나로 전원이 같은 환경.

명세: [docs/requirements-v0.3.md](../docs/requirements-v0.3.md) §7

```
docker compose up -d postgres kafka        # 인프라만 (백엔드·파이썬 로컬 개발)
docker compose up -d                        # postgres + kafka + backend + frontend
docker compose --profile pipeline up -d     # producer·spark 까지
docker compose --profile gdelt up -d        # GDELT 수집(HDFS namenode·datanode) 까지
docker compose down                         # 정지 (데이터 유지)
docker compose down -v                       # 정지 + 데이터 삭제 (스키마 재적재)
```

`.env.example` 을 `.env` 로 복사해서 채운다 (`.env` 는 gitignore).

## 서비스

| 서비스 | 포트 | 무엇 | 프로필 |
| --- | --- | --- | --- |
| postgres | 5432 | PostgreSQL 16 + pgvector. 스키마 자동 적재 | 기본 |
| kafka | 9092 | Kafka KRaft 단일 브로커 | 기본 |
| backend | 8080 | Spring Boot. `ddl-auto=validate` | 기본 |
| frontend | 5174 | Vite dev server | 기본 |
| producer | — | EventStreams → Kafka | `pipeline` |
| spark | — | edit_windows 스트리밍 | `pipeline` |
| hdfs-namenode | 9870 | HDFS NameNode + WebHDFS 진입점 | `gdelt` |
| hdfs-datanode | — | HDFS DataNode (단일) | `gdelt` |

## GDELT 수집 (HDFS)

`WP-32`. GDELT GKG 원본을 적재할 **개발용 단일노드 HDFS**다. `--profile
gdelt` 로 namenode·datanode 가 뜬다. `db/migrations` 처럼 무언가 자동 적재하는
건 없고, GDELT producer(`data-pipeline/gdelt/`)가 WebHDFS 로 파일을 넣는다.

- **왜 로컬 HDFS 를 두나.** GDELT→HDFS producer 인데 HDFS 타깃이 로컬에 없으면
  WebHDFS 쓰기 경로를 검증할 수 없다. `-63` 이 세운 "개발 도커 ≠ EC2 실물" 경계를
  그대로 따라 단일 datanode·복제 1 로 둔다. EC2 실물(`WP-28`)은 2노드·복제 2.
- ⚠️ **WebHDFS 는 클라이언트를 datanode 호스트로 리다이렉트한다.** producer 를
  compose 네트워크 **안**에서 돌리면 `hdfs-datanode` 가 그대로 해석돼 매끄럽다.
  호스트에서 직접(`python -m gdelt.producer`) 돌리면 그 호스트명을 못 찾으므로,
  로컬 파일 싱크(`GDELT_SINK=local`)로 개발하고 HDFS 검증만 컨테이너로 한다.
- 세이프모드가 풀려야 쓰기가 된다. namenode healthcheck 가 그 시점을 healthy 로
  잡아 producer 의 `depends_on` 이 기다리게 해뒀다. 최초 기동은 포맷까지 40초±.
- ⚠️ 최초 포맷은 이미지 `starter.sh` 의 `ENSURE_NAMENODE_DIR` 이 한다. 이건 그
  디렉터리가 **없을 때만** 포맷하므로, 볼륨을 `name.dir`(`/data/name`)이 아니라
  **부모 `/data`** 에 건다. name.dir 자체에 걸면 디렉터리가 늘 존재해 포맷이 영영
  안 돌고 namenode 가 `InconsistentFSStateException` 으로 죽는다 (2026-09-09 실측).

### 검증 (2026-09-09, 이 스택으로 직접 확인)

- namenode 최초 포맷·기동 → healthcheck healthy(세이프모드 OFF), datanode 1대 등록.
- **WebHDFS 왕복 성공** — `PUT op=CREATE` HTTP 201(namenode→datanode 리다이렉트
  쓰기), `LISTSTATUS` 200, `OPEN` 으로 내용 일치 확인. producer 의 `WebHdfsSink`
  가 쓸 바로 그 경로다. compose 네트워크 안에서 `hdfs-datanode` 리다이렉트가
  그대로 해석됨.

## 왜 이렇게 없애나

- **파이썬 3.11 고정.** PySpark 3.5 는 3.12+ 에서 워커가 죽는다. 컨테이너가
  3.11 을 못박아 팀원이 3.13/3.14 를 깔아도 안 깨진다.
- **PostgreSQL + pgvector 를 각자 안 깐다.** 이미지가 확장까지 들고 온다.
  `db/migrations` 가 최초 기동 때 자동 적재돼 스키마가 항상 최신이다.
- **JDK·Gradle 을 각자 안 깐다.** 백엔드 이미지가 빌드·실행을 다 한다.
- **시간대 문제 없음.** 임베디드 PG(pgserver)에서 겪던 TimeZone 오류가
  실 PostgreSQL 에는 없다. `TZ=UTC` 로 못박았다.

## 검증 (2026-09-08, 이 스택으로 직접 확인)

- postgres·kafka 헬스체크 통과. **스키마 17개 테이블 + pgvector 자동 적재.**
- 백엔드 이미지 빌드(컨테이너 안 gradle bootJar) 후 실 PostgreSQL 에
  `ddl-auto=validate` 로 기동 성공 — 엔티티가 스키마와 정확히 맞는다.
- 실제 HTTP: `/actuator/health` UP, `/api/issues` 빈 배열 → 시드 후 카드,
  `/api/issues/1` 관련종목 조인(NEE tier BOTH lift 10.5), `/api/stocks/NEE/issues`.

### 수동 시드 시 빠뜨리기 쉬운 것 (2026-09-17 실측)

`issue_cluster`·`cluster_member`·`cluster_stock`만 채우면 상세(`/issues/{id}`)는
바로 뜨지만, 목록(`GET /issues`)과 펄스맵(`GET /issues/map`)은 시각 미지정 시
**`cluster_snapshot`에서 최신 스냅샷을 고른다**(WP-106) — 이 테이블에
행이 없으면 `issue_cluster`가 있어도 조용히 빈 목록이 온다. 시드에 반드시
`cluster_snapshot` 행(같은 `snapshot_ts`·`source`)을 같이 넣는다.

⚠️ **펄스맵은 추가로 `cluster_member.window_start`/`window_end`가 NULL이 아니어야
한다.** 프론트 계약 검증(`frontend/src/data/pulse/contract.js`)이 이 두 값을
필수로 보고, `window_end <= snapshotTs`까지 확인한다 — 하나라도 어긋나면
"이 시점의 지도를 불러오지 못했습니다(metric window)"로 스냅샷 전체가 빠진다.
`editCount`·`views` 등 나머지 지표는 nullable이라 이 둘만 특히 잘 놓친다.

## 스키마를 고쳤을 때

`db/migrations` 는 볼륨이 비어 있을 때만(최초 1회) 적재된다. 스키마를 바꿨으면:

```
docker compose down -v      # 데이터 볼륨 삭제
docker compose up -d postgres
```

운영에서는 마이그레이션 도구(Flyway 등)로 증분 적용한다 — 그건 별도 결정
사항이다(`db/` README).

## 운영과 다른 점

이건 **개발용**이다. 전부 단일 인스턴스·복제 1이라 EC2 실물 구성
(`WP-26`·`-28`·`-29`, 2노드·복제 2)과 다르다. 프론트도 dev server(핫
리로드)라 프로덕션 정적 빌드가 아니다.

⚠️ Docker Desktop(또는 Engine)이 필요하다. 작성 PC 에 Docker 를 설치해
(4.90.0) 이 스택을 실제로 띄워 검증했다.

## Spark 이미지 (WP-136)

`docker/spark/Dockerfile` 이 Spark 잡 실행 이미지를 만든다 — `python:3.11-slim-bookworm`
+ JRE 17 + `pyspark==3.5.3` + `psycopg[binary]==3.3.5`.

공식 `apache/spark:3.5.3-python3` 을 안 쓰는 이유는 그 이미지의 파이썬이 **3.8.10**
(Ubuntu 20.04 focal)이라 `psycopg 3.3.5` 가 안 깔리고, 그래서 LIVE 의 `SINK=spike`
경로가 아예 못 돌기 때문이다. focal 저장소에 3.11 이 없어 외부 PPA 를 붙이느니
파이썬을 바닥으로 깔고 Spark 를 pip 로 올렸다 — 버전이 Dockerfile 한 곳에 모인다.

    docker compose --profile pipeline build spark
    SPARK_SINK=spike docker compose --profile pipeline up -d spark

⚠️ **EC2 적용은 Driver 와 Worker 를 동시에 바꾼다.** 드라이버와 워커의 파이썬이 갈리면
파이썬 워커가 뜨는 순간 executor 가 죽는다(CLAUDE.md 인프라 절). 순서:

1. 두 EC2 에서 이 이미지를 빌드하거나 레지스트리로 옮긴다 (`~/infra/spark`)
2. Worker → Master → Driver 순으로 교체하고 `spark-submit --version` 으로 파이썬을 확인한다
3. `SINK=spike` 로 한 배치를 흘려 `spike_candidate` 에 행이 생기는지 본다

🔴 `SINK=spike` 로 돌릴 때는 `SPARK_SLIDE_SIZE` 를 `SPARK_WINDOW_SIZE` 와 같게 둔다
(compose 기본값이 그렇다). 조회수가 시간 버킷이라 정각 윈도우만 확정으로 간다 —
5분 슬라이드면 대기가 12배로 쌓이고 11/12 는 만료될 때까지 자리만 차지한다.
