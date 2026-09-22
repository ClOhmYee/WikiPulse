# LIVE 상주 서비스 (WP-196)

서비스(기본) EC2 에서 도는 LIVE 파이프라인 세 개다.

```
Kafka(wiki.edits) → edit-stream → spike_candidate
                                       ↓
                    live-cycle → 조회수 적재 + 재판정 → spike
                                       ↓
                    live-cluster → issue_cluster / cluster_member
```

## 🔴 이 파일은 실물을 옮겨 적은 것이다

세 컨테이너는 **수동 `docker run`** 으로 떠 있었고 명령이 어디에도 없었다.
`docker inspect` 로 복원해 compose 로 옮겼다. **값을 고치지 않았다** — 2026-09-22
기준 돌고 있는 그대로다. 커맨드는 세 개 모두 실물과 바이트 단위로 대조했다.

고칠 것이 있으면 별건으로 한다. 먼저 현실을 적는 것이 순서다.

## 왜 필요했나

2026-09-22 에 WP-127(조회수 한 시간 밀림) 수정이 develop 에 머지됐는데
**LIVE 는 24시간 동안 옛 코드로 돌았다.** 배포 경로가 없어 아무도 몰랐고, 그 사이
`spike_candidate` 가 56,940건까지 쌓였다. 사람이 손으로 파일을 복사하고 컨테이너를
재시작해서야 풀렸다 — WP-194.

컨테이너는 `Up 24 hours` 로 **정상**이었고 로그에도 에러가 없었다. 파이프라인도
초록이었다. **"서버 코드가 develop 보다 낡았다"를 알 방법이 없었다.**

## 실행

```bash
cd /home/deploy/infra/live
docker compose up -d                 # 셋 다
docker compose up -d live-cycle      # 하나만
docker compose logs -f live-cycle
```

⚠️ `.env` 는 서버에만 둔다. 고칠 때는 **`infra/edit-env.sh`** 를 쓴다 —
`sed -i` 는 그룹 소유권을 날려 다음 배포를 죽인다(WP-178, 네 번 터졌다).

## 🔴 코드는 이미지가 아니라 bind mount 에서 온다

```
${LIVE_APP_DIR}  ->  /opt/app
기본값: /home/deploy/wikipulse-local-test/data-pipeline
```

이미지(`wikipulse-spark-standalone:local`)는 파이썬 3.11 런타임일 뿐이다
(`docker/spark/Dockerfile`, WP-136). 그래서:

- 코드를 바꾸면 **이미지 재빌드 없이** 재시작만으로 반영된다
- ⚠️ 반대로 **그 디렉터리가 저장소보다 낡아도 아무 신호가 없다**
- ⚠️ 그 디렉터리는 git 체크아웃이 아니다(tarball 복사본). `git pull` 이 안 된다

⚠️ **세 서비스가 같은 디렉터리를 공유한다.** 하나 때문에 파일을 바꾸면 나머지 둘도
다음 재시작에서 그 코드를 쓴다. 의도한 시점이 아닐 수 있다.

## ⚠️ `edit-stream` 이 두 개 있다

같은 토픽 `wiki.edits` 를 읽지만 역할이 다르다.

| | 데이터 EC2 `wikipulse-edit-stream` | 여기 `wikipulse-live-edit-stream` |
| --- | --- | --- |
| 정의 | `infra/pipeline/compose.yaml` | 이 파일 |
| `SINK` | `console` — 출력만 | **`spike` — DB 에 쓴다** |
| `SLIDE_SIZE` | 5 minutes | **1 hour** |
| `CHECKPOINT_DIR` | `hdfs://.../edit-windows-v1` | 없음 |

✅ 체크포인트가 겹치지 않아 오프셋을 서로 밟지 않는다 (2026-09-22 확인).

🔴 **`SINK` 과 `SLIDE_SIZE` 는 짝이다.** `SINK=spike` 는 정각 tumbling 이어야 한다
(`SLIDE_SIZE = WINDOW_SIZE`). 조회수가 시간 버킷이라 윈도우 시작이 정각이어야 1:1 로
붙는다. 5분 슬라이드면 문서 하나가 시간당 대기 12건을 만들고 그중 정각 하나만
확정된다 — 2026-09-18 실측에서 문서 2개가 24건을 만들었고 tumbling 으로 바꾸니
2건이 됐다.

⚠️ 데이터 EC2 쪽 `SLIDE_SIZE=5 minutes` 는 지금은 `SINK=console` 이라 무해하다.
**`SINK` 만 `spike` 로 바꾸면 그 12배가 터진다.**

## ⚠️ `infra/live-cycle/` 과의 관계

WP-135 가 만든 **다른 정의**다. 빌드 이미지·`wikipulse-net`·named volume 을
쓰는데 실물은 그걸 안 쓴다.

지우지 않고 남겨 뒀다. 어느 쪽으로 갈지는 WP-196 에서 정하고, 그 전에
**실물을 잃지 않는 것이 먼저**다.

🔴 두 네트워크(`wikipulse-net`·`postgres_default`)가 서버에 **다 존재한다.** 이름을
잘못 쓰면 에러 없이 DNS 만 실패한다.

## 아직 안 한 것

- [ ] 서버의 컨테이너를 이 compose 로 인수인계 (지금은 수동 `docker run` 이 계속 돈다)
- [ ] `data-pipeline/` 변경을 서버로 옮기는 배포 경로
- [ ] 서버 코드가 develop 보다 낡았는지 드러내는 검사 — WP-193 의
      `check:migrations` 와 같은 발상

⚠️ **이 파일이 있다고 배포되는 것은 아니다.** compose 로 기술했을 뿐이고, 실제
컨테이너는 여전히 수동으로 뜬 것들이다. `docker compose up -d` 로 인수인계하려면
기존 컨테이너를 먼저 내려야 하는데, 그건 LIVE 를 잠깐 끊는 일이라 별도로 잡는다.
