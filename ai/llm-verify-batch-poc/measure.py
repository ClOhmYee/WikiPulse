"""후보 배치 검증이 실제로 얼마나 싼지 잰다 (WP-170).

지금 검증은 **후보 하나당 LLM 1회**다. 이슈 컨텍스트(시스템 프롬프트 + 대표 텍스트 +
GDELT 기관명)가 후보 수만큼 재전송된다. 후보 15개면 그 공유분이 15번 나간다.

배치는 공유분을 한 번만 보낸다. ⚠️ 그렇다고 비용이 1/15 이 되지는 않는다 — **출력은
후보마다 판정 6필드가 필요해 그대로 남는다.** 그래서 호출 수가 아니라 토큰으로 재야
한다. 이 스크립트가 그 차이를 재는 이유다.

두 모드
    (기본) 오프라인   문자 수 회계. GATEWAY 키·크레딧이 필요 없다. 두 프롬프트를 실제로
                      조립해 공유분/고유분을 센다.
    --live            GATEWAY 실호출. 단건 N회와 배치 1회를 같은 입력으로 돌려 판정·토큰·
                      크레딧을 대조한다. 🔴 팀 크레딧을 쓴다.

🔴 **응답은 티커로 매칭한다.** 배치 응답을 순서로 붙이면 모델이 15개 중 14개만
돌려줬을 때 14번째 판정이 15번째 티커에 붙는다 — 에러 없이 조용히 오배정된다.
`verify_batch_system_v2.txt` 가 티커를 필수로 요구하고, 여기서도 티커로만 찾는다.

⚠️ 오프라인 모드는 **문자 수**지 토큰이 아니다. 로컬에 토크나이저가 없어서 실제
토큰은 `--live` 의 API `usage` 로만 확인된다. 문자 비율과 토큰 비율이 크게 다르면
그 사실 자체가 결과다 — 추정으로 메우지 않는다.

실행 (저장소 루트에서)::

    python ai/llm-verify-batch-poc/measure.py --case Milton
    python ai/llm-verify-batch-poc/measure.py --case Milton --live

`--live` 는 저장소 루트 `.env` 의 `LLM_GATEWAY_KEY` 를 읽는다(환경변수가 있으면 그쪽 우선).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

import requests
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ai", "matching-goldset"))
from cases import CASES  # noqa: E402

GATEWAY = "https://llm-gateway.example.com"
LLM_MODEL = "claude-sonnet-4-5-20250929"
UA = {"User-Agent": "WikiPulse/0.1 (WikiPulse research; contact via GitLab)"}

#: 이슈 대표 텍스트 상한. 명세 §6.2 · `CandidateProperties.maxChars` 와 같은 값.
MAX_CHARS = 2000

#: 단건 프롬프트는 프로덕션이 쓰는 v1 을 그대로 읽는다 — 비교 기준이 실물이어야 한다.
SINGLE_PROMPT = io.open(
    os.path.join(ROOT, "ai", "llm-verify-poc", "prompts", "verify_system_v1.txt"),
    encoding="utf-8").read()
BATCH_PROMPT = io.open(
    os.path.join(HERE, "prompts", "verify_batch_system_v2.txt"), encoding="utf-8").read()

#: 배치 응답 상한. 후보마다 6필드가 나오므로 단건(800)의 후보 수 배가 필요하다.
#: ⚠️ 모자라면 JSON 이 중간에서 잘려 전부 폐기된다 — 단건의 절단 실패와 같은 형태인데
#: 배치는 한 번에 전부 잃는다.
BATCH_MAX_TOKENS_PER_CANDIDATE = 220
SINGLE_MAX_TOKENS = 800


def load_key() -> str:
    key = os.environ.get("LLM_GATEWAY_KEY", "").strip()
    if key:
        return key
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in io.open(env, encoding="utf-8"):
            if line.startswith("LLM_GATEWAY_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("LLM_GATEWAY_KEY 없음 — 저장소 루트 .env 에 넣거나 환경변수로 준다")


def credits(key: str) -> float:
    r = requests.get(f"{GATEWAY}/key-info", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    body = r.json()
    for k in ("used_credit", "usedCredit", "used"):
        if k in body:
            return float(body[k])
    raise SystemExit(f"key-info 응답에서 사용량 필드를 못 찾음: {sorted(body)}")


# --------------------------------------------------------------------------
# 입력 조립 — 단건·배치가 **같은 재료**를 쓴다
# --------------------------------------------------------------------------

#: 입력 재료 캐시. ⚠️ 같은 입력으로 단건·배치를 돌려야 비교가 성립하는데, 매 실행마다
#: 위키·yfinance 를 다시 부르면 그 사이 문서가 바뀌어 **다른 입력을 비교하게 된다.**
#: 429 도 피한다 — WP-164 수집이 같은 IP 의 api.php 예산을 쓰고 있어 실제로 맞았다.
CACHE = os.path.join(HERE, "cache.json")


def _cache() -> dict:
    if os.path.exists(CACHE):
        return json.load(io.open(CACHE, encoding="utf-8"))
    return {}


def _cache_put(key: str, value) -> None:
    c = _cache()
    c[key] = value
    io.open(CACHE, "w", encoding="utf-8").write(
        json.dumps(c, ensure_ascii=False, indent=1))


def _get(url: str, **kw):
    """429 지수 백오프. api.php 는 간격이 아니라 총량 예산이라 백오프가 실질 페이서다."""
    delay = 5.0
    for attempt in range(6):
        r = requests.get(url, **kw)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        wait = float(r.headers.get("Retry-After") or delay)
        print(f"  429 — {wait:.0f}초 대기 ({attempt + 1}/6)", file=sys.stderr, flush=True)
        time.sleep(wait)
        delay *= 2
    raise SystemExit("429 가 계속된다 — 다른 수집이 도는 중이면 끝나고 다시 돌린다")


def wiki_intro(title: str) -> str:
    hit = _cache().get(f"wiki:{title}")
    if hit is not None:
        return hit
    r = _get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "redirects": 1, "titles": title, "format": "json", "formatversion": "2"})
    pages = r.json()["query"]["pages"]
    text = pages[0].get("extract", "") if pages else ""
    _cache_put(f"wiki:{title}", text)
    return text


def build_issue_text(seed_articles: list[str]) -> str:
    """명세 §6.2: 문서별 `제목: 도입부` 나열, 영어 유지. LLM 요약을 쓰지 않는다."""
    parts = [f"{t}: {wiki_intro(t)}" for t in seed_articles]
    return "\n\n".join(p for p in parts if p.strip())[:MAX_CHARS]


def candidate_info(ticker: str) -> tuple[str, str]:
    hit = _cache().get(f"stock:{ticker}")
    if hit is not None:
        return hit[0], hit[1]
    info = yf.Ticker(ticker).info
    pair = [info.get("shortName") or ticker, (info.get("longBusinessSummary") or "").strip()]
    _cache_put(f"stock:{ticker}", pair)
    return pair[0], pair[1]


def single_user_message(issue_text, gdelt, name, ticker, summary) -> str:
    """`ai/llm-verify-poc/verify_experiment.py` 의 형식을 그대로 옮긴다."""
    return (
        f"## Issue\n{issue_text}\n\n"
        f"## News co-mention context\n{gdelt or '(none available)'}\n\n"
        f"## Candidate company\n"
        f"Name: {name}\nTicker: {ticker}\nBusiness description: {summary}\n\n"
        "Decide whether this candidate is verified as related to the issue above, "
        "following the rules in the system prompt. Output only the JSON object.")


def batch_user_message(issue_text, gdelt, candidates) -> str:
    lines = []
    for i, (name, ticker, summary) in enumerate(candidates, 1):
        lines.append(f"{i}. Name: {name}\n   Ticker: {ticker}\n   Business description: {summary}")
    return (
        f"## Issue\n{issue_text}\n\n"
        f"## News co-mention context\n{gdelt or '(none available)'}\n\n"
        f"## Candidate companies ({len(candidates)})\n" + "\n\n".join(lines) + "\n\n"
        "Classify the issue once, then judge every candidate independently. "
        "Output only the JSON object, with exactly one verdict per candidate, keyed by ticker.")


# --------------------------------------------------------------------------
# 오프라인 회계
# --------------------------------------------------------------------------

def offline(issue_text, gdelt, candidates) -> dict:
    n = len(candidates)
    singles = [single_user_message(issue_text, gdelt, *c) for c in candidates]
    batch = batch_user_message(issue_text, gdelt, candidates)

    single_in = sum(len(SINGLE_PROMPT) + len(m) for m in singles)
    batch_in = len(BATCH_PROMPT) + len(batch)
    shared = len(SINGLE_PROMPT) + len(issue_text) + len(gdelt or "(none available)")

    print(f"후보 {n}개")
    print(f"  공유분(시스템+이슈+GDELT)   {shared:>9,} 자")
    print(f"  단건: 호출 {n}회, 입력 합계  {single_in:>9,} 자  "
          f"(공유분 {shared * n:,} 자가 {n}번 나간다)")
    print(f"  배치: 호출 1회, 입력 합계    {batch_in:>9,} 자")
    print(f"  입력 절감                   {1 - batch_in / single_in:>9.1%}")
    print()
    print("  ⚠️ 출력은 줄지 않는다 — 후보마다 판정 6필드가 그대로 필요하다.")
    print(f"     단건 상한 {SINGLE_MAX_TOKENS} × {n} vs 배치 상한 "
          f"{BATCH_MAX_TOKENS_PER_CANDIDATE * n} (후보당 {BATCH_MAX_TOKENS_PER_CANDIDATE})")
    print("  ⚠️ 문자 수지 토큰이 아니다. 실제 토큰은 --live 의 API usage 로만 나온다.")
    return {"n": n, "single_chars": single_in, "batch_chars": batch_in, "shared_chars": shared}


# --------------------------------------------------------------------------
# 실호출
# --------------------------------------------------------------------------

def call(key: str, system: str, user: str, max_tokens: int,
         model: str = LLM_MODEL) -> tuple[str, dict]:
    """GATEWAY 경유 호출. 모델 이름으로 공급자를 고른다.

    ⚠️ 두 공급자의 API 모양이 다르다 — Anthropic 은 `system` 이 별도 필드이고 사용량이
    `usage.input_tokens`, OpenAI 는 system 이 메시지 배열의 첫 항목이고 사용량이
    `usage.prompt_tokens` 다. 한쪽 모양으로 다른 쪽을 부르면 조용히 빈 응답이 온다.
    """
    if model.startswith("claude"):
        r = requests.post(
            f"{GATEWAY}/api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=300)
        r.raise_for_status()
        body = r.json()
        text = "".join(b.get("text", "") for b in body.get("content", []))
        u = body.get("usage", {})
        return text, {"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0)}

    r = requests.post(
        f"{GATEWAY}/api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": model,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}],
              # 🔴 nano 계열은 추론 토큰을 먼저 먹는다. 출력 상한을 넉넉히 주지 않으면
              #    본문이 비어 온다 — 에러가 아니라 빈 문자열이라 조용히 실패한다.
              "max_completion_tokens": max_tokens * 4},
        timeout=300)
    r.raise_for_status()
    body = r.json()
    text = body["choices"][0]["message"].get("content") or ""
    u = body.get("usage", {})
    return text, {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}


def parse(raw: str):
    """```json 울타리를 걷어내고 파싱. 실패하면 None 과 원문 앞부분을 돌려준다."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in s else s
    try:
        return json.loads(s), None
    except json.JSONDecodeError as e:
        return None, f"{e} / 원문 앞 200자: {raw[:200]!r}"


def live(key, issue_text, gdelt, candidates, expected,
         model=LLM_MODEL, batch_only=False, reverse=False, args_case="case") -> None:
    """🔴 단계마다 크레딧을 읽어 단건/배치를 **분리해서** 잰다. 합계만 보면 어느 쪽이
    얼마인지 못 나누고, 그러면 '배치가 몇 배 싼가'를 추정으로 말하게 된다."""
    if reverse:
        candidates = list(reversed(candidates))
    n = len(candidates)
    print(f"\n모델 {model} / 후보 순서 {'역순' if reverse else '정순'}")
    before = credits(key)

    single_verdicts, s_in, s_out = {}, 0, 0
    print(f"\n{'=' * 70}\n" + ("단건 건너뜀 (--batch-only)" if batch_only else f"단건 {n}회"))
    for name, ticker, summary in ([] if batch_only else candidates):
        raw, usage = call(key, SINGLE_PROMPT,
                          single_user_message(issue_text, gdelt, name, ticker, summary),
                          SINGLE_MAX_TOKENS, model)
        s_in += usage["in"]
        s_out += usage["out"]
        obj, err = parse(raw)
        if obj is None:
            print(f"  {ticker:<6} ⚠️ 파싱 실패 {err}")
            continue
        single_verdicts[ticker] = obj
        print(f"  {ticker:<6} verified={str(obj.get('verified')):<5} "
              f"class={obj.get('issue_class')} path={obj.get('match_path')}")
        time.sleep(0.3)

    mid = credits(key)
    single_cost = mid - before
    print(f"\n{'=' * 70}\n배치 1회")
    raw, usage = call(key, BATCH_PROMPT, batch_user_message(issue_text, gdelt, candidates),
                      BATCH_MAX_TOKENS_PER_CANDIDATE * n, model)
    b_in, b_out = usage["in"], usage["out"]
    obj, err = parse(raw)
    batch_verdicts = {}
    if obj is None:
        print(f"  🔴 파싱 실패 — 후보 {n}개를 통째로 잃는다: {err}")
    else:
        # 🔴 티커로 매칭한다. 순서로 붙이면 누락 시 조용히 밀려 오배정된다.
        for v in obj.get("verdicts", []):
            t = v.get("ticker")
            if t in {c[1] for c in candidates}:
                batch_verdicts[t] = dict(v, issue_class=obj.get("issue_class"))
        missing = [c[1] for c in candidates if c[1] not in batch_verdicts]
        extra = [v.get("ticker") for v in obj.get("verdicts", [])
                 if v.get("ticker") not in {c[1] for c in candidates}]
        print(f"  issue_class={obj.get('issue_class')} / 판정 {len(batch_verdicts)}/{n}")
        # ⚠️ 판정을 여기서 찍는다. --batch-only 에서는 아래 대조표가 "비교 불가"만 내므로
        #    이 줄이 없으면 크레딧을 쓰고도 결과를 못 본다 (2026-09-21 실제로 그랬다).
        for _, t, _ in candidates:
            v = batch_verdicts.get(t)
            if v:
                print(f"    {t:<6} verified={str(v.get('verified')):<5} "
                      f"path={v.get('match_path')} 기대={expected.get(t, '-')}")
        if missing:
            print(f"  ⚠️ 누락 티커 {missing}")
        if extra:
            print(f"  ⚠️ 입력에 없는 티커 {extra}")

    print(f"\n{'=' * 70}\n대조")
    agree = 0
    compared = 0
    for _, ticker, _ in candidates:
        s, b = single_verdicts.get(ticker), batch_verdicts.get(ticker)
        if s is None or b is None:
            print(f"  {ticker:<6} 비교 불가 (단건={s is not None} 배치={b is not None})")
            continue
        compared += 1
        same = s.get("verified") == b.get("verified")
        agree += same
        mark = "일치" if same else "🔴 불일치"
        print(f"  {ticker:<6} {mark}  단건={s.get('verified')} 배치={b.get('verified')} "
              f"기대={expected.get(ticker, '-')}")
    if compared:
        print(f"  verified 일치율 {agree}/{compared} = {agree / compared:.1%}")

    # single 쪽 issue_class 가 후보마다 갈리는지 — 배치의 부수 이득 여부
    classes = {v.get("issue_class") for v in single_verdicts.values()}
    print(f"\n  단건 issue_class 종류 {classes} "
          f"{'(후보마다 갈렸다)' if len(classes) > 1 else ''}")

    # 🔴 판정을 파일로 남긴다. 실호출은 크레딧을 쓰므로 결과를 화면에만 두면
    #    스크롤에서 사라졌을 때 다시 돈을 내야 한다.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = f"{model}-{'rev' if reverse else 'fwd'}{'-batchonly' if batch_only else ''}"
    io.open(os.path.join(HERE, f"result-{args_case}-{tag}-{stamp}.json"), "w",
            encoding="utf-8").write(json.dumps(
        {"model": model, "reverse": reverse, "batch_only": batch_only,
         "expected": expected, "single": single_verdicts, "batch": batch_verdicts,
         "tokens": {"single_in": s_in, "single_out": s_out, "batch_in": b_in,
                    "batch_out": b_out}}, ensure_ascii=False, indent=1))

    after = credits(key)
    batch_cost = after - mid
    print(f"\n{'=' * 70}\n토큰·크레딧")
    if not batch_only:
        print(f"  단건  입력 {s_in:>7,}  출력 {s_out:>6,}  합 {s_in + s_out:>7,}  "
              f"크레딧 {single_cost:>7.0f} (회당 {single_cost / max(n, 1):.1f})")
    print(f"  배치  입력 {b_in:>7,}  출력 {b_out:>6,}  합 {b_in + b_out:>7,}  "
          f"크레딧 {batch_cost:>7.0f}")
    if not batch_only and s_in + s_out:
        print(f"  토큰 절감 {1 - (b_in + b_out) / (s_in + s_out):.1%}")
    if not batch_only and batch_cost > 0:
        print(f"  크레딧 절감 {1 - batch_cost / max(single_cost, 1e-9):.1%} "
              f"— 배치가 {single_cost / batch_cost:.1f}배 싸다")
    print(f"  누적 {after:.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="Milton", choices=sorted(CASES))
    ap.add_argument("--limit", type=int, default=0, help="후보 수 상한 (0=전부)")
    ap.add_argument("--gdelt", default="", help="GDELT 기관명 컨텍스트 (비우면 none)")
    ap.add_argument("--live", action="store_true", help="🔴 GATEWAY 실호출 — 크레딧을 쓴다")
    ap.add_argument("--model", default=LLM_MODEL,
                    help="claude-* 면 Anthropic, 그 외면 OpenAI 경로 (예: gpt-5.4-nano)")
    ap.add_argument("--batch-only", action="store_true", help="단건 생략 — 배치만")
    ap.add_argument("--reverse", action="store_true", help="후보 순서 뒤집기 (순서 민감도)")
    args = ap.parse_args()

    case = CASES[args.case]
    issue_text = build_issue_text(case["seed_articles"])
    tickers = [t for t, _, _ in case["answers"]] + list(case["noise"])
    if args.limit:
        tickers = tickers[:args.limit]

    expected = {t: c for t, c, _ in case["answers"]}
    for t in case["noise"]:
        expected.setdefault(t, "reject")

    candidates = []
    for t in tickers:
        name, summary = candidate_info(t)
        if not summary:
            print(f"⚠️ {t}: 사업 설명 없음 — 제외")
            continue
        candidates.append((name, t, summary))

    print(f"사례 {args.case} / 이슈 텍스트 {len(issue_text)}자 / 후보 {len(candidates)}개\n")
    offline(issue_text, args.gdelt, candidates)

    if args.live:
        live(load_key(), issue_text, args.gdelt, candidates, expected,
             args.model, args.batch_only, args.reverse, args.case)
    else:
        print("\n(--live 를 주면 실호출로 판정·토큰·크레딧까지 잰다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
