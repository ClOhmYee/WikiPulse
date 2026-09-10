"""WP-39 — 매칭 정답셋 채점 스크립트.

cases.py의 5개 사례(사건형 3 + 기업형 2)에 대해:
  1. 이슈 대표 텍스트(명세 §6.2 확정 규칙)를 만들어 임베딩 Top-K를 낸다.
  2. GDELT DOC 2.0 API로 사건 기간 내 "사건어 ∧ 회사명" 기사 수를 세어 Top-K를 낸다.
  3. 명세 §6.3 등급(1: 교집합, 2: GDELT 단독, 3: 임베딩 단독)으로 나눠 각 등급이
     실제 정답을 몇 개 건지는지, 노이즈가 몇 개 섞이는지 K별로 잰다.

K를 바꿔가며 다시 돌리려면 sys.argv로 K 목록을 넘긴다:
    py -3 goldset_experiment.py [출력파일] [K1,K2,...]

LLM_GATEWAY_KEY 환경변수 필요. GDELT DOC API는 초당 요청 제한이 있어(429 관측,
2026-09-10) 사례당 1회 ArtList 호출로 묶고 사례 사이 25초를 둔다 — 총
5회 호출, 전체 실행은 1~2분 안팎(+임베딩·yfinance 호출 시간).
"""

import io
import json
import os
import sys
import time

import numpy as np
import requests
import yfinance as yf

from cases import CASES

GATEWAY = "https://llm-gateway.example.com"
KEY = os.environ["LLM_GATEWAY_KEY"]
EMBED_MODEL = "text-embedding-3-small"
UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"}
MAX_CHARS = 2000
GDELT_DELAY_S = 25  # 6초 429 재현, 15초 통과(2026-09-10 1차 실측) → 20초도 연속 호출에선 429 다발(2차 실측). 티커당 쿼리를 버리고 사례당 1회 ArtList로 바꿔 호출 수 자체를 57→5로 줄였다(3차, 아래 gdelt_titles).

ALIASES = {
    "NEE": "NextEra Energy", "DUK": "Duke Energy", "GNRC": "Generac",
    "HD": "Home Depot", "LOW": "Lowe's", "LEN": "Lennar", "ETN": "Eaton",
    "UAL": "United Airlines", "DIS": "Disney",
    "MNST": "Monster Beverage", "INTC": "Intel", "NKE": "Nike", "KO": "Coca-Cola",
    "PG": "Procter & Gamble", "CRM": "Salesforce",
    "CRWD": "CrowdStrike", "DAL": "Delta Air Lines", "MSFT": "Microsoft",
    "AAL": "American Airlines", "PANW": "Palo Alto Networks", "FTNT": "Fortinet",
    "SBUX": "Starbucks", "T": "AT&T",
    "WAL": "Western Alliance", "ZION": "Zions Bancorporation", "CMA": "Comerica",
    "KEY": "KeyCorp", "SCHW": "Charles Schwab", "JPM": "JPMorgan Chase",
    "BAC": "Bank of America", "GS": "Goldman Sachs", "FITB": "Fifth Third Bancorp",
    "IBM": "IBM", "MU": "Micron Technology", "DELL": "Dell Technologies",
    "HPE": "Hewlett Packard Enterprise", "ORCL": "Oracle",
    "PYPL": "PayPal", "XYZ": "Block, Inc.", "V": "Visa", "MA": "Mastercard",
    "ADYEY": "Adyen",
}

# 기사 제목에서 찾을 키워드. 너무 일반적인 단어(delta·united·key 단독)는 오탐이라
# 구체적으로 잡는다 — 그래도 제목만 보는 근사치라 재현율은 낮게 잡힌다(아래 gdelt_titles 주석).
SEARCH_KEYWORD = {
    "NEE": "nextera", "DUK": "duke energy", "GNRC": "generac", "HD": "home depot",
    "LOW": "lowe", "LEN": "lennar", "ETN": "eaton", "UAL": "united airlines", "DIS": "disney",
    "MNST": "monster beverage", "INTC": "intel", "NKE": "nike", "KO": "coca-cola",
    "PG": "procter", "CRM": "salesforce",
    "CRWD": "crowdstrike", "DAL": "delta air lines", "MSFT": "microsoft",
    "AAL": "american airlines", "PANW": "palo alto networks", "FTNT": "fortinet",
    "SBUX": "starbucks", "T": "at&t",
    "WAL": "western alliance", "ZION": "zions", "CMA": "comerica", "KEY": "keycorp",
    "SCHW": "charles schwab", "JPM": "jpmorgan", "BAC": "bank of america", "GS": "goldman sachs",
    "FITB": "fifth third",
    "IBM": "ibm", "MU": "micron", "DELL": "dell", "HPE": "hewlett packard", "ORCL": "oracle",
    "PYPL": "paypal", "XYZ": "block", "V": "visa", "MA": "mastercard", "ADYEY": "adyen",
}


def credits():
    r = requests.get(f"{GATEWAY}/key-info", headers={"Authorization": f"Bearer {KEY}"}, timeout=30)
    return r.json()["usedCredit"]


def wiki_intro(title):
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "extracts", "exintro": True,
                "explaintext": True, "redirects": 1, "titles": title, "format": "json"},
        headers=UA, timeout=30,
    )
    r.raise_for_status()
    for page in r.json().get("query", {}).get("pages", {}).values():
        return page.get("extract", "").strip()
    return ""


def first_sentences(text, n):
    parts = text.replace("\n", " ").split(". ")
    return ". ".join(parts[:n]).strip().rstrip(".") + "." if parts else ""


def build_issue_text(seed_articles):
    """명세 §6.2 확정 규칙(D). 문서 1개면 6문장, 상한 2000자."""
    per_doc = 6 if len(seed_articles) == 1 else (4 if len(seed_articles) <= 3 else 2)
    intros = {a: wiki_intro(a) for a in seed_articles}
    return "\n".join(f"{a}: {first_sentences(intros[a], per_doc)}" for a in seed_articles)[:MAX_CHARS]


def embed(texts):
    r = requests.post(
        f"{GATEWAY}/api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": EMBED_MODEL, "input": texts}, timeout=120,
    )
    r.raise_for_status()
    return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)


def gdelt_titles(query, start, end):
    """사건 기간 내 query 매칭 기사 제목 목록 (최대 250건, GDELT ArtList 상한).

    티커마다 따로 쿼리하던 1차 방식은 사례당 10~15회 호출이 필요해 25초
    간격을 둬도 429가 계속 났다(2026-09-10 2차 실측). 사례당 1회 ArtList로
    바꿔 호출 수를 57 → 5로 줄였다. 대신 본문 전체가 아니라 제목만 보므로
    회사명이 제목에 직접 안 나온 기사는 놓친다 — 재현율은 낮지만 "제목에
    실릴 만큼 중심적인가"라는 방향성은 살아있다. 전수 카운트는 -48에서
    HDFS의 GDELT 원본으로 다시 잰다.
    """
    params = {
        "query": query, "mode": "artlist", "maxrecords": 250, "format": "json",
        "startdatetime": start.replace("-", "") + "000000",
        "enddatetime": end.replace("-", "") + "235959",
    }
    for attempt in range(5):
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(GDELT_DELAY_S * (attempt + 2))
            continue
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError:
            return []
        return [a["title"] for a in data.get("articles", [])]
    raise RuntimeError(f"GDELT 429 재시도 소진: {query}")


def grade_split(emb_ranked, gdelt_ranked, k):
    emb_top = set(emb_ranked[:k])
    gdelt_top = set(gdelt_ranked[:k])
    return {
        "grade1_교집합": emb_top & gdelt_top,
        "grade2_GDELT단독": gdelt_top - emb_top,
        "grade3_임베딩단독": emb_top - gdelt_top,
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "result.txt"
    ks = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [5, 10]
    out = io.open(out_path, "w", encoding="utf-8")

    def p(*a):
        out.write(" ".join(str(x) for x in a) + "\n")
        out.flush()

    used_before = credits()

    for ci, (name, case) in enumerate(CASES.items()):
        if ci > 0:
            time.sleep(GDELT_DELAY_S)  # 사례 간 GDELT 호출 간격
        p(f"\n{'=' * 70}\n## {name} ({case['type']}) — {case['event_date']}")
        answers = {t: (conf, why) for t, conf, why in case["answers"]}
        tickers = list(answers) + case["noise"]

        p("  종목 설명 수집 중...")
        descs, kept = [], []
        for t in tickers:
            try:
                d = yf.Ticker(t).info.get("longBusinessSummary", "") or ""
            except Exception as e:
                d = ""
                p(f"    {t} 실패: {type(e).__name__}")
            if d:
                kept.append(t)
                descs.append(d[:MAX_CHARS])
        missing = sorted(set(tickers) - set(kept))
        if missing:
            p(f"  설명 없음(제외): {missing}")
        stock_vecs = embed(descs)

        issue_text = build_issue_text(case["seed_articles"])
        issue_vec = embed([issue_text])[0]
        v = issue_vec / np.linalg.norm(issue_vec)
        m = stock_vecs / np.linalg.norm(stock_vecs, axis=1, keepdims=True)
        sims = m @ v
        emb_order = np.argsort(-sims)
        emb_ranked = [kept[i] for i in emb_order]
        p(f"  임베딩 순위: {', '.join(emb_ranked)}")

        p("  GDELT 조회 중 (사례당 1회, ArtList 최대 250건)...")
        start, end = case["event_window"]
        titles = []
        for retry in range(2):  # 429는 재시도 횟수보다 경과 시간이 관건이었다 (2026-09-10 실측)
            try:
                titles = gdelt_titles(case["gdelt_query"], start, end)
                break
            except Exception as e:
                p(f"    GDELT 조회 실패({'재시도 전' if retry == 0 else '포기'}): {e}")
                if retry == 0:
                    time.sleep(90)
        titles_l = [t.lower() for t in titles]
        gdelt_counts = {
            t: sum(1 for title in titles_l if SEARCH_KEYWORD.get(t, t).lower() in title)
            for t in kept
        }
        gdelt_ranked = sorted(kept, key=lambda t: -gdelt_counts[t])
        p(f"  GDELT 제목 {len(titles)}건 수집. 제목 내 언급수: {json.dumps(gdelt_counts, ensure_ascii=False)}")

        for k in ks:
            grades = grade_split(emb_ranked, gdelt_ranked, k)
            p(f"\n  --- K={k} ---")
            for label, members in grades.items():
                hits = sorted(t for t in members if t in answers)
                noise_n = len(members) - len(hits)
                noise_pct = f"{100 * noise_n / len(members):.0f}%" if members else "-"
                p(f"    {label}: 정답 {hits} / 전체 {len(members)}개 (노이즈 {noise_pct})")
            missed = [t for t in answers if t not in set(emb_ranked[:k]) | set(gdelt_ranked[:k])]
            if missed:
                p(f"    K={k}에서 아무 등급에도 안 걸린 정답: {missed}")

    used_after = credits()
    p(f"\n크레딧 사용: {used_after - used_before} (누적 {used_after})")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
