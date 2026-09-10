"""WP-48 — 실제 텍스트·모델로 후보 겹침 재측정.

명세 §11 "임베딩 vs GDELT 후보 교집합"(2026-09-07)은 이슈 텍스트를 위키 도입부로
대신하고 텍스트 규칙이 확정되기 전에 잰 값이다. 확정된 이슈 텍스트 규칙(§6.2,
WP-42)과 종목 임베딩 규격(§6.1, WP-43)으로 다시 재고, 정답은
WP-39 정답셋(`ai/matching-goldset/cases.py`)을 그대로 쓴다.

후보 풀은 S&P 500(502종목, `sp500.py`) — DB의 5,100종목 전수가 아니라 이전
실측과 규모를 맞춘 것이다(사유는 sp500.py docstring). 정답 티커가 S&P 500에
없으면(외국 ADR 등) 후보 풀에 추가해 최소한 측정은 되게 한다.

실행: py -3 overlap_experiment.py [출력파일] [K1,K2,...]
LLM_GATEWAY_KEY 필요. yfinance 요약 수집은 summaries.json에 체크포인트하며 이어서 받는다.
"""
import io
import json
import os
import sys
import time

import numpy as np
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "matching-goldset"))
from cases import CASES  # noqa: E402
from goldset_experiment import (  # noqa: E402
    ALIASES, SEARCH_KEYWORD, build_issue_text, embed, gdelt_titles, credits,
)
from sp500 import fetch as fetch_sp500  # noqa: E402

HERE = os.path.dirname(__file__)
SUMMARY_CACHE = os.path.join(HERE, "summaries.json")
EMBED_CACHE = os.path.join(HERE, "embeddings.json")
GDELT_DELAY_S = 25


def build_candidate_universe():
    """S&P 500 + 정답셋 티커 중 빠진 것. {ticker: company_name}."""
    universe = {s["ticker"]: s["name"] for s in fetch_sp500()}
    for case in CASES.values():
        for t, _, _ in case["answers"]:
            if t not in universe:
                universe[t] = ALIASES.get(t, t)
    return universe


def load_json(path):
    return json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}


def save_json(path, obj):
    json.dump(obj, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def fetch_summaries(tickers, log):
    cache = load_json(SUMMARY_CACHE)
    pending = [t for t in tickers if t not in cache]
    log(f"  종목 설명: 캐시 {len(cache)}개, 신규 {len(pending)}개 수집 중...")
    for i, t in enumerate(pending, 1):
        try:
            cache[t] = yf.Ticker(t).info.get("longBusinessSummary") or ""
        except Exception:
            cache[t] = ""
        if i % 50 == 0 or i == len(pending):
            save_json(SUMMARY_CACHE, cache)
            log(f"    {i}/{len(pending)}")
        time.sleep(0.1)
    save_json(SUMMARY_CACHE, cache)
    return {t: s for t, s in cache.items() if t in tickers and s}


def embed_universe(descs_by_ticker, log):
    """{ticker: text} -> {ticker: np.array}. 이미 임베딩한 건 재사용."""
    cache = load_json(EMBED_CACHE)
    pending = {t: d for t, d in descs_by_ticker.items() if t not in cache}
    log(f"  임베딩: 캐시 {len(cache)}개, 신규 {len(pending)}개")
    items = list(pending.items())
    for start in range(0, len(items), 100):
        chunk = items[start:start + 100]
        vecs = embed([d for _, d in chunk])
        for (t, _), v in zip(chunk, vecs):
            cache[t] = v.tolist()
        save_json(EMBED_CACHE, cache)
        log(f"    {min(start + 100, len(items))}/{len(items)}")
    return {t: np.array(cache[t], dtype=np.float32) for t in descs_by_ticker if t in cache}


def gdelt_rank(query, start, end, company_names, log):
    """company_names: {ticker: name}. 반환: 제목 언급수 내림차순 티커 목록."""
    titles = []
    for retry in range(2):
        try:
            titles = gdelt_titles(query, start, end)
            break
        except Exception as e:
            log(f"    GDELT 조회 실패({'재시도 전' if retry == 0 else '포기'}): {e}")
            if retry == 0:
                time.sleep(90)
    titles_l = [t.lower() for t in titles]
    counts = {
        t: sum(1 for title in titles_l if SEARCH_KEYWORD.get(t, name).lower() in title)
        for t, name in company_names.items()
    }
    ranked = sorted(company_names, key=lambda t: -counts[t])
    return ranked, counts, len(titles)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "result.txt"
    ks = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [10, 20, 30]
    out = io.open(out_path, "w", encoding="utf-8")

    def log(*a):
        line = " ".join(str(x) for x in a)
        out.write(line + "\n")
        out.flush()

    used_before = credits()
    universe = build_candidate_universe()
    log(f"후보 풀 {len(universe)}종목 (S&P 500 + 정답셋 보강)")

    descs = fetch_summaries(list(universe), log)
    log(f"  설명 확보 {len(descs)}/{len(universe)} ({100 * len(descs) / len(universe):.0f}%)")
    stock_vecs = embed_universe(descs, log)
    tickers = list(stock_vecs)
    m = np.stack([stock_vecs[t] for t in tickers])
    m = m / np.linalg.norm(m, axis=1, keepdims=True)

    for ci, (name, case) in enumerate(CASES.items()):
        if ci > 0:
            time.sleep(GDELT_DELAY_S)
        log(f"\n{'=' * 70}\n## {name} ({case['type']}) — {case['event_date']}")
        answers = {t for t, _, _ in case["answers"]}
        missing = answers - set(tickers)
        if missing:
            log(f"  설명 없어 후보에서 빠진 정답: {missing}")

        issue_vec = embed([build_issue_text(case["seed_articles"])])[0]
        v = issue_vec / np.linalg.norm(issue_vec)
        sims = m @ v
        emb_ranked = [tickers[i] for i in np.argsort(-sims)]

        start, end = case["event_window"]
        company_names = {t: ALIASES.get(t, universe[t]) for t in tickers}
        gdelt_ranked, gdelt_counts, n_titles = gdelt_rank(
            case["gdelt_query"], start, end, company_names, log
        )
        nonzero = sum(1 for c in gdelt_counts.values() if c > 0)
        log(f"  GDELT 제목 {n_titles}건, 언급된 종목 {nonzero}/{len(tickers)}개")

        for k in ks:
            emb_top = set(emb_ranked[:k])
            gdelt_top = set(gdelt_ranked[:k])
            overlap = emb_top & gdelt_top
            emb_only = emb_top - gdelt_top
            noise_pct = (
                100 * len(emb_only - answers) / len(emb_only) if emb_only else 0
            )
            log(f"  --- K={k} ---")
            log(f"    임베딩∩GDELT 겹침: {len(overlap)}개 {sorted(overlap)}")
            log(f"    정답 포함 — 임베딩Top-K: {sorted(answers & emb_top)} "
                f"/ GDELT Top-K: {sorted(answers & gdelt_top)}")
            log(f"    임베딩 단독 후보 노이즈 비율: {noise_pct:.0f}% ({len(emb_only)}개 중)")

    used_after = credits()
    log(f"\n크레딧 사용: {used_after - used_before} (누적 {used_after})")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
