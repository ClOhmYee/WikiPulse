# 종목 적재 (WP-147)

`stock` 테이블을 채운다. **일회성**이고 **서비스(기본) EC2** 에서 돈다.

코드와 동작 근거는 [data-pipeline/stock/README.md](../../data-pipeline/stock/README.md) 가
정본이다. 이 문서는 **EC2 에서 어떤 순서로 무엇을 조심하며 돌리는가**만 적는다.

## 왜 이 폴더가 생겼나

2026-09-20 에 EC2 운영 DB 를 조회했더니 `stock` 이 **0행**이었다. 올리는 걸 깜빡한 게
아니라 **올릴 경로가 없었다** — `~/infra/` 에 stock 항목이 없고 CI 에도 테스트뿐이었다.

⚠️ WP-33·34 는 "코드 작성 + 로컬 적재 확인"으로 완료 처리됐고 운영 적재는 어느
완료 조건에도 없었다. **코드와 Jira 만 보면 끝난 것으로 보이는데 운영에는 없는** 유형이다.

## 순서 의존 — 이게 늦으면 매칭이 통째로 0건이다

WP-143 이 풀려 `spike` 가 쌓이기 시작해도, `stock` 이 0 이면 종목 매칭은 계속
0건이다. 후보 생성 워커(WP-67)가 임베딩 Top-K 를 뽑을 대상이 없기 때문이다.
`application.yml` 의 🔴 "폴러는 종목 임베딩 전량 적재 후에 켠다" 도 같은 이야기다.

**즉 이 적재는 -143 보다 먼저이거나 최소한 병행이어야 한다.**

## 실행

```bash
cd ~/infra/stock
cp .env.example .env && chmod 0600 .env   # 값 채우기 (DB 는 infra/db/.env 와 같게)

docker compose --profile stock run --rm universe     # 1. 마스터 (~5,400종목, 수 분)
docker compose --profile stock run --rm summaries    # 2. 사업 설명 (수십 분)
docker compose --profile stock run --rm embed        # 3. 임베딩 (크레딧 소비)
```

🔴 **`up` 이 아니라 `run --rm` 이다.** 세 서비스는 `profiles: [stock]` 뒤에 숨겨 뒀다 —
일회성이라 `docker compose up` 에 딸려 올라가면 안 된다.

⚠️ **중간에 죽어도 그냥 다시 돌린다.** 각 단계는 "앞 단계가 채운 것 중 아직 안 한 것"만
집는다. 이미 끝난 종목을 다시 호출하지 않는다 — 특히 embed 는 크레딧을 쓴다.

## 🔴 3단계 전에 크레딧 잔액을 본다

대량 임베딩 호출 전에 사용하는 서비스의 잔액과 예산 상한을 확인한다.

```bash
curl -s -H "Authorization: Bearer $LLM_GATEWAY_KEY" https://llm-gateway.example.com/key-info
```

과거 실측은 **임베딩 502건에 100 남짓**이었다(2026-09-07). 5,400종목이면 그 10배 규모다.
⚠️ 이 환산은 선형 가정이고 실측한 적이 없다 — 잔액을 보고 들어간다.

## 확인

```bash
docker exec -i postgres-postgres-1 psql -U wikipulse -d wikipulse -c \
  "SELECT count(*) total, count(cik) cik, count(business_summary) summary, count(embedding) embedding FROM stock;"
```

`total` 과 `embedding` 이 0 이 아니어야 끝난 것이다. `summary` 없이 `embedding` 은 안 생긴다.

로컬 검증값(2026-09-20, 아래 §실측)과 자릿수가 맞는지 본다. 크게 적으면 소스 쪽이
바뀐 것이므로 `data-pipeline/stock/README.md` 의 "함정"을 먼저 읽는다.

## 실측 (2026-09-20, 로컬 Docker PostgreSQL)

EC2 가 아니라 **로컬**에서 같은 이미지·같은 명령으로 돌린 값이다.

| 단계 | 결과 |
| --- | --- |
| universe | **5,396종목** 적재 · CIK 매칭 5,347 (99%) |
| | 거래소: NASDAQ 3,145 · NYSE 1,991 · NYSE American 260 |

2026-09-08 실측(5,389)보다 7종목 많다 — 상장·폐지에 따른 정상 변동이다.

⚠️ `XOM` 의 이름이 `ExxonMobil Holdings Corp` 로 들어간다. SEC 원본 그대로이고 오류가
아니다(`data-pipeline/stock/README.md` 함정 절).

## ⚠️ 아직 EC2 에서 돌린 적이 없다

이 폴더는 2026-09-20 에 **로컬 검증만 거쳤다.** EC2 실행 시 처음 만날 수 있는 것:

- `wikipulse-net` 네트워크가 external 이라 **먼저 떠 있어야 한다**(`infra/service` 가 만든다).
- 빌드 컨텍스트가 `../../data-pipeline` 이라 **저장소 체크아웃이 서버에 있어야 한다.**
  `~/infra` 만 복사돼 있으면 빌드가 실패한다.
- `embed` 는 `LLM_GATEWAY_KEY` 가 없으면 compose 가 기동 전에 막는다(`:?` 치환).
- ⚠️ **2026-09-20 실측: 서버 `infra/service/.env` 의 `LLM_GATEWAY_KEY` 는 이름만 있고 값이 비어 있다.**
  (`.env` 15번 줄이 `LLM_GATEWAY_KEY=` 9바이트, 백엔드 컨테이너에서도 길이 0). 매칭 워커가
  여태 못 돈 이유이기도 하다. 적재 전에 값을 채워야 한다.
