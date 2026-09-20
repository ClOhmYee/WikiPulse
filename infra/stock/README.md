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

~~과거 실측은 임베딩 502건에 100 남짓이었다(2026-09-07). 5,400종목이면 그 10배 규모다~~
→ **실측했다 (2026-09-20): 5,311건에 215 크레딧.** 건당 약 0.04 다.

⚠️ **옛 환산은 5배 과대였다.** 근거였던 "502건 + LLM 3건 = 143 크레딧"에서 비용의
대부분은 **LLM 호출 3건**이었고 임베딩은 얼마 안 됐다. 둘을 합친 값을 임베딩 단가로
나눠 쓴 것이 과대추정의 원인이다. **임베딩은 싸고 LLM 이 비싸다** — 크레딧 계획은 LLM
호출 수로 잡는다.

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

| 단계 | 결과 | 소요 |
| --- | --- | --- |
| universe | **5,396종목** 적재 · CIK 매칭 5,347 (99%) | 수 분 |
| | 거래소: NASDAQ 3,145 · NYSE 1,991 · NYSE American 260 | |
| summaries | **확보 5,311 · 없음 85** (1.6%) | 약 1시간 |
| embed | **5,311종목** · 1536차원 | 수 분 · **215 크레딧** |

2026-09-08 실측(5,389)보다 7종목 많다 — 상장·폐지에 따른 정상 변동이다.

⚠️ **`summaries` 는 한 시간쯤 걸린다.** 종목마다 yfinance 왕복이라 그렇다. SSH 가 끊겨도
살아남게 `nohup` 으로 분리 실행하는 편이 낫다.

없음 85건은 전부 워런트(`.W`)·유닛(`.U`)·클래스주(`MOG.B`·`AKO.B`) 로, Yahoo 에 데이터가
없는 것들이다 — 실패가 아니라 정상 결측이다(`data-pipeline/stock/README.md` 함정 절).

⚠️ `XOM` 의 이름이 `ExxonMobil Holdings Corp` 로 들어간다. SEC 원본 그대로이고 오류가
아니다(`data-pipeline/stock/README.md` 함정 절).

## EC2 실측 (2026-09-20)

**세 단계 모두 운영 EC2 에서 끝까지 돌렸다.** 그 전까지 운영 DB 는 전 테이블 0행이었다.

```
종목 5,396 | cik 5,347 | 설명 5,311 | 임베딩 5,311 (1536차원)
```

pgvector 온전성 확인 — `XOM`(엑손모빌) 코사인 Top-5 가 전부 에너지다:
`IMO` 0.731 · `CVX` 0.623 · `SHEL` 0.618 · `PSX` 0.618 · `OXY` 0.613.
2026-09-08 로컬 실측(CVX 0.62)과 일치한다.

### EC2 에서 실제로 걸린 것

- 🔴 **이미지에 `stock/` 이 없었다.** `data-pipeline/Dockerfile` 이 producer·spike·batch
  만 복사해서 `ModuleNotFoundError: No module named 'stock'` 로 죽었다. `stock` 타깃을
  추가하고 compose 가 `target: stock` 을 지정하게 고쳤다.
- 🔴 **`LLM_GATEWAY_KEY` 가 값 없이 이름만 있었다** (`infra/service/.env`). 매칭 워커가 여태 못
  돈 이유이기도 하다.
- ⚠️ **저장소 체크아웃이 서버에 없다.** `~/infra` 만 있다. `data-pipeline/` 을
  `infra/stock/app` 으로 복사해 빌드 컨텍스트로 쓴다 — 데이터 EC2 의
  `infra/pipeline/app` 과 같은 방식이다.

### 그래도 아직 안 해 본 것

- `wikipulse-net` 네트워크가 external 이라 먼저 떠 있어야 한다(`infra/service` 가 만든다).
  이번에는 이미 떠 있어서 확인만 됐다.
- 주가(`stock.prices`)는 안 돌렸다 — 범위 밖(WP-64).
- `app/` 복사는 손으로 했다. CI 에 붙이는 것은 후속이다.

## 함정

- 🔴 **`embed` 에 `${LLM_GATEWAY_KEY:?}` 같은 가드를 걸지 말 것.** compose 는 어느 서비스를
  돌리든 **파일 전체를 보간**해서, `embed` 에 `:?` 를 걸면 키가 필요 없는
  `universe`·`summaries` 까지 같이 막힌다 — 2026-09-20 EC2 에서 실제로 막혔다.
  빈 키 검사는 `stock/embed.py` 가 한다.
- ⚠️ **`LLM_GATEWAY_KEY` 는 `infra/service/.env` 와 같은 값을 쓴다.** 두 군데 적게 하면 한쪽이
  반드시 빈다. 서버에서는 이렇게 가져온다:
  `grep '^LLM_GATEWAY_KEY=' ~/infra/service/.env >> ~/infra/stock/.env`
- ⚠️ `stock/embed.py` 만 `LLM_GATEWAY_API_KEY` 라는 이름을 읽는다. compose 가 `LLM_GATEWAY_KEY` 를
  받아 그 이름으로 넘겨 주므로 `.env` 에는 `LLM_GATEWAY_KEY` 하나만 적는다.
