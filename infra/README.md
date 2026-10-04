# EC2 인프라 (WP-133)

EC2 두 대의 `~/infra/*` 를 저장소로 옮긴 것이다. **서버가 날아가면 복구 근거가 사라진다**
는 https://github.com/ClOhmYee/WikiPulse 경고가 2026-09-18 에 실제로 물렸다 — 마이그레이션 V7~V9 가 EC2 에만 안
들어가 있었고, 백엔드 DB 롤에는 권한이 하나도 없었는데 둘 다 배포 경로에 없어서 아무도
몰랐다. 여기 있는 파일이 그 서버의 정본이다.

    infra/db       PostgreSQL + pgvector       (기본 EC2)
    infra/service  backend + frontend          (기본 EC2)
    infra/nginx    리버스 프록시 · certbot      (기본 EC2)
    infra/spark    Master + Worker             (추가 EC2 = Master·Driver, 기본 EC2 = Worker)
    infra/hdfs     NameNode · DataNode          (추가 EC2 = NameNode, 둘 다 DataNode)
    infra/pipeline LIVE producer + edit-stream  (추가 EC2, 2026-09-18 배포)
    infra/live     LIVE 상주 셋 — edit-stream·live-cycle·live-cluster
                                                 (기본 EC2, WP-196)
    infra/live-cycle 시간별 조회수·재판정 주기 (기본 EC2, WP-135)
                   ⚠️ infra/live 와 **다른 정의**다. 실물은 infra/live 쪽이고
                      이건 안 쓰인다 — 어느 쪽으로 갈지는 -196 에서 정한다
    infra/stock    종목 마스터·설명·임베딩 적재 (기본 EC2, WP-147)
                   ⚠️ 상주 서비스가 아니라 일회성이다 — `run --rm` 으로 돌린다

## 🔴 비밀값은 안 들어온다

`.env` 는 `.gitignore` 로 막혀 있고 `.env.example` 만 커밋한다 — **키 이름이 어디에도
없으면 서버를 다시 못 만든다.** 실제 값(DB 비밀번호·`LLM_GATEWAY_KEY`·사설 IP)은 서버의 `.env`
에만 둔다.

⚠️ `infra/spark/hadoop-conf/*.xml` 에는 사설 IP 가 들어 있다. private 저장소라 그대로
두지만, 공개 저장소로 옮기면 지운다.

## 🔴 배포 러너 권한

`deploy:backend` 는 `ubuntu` 가 아니라 **`gitlab-runner` 계정으로** 돈다 (ec2-shell
러너, 서비스 EC2). 그래서 그 계정이 다음 두 파일을 **읽을 수 있어야 한다.**

    /home/deploy/infra/db/.env        # MIGRATION_USER · POSTGRES_PASSWORD
    /home/deploy/infra/service/.env   # POSTGRES_* · APP_DB_ROLE

⚠️ 이 전제가 적혀 있지 않아서 실제로 두 번 터졌다 — 파이프라인 #207183(2026-09-18,
`-133` 머지)과 #207748(2026-09-19). 둘 다 `infra/apply-migrations.sh` 의 첫 검사에서
1초 만에 죽었고, 배포는 한 줄도 실행되지 않았다.

`.env` 는 비밀값이라 `0600 ubuntu:ubuntu` 다. 파일을 세계 공개로 열지 말고 배포
계정만 읽게 한다. ACL 보다 그룹이 낫다 — `ls -l` 에 보이므로 나중에 왜 이런지 안다.

```bash
sudo groupadd -f wikipulse-deploy
sudo usermod -aG wikipulse-deploy gitlab-runner
sudo chgrp wikipulse-deploy /home/deploy/infra/db/.env /home/deploy/infra/service/.env
sudo chmod 0640 /home/deploy/infra/db/.env /home/deploy/infra/service/.env
sudo systemctl restart gitlab-runner     # 🔴 그룹은 프로세스를 다시 띄워야 붙는다

# 확인 — 이 세 줄이 다 통과해야 배포 잡이 넘어간다
sudo -u gitlab-runner test -r /home/deploy/infra/db/.env && echo "db env OK"
sudo -u gitlab-runner test -r /home/deploy/infra/service/.env && echo "service env OK"
sudo -u gitlab-runner docker ps >/dev/null && echo "docker OK"
```

### 🔴 `.env` 를 **편집하면** 권한이 리셋된다 — 세 번째로 물린 함정

위 설정은 **최초 1회**가 아니다. 파일을 고칠 때마다 다시 확인해야 한다.

⚠️ **`sed -i` 는 파일을 새로 만들어 교체한다.** 그래서 그룹 소유권이 날아가고
`ubuntu:ubuntu` 로 돌아간다. `chmod 0600` 도 그룹 읽기를 지운다. 둘 중 하나만 해도
다음 배포가 첫 검사에서 죽는다.

🔴 **`infra/edit-env.sh` 를 쓴다** (WP-178). 편집·권한 복구·러너 읽기 검증을
한 덩어리로 묶는다. 사람이 세 단계를 기억하는 구조라 **네 번 터졌다.**

```bash
infra/edit-env.sh /home/deploy/infra/service/.env     WIKIPULSE_MATCHING_SUMMARY_ENABLED=true     WIKIPULSE_MATCHING_SUMMARY_SOURCE=replay
```

그룹이 이미 틀어진 파일도 이 스크립트를 거치면 바로잡힌다. 손으로 고쳐야 한다면
아래 두 줄이 최소한이다.

```bash
sudo chgrp gitlab-runner /home/deploy/infra/service/.env
sudo chmod 0640 /home/deploy/infra/service/.env
```

### 왜 `sed -i` 가 문제인가 (2026-09-21 실측)

```
원본        -rw-r----- ubuntu gitlab-runner
sed -i 뒤   -rw-r----- ubuntu ubuntu          ← 그룹이 날아간다
cat > 뒤    -rw-r----- ubuntu gitlab-runner   ← 보존된다
```

`sed -i` 는 새 파일을 만들어 **교체**한다. `cat tmp > 파일` 은 **기존 inode 에 써 넣어서**
소유권·권한이 남는다. `edit-env.sh` 가 쓰는 경로가 이쪽이다.

⚠️ **실제 그룹은 `gitlab-runner` 다.** 위 설정 절이 제안한 `wikipulse-deploy` 그룹은
이 서버에 **존재하지 않는다**(2026-09-21 실측). `infra/db/.env` 도 `ubuntu:gitlab-runner
0640` 이다 — 새 파일을 만들면 그쪽에 맞춘다.

이 함정으로 죽은 파이프라인: #207183(2026-09-18) · #207748(2026-09-19) ·
#210453(2026-09-21, `.env` 에 GATEWAY 키를 넣다가) · **#214248(2026-09-21, `-168` 머지 —
앞선 세션이 `SUMMARY_ENABLED` 를 토글하면서 리셋)**. 앞의 둘은 최초 설정 누락이었고
나머지는 **편집 뒤 복구 누락**이라 원인이 다르다 — 그래서 이 절을 따로 둔다.

⚠️ 이건 **CI 가 DB 소유자 비밀번호를 읽을 수 있게 된다**는 뜻이다. 그 러너는 이미
develop 의 코드를 그대로 실행하고 `docker compose up` 으로 같은 `.env` 를 쓰므로 새
경계가 무너지는 건 아니지만, 팀에 알리고 넘어간다.

⚠️ 권한을 고친 뒤에는 **실패한 잡을 Retry 해서 초록불을 확인한다.** 이 관문 다음에
`docker build` → `docker compose up -d backend` → health check 가 남아 있고, 그 구간은
아직 한 번도 끝까지 성공한 적이 없다.

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
2. ~~**`live-cycle` 서비스** — EC2 compose 에 아직 없다~~ → `infra/live-cycle` 로
   들어왔다 (2026-09-20). **아직 배포는 안 했다** — 절차와 canary 게이트는
   `infra/live-cycle/README.md`.
   🔴 옮기면서 안 것: 루트 `docker-compose.yml` 의 그 서비스는 **한 번도 뜬 적이
   없었다.** `data-pipeline/Dockerfile` 이 `producer/` 만 복사해서
   `python -m spike.live_cycle` 이 `ModuleNotFoundError` 로 즉사한다. 이미지를
   직접 빌드해 확인했고 같은 커밋에서 `spike/`·`batch/`·`psycopg` 를 더했다.

## 로컬과 뭐가 다른가

저장소 루트 `docker-compose.yml` 은 **개발 전용**이다(단일 인스턴스·복제 1·빌드 컨텍스트
로컬). 여기 `infra/*` 는 EC2 실물(2노드·복제 2·host 네트워크·외부 `wikipulse-net`)이다.
같은 서비스가 두 곳에 있는 건 의도된 것이고, 한쪽을 고치면 다른 쪽도 본다.
