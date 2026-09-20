# LIVE 시간 주기 배포 (WP-135)

`live-cycle` 이라는 독립 Compose 프로젝트로 **서비스(기본) EC2** 에서 돈다.
한 주기는 이렇다 — 자세한 근거는 `data-pipeline/spike/live_cycle.py` 머리말.

    1. 대기 중인데 조회수가 아직 없는 윈도우를 찾는다  (spike_candidate ⟕ page_view_hourly)
    2. 그 시간·그 문서만 적재한다                      (batch.pageview_hourly_ingest)
    3. 재판정한다                                     (spike.recheck)

🔴 **추가 EC2 가 아니라 기본 EC2 다.** PostgreSQL 이 거기 있고 `wikipulse-net` 안에서
`postgres:5432` 로 붙는다. 추가 EC2 에서는 아직 못 붙는다 — 5432 가 사설망에 게시돼
있지 않다(WP-143). 같은 호스트에 두면 그 문제를 안 만난다.

## 🔴 이미지가 고쳐진 뒤에야 돈다

`data-pipeline/Dockerfile` 이 `producer/` 만 복사하고 있어서 이 서비스는 **한 번도 뜬 적이
없었다** — `python -m spike.live_cycle` 이 `ModuleNotFoundError: No module named 'spike'`
로 즉사한다. 2026-09-20 에 이미지를 직접 빌드해 확인했고 같은 커밋에서 `spike/`·`batch/`
복사와 `psycopg` 설치를 더했다. 루트 `docker-compose.yml` 의 같은 이름 서비스도 이 때문에
안 돌던 것이라 같이 고쳐졌다.

⚠️ 그래서 **배포 전에 이미지부터 확인한다.** 이 한 줄이 usage 를 뱉어야 한다.

```bash
docker compose --env-file .env run --rm --build live-cycle python -m spike.live_cycle --help
```

## 준비

```bash
cd /home/deploy/infra/live-cycle
cp .env.example .env
chmod 0600 .env
# POSTGRES_* 는 infra/db/.env · infra/service/.env 와 같은 값이어야 한다.
# CONTACT_EMAIL 이 비면 Wikimedia 가 User-Agent 로 차단한다.
sudo docker compose --env-file .env config --quiet
```

## canary

`RESTART_POLICY=no` 인 채로 한 주기만 돌려 본다. `--dry-run` 은 아무것도 안 쓴다.

```bash
sudo docker compose --env-file .env run --rm live-cycle \
    python -m spike.live_cycle --dry-run
```

받을 게 보이면 실제로 한 주기를 돌린다.

```bash
sudo docker compose --env-file .env run --rm live-cycle \
    python -m spike.live_cycle
```

`spike_candidate` 의 대기가 줄고 `page_view_hourly` 에 그 시간 행이 생기는지 DB 에서
직접 확인한다 — 로그만 보고 넘어가지 않는다(CLAUDE.md "운영 DB 에서 행 수 확인").

## 상주 전환

canary 가 통과한 뒤에만 policy 를 바꾼다.

```bash
sed -i 's/^RESTART_POLICY=no$/RESTART_POLICY=unless-stopped/' .env
grep -qx 'RESTART_POLICY=unless-stopped' .env
sudo docker compose --env-file .env up -d --build live-cycle
sudo docker compose --env-file .env logs --since 20m live-cycle
```

## 디스크

받은 시간별 덤프가 `live-cycle-data` 볼륨에 쌓인다. gz 시간당 약 45 MB → **하루 1 GB
남짓이고 지우는 코드는 없다.** 서비스 EC2 디스크를 주기적으로 본다.

```bash
docker system df -v | grep live-cycle-data
```

## 중지

```bash
sudo docker compose --env-file .env stop live-cycle
```

멱등이라 다시 켜면 밀린 구간을 `--max-hours` 씩 따라잡는다. 대기·확정 상태는 전부 DB 에
있으므로 볼륨을 지워도 결과는 같다(덤프를 다시 받을 뿐이다).
