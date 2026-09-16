"""기관명 → 종목 마스터 ticker 매칭. 순수 파이썬.

GKG 기관명은 소문자·비정형("florida power light", "duke energy")이고 종목 마스터
이름은 정식 상호("Duke Energy Corporation")다. 정규화 후 **정확 일치**만 붙인다.

⚠️ 부분문자열 매칭은 안 한다 — News Corp·Meta 같은 오탐이 남는다(§10 Open Issues,
   CLAUDE.md). 자회사·별칭(FPL↔NextEra 등) 해소는 별칭 테이블(WP-47)이
   붙은 뒤 재조인한다. 지금은 못 맞추면 ticker=NULL 로 두고 그대로 저장한다 —
   NULL 기관명도 LLM 검증의 RAG 컨텍스트로 쓴다(스키마 주석).

정규화가 하는 일: 소문자화, 구두점 제거, 흔한 법인격 접미어 제거, 공백 접기.
양쪽(종목 이름·기관명)에 똑같이 적용해야 대칭이 맞는다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: 정규화에서 떼는 법인격 접미어(단어 경계). 순서 무관 — 반복 적용한다.
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "llc", "lp", "plc", "sa", "ag", "nv", "se", "spa",
    "holdings", "holding", "group", "groupe", "the",
}

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """상호를 비교 가능한 형태로. 빈 결과면 매칭 불가(빈 문자열 반환)."""
    text = _PUNCT_RE.sub(" ", name.lower())
    tokens = [t for t in _WS_RE.sub(" ", text).strip().split(" ") if t]
    # 접미어를 앞뒤에서 반복해 벗긴다 ("... co inc" 같은 겹침도 처리).
    changed = True
    while changed and tokens:
        changed = False
        if tokens[-1] in _LEGAL_SUFFIXES:
            tokens.pop()
            changed = True
        if tokens and tokens[0] in _LEGAL_SUFFIXES:
            tokens.pop(0)
            changed = True
    return " ".join(tokens)


def build_ticker_index(rows: Iterable[tuple[str, str]]) -> dict[str, str]:
    """(ticker, name) 목록 → 정규화 이름 → ticker.

    충돌(다른 티커가 같은 정규화 이름)이면 먼저 온 것을 남긴다 — 마스터를 티커
    순으로 넣으면 결정적이다. 정규화가 빈 문자열이 되는 이름은 색인하지 않는다.
    """
    index: dict[str, str] = {}
    for ticker, name in rows:
        key = normalize_name(name)
        if key and key not in index:
            index[key] = ticker
    return index


def match_ticker(org_name: str, index: dict[str, str]) -> str | None:
    """정규화 정확 일치로 ticker 를 찾는다. 없으면 None."""
    return index.get(normalize_name(org_name))


def merge_aliases(
    index: dict[str, str], aliases: dict[str, str], blocklist: set[str]
) -> dict[str, str]:
    """종목 마스터 색인에 별칭(WP-47, aliases.py)을 겹쳐 새 dict 로 반환.

    종목 마스터가 항상 이긴다(setdefault) — 별칭은 마스터가 못 잡은 자회사·구
    사명·브랜드명만 메운다. blocklist 에 있는 정규화 키는 aliases 에 있어도
    등록하지 않는다(짧은 이름 오탐 방지, aliases.py 참고).
    """
    merged = dict(index)
    for alias_text, ticker in aliases.items():
        key = normalize_name(alias_text)
        if key in blocklist:
            continue
        merged.setdefault(key, ticker)
    return merged
