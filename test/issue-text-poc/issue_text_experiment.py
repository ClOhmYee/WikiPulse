"""WP-42 — 이슈 대표 텍스트 만드는 규칙 비교 실험.

급증 문서 클러스터를 임베딩 입력용 한 덩이 텍스트로 만드는 세 가지 방식을
같은 조건에서 비교한다.

  A) 대표 문서 위키 도입부      (지금까지 실측에 쓰던 방식)
  B) 클러스터 문서 제목 + 요약 나열
  C) B를 LLM에 한 번 넣어 만든 이슈 요약

비교 기준: 길이 / 생성 지연 / LLM 호출 수 / 종목 랭킹 품질.

종목 세트는 정답 후보와 노이즈를 섞은 32개 고정 목록이다. 전체 5,100종목을
적재하기 전에 "어느 텍스트가 정답을 위로 올리는가"만 보면 되므로 작게 잡았다.
정답 목록은 잠정값이다 — 확정은 WP-39(정답셋)에서 한다.

실행: LLM_GATEWAY_KEY 환경변수 필요.
    py -3 issue_text_experiment.py [출력파일]
"""

import io
import json
import os
import sys
import time

import numpy as np
import requests
import yfinance as yf

GATEWAY = "https://llm-gateway.example.com"
KEY = os.environ["LLM_GATEWAY_KEY"]
EMBED_MODEL = "text-embedding-3-small"
LLM_MODEL = "claude-sonnet-4-5-20250929"
UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"}

# 급증 문서 클러스터. 사건형 둘 + 대조군으로 기업형 하나.
CLUSTERS = {
    "Milton": {
        "articles": ["Hurricane Milton", "Florida", "Storm surge", "Tampa, Florida"],
        # §11 GDELT lift 실측 상위 + 임베딩 Top-20에서 정답으로 표기된 것
        "answers": ["NEE", "DUK", "GNRC", "HD", "LOW", "LEN", "ETN", "UAL"],
    },
    "Hormuz": {
        "articles": ["Strait of Hormuz", "Iran", "Oil tanker", "Petroleum"],
        "answers": ["XOM", "CVX", "OXY", "FRO", "DHT", "TNK", "LMT", "RTX", "DAL"],
    },
    "Nvidia": {
        "articles": ["Nvidia"],
        "answers": ["NVDA", "AMD", "TSM"],
    },
}

TICKERS = [
    # Milton 계열
    "NEE", "DUK", "GNRC", "HD", "LOW", "LEN", "ETN", "UAL",
    # Hormuz 계열
    "XOM", "CVX", "OXY", "FRO", "DHT", "TNK", "LMT", "RTX", "DAL",
    # Nvidia 계열
    "NVDA", "AMD", "TSM",
    # 노이즈
    "MNST", "INTC", "NKE", "SBUX", "KO", "PG", "CRM", "ADBE", "T", "VZ", "MCD", "COST",
]

MAX_CHARS = 2000  # 임베딩 입력 상한. 규칙 확정 시 함께 결정한다.


def credits():
    r = requests.get(f"{GATEWAY}/key-info", headers={"Authorization": f"Bearer {KEY}"}, timeout=30)
    return r.json()["usedCredit"]


def wiki_intro(title):
    """문서 도입부 평문. 없으면 빈 문자열."""
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query", "prop": "extracts", "exintro": True,
            "explaintext": True, "redirects": 1, "titles": title, "format": "json",
        },
        headers=UA, timeout=30,
    )
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    for page in pages.values():
        return page.get("extract", "").strip()
    return ""


def first_sentences(text, n=2):
    parts = text.replace("\n", " ").split(". ")
    return ". ".join(parts[:n]).strip().rstrip(".") + "." if parts else ""


def embed(texts):
    r = requests.post(
        f"{GATEWAY}/api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": EMBED_MODEL, "input": texts}, timeout=120,
    )
    r.raise_for_status()
    return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)


def llm_summary(listing):
    # 출력은 영어로 받는다. 종목 설명이 영어라 요약이 한국어면 언어 불일치만으로
    # 코사인이 절반으로 떨어진다 (2026-09-08 실험 1차에서 확인).
    prompt = (
        "The following Wikipedia articles all had a simultaneous surge in edits. "
        "Their titles and lead sections are given below.\n\n"
        "Write 3-4 sentences in English describing the event that caused this surge. "
        "State what happened and where, and which industries, commodities, or business "
        "activities it affects. Do not name any company or ticker. "
        "Do not invent facts that are not supported by the text below. "
        "Output only the description.\n\n" + listing
    )
    r = requests.post(
        f"{GATEWAY}/api.anthropic.com/v1/messages",
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": LLM_MODEL, "max_tokens": 400,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def build_variants(articles):
    """세 방식의 텍스트와 각각의 생성 지연·LLM 호출 수를 만든다."""
    t0 = time.time()
    intros = {a: wiki_intro(a) for a in articles}
    fetch_s = time.time() - t0

    a_text = intros[articles[0]][:MAX_CHARS]
    b_text = "\n".join(f"{a}: {first_sentences(intros[a])}" for a in articles)[:MAX_CHARS]

    # D: B와 같되 문서 수에 따라 문서당 문장 수를 조절한다. 문서가 적으면
    # 2문장으로 자르는 게 손해다 (Nvidia 단일 문서에서 A보다 나빴다).
    per_doc = 6 if len(articles) == 1 else (4 if len(articles) <= 3 else 2)
    d_text = "\n".join(
        f"{a}: {first_sentences(intros[a], per_doc)}" for a in articles
    )[:MAX_CHARS]

    t1 = time.time()
    c_text = llm_summary(b_text)[:MAX_CHARS]
    llm_s = time.time() - t1

    return {
        "A 대표문서 도입부": (a_text, fetch_s, 0),
        "B 제목+요약 나열": (b_text, fetch_s, 0),
        "C LLM 이슈 요약": (c_text, fetch_s + llm_s, 1),
        "D 문서수 적응 나열": (d_text, fetch_s, 0),
    }


def cosine_rank(vec, stock_vecs):
    v = vec / np.linalg.norm(vec)
    m = stock_vecs / np.linalg.norm(stock_vecs, axis=1, keepdims=True)
    return m @ v


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "result.txt"
    out = io.open(out_path, "w", encoding="utf-8")

    def p(*a):
        out.write(" ".join(str(x) for x in a) + "\n")
        out.flush()

    used_before = credits()

    p("## 종목 설명 수집")
    descs, kept = [], []
    for t in TICKERS:
        try:
            d = yf.Ticker(t).info.get("longBusinessSummary", "") or ""
        except Exception as e:
            d = ""
            p(f"  {t} 실패: {type(e).__name__}")
        if d:
            kept.append(t)
            descs.append(d[:MAX_CHARS])
    p(f"  {len(kept)}/{len(TICKERS)}종목 설명 확보. 누락: {sorted(set(TICKERS) - set(kept))}")

    stock_vecs = embed(descs)
    p(f"  임베딩 {stock_vecs.shape}\n")

    rows = []
    for name, spec in CLUSTERS.items():
        p(f"\n{'=' * 70}\n## 클러스터 {name} — {spec['articles']}")
        answers = [a for a in spec["answers"] if a in kept]
        variants = build_variants(spec["articles"])

        for label, (text, gen_s, calls) in variants.items():
            vec = embed([text])[0]
            sims = cosine_rank(vec, stock_vecs)
            order = np.argsort(-sims)
            ranked = [kept[i] for i in order]

            ans_ranks = [ranked.index(a) + 1 for a in answers]
            noise = [t for t in kept if t not in answers]
            top5 = ranked[:5]
            hit5 = sum(1 for t in top5 if t in answers)
            hit10 = sum(1 for t in ranked[:10] if t in answers)
            ans_mean = float(np.mean([sims[kept.index(a)] for a in answers]))
            noise_mean = float(np.mean([sims[kept.index(t)] for t in noise]))

            p(f"\n### {label}")
            p(f"  길이 {len(text)}자 · 생성 {gen_s:.1f}s · LLM 호출 {calls}회")
            p(f"  Top-10: {', '.join(ranked[:10])}")
            p(f"  정답 평균 순위 {np.mean(ans_ranks):.1f} / {len(kept)}  (정답 {len(answers)}개)")
            p(f"  Top-5 정답 {hit5}개 · Top-10 정답 {hit10}개")
            p(f"  코사인 — 정답 평균 {ans_mean:.3f} · 노이즈 평균 {noise_mean:.3f} · 분리도 {ans_mean - noise_mean:+.3f}")
            p(f"  본문: {text[:300].replace(chr(10), ' ')}...")

            rows.append((name, label, len(text), gen_s, calls,
                         float(np.mean(ans_ranks)), hit5, hit10, ans_mean - noise_mean))

    p(f"\n\n{'=' * 70}\n## 요약표\n")
    p(f"{'클러스터':<10}{'방식':<20}{'길이':>6}{'생성s':>7}{'LLM':>5}{'정답평균순위':>12}{'T5':>4}{'T10':>5}{'분리도':>8}")
    for r in rows:
        p(f"{r[0]:<10}{r[1]:<20}{r[2]:>6}{r[3]:>7.1f}{r[4]:>5}{r[5]:>12.1f}{r[6]:>4}{r[7]:>5}{r[8]:>+8.3f}")

    used_after = credits()
    p(f"\n크레딧 사용: {used_after - used_before} (누적 {used_after})")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
