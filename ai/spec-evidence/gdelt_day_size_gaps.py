"""§11 "GDELT GKG 하루" · "GDELT 결손" 행 재현. HEAD 요청만으로 하루치 GKG 96개
슬롯 총 용량을 재고(gdelt/catalog.py 의 15분 격자), 알려진 결손 구간을 확인한다.

실행: 네트워크만 필요.
    py -3 gdelt_day_size_gaps.py [YYYYMMDD]   # 기본: 2024-10-10
"""

import sys
import time

import requests

sys.path.insert(0, "../../data-pipeline")
from gdelt.catalog import iter_slots, parse_ts, format_ts, floor_to_slot  # noqa: E402

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"

# 명세 §11 "GDELT 결손" — 2025-06-13~07-04 전부 404 (2026-09-07 확인).
KNOWN_GAP = ("20250613000000", "20250704234500")


def head_size(ts: str) -> int | None:
    url = f"http://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip"
    for attempt in range(3):
        try:
            r = requests.head(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return int(r.headers.get("Content-Length", 0))
        except requests.RequestException as e:
            print(f"    {ts} 실패({attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    return None


def day_size(day_ymd: str) -> None:
    from datetime import datetime, timedelta, timezone
    start = datetime.strptime(day_ymd, "%Y%m%d").replace(tzinfo=timezone.utc)
    slots = list(iter_slots(start, start + timedelta(hours=23, minutes=45)))
    print(f"{day_ymd} — 슬롯 {len(slots)}개(96개가 정상) HEAD 확인 중...")
    total = 0
    missing = 0
    for ts in slots:
        size = head_size(ts)
        if size is None:
            missing += 1
        else:
            total += size
        time.sleep(0.1)
    print(f"  존재 {len(slots) - missing}/{len(slots)} · 결손 {missing} · "
          f"합계 {total:,} bytes ({total / 1_000_000:.0f} MB)")


def check_gap() -> None:
    """구간 안 5곳(시작·1/4·중간·3/4·끝, 15분 격자로 내림)만 표본 확인 —
    96슬롯 x 21일을 전부 때리지 않는다."""
    start, end = KNOWN_GAP
    s, e = parse_ts(start), parse_ts(end)
    fractions = [0, 0.25, 0.5, 0.75, 1.0]
    check_points = [format_ts(floor_to_slot(s + (e - s) * f)) for f in fractions]
    print(f"\n알려진 결손 구간 표본 확인 {start}~{end}:")
    for ts in check_points:
        size = head_size(ts)
        print(f"  {ts}: {'404(결손, 예상대로)' if size is None else f'{size} bytes — 값이 바뀌었다(GDELT가 백필했나) — 재확인 필요'}")


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "20241010"
    day_size(day)
    check_gap()


if __name__ == "__main__":
    main()
