# stock — 종목 마스터·설명·임베딩·주가 적재

- `WP-33` 종목 마스터 (SEC + NASDAQ Trader → PostgreSQL)
- `WP-34` 사업 설명 수집 + 임베딩 (yfinance → text-embedding-3-small → pgvector)
- `WP-64` 주가 일봉 적재 + 일별 증분 갱신 (yfinance → stock_price)

명세: [docs/requirements-v0.3.md](../../docs/requirements-v0.3.md) §3.2 9번, §4, §5, §6

```
종목 마스터 ──▶ 사업 설명 ──▶ 임베딩
 universe      summaries       embed
 (SEC+NASDAQ)  (yfinance)      (GATEWAY)
      └──────▶ 주가 일봉
               prices
               (yfinance)
```

세 단계를 나눴다. 뒤 단계는 "앞 단계가 채운 것 중 아직 안 한 것"부터
이어서 한다 — 수집이 잘 끊기고, 임베딩은 크레딧을 써서, 중간에 죽어도
다시 호출하지 않게 DB 에 단계별로 저장한다.

## 실행

```bash
export DATABASE_URL=postgresql://wikipulse:pw@localhost:5432/wikipulse
export LLM_GATEWAY_API_KEY=...            # .env 참고. 저장소에 넣지 않는다.

python -m stock.universe          # 1. 마스터 (약 5,400종목)
python -m stock.summaries         # 2. 사업 설명
python -m stock.embed             # 3. 임베딩
python -m stock.prices            # 4. 주가 일봉 (첫 실행 5년, 이후 증분)

python -m stock.universe --dry-run   # 적재 없이 개수만
```

## 주가 (prices)

한 코드 경로가 초기 적재와 일별 갱신을 둘 다 한다. 종목마다 `stock_price` 에
마지막 `trade_date` 가 있으면 **그 날부터**(포함, upsert 로 정정도 반영), 없으면
**5년 전체**를 받는다.

```bash
python -m stock.prices                       # 전 종목. 없으면 5년, 있으면 마지막 날부터
python -m stock.prices --period 2y           # 기존 행 없는 종목의 초기 기간
python -m stock.prices --tickers AAPL,MSFT   # 특정 종목만
python -m stock.prices --throttle 0.5        # 야후에 차단당하면 간격을 올린다
python -m stock.prices --limit 20 --dry-run  # DB 안 건드리고 20종목만 시험
```

- **첫 실행** = 전 종목 5년 초기 적재. **매일 cron** = 인자 없이 돌리면 마지막 날
  이후만 받는 증분 갱신이다. **중간에 죽고 재실행** = 받은 종목은 마지막 날만,
  못 받은 종목은 5년 — `summaries`·`embed` 와 같은 "이어서" 원리.
- **재실행 안전**: `ON CONFLICT (ticker, trade_date) DO UPDATE` 라 중복 행이 안 생긴다.
- **실패 격리**: 종목별 지수 백오프(2·4·8초, 최대 4시도) 후에도 실패하면 그 종목만
  건너뛰고 나머지를 계속 적재한다. 끝에 `적재·데이터없음·실패` 개수를 보고한다.
- **조용한 대량 실패 감지**: 하드 실패뿐인데 하나도 못 받았거나, 초기 적재 대상이
  전부 0행이면 **종료코드 1** 로 끝나 cron 이 성공으로 오인하지 않는다. 초기 적재
  (마지막 `trade_date` 없음)인데 0행이면 정상 "신규 없음"이 아니라 차단 의심이라
  따로 세어(`초기적재 빈결과 N`) 경고한다.
  - ⚠️ **주말·휴장일 증분 실행은 정상적으로 `ok==0`**(신규 거래일 없음)이라 종료코드
    0 이다 — 이걸 실패로 보지 않는다. 증분(start 있음) 빈결과는 실패 판정·서킷
    브레이커 어디에도 카운트하지 않는다.
- **서킷 브레이커 (P2-F)**: 연속 25종목을 못 받으면(실패 또는 초기적재 0행) 야후
  전면 차단으로 보고 조기 중단한다. 차단 상태에서 5,100종목을 각 ~14초씩 헛도는
  것을 막는다. 하나라도 받으면 카운터가 리셋된다. `--throttle` 로 간격을 올려
  재실행한다.
- **`--tickers` 가드**: 마스터(`stock`)에 없는 심볼은 자동 제외한다. `stock_price`
  가 `stock` 을 FK 참조해, 없는 심볼을 넣으면 저장이 통째로 막히기 때문이다.
- 🔴 **raw(조정 안 함) OHLC 를 저장한다.** 조정가는 배당·분할마다 과거 전 구간이
  다시 계산돼, 5년 초기분과 매일 증분분의 기준이 어긋난다. raw 는 날짜별 값이
  안 변해 증분 append 와 정합하다. 분할일 차트 튐은 "참고 컨텍스트"라 허용한다.

## 규모 (2026-09-08 실측)

```
보통주 5389종목
  거래소: NASDAQ 3141 · NYSE 1989 · NYSE American 259
  SEC CIK 매칭: 5339 (99%)
```

명세의 "약 5,100"과 맞는다. ETF·우선주·워런트·유닛을 빼고 보통주만 남긴 값이다.

## 왜 이렇게 소스를 골랐나

**티커는 NASDAQ Trader 가 정답이다.** Wikidata `wdt:P249` 로 조회하면 40건만
나온다 — 티커가 P414 문의 한정어라 조용히 0에 수렴한다 (CLAUDE.md 폐기 절).
NASDAQ Trader `nasdaqlisted.txt` + `otherlisted.txt` 가 거래소별 상장 목록을
그대로 준다.

**CIK·정식 회사명은 SEC 로 보강한다.** 거래소 파일의 이름은 "- Common Stock"
같은 접미가 붙어 지저분하다. SEC `company_tickers.json` 의 title 로 덮는다.
SEC 에 없으면 거래소 이름을 그대로 둔다.

**보통주만 남긴다.** 우선주·ADR·워런트는 사업 설명이 보통주와 겹쳐 매칭
노이즈만 늘린다. Test Issue·ETF 플래그로 거르고, Security Name 이
"Common Stock" / "Ordinary Shares" 인 것만 통과시킨다.

## 검증

```bash
python -m pytest                 # 파싱·필터·주가변환·대상선택, 네트워크 없이 21개
```

마스터·설명·임베딩 end-to-end 는 진짜 PostgreSQL 로 확인했다 (2026-09-08). 마스터
5,389종목 적재 → 표본 12종목 설명 수집 → GATEWAY 임베딩(1536차원) → pgvector Top-K.
XOM(엑손모빌) 코사인 Top-5 에 CVX(셰브론) 0.62, FRO(유조선) 등 에너지가 뭉쳤다.

주가 fetch 는 라이브 Yahoo 로 확인했다 (2026-09-10). AAPL 초기 period·MSFT 증분
start·없는 티커 graceful 세 경로 모두 정상, raw OHLCV·정수 volume·거래일 날짜 확인.
`run()`·upsert 는 pgserver 실 PostgreSQL e2e 로 확인했다 (2026-09-11): 마지막 종목
실패 시 잔여 버퍼 저장, 전량 빈결과 시 종료코드 1, dry-run 무저장, `--tickers`
미존재 심볼 제외 — 4경로 모두 통과.

**전수 백필 실측 (2026-09-11, 로컬 dev PostgreSQL)**: 마스터 5,391종목 →
`stock_price` **5,369종목 · 5,754,172행** (2021-09-13 ~ 2026-09-10, 5년). 미적재 22개는
전부 워런트(`.W`)·유닛(`.U`)로 Yahoo 에 데이터가 없다 — 워런트/유닛 아닌 실 종목은
100% 적재. 주요 종목 1,254행 풀 확인(AAPL·MSFT·NVDA·BRK.A 809,350 등).

## 함정

- **GATEWAY 크레딧.** 502건 임베딩에 100 남짓 썼다 (2026-09-07).
- **임베딩 차원.** `text-embedding-3-small` 은 1536. `db` 스키마의 `vector(1536)`
  과 맞아야 한다. `embed.py` 가 응답 차원을 검사해서 다르면 멈춘다.
- **yfinance 결측.** 표본 200종목 보유율 100% 였지만 전체에서 일부는 설명이
  없을 수 있다. `summaries.py` 가 없는 것을 세어 보고한다.
- **⚠️ yfinance 버전.** `0.2.51` 은 `.history()` 가 현재 Yahoo 에서 깨져 전 종목
  0행이 **조용히** 나온다 (크럼 단계 "Expecting value"). `1.7.0` 으로 올렸다
  (2026-09-10). 다시 내리면 주가가 안 쌓이는데 에러가 안 나 늦게 발견된다.
- **⚠️ Yahoo 글리치 값.** 일부 종목(리버스 스플릿 이력 등)은 Yahoo 가 말도 안 되는
  가격을 뱉는다. WHLR 은 최대 ~1,475억까지 나왔다 (2026-09-11 전수 실측). `_price`
  가 NUMERIC(14,4) 범위(10^10 미만) 밖은 버려 **크래시는 막지만**, 10^10 미만의
  억대 글리치(WHLR 67.9억 등)는 통과해 그대로 저장된다. 정밀 이상치 제거(중앙값·MAD
  기준)는 별도 과제다 — 지금은 "참고 컨텍스트" 차트라 허용한다.
- **클래스주 티커.** 마스터는 `BRK.A`(NASDAQ Trader 형식)인데 Yahoo 는 `BRK-A`.
  `_yahoo_symbol` 이 `.`→`-` 변환한다. 안 하면 클래스주가 조용히 0행이 된다.
- **SEC 이름이 최신이다.** XOM 이 `ExxonMobil Holdings Corp` 로 나오는데
  (CIK 2115436) 이건 SEC 원본 그대로다 — 오류가 아니다.

## 미확정

- **적재 스케줄.** 지금은 수동이다. 마스터는 자주 안 바뀌니 주 1회 cron,
  주가(`prices`)는 장 마감 후 일 1회 cron 이면 된다 — 스크립트 자체가 증분이라
  인자 없이 반복하면 된다. 상장·폐지 반영 주기와 cron 배치 위치는 팀 결정 사항이다.
