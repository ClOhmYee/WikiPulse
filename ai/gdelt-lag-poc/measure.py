"""WP-46 — GDELT 신호가 이슈 발생 후 언제부터 잡히는지 실측.

사건 3건의 발생 시각부터 15분 단위로 GKG 슬롯을 받아, 이슈 매칭 기사 수·
목표 기관 언급 수·lift 가 시간에 따라 어떻게 쌓이는지 본다. GDELT는 15분
파일 단위라 최소 15분 지연은 구조적이다 — 그 위에 "몇 슬롯을 더 기다려야
lift 가 쓸 만해지는가"를 잰다.

방법: gkg/parse.py 로 슬롯마다 Record 를 파싱해 (a) 이슈 술어 매칭 여부
(b) 목표 기관 언급 여부를 센다. 누적(발생 시각부터 현재 슬롯까지)으로
lift = (누적 이슈 매칭 기사 중 목표기관 언급 수 / 누적 이슈 매칭 기사 수)
     / (누적 전체 기사 중 목표기관 언급 수 / 누적 전체 기사 수)
를 슬롯마다 다시 계산해 값이 언제 안정되는지 본다. 4시간(16슬롯) 창 끝의
값을 "안정값"으로 보고, 그 값의 ±20% 안에 처음 들어온 시점을 "안정 도달"로
잡는다.

실행: 네트워크만 필요(무료 GDELT 엔드포인트), LLM_GATEWAY_KEY 불필요.
    py -3 measure.py
"""

import io
import sys
import time
import zipfile
from dataclasses import dataclass

import requests

sys.path.insert(0, "../../data-pipeline")
from gkg.parse import parse_text  # noqa: E402

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"
SLOTS_AFTER_ONSET = 17  # onset-15분 슬롯 1개 + onset+0~4h(16슬롯)
STABLE_TOLERANCE = 0.20  # 안정값의 ±20% 안에 처음 들어오면 "안정 도달"


@dataclass
class Event:
    name: str
    onset_utc: str  # 14자리 YYYYMMDDHHMMSS, 15분 격자에 내림
    predicate: str  # "theme:HURRICANE+florida" 또는 "org:crowdstrike"
    target_orgs: list[str]  # 이 사건에서 볼 목표 기관(원시 GKG 표기, 소문자)
    source_note: str  # 발생 시각 근거


EVENTS = [
    Event(
        name="Hurricane Milton",
        onset_utc="20241010003000",  # 2024-10-09 20:30 EDT 상륙 = 2024-10-10 00:30 UTC, 15분 격자 내림
        predicate="theme:HURRICANE+florida",
        target_orgs=["florida power light company", "florida power light", "duke energy",
                      "duke energy florida", "generac"],
        source_note="NHC 상륙 시각 공개 보도 기준 2024-10-09 20:30 EDT",
    ),
    Event(
        name="CrowdStrike outage",
        onset_utc="20240719040000",  # 결함 업데이트 배포 04:09 UTC(각사 사후보고서), 15분 격자로 내림
        predicate="org:crowdstrike",
        target_orgs=["crowdstrike", "delta air lines", "microsoft"],
        source_note="CrowdStrike/Microsoft 사후 보고서 공개 보도 기준 2024-07-19 04:09 UTC",
    ),
    Event(
        name="SVB collapse",
        onset_utc="20230310173000",  # 캘리포니아 금융보호혁신국 폐쇄 발표, 공개 보도 기준 근사치
        predicate="org:silicon valley bank",
        target_orgs=["silicon valley bank", "svb financial", "first republic",
                      "signature bank"],
        source_note="⚠️ 분 단위 근사 — 공개 보도가 시각을 오전 late PT 로만 특정, "
                     "여기서는 09:30am PT=17:30 UTC 로 잡음",
    ),
]


def gen_slots(onset: str, n: int):
    from datetime import datetime, timedelta, timezone
    start = datetime.strptime(onset, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return [(start + timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(n)]


def fetch_zip(ts: str) -> bytes | None:
    url = f"http://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print(f"  {ts} 실패({attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(3)
    return None


def records_from_zip(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if not names:
            return []
        text = zf.read(names[0]).decode("utf-8", "replace")
    return list(parse_text(text))


def matches_predicate(record, predicate: str) -> bool:
    kind, _, arg = predicate.partition(":")
    if kind == "org":
        return arg in record.orgs
    if kind == "theme":
        theme_term, _, location_term = arg.partition("+")
        theme_ok = any(theme_term in code for code in record.themes)
        loc_ok = any(location_term == loc or f" {location_term}" in loc or loc.startswith(location_term)
                     for loc in record.locations)
        return theme_ok and loc_ok
    raise ValueError(predicate)


def compute_lift(issue_hits, issue_total, corpus_hits, corpus_total) -> float | None:
    if issue_total == 0 or corpus_total == 0 or corpus_hits == 0:
        return None
    return (issue_hits / issue_total) / (corpus_hits / corpus_total)


def main():
    out = io.open("result.txt", "w", encoding="utf-8")

    def p(*a):
        line = " ".join(str(x) for x in a)
        out.write(line + "\n")
        out.flush()

    for event in EVENTS:
        p(f"\n{'=' * 78}\n## {event.name}  (predicate={event.predicate})")
        p(f"   발생 시각(UTC, 15분 격자): {event.onset_utc}  — {event.source_note}")
        slots = gen_slots(event.onset_utc, SLOTS_AFTER_ONSET)

        cum_corpus = 0
        cum_issue = 0
        cum_org = {o: 0 for o in event.target_orgs}
        cum_org_in_issue = {o: 0 for o in event.target_orgs}
        first_seen_min = {o: None for o in event.target_orgs}

        rows = []  # (offset_min, corpus_this, issue_this, cum_corpus, cum_issue, lift-by-org dict)
        for i, ts in enumerate(slots):
            offset_min = i * 15
            data = fetch_zip(ts)
            if data is None:
                p(f"   +{offset_min:>4}분 [{ts}] 결손(404)")
                rows.append((offset_min, 0, 0, cum_corpus, cum_issue, dict(cum_org)))
                continue
            records = records_from_zip(data)
            this_corpus = len(records)
            this_issue = 0
            for r in records:
                is_issue = matches_predicate(r, event.predicate)
                if is_issue:
                    this_issue += 1
                for o in event.target_orgs:
                    if o in r.orgs:
                        cum_org[o] += 1
                        if is_issue:
                            cum_org_in_issue[o] += 1
                        if first_seen_min[o] is None:
                            first_seen_min[o] = offset_min

            cum_corpus += this_corpus
            cum_issue += this_issue

            lifts = {
                o: compute_lift(cum_org_in_issue[o], cum_issue, cum_org[o], cum_corpus)
                for o in event.target_orgs
            }
            p(f"   +{offset_min:>4}분 [{ts}]  코퍼스 {this_corpus:>4}(누적{cum_corpus:>5})  "
              f"이슈매칭 {this_issue:>4}(누적{cum_issue:>5})  "
              + "  ".join(f"{o}:{('-' if lifts[o] is None else f'{lifts[o]:.2f}')}"
                          for o in event.target_orgs))
            rows.append((offset_min, this_corpus, this_issue, cum_corpus, cum_issue, lifts))
            time.sleep(1)  # GDELT 예의상 간격

        # 안정 도달 시점 — 마지막(최장 누적) lift 를 기준값으로, 그 ±20% 안에
        # 처음 들어온 시점을 찾는다. 목표 기관마다 따로 판정한다.
        p(f"\n   -- 안정 도달 판정(안정값=+{rows[-1][0]}분 시점 lift, 허용 ±{STABLE_TOLERANCE:.0%}) --")
        final_lifts = rows[-1][5]
        for o in event.target_orgs:
            stable = final_lifts[o]
            first_min = first_seen_min[o]
            if stable is None:
                p(f"   {o}: 4시간 안에 lift 계산 불가(언급 부족) — 최초 언급 {first_min}분")
                continue
            reached = None
            for offset_min, *_rest, lifts in rows:
                v = lifts[o]
                if v is not None and abs(v - stable) <= STABLE_TOLERANCE * max(stable, 1e-9):
                    reached = offset_min
                    break
            p(f"   {o}: 최초 언급 {first_min}분 후 / 안정값 {stable:.2f} / "
              f"안정 도달 {reached}분 후" + (f" (누적기사 {cum_issue if reached==rows[-1][0] else '-'})"
                                             if reached is not None else ""))

    out.close()
    print("wrote result.txt")


if __name__ == "__main__":
    main()
