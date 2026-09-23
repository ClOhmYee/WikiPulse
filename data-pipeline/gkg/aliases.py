"""기관명 → ticker 별칭 테이블 (WP-47).

match.py 의 정확 일치가 실패한 기관명 중 실제로는 종목 마스터의 자회사·구
사명·브랜드명인 것들을 여기서 보강한다. 정확 일치가 우선이다 — 여기 있는
키가 종목 마스터 정규화 이름과 겹쳐도 stock 마스터 쪽이 이긴다(driver.py가
`setdefault` 로 병합).

## 갱신 방법

새 별칭은 실측(운영 중 미매칭 상위 기관 로그, 또는 ai/gkg-alias-poc/measure.py
재실행)으로 확인한 뒤에만 추가한다 — 추측으로 채우지 않는다. 근거는
ai/gkg-alias-poc/RESULT.md.

## 짧은 이름 처리 규칙

`BLOCKLIST_KEYS` 에 있는 정규화 이름은 ALIASES 에 등록돼 있어도 붙이지 않는다.
공용 명사·지명·통화기호 등과 겹쳐 오탐 위험이 원 매칭 이득보다 큰 것들이다.
오탐(엉뚱한 회사가 화면에 뜬다)이 누락(RAG 컨텍스트 하나 빠짐)보다 비싸다 —
안 붙어도 원래 법인명(예: "Delta Air Lines")으로는 정확 일치가 그대로 된다.

블록리스트는 ALIASES 와 비대칭이다 — ALIASES 는 실측(아래 실측 표)으로 확인한
것만 넣지만, 블록리스트는 "붙이지 않는 게 항상 안전한 선택"이라 관찰 전에도
알려진 위험 단어를 미리 넣어둔다.
"""

from __future__ import annotations

#: 별칭 텍스트(원문 그대로, normalize_name 이 알아서 정규화) -> ticker.
#: 전부 Hurricane Milton 실측(ai/gkg-alias-poc/RESULT.md, 2026-09-16)에서 실제
#: GKG 기관명으로 관찰되고, 대응 ticker 가 종목 마스터에 있는 것만 확인 후 등록.
ALIASES: dict[str, str] = {
    # 전력사 자회사 — GKG 는 지역 자회사 이름으로 나오고 마스터는 지주사 이름이다.
    "Florida Power & Light Company": "NEE",
    "Florida Power Light Company": "NEE",
    "Florida Power Light": "NEE",
    "Duke Energy Florida": "DUK",
    # 소비자 브랜드 — 법인명(Inc/Corp 등)과 달라 legal-suffix 제거만으로는 안 붙는다.
    "Disney": "DIS",
    "Walt Disney World Resort": "DIS",
    "Facebook": "META",
    "Instagram": "META",
    "Google": "GOOGL",
    "Verizon": "VZ",
    # 미디어 자회사 — 브랜드명이 지주회사와 다르다.
    "Warner Bros": "WBD",
    "Discovery Company": "WBD",
    "Cable News Network Inc": "WBD",
    "CNN": "WBD",
    "New York Post": "NWSA",
    # 2026-09-23 시연일 키워드 술어 실측(WP-221) — 이슈 기사에서 lift 상위로 관찰.
    #   The Odyssey(07-17): universal pictures 140.1 (이슈 32/코퍼스 56) · universal studios 129.8
    #   IMAX(07-17):        universal pictures 127.4 (이슈 4/코퍼스 75)
    #   SummerSlam(08-02):  espn 34.7 (이슈 27/코퍼스 351)
    # 배급사·방송 브랜드라 법인명으로는 안 붙는다. 모회사가 마스터에 있다.
    "Universal Pictures": "CMCSA",   # NBCUniversal → Comcast
    "Universal Studios": "CMCSA",
    "ESPN": "DIS",                   # Disney 소유
}

#: 단일 토큰 등 오탐 위험이 큰 정규화 키. ALIASES에 있어도 여기 있으면 등록하지 않는다.
BLOCKLIST_KEYS: set[str] = {
    "meta",     # 흔한 영단어("메타", 게임 용어)와 겹침. 원래 법인명은 "Meta Platforms".
    "apple",    # 과일과 겹침. 원래 법인명 "Apple Inc"는 정확 일치로 이미 붙는다.
    "delta",    # 그리스 문자·강 하구·감염병 변이명과 겹침. 원 법인명 "Delta Air Lines"는 안전.
    "target",   # "목표"라는 일반 명사와 겹침. 원 법인명 "Target Corporation"은 안전.
    "block",    # 일반 명사("차단"·"블록")와 겹침. 원 법인명 "Block Inc"는 안전.
    "dodge",    # Milton 실측에서 관찰 — "폭풍을 피하다"라는 동사로 훨씬 흔히 쓰인다
                # (이슈 5/코퍼스 12, 문맥상 GDELT NER 오탐 가능성 높음). Stellantis 브랜드지만 등록 안 함.
    "mcdonald", # Milton 실측에서 관찰 — 성씨와 겹친다("McDonald's"는 아포스트로피가
                # GKG 정규화에서 빠져 "mcdonald"가 된다). lift<1(무관)이라 근거도 약함.
}
