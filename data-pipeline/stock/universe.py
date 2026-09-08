"""미국 3대 거래소 보통주 마스터를 만든다.

    python -m stock.universe            # PostgreSQL 에 적재
    python -m stock.universe --dry-run  # 개수만 세고 끝

소스 (2026-09-08 실측)
    NASDAQ Trader nasdaqlisted.txt  — 나스닥 상장. 파이프 구분.
    NASDAQ Trader otherlisted.txt   — NYSE(N)·NYSE American(A) 등. Exchange 컬럼.
    SEC company_tickers.json        — CIK 와 정식 회사명 보강.

왜 Wikidata 를 안 쓰나
    wdt:P249 로 티커를 조회하면 40건만 나온다. 티커는 P414 문의 한정어라
    조용히 0에 수렴한다 (CLAUDE.md 폐기 절). NASDAQ Trader 가 정답 소스다.

보통주만 남긴다
    두 파일에는 ETF·우선주·워런트·유닛이 섞여 있다. Test Issue·ETF 플래그로
    거르고, Security Name 이 "Common Stock" / "Ordinary Shares" 인 것만 남긴다.
    이렇게 해야 명세의 "약 5,100종목" 규모가 나온다. 우선주·ADR 은 사업 설명
    임베딩이 보통주와 겹쳐 매칭 노이즈만 늘린다.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
from dataclasses import dataclass

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"

USER_AGENT = "WikiPulse/0.1 (WikiPulse; https://github.com/ClOhmYee/WikiPulse)"

# otherlisted 의 Exchange 코드. NYSE(N)·NYSE American(A) 만 받는다.
# P(NYSE Arca)·Z(Cboe BZX) 는 대부분 ETF 라 제외한다.
NYSE_EXCHANGES = {"N": "NYSE", "A": "NYSE American"}

# 보통주로 볼 Security Name 접미. 우선주(Preferred)·워런트(Warrant)·
# 유닛(Unit)·노트(Note)·라이트(Right) 는 여기 없어서 자동으로 빠진다.
COMMON_STOCK_PATTERNS = (
    "common stock",
    "common shares",
    "ordinary shares",
    "class a common",
    "class b common",
    "class c common",
)


@dataclass(frozen=True)
class Stock:
    ticker: str
    name: str
    exchange: str
    cik: str | None = None


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        # NASDAQ Trader 파일에 latin-1 문자가 섞여 있다.
        return resp.read().decode("latin-1")


def _is_common(security_name: str) -> bool:
    lowered = security_name.lower()
    return any(p in lowered for p in COMMON_STOCK_PATTERNS)


def _parse_pipe(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()
    header = lines[0].split("|")
    rows = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        fields = line.split("|")
        if len(fields) == len(header):
            rows.append(fields)
    return header, rows


def parse_nasdaq(text: str) -> list[Stock]:
    header, rows = _parse_pipe(text)
    col = {name: header.index(name) for name in header}
    out = []
    for f in rows:
        if f[col["Test Issue"]] != "N" or f[col["ETF"]] != "N":
            continue
        name = f[col["Security Name"]].strip()
        if not _is_common(name):
            continue
        out.append(Stock(ticker=f[col["Symbol"]].strip(), name=name, exchange="NASDAQ"))
    return out


def parse_other(text: str) -> list[Stock]:
    header, rows = _parse_pipe(text)
    col = {name: header.index(name) for name in header}
    out = []
    for f in rows:
        if f[col["Test Issue"]] != "N" or f[col["ETF"]] != "N":
            continue
        exchange = NYSE_EXCHANGES.get(f[col["Exchange"]])
        if exchange is None:
            continue
        name = f[col["Security Name"]].strip()
        if not _is_common(name):
            continue
        out.append(Stock(ticker=f[col["ACT Symbol"]].strip(), name=name, exchange=exchange))
    return out


def load_sec_index(text: str) -> dict[str, tuple[str, str]]:
    """ticker -> (cik10, 정식 회사명). SEC 는 전 거래소를 다 담고 있다."""
    data = json.loads(text)
    index: dict[str, tuple[str, str]] = {}
    for entry in data.values():
        ticker = entry["ticker"].strip().upper()
        cik = str(entry["cik_str"]).zfill(10)
        index[ticker] = (cik, entry["title"])
    return index


def build_universe() -> list[Stock]:
    nasdaq = parse_nasdaq(_fetch(NASDAQ_LISTED))
    other = parse_other(_fetch(OTHER_LISTED))
    sec = load_sec_index(_fetch(SEC_TICKERS))

    # 같은 티커가 두 파일에 나오면 (드물지만) 먼저 온 것을 쓴다.
    by_ticker: dict[str, Stock] = {}
    for stock in [*nasdaq, *other]:
        # NASDAQ Trader 티커에 붙는 접미 기호($ 등)가 섞인 행은 버린다.
        if not re.fullmatch(r"[A-Z][A-Z.]{0,6}", stock.ticker):
            continue
        if stock.ticker in by_ticker:
            continue
        cik, sec_name = sec.get(stock.ticker, (None, None))
        by_ticker[stock.ticker] = Stock(
            ticker=stock.ticker,
            # SEC 정식 회사명이 있으면 그걸 쓴다. 거래소 파일 이름은 "- Common Stock"
            # 같은 접미가 붙어 지저분하다.
            name=sec_name or stock.name,
            exchange=stock.exchange,
            cik=cik,
        )
    return sorted(by_ticker.values(), key=lambda s: s.ticker)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="적재 없이 개수만")
    args = parser.parse_args()

    universe = build_universe()

    from collections import Counter

    by_exchange = Counter(s.exchange for s in universe)
    with_cik = sum(1 for s in universe if s.cik)
    print(f"보통주 {len(universe)}종목", file=sys.stderr)
    print(f"  거래소: {dict(by_exchange)}", file=sys.stderr)
    print(f"  SEC CIK 매칭: {with_cik} ({with_cik / len(universe) * 100:.0f}%)", file=sys.stderr)

    if args.dry_run:
        return 0

    from .db import upsert_stocks

    inserted = upsert_stocks(universe)
    print(f"적재 완료: {inserted}종목", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
