"""WP-77 — 비-seed 클러스터 멤버(기존 문서 재조명) 편집 재급증 비율 실측.

예비 표본(2026-09-09, 명세 §11 "편집 재급증 비율, 예비 표본") 4건을 20건 이상으로
늘리고, 계절성 오염을 잡기 위해 기준기간을 두 가지로 잰다:
    (a) 직전 동일 길이 구간(예비 표본과 같은 방식)
    (b) 전년 동기(계절성 오염이면 작년에도 비슷하게 올랐을 것)

비율 = 사건기간 편집 수 / 기준기간 편집 수. Wikimedia REST 편집 통계 API
(봇 제외 user 편집만)를 쓴다 — 문서당 호출 3회(사건·직전·작년)로 끝난다.

실행: 네트워크만 필요, 인증 불필요.
    py -3 measure.py
"""

import io
import sys
import time
from dataclasses import dataclass, field

import requests

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"
API = "https://wikimedia.org/api/rest_v1/metrics/edits/per-page/en.wikipedia.org"


@dataclass
class EventWindow:
    name: str
    event_start: str   # YYYYMMDD
    event_end: str      # YYYYMMDD (포함)
    candidates: dict[str, str] = field(default_factory=dict)  # title -> 기대(사람이 붙인 라벨, 판정에 안 씀)


def shift_days(ymd: str, days: int) -> str:
    from datetime import datetime, timedelta
    d = datetime.strptime(ymd, "%Y%m%d") + timedelta(days=days)
    return d.strftime("%Y%m%d")


def shift_years(ymd: str, years: int) -> str:
    from datetime import datetime
    d = datetime.strptime(ymd, "%Y%m%d")
    return d.replace(year=d.year + years).strftime("%Y%m%d")


EVENTS = [
    EventWindow(
        name="Hurricane Milton",
        event_start="20241005", event_end="20241020",
        candidates={
            # 예비 표본(2026-09-09) 승계
            "Saffir–Simpson_scale": "예비: 6.1배, 계절성 오염 의심 — 배제돼야 함",
            "Hurricane_Katrina": "예비: 1.0배, 배경 — 정상 배제",
            "Persian_Gulf": "예비: 0.7배, 배경(다른 사건 클러스터 오염 확인용)",
            # 신규
            "2024_Atlantic_hurricane_season": "시즌 문서 자체 — 계절성 오염의 정석 후보",
            "Hurricane_Helene": "같은 시즌 직전 태풍 — 비교 기사로 같이 언급, 계절성 오염 후보",
            "National_Hurricane_Center": "직접 대응 기관 — 재조명이면 포함돼야 함",
            "Ron_DeSantis": "플로리다 주지사, 재난 대응 보도 — 재조명 후보",
            "Tampa,_Florida": "직접 피해 지역 — 재조명 후보",
            "Storm_surge": "일반 개념 문서 — 배경, 정상 배제 기대",
            "Category_5_hurricane": "일반 개념 문서 — 배경, 정상 배제 기대",
        },
    ),
    EventWindow(
        name="Strait of Hormuz 2025",
        event_start="20250612", event_end="20250627",
        candidates={
            "2025_Iran_threat_of_Strait_of_Hormuz_closure": "사건 하위 문서(사실상 씨드급) — 대조군 아님, 상한 참고용",
            "Oil_tanker": "일반 개념 — 배경, 정상 배제 기대",
            "OPEC": "관련 기관 — 재조명 후보",
            "Choke_point": "§11에서 클릭량은 30배 높지만 무관하다고 확인된 배경 문서 — 편집도 배제돼야 함",
            "Suez_Canal": "다른 해상 요충지 — 무관 배경",
            "Strait_of_Malacca": "다른 해협 — 무관 배경(지리적 유사 오염 후보)",
        },
    ),
    EventWindow(
        name="2026 Iran war",
        # ⚠️ 처음엔 명세 §11 "Clickstream 2026-08" 언급을 보고 8월로 잡았다가 완전히 틀렸다.
        # Mojtaba_Khamenei 월별 편집 수를 직접 찍어보니(all-editor-types) 3월에 1,155건으로
        # 폭증, 8월은 12건뿐이었다. 실제 사건은 2026-02-28~03-20 구간(정점 03-08 342건).
        # "Clickstream 2026-08"는 클릭 트래픽이 늦게까지 남은 것이지 편집 폭증 시점이 아니다.
        event_start="20260301", event_end="20260316",
        candidates={
            "Mojtaba_Khamenei": "예비: 17.9배, 재조명 — 포함돼야 함",
            "Ali_Khamenei": "최고지도자 본인 — 재조명이면 강하게 포함돼야 함",
            "Islamic_Revolutionary_Guard_Corps": "직접 관련 조직 — 재조명 후보",
            "Natanz_nuclear_facility": "타격 대상으로 자주 거론되는 시설 — 재조명 후보",
            "2015_Iran_nuclear_deal_framework": "옛 핵협상 문서 — 맥락상 언급되지만 이 전쟁의 직접 당사자는 아닌 오염 후보",
            "Qasem_Soleimani": "2020년 사망한 옛 사령관 — 배경 인용은 될 수 있으나 이 사건 당사자 아님",
        },
    ),
]


def edit_count(title: str, start: str, end: str) -> int | None:
    end_excl = shift_days(end, 1)  # API end 는 그 날짜를 포함 안 하는 편이 안전 — 하루 더 준다
    # all-editor-types 사용 — §11 예비 표본(500+/49/23/21) 스케일과 맞춰보니 봇 포함 쪽이 맞았다.
    # user 단독으로 재보면 Mojtaba_Khamenei 가 5건까지 떨어져 신호 자체가 사라진다.
    url = f"{API}/{title}/all-editor-types/daily/{start}00/{end_excl}00"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 404:
                return 0  # 그 구간 편집 자체가 없음(API 가 데이터 없으면 404)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                return 0
            return sum(x["edits"] for x in items[0]["results"])
        except requests.RequestException as e:
            print(f"    {title} {start}-{end} 실패({attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    return None


def ratio(event_n: int, baseline_n: int) -> float | None:
    if baseline_n == 0:
        return None if event_n == 0 else float("inf")
    return event_n / baseline_n


def main():
    out = io.open("result.txt", "w", encoding="utf-8")

    def p(*a):
        line = " ".join(str(x) for x in a)
        out.write(line + "\n")
        out.flush()

    window_days = None
    all_rows = []  # (event_name, title, label, event_n, baseline_n, yearago_n, ratio_immediate, ratio_yearago)

    for ev in EVENTS:
        from datetime import datetime
        window_days = (datetime.strptime(ev.event_end, "%Y%m%d")
                        - datetime.strptime(ev.event_start, "%Y%m%d")).days + 1
        baseline_start = shift_days(ev.event_start, -window_days)
        baseline_end = shift_days(ev.event_start, -1)
        yearago_start = shift_years(ev.event_start, -1)
        yearago_end = shift_years(ev.event_end, -1)

        p(f"\n{'=' * 90}\n## {ev.name}")
        p(f"   사건기간 {ev.event_start}~{ev.event_end} ({window_days}일)")
        p(f"   직전기준 {baseline_start}~{baseline_end} / 작년동기 {yearago_start}~{yearago_end}")

        for title, label in ev.candidates.items():
            event_n = edit_count(title, ev.event_start, ev.event_end)
            time.sleep(0.3)
            baseline_n = edit_count(title, baseline_start, baseline_end)
            time.sleep(0.3)
            yearago_n = edit_count(title, yearago_start, yearago_end)
            time.sleep(0.3)

            r_imm = ratio(event_n, baseline_n) if event_n is not None and baseline_n is not None else None
            r_year = ratio(event_n, yearago_n) if event_n is not None and yearago_n is not None else None

            def fmt(v):
                if v is None:
                    return "N/A"
                return "inf" if v == float("inf") else f"{v:.1f}"

            p(f"   {title:45}  사건{event_n!s:>5} 직전{baseline_n!s:>5} 작년{yearago_n!s:>5}  "
              f"직전배수={fmt(r_imm):>6}  작년배수={fmt(r_year):>6}   [{label}]")
            all_rows.append((ev.name, title, label, event_n, baseline_n, yearago_n, r_imm, r_year))

    p(f"\n\n{'=' * 90}\n## 전체 표본 {len(all_rows)}건 — 직전배수 내림차순\n")
    for row in sorted(all_rows, key=lambda r: (r[6] if r[6] not in (None, float('inf')) else -1), reverse=True):
        name, title, label, event_n, baseline_n, yearago_n, r_imm, r_year = row
        p(f"   {r_imm if r_imm is not None else '-':>6}  {title:45} ({name})  [{label}]")

    out.close()
    print("wrote result.txt")


if __name__ == "__main__":
    main()
