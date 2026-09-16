"""WP-47 — 별칭 테이블 적용 전후 매칭 개선 실측.

실물 GDELT GKG(Hurricane Milton 2024-10-10, 90분 간격 16슬롯 — gkg/README.md §11과
같은 표본)를 직접 받아 기관 lift 를 내고, 종목 마스터(SEC+NASDAQ, 실시간 fetch)
정확 일치만 있을 때와 별칭 테이블(gdelt/../gkg/aliases.py)을 더했을 때 매칭
건수를 비교한다. DB·Spark 없이 순수 파이썬(gkg/lift.py·match.py가 이미 그렇게
설계돼 있다).

실행:
    py -3 measure.py
"""

import io
import sys
import time
import zipfile

import requests

sys.path.insert(0, "../../data-pipeline")

from gkg.lift import IssuePredicate, aggregate, rank  # noqa: E402
from gkg.match import build_ticker_index, match_ticker, merge_aliases  # noqa: E402
from gkg.parse import parse_text  # noqa: E402
from stock.universe import build_universe  # noqa: E402

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"


def gen_slots():
    """gkg/README.md §11과 같은 표본: 2024-10-10, 90분 간격 16슬롯."""
    ts = []
    for step in range(16):
        minutes = step * 90
        hh, mm = divmod(minutes, 60)
        if hh >= 24:
            break
        ts.append(f"20241010{hh:02d}{mm:02d}00")
    return ts


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
            print(f"  {ts} 실패({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(3)
    return None


def records_from_zip(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if not names:
            return []
        text = zf.read(names[0]).decode("utf-8", "replace")
    return list(parse_text(text))


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "result.txt"
    out = io.open(out_path, "w", encoding="utf-8")

    def p(*a):
        line = " ".join(str(x) for x in a)
        out.write(line + "\n")
        out.flush()

    slots = gen_slots()
    p(f"슬롯 {len(slots)}개 다운로드 중...")
    predicate = IssuePredicate(themes=("HURRICANE",), locations=("florida",))
    from gkg.lift import Aggregate
    agg = Aggregate()
    for ts in slots:
        data = fetch_zip(ts)
        if data is None:
            p(f"  {ts}: 결손(404)")
            continue
        records = records_from_zip(data)
        for record in records:
            agg.add(record, predicate.matches(record))
        agg.files += 1
    p(f"이슈 기사 {agg.n_issue:,} / 코퍼스 {agg.n_corpus:,}")

    lifts = rank(agg, min_issue_count=3)
    p(f"기관 {len(lifts)}건 (min_issue_count=3)")

    p("\n종목 마스터 받는 중 (SEC + NASDAQ Trader)...")
    universe = build_universe()
    base_index = build_ticker_index((s.ticker, s.name) for s in universe)
    p(f"종목 {len(universe)}개, 정규화 색인 {len(base_index)}개")

    from gkg.aliases import ALIASES, BLOCKLIST_KEYS

    alias_index = merge_aliases(base_index, ALIASES, BLOCKLIST_KEYS)

    before = [(l, match_ticker(l.org_name, base_index)) for l in lifts]
    after = [(l, match_ticker(l.org_name, alias_index)) for l in lifts]

    n_before = sum(1 for _, t in before if t)
    n_after = sum(1 for _, t in after if t)
    p(f"\n매칭: 별칭 전 {n_before}/{len(lifts)}  ->  별칭 후 {n_after}/{len(lifts)}")

    p(f"\n별칭 전 매칭된 것 ({n_before}건, 오탐 없는지 육안 확인용):")
    for l, t in before:
        if t:
            p(f"  {t:6}  {l.org_name}  (lift {l.lift:.2f}, 이슈 {l.issue_count}/코퍼스 {l.corpus_count})")

    newly_matched = [(l, t) for (l, t0), (_, t) in zip(before, after) if not t0 and t]
    p(f"\n별칭으로 새로 붙은 것 ({len(newly_matched)}건):")
    for l, t in newly_matched:
        p(f"  {t:6}  {l.org_name}  (lift {l.lift:.2f}, 이슈 {l.issue_count}/코퍼스 {l.corpus_count})")

    still_unmatched = [l for l, t in after if not t]
    p(f"\n여전히 미매칭 전체 ({len(still_unmatched)}건, lift 내림차순):")
    for l in still_unmatched:
        p(f"  {l.lift:7.2f}  {l.org_name}  (이슈 {l.issue_count}/코퍼스 {l.corpus_count})")

    p(f"\nBLOCKLIST_KEYS (등록 안 하는 정규화 키): {sorted(BLOCKLIST_KEYS)}")
    out.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
