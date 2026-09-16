"""§11 "Wikidata 티커" 행 재현. CLAUDE.md 폐기 절의 함정 그대로 —
`wdt:P249`(순진한 접근, 40건) vs `p:P414 → pq:P249`(P414 문의 한정어로 접근, 15,875건).

실행: 네트워크만 필요(Wikidata Query Service, 인증 불필요). 쿼리가 무거워
수십 초 걸릴 수 있다.
    py -3 wikidata_ticker_trap.py
"""

import sys

import requests

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"
ENDPOINT = "https://query.wikidata.org/sparql"

NAIVE_QUERY = """
SELECT (COUNT(DISTINCT ?company) AS ?n) WHERE {
  ?company wdt:P249 ?ticker .
}
"""

CORRECT_QUERY = """
SELECT (COUNT(DISTINCT ?company) AS ?n) WHERE {
  ?company p:P414 ?stmt .
  ?stmt pq:P249 ?ticker .
}
"""

NYSE_NASDAQ_QUERY = """
SELECT (COUNT(DISTINCT ?company) AS ?n) WHERE {
  ?company p:P414 ?stmt .
  ?stmt ps:P414 ?exchange ;
        pq:P249 ?ticker .
  VALUES ?exchange { wd:Q13677 wd:Q82059 }  # NYSE, NASDAQ
}
"""


def run(query: str) -> int:
    r = requests.get(
        ENDPOINT, params={"query": query, "format": "json"},
        headers={"User-Agent": UA}, timeout=120,
    )
    r.raise_for_status()
    return int(r.json()["results"]["bindings"][0]["n"]["value"])


def main():
    print("naive  wdt:P249 (회사 속성으로 직접 조회)              ...", file=sys.stderr)
    naive = run(NAIVE_QUERY)
    print("correct p:P414 -> pq:P249 (거래소 진술의 한정어로 조회) ...", file=sys.stderr)
    correct = run(CORRECT_QUERY)
    print("nyse_nasdaq 위 조회를 NYSE·NASDAQ 로 좁힘               ...", file=sys.stderr)
    nyse_nasdaq = run(NYSE_NASDAQ_QUERY)

    print(f"\nwdt:P249 (naive)         : {naive:,}건")
    print(f"p:P414 -> pq:P249 (correct): {correct:,}건")
    print(f"  중 NYSE+NASDAQ만          : {nyse_nasdaq:,}건")
    print(f"\n비율: correct/naive = {correct / naive:.0f}배" if naive else "")


if __name__ == "__main__":
    main()
