"""S&P 500 구성 종목 목록 (티커·회사명). 위키피디아 표를 파싱한다.

DB(stock.universe)의 5,100종목 전수 대신 S&P 500만 쓰는 이유: 이전 실측(명세
§11 "임베딩 vs GDELT 후보 교집합", 2026-09-07)도 같은 규모를 썼고, 이번 재측정은
그 수치의 재현이 목적이라 규모를 맞춘다. 전수(5,100종목) 재측정은 yfinance 호출
5,100회·임베딩 크레딧이 10배 이상 들어 이 이슈의 범위를 넘는다 — 필요해지면
`data-pipeline/stock/universe.py`를 그대로 쓴다.
"""
import io
import json
import os
import re
import urllib.request

UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"}
CACHE = os.path.join(os.path.dirname(__file__), "sp500.json")


def fetch() -> list[dict]:
    if os.path.exists(CACHE):
        return json.load(io.open(CACHE, encoding="utf-8"))

    req = urllib.request.Request(
        "https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies"
        "&prop=wikitext&section=1&format=json",
        headers=UA,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        wt = json.loads(resp.read().decode("utf-8"))["parse"]["wikitext"]["*"]

    rows = wt.split("|-")[1:]
    out = []
    for row in rows:
        m_sym = re.search(r"\{\{\w*Symbol\|(\S+?)\}\}", row)
        m_name = re.search(r"\|\|\s*\[\[([^\]|]+)", row.split("\n", 2)[-1] if False else row)
        lines = [l.strip() for l in row.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        sym_m = re.search(r"\{\{\w*Symbol\|(\S+?)\}\}", lines[0])
        if not sym_m:
            continue
        ticker = sym_m.group(1).strip().rstrip("}")
        name_m = re.search(r"\[\[([^\]|]+)", lines[1])
        name = name_m.group(1).strip() if name_m else lines[1].lstrip("|").strip()
        out.append({"ticker": ticker, "name": name})

    json.dump(out, io.open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    lst = fetch()
    print(f"{len(lst)}개 종목")
    print(lst[:5])
