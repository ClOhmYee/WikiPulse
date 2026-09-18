# EC2 인프라 (WP-133)

EC2 두 대의 `~/infra/*` 를 저장소로 옮긴 것이다. **서버가 날아가면 복구 근거가 사라진다**
는 CLAUDE.md 경고가 2026-09-18 에 실제로 물렸다 — 마이그레이션 V7~V9 가 EC2 에만 안
들어가 있었고, 백엔드 DB 롤에는 권한이 하나도 없었는데 둘 다 배포 경로에 없어서 아무도
몰랐다. 여기 있는 파일이 그 서버의 정본이다.

    infra/db       PostgreSQL + pgvector       (기본 EC2)
    infra/service  backend + frontend          (기본 EC2)
    infra/nginx    리버스 프록시 · certbot      (기본 EC2)
    infra/spark    Master + Worker             (추가 EC2 = Master·Driver, 기본 EC2 = Worker)
    infra/hdfs     NameNode · DataNode          (추가 EC2 = NameNode, 둘 다 DataNode)
    infra/pipeline LIVE producer + edit-stream  (추가 EC2, 2026-09-18 배포)

## 🔴 비밀값은 안 들어온다

`.env` 는 `.gitignore` 로 막혀 있고 `.env.example` 만 커밋한다 — **키 이름이 어디에도
없으면 서버를 다시 못 만든다.** 실제 값(DB 비밀번호·`LLM_GATEWAY_KEY`·사설 IP)은 서버의 `.env`
에만 둔다.

⚠️ `infra/spark/hadoop-conf/*.xml` 에는 사설 IP 가 들어 있다. private 저장소라 그대로
두지만, 공개 저장소로 옮기면 지운다.

## 배포와 스키마

    # 남은 마이그레이션 적용 + 애플리케이션 롤 권한 (재실행 안전)
    python db/apply_migrations.py --grant-role "$APP_DB_ROLE"

    # 이력이 없던 DB 에 한 번만 — 이미 손으로 적용한 버전까지 기록한다
    python db/apply_migrations.py --baseline 10

`schema_migration` 테이블이 무엇을 적용했는지 들고 있어서 **다시 돌려도 안전하다.**
권한은 `ALTER DEFAULT PRIVILEGES` 로 앞으로 만들 테이블까지 덮는다 — 마이그레이션마다
사람이 기억해서 GRANT 하는 구조였으면 또 빠진다.

## 🔴 마이그레이션은 DB 소유자로 붙는다

앱 롤(`user_wikipulse`)은 DML 만 갖고 있어서 테이블을 못 만든다 — 그게 맞는 상태다.
그래서 `infra/db/.env` 의 `MIGRATION_USER` 를 쓴다. 2026-09-18 에 두 `.env` 를 같이
읽었더니 `service/.env` 의 `POSTGRES_USER`(=앱 롤)가 이겨서
`permission denied for table wiki_page` 로 죽었다.

## 서버 반영 상태 (2026-09-18)

- ✅ **V1~V10 적용 완료.** `--baseline 9` 로 이력을 심고 V10 을 적용했다. 이력 10건,
  `spike_candidate` 존재, 앱 롤의 SELECT 권한 확인. 재실행은 `0개 적용 (변경 없음)`.
- ✅ 백엔드 롤 권한 — 이슈 API 가 500 에서 200 으로 돌아왔다.

아직 남은 것:

1. **Spark 이미지** — EC2 는 아직 `apache/spark:3.5.3-python3`(파이썬 3.8.10)라
   `SINK=spike` 가 못 돈다. `docker/spark/Dockerfile`(파이썬 3.11)로 바꾼다.
   ⚠️ **Driver 와 Worker 를 동시에** 바꾼다 — 버전이 갈리면 파이썬 워커가 뜨는 순간
   executor 가 죽는다. 절차는 `docker/README.md`.
   ⚠️ 바꿀 대상에 `infra/pipeline` 의 `edit-stream` 도 포함된다. 2026-09-18 에
   배포한 그 driver 가 지금 Worker 와 같은 `apache/spark:3.5.3-python3` 을 쓰고 있어
   현재는 짝이 맞지만, Worker 만 3.11 로 올리면 그 순간 갈린다.
2. **`live-cycle` 서비스** — 시간별 조회수 적재·재판정 주기(WP-135)가 EC2
   compose 에 아직 없다. `docker-compose.yml` 의 같은 이름 서비스를 참고해 옮긴다.

## 로컬과 뭐가 다른가

저장소 루트 `docker-compose.yml` 은 **개발 전용**이다(단일 인스턴스·복제 1·빌드 컨텍스트
로컬). 여기 `infra/*` 는 EC2 실물(2노드·복제 2·host 네트워크·외부 `wikipulse-net`)이다.
같은 서비스가 두 곳에 있는 건 의도된 것이고, 한쪽을 고치면 다른 쪽도 본다.
