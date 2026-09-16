"""WP-45 — LLM 검증 프롬프트·응답 형식 실험.

prompts/verify_system_v1.txt (시스템 프롬프트) + schema/verify_response_v1.json
(출력 스키마)를 실제 GATEWAY 경유 Claude 호출로 검증한다. matching-goldset(-39)
정답셋에서 (이슈, 후보 종목) 쌍 5개를 뽑아 호출하고, 응답이 스키마를 지키는지,
재시도·폐기 규칙이 동작하는지 확인한다.

⚠️ GDELT 동시출현 컨텍스트는 이 실험에서 항상 비워 보낸다. GDELT GKG 기관명
추출(-47)이 아직 없어 실제로 채울 수 없다 — "컨텍스트 없이 임베딩·설명만으로
얼마나 잡히는가"가 이 실험이 실측하려는 것 중 하나다.

실행: LLM_GATEWAY_KEY 환경변수 필요.
    py -3 verify_experiment.py [출력파일]
"""

import io
import json
import os
import sys

import requests
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "matching-goldset"))
from cases import CASES  # noqa: E402

GATEWAY = "https://llm-gateway.example.com"
LLM_MODEL = "claude-sonnet-4-5-20250929"
UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"}
MAX_CHARS = 2000
PROMPT_VERSION = "v1"

HERE = os.path.dirname(__file__)
SYSTEM_PROMPT = io.open(
    os.path.join(HERE, "prompts", f"verify_system_{PROMPT_VERSION}.txt"), encoding="utf-8"
).read()

# (사례 키, 후보 티커, 기대) — 기대는 사람이 정답셋(cases.py)에서 미리 아는 값.
# 실제 응답이 이와 다르면 오답이지 실험 실패가 아니다 — 있는 그대로 기록한다.
SAMPLE_PAIRS = [
    ("Milton", "NEE", "verified(strong) — 직접 피해 전력사"),
    ("Milton", "MNST", "reject — 노이즈"),
    ("CrowdStrike", "MSFT", "verified(weak) — 간접, 보도에 이름만 많이 섞임"),
    ("IBM_profit_warning", "MU", "불확실 — GDELT 없이 이슈 본문만으로는 근거를 못 만들 가능성 (테스트 목적)"),
    ("PayPal_buyout_collapse", "XYZ", "reject — 동종업계지만 무관"),
]


def credits():
    r = requests.get(f"{GATEWAY}/key-info", headers={"Authorization": f"Bearer {os.environ['LLM_GATEWAY_KEY']}"}, timeout=30)
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
    """명세 §6.2 확정 규칙(D) — goldset_experiment.py와 동일."""
    per_doc = 6 if len(seed_articles) == 1 else (4 if len(seed_articles) <= 3 else 2)
    intros = {a: wiki_intro(a) for a in seed_articles}
    return "\n".join(f"{a}: {first_sentences(intros[a], per_doc)}" for a in seed_articles)[:MAX_CHARS]


def candidate_info(ticker):
    info = yf.Ticker(ticker).info
    name = info.get("shortName") or info.get("longName") or ticker
    summary = (info.get("longBusinessSummary") or "")[:MAX_CHARS]
    return name, summary


def build_user_message(issue_text, gdelt_context, name, ticker, summary):
    return (
        f"## Issue\n{issue_text}\n\n"
        f"## News co-mention context\n{gdelt_context or '(none available)'}\n\n"
        f"## Candidate company\n"
        f"Name: {name}\nTicker: {ticker}\nBusiness description: {summary}\n\n"
        "Decide whether this candidate is verified as related to the issue above, "
        "following the rules in the system prompt. Output only the JSON object."
    )


def call_llm(messages):
    r = requests.post(
        f"{GATEWAY}/api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["LLM_GATEWAY_KEY"], "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": LLM_MODEL, "max_tokens": 400, "system": SYSTEM_PROMPT, "messages": messages},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


REQUIRED_KEYS = {"issue_class", "verified", "match_path", "confidence", "rationale_en", "rationale_ko"}
ISSUE_CLASSES = {"SINGLE_COMPANY_EVENT", "SECTOR_OR_REGION_EVENT"}
MATCH_PATHS = {"DIRECT_MENTION", "PRODUCT_INDUSTRY", "SUPPLY_CHAIN", "REGION"}
CONFIDENCES = {"strong", "weak"}


def validate(resp):
    """스키마 위반이면 문제 사유 문자열을 반환, 문제 없으면 None."""
    if not isinstance(resp, dict):
        return "object 아님"
    if set(resp.keys()) != REQUIRED_KEYS:
        return f"키 불일치: {sorted(resp.keys())}"
    if resp["issue_class"] not in ISSUE_CLASSES:
        return f"issue_class 값 이상: {resp['issue_class']!r}"
    if not isinstance(resp["verified"], bool):
        return "verified가 boolean 아님"
    fields = ["match_path", "confidence", "rationale_en", "rationale_ko"]
    if resp["verified"]:
        if resp["match_path"] not in MATCH_PATHS:
            return f"match_path 값 이상: {resp['match_path']!r}"
        if resp["confidence"] not in CONFIDENCES:
            return f"confidence 값 이상: {resp['confidence']!r}"
        for f in ["rationale_en", "rationale_ko"]:
            if not resp[f] or not isinstance(resp[f], str):
                return f"{f} 비어있음"
    else:
        if any(resp[f] is not None for f in fields):
            return "verified=false인데 나머지 필드가 null 아님"
    return None


def verify_candidate(issue_text, gdelt_context, name, ticker, summary):
    """재시도 규칙: JSON 파싱/스키마 실패 시 같은 대화에 정정 요청 1회 추가. 그래도 실패하면 폐기(None)."""
    messages = [{"role": "user", "content": build_user_message(issue_text, gdelt_context, name, ticker, summary)}]
    for attempt in range(2):
        raw = call_llm(messages)
        try:
            resp = json.loads(strip_fences(raw))
            problem = validate(resp)
        except json.JSONDecodeError as e:
            resp, problem = None, f"JSON 파싱 실패: {e}"
        if problem is None:
            return resp, attempt + 1, None
        if attempt == 0:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                              f"That response was invalid ({problem}). "
                              "Return ONLY the JSON object matching the schema, nothing else."})
    return None, 2, problem


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "result.txt"
    out = io.open(out_path, "w", encoding="utf-8")

    def p(*a):
        out.write(" ".join(str(x) for x in a) + "\n")
        out.flush()

    used_before = credits()
    p(f"프롬프트 버전: {PROMPT_VERSION} / 모델: {LLM_MODEL}\n")

    for case_key, ticker, expected in SAMPLE_PAIRS:
        case = CASES[case_key]
        issue_text = build_issue_text(case["seed_articles"])
        name, summary = candidate_info(ticker)
        p(f"{'=' * 70}\n## {case_key} × {ticker} ({name})")
        p(f"  기대: {expected}")
        if not summary:
            p("  사업 설명 없음 — 건너뜀")
            continue

        resp, attempts, problem = verify_candidate(issue_text, "", name, ticker, summary)
        p(f"  호출 횟수: {attempts}")
        if resp is None:
            p(f"  ⚠️ 폐기 — 스키마 미준수: {problem}")
            continue
        p(f"  결과: {json.dumps(resp, ensure_ascii=False)}")

    used_after = credits()
    p(f"\n크레딧 사용: {used_after - used_before} (누적 {used_after})")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
