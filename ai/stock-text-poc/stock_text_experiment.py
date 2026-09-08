"""WP-43 — 종목 임베딩 입력 텍스트 규격 비교 실험.

yfinance longBusinessSummary 를 그대로 넣을지, 메타데이터를 앞에 붙일지,
상투 문구(설립연도·본사 소재지)를 제거할지를 같은 이슈 텍스트로 비교한다.

  A) 사업 설명 그대로            (지금까지 실측에 쓰던 방식)
  B) 회사명·섹터·산업 접두 + 사업 설명
  C) B에서 상투 문구 제거 ("... was founded in 19xx and is headquartered in ...")

이슈 쪽은 WP-42 확정 규칙(D: 문서수 적응 나열)을 그대로 쓴다.
종목·클러스터·정답 목록은 issue-text-poc 실험과 동일 — 비교 기준을 맞추기 위해서다.

실행: LLM_GATEWAY_KEY 환경변수 필요.
    uv run --python 3.11 --with-requirements requirements.txt --no-project python stock_text_experiment.py [출력파일]
"""

import io
import os
import re
import sys

import numpy as np
import requests
import yfinance as yf

GATEWAY = "https://llm-gateway.example.com"
KEY = os.environ["LLM_GATEWAY_KEY"]
EMBED_MODEL = "text-embedding-3-small"
UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"}

# issue-text-poc 실험과 동일한 클러스터·정답·종목 세트.
CLUSTERS = {
    "Milton": {
        "articles": ["Hurricane Milton", "Florida", "Storm surge", "Tampa, Florida"],
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
    "NEE", "DUK", "GNRC", "HD", "LOW", "LEN", "ETN", "UAL",
    "XOM", "CVX", "OXY", "FRO", "DHT", "TNK", "LMT", "RTX", "DAL",
    "NVDA", "AMD", "TSM",
    "MNST", "INTC", "NKE", "SBUX", "KO", "PG", "CRM", "ADBE", "T", "VZ", "MCD", "COST",
]

MAX_CHARS = 2000
# 사업 설명 끝에 거의 항상 붙는 상투 문장. 설립연도·본사 소재지는 사업 정체성과
# 무관해서 임베딩 변별력을 흐릴 수 있다는 가설을 검증한다.
BOILERPLATE = re.compile(
    r"[^.]*\b(was founded|is headquartered|was incorporated)\b[^.]*\.", re.I
)


def wiki_intro(title):
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


def issue_text(articles):
    """WP-42 확정 규칙(D: 문서수 적응 나열)."""
    intros = {a: wiki_intro(a) for a in articles}
    per_doc = 6 if len(articles) == 1 else (4 if len(articles) <= 3 else 2)
    return "\n".join(
        f"{a}: {first_sentences(intros[a], per_doc)}" for a in articles
    )[:MAX_CHARS]


def embed(texts):
    r = requests.post(
        f"{GATEWAY}/api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": EMBED_MODEL, "input": texts}, timeout=120,
    )
    r.raise_for_status()
    return np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)


def credits():
    r = requests.get(f"{GATEWAY}/key-info", headers={"Authorization": f"Bearer {KEY}"}, timeout=30)
    return r.json()["usedCredit"]


def build_variants(info):
    """종목 하나의 세 방식 텍스트를 만든다."""
    summary = info.get("longBusinessSummary", "") or ""
    name = info.get("shortName", "") or ""
    sector = info.get("sector", "") or ""
    industry = info.get("industry", "") or ""

    a_text = summary[:MAX_CHARS]

    prefix = f"{name}. {sector} — {industry}. " if (sector or industry) else f"{name}. "
    b_text = (prefix + summary)[:MAX_CHARS]

    stripped = BOILERPLATE.sub("", summary).strip()
    c_text = (prefix + stripped)[:MAX_CHARS]

    return {"A 설명 그대로": a_text, "B 메타 접두": b_text, "C 메타+상투문구 제거": c_text}


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

    p("## 종목 정보 수집")
    infos, kept = {}, []
    for t in TICKERS:
        try:
            info = yf.Ticker(t).info
        except Exception as e:
            p(f"  {t} 실패: {type(e).__name__}")
            continue
        if info.get("longBusinessSummary"):
            infos[t] = info
            kept.append(t)
    p(f"  {len(kept)}/{len(TICKERS)}종목 확보\n")

    variant_texts = {t: build_variants(infos[t]) for t in kept}
    labels = list(next(iter(variant_texts.values())).keys())

    p("## 이슈 텍스트 (WP-42 규칙)")
    issue_vecs = {}
    for name, spec in CLUSTERS.items():
        text = issue_text(spec["articles"])
        issue_vecs[name] = embed([text])[0]
        p(f"  {name}: {len(text)}자")

    rows = []
    for label in labels:
        stock_vecs = embed([variant_texts[t][label] for t in kept])
        avg_len = np.mean([len(variant_texts[t][label]) for t in kept])

        p(f"\n{'=' * 70}\n## {label} (평균 길이 {avg_len:.0f}자)")
        for cname, spec in CLUSTERS.items():
            answers = [a for a in spec["answers"] if a in kept]
            sims = cosine_rank(issue_vecs[cname], stock_vecs)
            order = np.argsort(-sims)
            ranked = [kept[i] for i in order]

            ans_ranks = [ranked.index(a) + 1 for a in answers]
            noise = [t for t in kept if t not in answers]
            hit5 = sum(1 for t in ranked[:5] if t in answers)
            hit10 = sum(1 for t in ranked[:10] if t in answers)
            ans_mean = float(np.mean([sims[kept.index(a)] for a in answers]))
            noise_mean = float(np.mean([sims[kept.index(t)] for t in noise]))

            p(f"\n### {cname}")
            p(f"  Top-10: {', '.join(ranked[:10])}")
            p(f"  정답 평균 순위 {np.mean(ans_ranks):.1f} / {len(kept)}  (정답 {len(answers)}개)")
            p(f"  Top-5 정답 {hit5}개 · Top-10 정답 {hit10}개")
            p(f"  코사인 — 정답 평균 {ans_mean:.3f} · 노이즈 평균 {noise_mean:.3f} · 분리도 {ans_mean - noise_mean:+.3f}")

            rows.append((label, cname, round(avg_len), float(np.mean(ans_ranks)),
                         hit5, hit10, ans_mean - noise_mean))

    p(f"\n\n{'=' * 70}\n## 요약표\n")
    p(f"{'방식':<24}{'클러스터':<10}{'평균길이':>8}{'정답평균순위':>12}{'T5':>4}{'T10':>5}{'분리도':>8}")
    for r in rows:
        p(f"{r[0]:<24}{r[1]:<10}{r[2]:>8}{r[3]:>12.1f}{r[4]:>4}{r[5]:>5}{r[6]:>+8.3f}")

    used_after = credits()
    p(f"\n크레딧 사용: {used_after - used_before} (누적 {used_after})")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
