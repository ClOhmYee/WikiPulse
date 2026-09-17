# gdelt — GDELT GKG 15분 폴링 → HDFS 적재

`WP-32`. GDELT 2.0 GKG(15분마다 나오는 전 세계 뉴스 메타데이터)를 받아
HDFS 에 적재한다. 이 원본을 Spark 배치가 테마·지역 술어로 필터링해 이슈별 기관명
lift 를 뽑고, 기관명 상위가 LLM 종목 검증의 RAG 컨텍스트가 된다. 테마·지역 자체는
현재 저장하거나 LLM에 전달하지 않는다.

명세: [docs/requirements-v0.2.md](../../docs/requirements-v0.2.md) §3·§4·§5·§11

```
GDELT GKG (15분 파일)  ──[이 모듈]──▶  HDFS  ──▶  Spark 배치  ──▶  이슈↔종목 근거
  lastupdate.txt / masterfilelist.txt      (2노드·복제2)
```

## 하는 일

1. **15분 폴링** — `lastupdate.txt` 를 읽어 최신 `*.gkg.csv.zip` 을 받아 싱크에 저장.
2. **자가치유** — 매 폴링마다 최근 `selfheal_hours` 구간에서 빠진 슬롯을 채운다.
3. **백필** — `masterfilelist.txt` 로 과거 구간을 일괄 적재.
4. **결손 기록** — GDELT 에 없는 시간대(404·미등록)를 `gaps.json` 에 남긴다.
   확인된 예: 2025-06-14 18:00\~07-02 02:00 UTC 전 구간 404 (2026-09-16 경계
   재확인, 명세 §11 — 처음 기록은 06-13\~07-04로 더 넓었다).

싱크가 "이미 받은 파일"의 정본이다 — 별도 매니페스트 없이 `exists()` 로 판단해
재시작·장애 후에도 빠진 것만 다시 채운다.

## 실행

```bash
cd data-pipeline
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r gdelt/requirements.txt

# 15분 폴링 (기본). 로컬 개발은 파일 싱크로.
GDELT_SINK=local GDELT_LOCAL_DIR=gdelt-data .venv/Scripts/python.exe -m gdelt.producer

# 과거 구간 백필
.venv/Scripts/python.exe -m gdelt.producer backfill --from 20241010000000 --to 20241010234500
```

HDFS 로 쓰려면 `GDELT_SINK=webhdfs`. 단 **WebHDFS 는 datanode 로 리다이렉트**하므로
compose 네트워크 안(gdelt-producer 서비스)에서 돌려야 `hdfs-datanode` 가 해석된다.
호스트에서 직접 돌릴 땐 `local` 을 쓴다. 상세는 [docker/README.md](../../docker/README.md).

## 설정 (환경 변수)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `GDELT_SINK` | `local` | `local` \| `webhdfs` |
| `GDELT_LOCAL_DIR` | `gdelt-data` | local 싱크 루트 |
| `WEBHDFS_URL` | `http://hdfs-namenode:9870` | NameNode WebHDFS |
| `HDFS_BASE_PATH` | `/gdelt/gkg` | HDFS 적재 루트 |
| `WEBHDFS_USER` | `hadoop` | WebHDFS user.name |
| `GDELT_GAPS_PATH` | `gdelt-data/gaps.json` | 결손 로그 |
| `GDELT_POLL_SECONDS` | `900` | 폴링 주기(15분) |
| `GDELT_SELFHEAL_HOURS` | `6` | 매 폴링 시 되돌아보는 자가치유 창 |
| `GDELT_LASTUPDATE_URL` / `GDELT_MASTERLIST_URL` / `GDELT_FILE_BASE_URL` | GDELT 2.0 기본 | 소스 URL |
| `CONTACT_EMAIL` | (없음) | User-Agent 에 붙일 연락처(선택) |

## 저장 레이아웃

```
{HDFS_BASE_PATH 또는 LOCAL_DIR}/YYYY/MM/DD/YYYYMMDDHHMMSS.gkg.csv.zip
```

날짜로 파티션을 나눠 Spark 배치가 하루치를 통째로 읽기 좋게 한다. 파일명은
타임스탬프 그대로(이슈 요구사항).

## 무결성

- `lastupdate`/`masterlist` 가 주는 **size·md5** 로 대조한다.
- md5 를 모르는 자가치유 경로에서도 **zip 매직 바이트**로 최소 검증(HTML 오류
  페이지·잘린 다운로드를 잡는다).
- 임시 파일에 다 쓴 뒤 원자적 rename — 반쪽 파일이 완성본처럼 남지 않는다.

## 실측으로 확인한 것 (2026-09-09)

- GDELT URL 은 `http://` 지만 **https 로 301 리다이렉트**된다. 다운로드는
  리다이렉트를 따라간다. 기본 URL 은 https 로 둬 왕복을 아낀다.
- 파일 형식: `<size> <md5> <url>` 공백 3필드. `.gkg.csv.zip` 줄만 쓴다.
- 실 폴링으로 최신 파일(2.9\~3.3 MB) 저장·size/md5 검증 통과 확인.

## 테스트

```bash
cd data-pipeline/gdelt
../.venv/Scripts/python.exe -m pytest
```

네트워크·HDFS·실시간 없이 돈다(가짜 세션·싱크·다운로더 주입). WebHDFS 실 왕복은
compose 단일노드 HDFS 로 따로 검증했다(`docker compose --profile gdelt`).

## 결손 기록 영속

`gaps.json` 은 compose 에서 named 볼륨(`gdelt-gaps`)에 둔다. `docker compose down`
후 재생성해도 유지된다. 필요하면 Spark 컨테이너가 같은 볼륨을 마운트해 읽을 수
있다. 더 강한 영속·공유가 필요하면 결손 기록을 HDFS 로 옮기는 것이 다음 후보다.

## 아직 안 한 것

- **EC2 배포** — 실 HDFS 2노드(`WP-28`) 준비 후. producer 는
  `GDELT_SINK=webhdfs` + 주소만 바꾸면 붙는다.
- **결손 기록의 HDFS 이전(선택)** — 지금은 named 볼륨. Spark 접근·영속을 더 강하게
  가져가려면 HDFS 로 옮긴다.
