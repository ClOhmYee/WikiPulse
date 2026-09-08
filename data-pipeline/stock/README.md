# stock — 종목 마스터·설명·임베딩 적재

- `WP-33` 종목 마스터 (SEC + NASDAQ Trader → PostgreSQL)
- `WP-34` 사업 설명 수집 + 임베딩 (yfinance → text-embedding-3-small → pgvector)

명세: [docs/requirements-v0.1.md](../../docs/requirements-v0.1.md) §4, §5, §6

```
종목 마스터 ──▶ 사업 설명 ──▶ 임베딩
 universe      summaries       embed
 (SEC+NASDAQ)  (yfinance)      (GATEWAY)
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

python -m stock.universe --dry-run   # 적재 없이 개수만
```

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
python -m pytest tests/test_universe.py    # 파싱·필터, 네트워크 없이 8개
```

end-to-end 는 진짜 PostgreSQL 로 확인했다 (2026-09-08). 마스터 5,389종목 적재 →
표본 12종목 설명 수집 → GATEWAY 임베딩(1536차원) → pgvector Top-K. XOM(엑손모빌)
코사인 Top-5 에 CVX(셰브론) 0.62, FRO(유조선) 등 에너지가 뭉쳤다.

## 함정

- **GATEWAY 크레딧.** 502건 임베딩에 100 남짓 썼다 (2026-09-07).
- **임베딩 차원.** `text-embedding-3-small` 은 1536. `db` 스키마의 `vector(1536)`
  과 맞아야 한다. `embed.py` 가 응답 차원을 검사해서 다르면 멈춘다.
- **yfinance 결측.** 표본 200종목 보유율 100% 였지만 전체에서 일부는 설명이
  없을 수 있다. `summaries.py` 가 없는 것을 세어 보고한다.
- **SEC 이름이 최신이다.** XOM 이 `ExxonMobil Holdings Corp` 로 나오는데
  (CIK 2115436) 이건 SEC 원본 그대로다 — 오류가 아니다.

## 미확정

- **적재 스케줄.** 지금은 수동이다. 마스터는 자주 안 바뀌니 주 1회 cron 이면
  되지만, 상장·폐지 반영 주기는 팀 결정 사항이다.
- **주가 적재는 별도** (`WP-10` 에픽). 여기는 마스터·설명·임베딩까지다.
