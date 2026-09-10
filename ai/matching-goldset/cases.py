"""WP-39 — 이슈-종목 매칭 정답셋.

사례마다: 위키 씨드 문서, 사건 기간(GDELT 조회용), GDELT 검색어, 후보 종목
(정답 + 노이즈), 정답 사유와 근거. 정답 사유는 실제 기사로 확인한 것만 적는다
(추측 금지 — CLAUDE.md "표본·명세만 보고 단정하지 말 것").

answers 안의 각 항목은 (ticker, 확신도, 사유) 튜플이다.
확신도: "strong" = 사건의 직접 원인·직접 피해 당사자. "weak" = 언론에 크게
같이 언급되지만 인과가 간접적이거나(2차 효과) 사건의 주 원인은 아님 — GDELT
단독으로만 잡힐 가능성이 높은 부류라 등급(§6.3) 검증에 특히 중요하다.
"""

CASES = {
    # ── 사건형 (event) ──────────────────────────────────────────────
    "Milton": {
        "type": "event",
        "seed_articles": ["Hurricane Milton"],
        "event_date": "2024-10-10",
        "event_window": ("2024-10-05", "2024-10-20"),
        "gdelt_query": "hurricane milton",
        "answers": [
            ("NEE", "strong", "NextEra Energy(FPL 모회사) — 플로리다 최대 전력사, 정전 복구 비용·설비투자 (GDELT lift 10.5, 명세 §11 2026-09-07 실측)"),
            ("DUK", "strong", "Duke Energy — 플로리다 팬핸들·인접 서비스권 정전 복구 (GDELT lift 8.4)"),
            ("GNRC", "strong", "Generac — 정전으로 비상 발전기 수요 급증 (GDELT lift 9.3)"),
            ("HD", "weak", "Home Depot — 태풍 대비·복구 자재 수요 (2차 효과, 명세 §6.3 임베딩 Top-20 포함)"),
            ("LOW", "weak", "Lowe's — Home Depot와 동일 논리"),
            ("LEN", "weak", "Lennar — 플로리다 본사 주택건설사, 피해 주택 재건 수요 노출"),
            ("ETN", "weak", "Eaton — 전력망 설비 제조, 복구 수요"),
            ("UAL", "strong", "United Airlines — 플로리다 공항 폐쇄로 대량 결항 (GDELT lift 6.3)"),
            ("DIS", "weak", "Disney — 올랜도 테마파크 임시 폐쇄 (GDELT lift 4.7)"),
        ],
        "noise": ["MNST", "INTC", "NKE", "KO", "PG", "CRM"],
        "notes": "issue-text-poc(-42) 잠정 답안을 그대로 승계 + GDELT lift 실측(§11)으로 확신도 부여. 다만 클러스터 자체는 사람이 고른 문서 묶음이라 실제 클러스터링(-51) 출력으로 재확인은 -48에서.",
    },
    "CrowdStrike": {
        "type": "event",
        "seed_articles": ["2024 CrowdStrike-related IT outages"],
        "event_date": "2024-07-19",
        "event_window": ("2024-07-19", "2024-08-02"),
        "gdelt_query": "crowdstrike outage",
        "answers": [
            ("CRWD", "strong", "CrowdStrike — 결함 업데이트를 배포한 당사자. 발표 당일 주가 20%+ 급락($343→$273, Reuters/Investing.com 2024-07-19)"),
            ("DAL", "strong", "Delta Air Lines — 5일간 약 7,000편 결항, 승객 140만 명 영향, 손실 5.5억 달러(연료 절감 5천만 달러 상쇄 후). CrowdStrike 상대 소송 진행 중 (Newsweek·Reuters, 2024-10)"),
            ("MSFT", "weak", "Microsoft — 원인은 CrowdStrike Falcon이지 Windows 결함이 아니지만, 보도가 온통 'Windows 대란'으로 다뤄져 GDELT 동시출현이 매우 높을 것으로 예상되는 간접 사례 — 등급(§6.3) 검증의 핵심 테스트 케이스"),
        ],
        "noise": ["AAL", "UAL", "PANW", "FTNT", "KO", "PG", "NKE", "SBUX", "INTC", "CRM", "T"],
        "notes": "Delta가 유독 크게 다뤄진 건 델타 자체 IT 복구 체계 문제가 겹쳤기 때문(보도 다수). 다른 항공사(AAL·UAL)는 더 빨리 복구해 노이즈로 분류. PANW·FTNT는 '보안업계 전반 재평가' 논조로 같이 언급될 수 있으나 이 사건의 직접 원인·피해 당사자가 아니라 정답에서 제외 — 등급3(임베딩 단독) 오탐 후보로 관찰용.",
    },
    "BankingCrisis2023": {
        "type": "event",
        "seed_articles": ["2023 United States banking crisis"],
        "event_date": "2023-03-10",
        "event_window": ("2023-03-09", "2023-03-31"),
        "gdelt_query": "silicon valley bank collapse",
        "answers": [
            ("WAL", "strong", "Western Alliance — 3/13 최대 65% 장중 급락, 예금 이탈 우려 최대 피해주 (Fortune·Yahoo Finance 2023-03-13)"),
            ("ZION", "strong", "Zions Bancorp — 3/13 개장 직후 20%+ 급락, 5월에도 9~12%대 추가 급락 (Fortune)"),
            ("CMA", "strong", "Comerica — 프리마켓 7% 하락 후 5월 추가 급락 9~12%대 (Fortune)"),
            ("KEY", "strong", "KeyCorp — 5월 추가 국면에서 9~12%대 급락 (Forbes)"),
            ("SCHW", "strong", "Charles Schwab — 프리마켓 20% 하락, 대차대조표 미실현 채권 손실 우려로 은행 아니지만 같이 휩쓸림 (Fortune)"),
            ("FITB", "strong", "Fifth Third Bancorp — 2023-05 국면에서 Zions·Comerica·KeyCorp과 함께 9~12%대 급락한 지역은행 바스켓의 일원 (Fortune). ~~Comerica(CMA)~~ → 2026-02-02 Comerica가 Fifth Third에 흡수합병·상장폐지되어(TipRanks·투자은행 8-K, 2026-09-10 확인) 이 정답셋에서는 CMA 대신 FITB로 표기 — 2023년 당시엔 별개 법인이었지만 지금은 이게 유일하게 조회 가능한 실체"),
        ],
        "noise": ["JPM", "BAC", "GS", "NKE", "KO", "PG", "INTC", "CRM"],
        "notes": "PacWest(PACW)·First Republic(FRC)은 실측 당시 최대 피해주였으나 이후 각각 Banc of California 합병·JPMorgan 인수로 상장폐지되어(2023) 2026-09 현재 원 티커로 조회 불가 — 정답셋에서 제외. JPM·BAC·GS는 대형 은행이라 오히려 예금 이탈의 반사 수혜(GDELT 보도량은 많지만 방향이 반대)라서 노이즈로 분류 — 등급 판정에서 '같이 언급되지만 정반대 인과'인 경우를 보는 표본.",
    },

    # ── 기업형 (company) ─────────────────────────────────────────────
    "IBM_profit_warning": {
        "type": "company",
        "seed_articles": ["IBM"],
        "event_date": "2026-07-14",
        "event_window": ("2026-07-14", "2026-07-28"),
        "gdelt_query": "IBM profit warning",
        "answers": [
            ("IBM", "strong", "당사자 본인. 2분기 예비실적 경고로 하루 만에 25.21% 폭락 — 1987-10-19(-23.7%) 이후 역대 최대 낙폭. 매출 172억 달러(예상 179억 미달), 소프트웨어·인프라 부문 부진, 메인프레임 매출 -7% (CNBC·Bloomberg·CNN 2026-07-14)"),
            ("MU", "weak", "Micron — CEO 서한이 부진 사유로 '고객이 메모리칩 등 하드웨어 구매로 지출을 이동'을 지목 (Motley Fool 2026-07-14). 이슈 문서에는 없는 인과 추론이라 임베딩으로 못 잡고 LLM 근거 경로 검증이 필요한 사례"),
        ],
        "noise": ["DELL", "HPE", "ORCL", "MSFT", "KO", "NKE"],
        "notes": "IBM은 문서=종목명이 같아 임베딩·GDELT 둘 다 자명하게 1위가 나와야 하는 대조군(같은 개체 매칭이 되는지 확인). 진짜 값은 MU처럼 이슈 본문에 안 나오는 인과 후보를 몇 등급에서 건지는지에 있다.",
    },
    "PayPal_buyout_collapse": {
        "type": "company",
        "seed_articles": ["PayPal"],
        "event_date": "2026-08-28",
        "event_window": ("2026-08-28", "2026-09-05"),
        "gdelt_query": "paypal stripe advent buyout",
        "answers": [
            ("PYPL", "strong", "당사자 본인. Advent International·Stripe 컨소시엄의 약 530억 달러($60.50/주) 인수 제안이 가격 이견으로 무산, 주가 하루 만에 12.71% 급락($53.66 마감) (Bloomberg·Yahoo Finance 2026-08-28)"),
        ],
        "noise": ["XYZ", "V", "MA", "ADYEY", "KO", "NKE"],
        "notes": "인수 상대측(Stripe·Advent International)은 비상장이라 대응 티커가 없다 — 정답이 1개뿐인 최소 사례. ~~SQ~~ → Block(구 Square)은 2025-01 티커를 XYZ로 변경(2026-09-10 확인) — 옛 이름으로 조회하면 yfinance가 404. V·MA·ADYEY·XYZ는 결제업계 동종이지만 이 사건과 직접 관련 없어 노이즈.",
    },
}
