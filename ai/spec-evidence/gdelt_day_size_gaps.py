"""§11 "GDELT GKG 하루" · "GDELT 결손" 행 재현. HEAD 요청만으로 하루치 GKG 96개
슬롯 총 용량을 재고(gdelt/catalog.py 의 15분 격자), 알려진 결손 구간을 확인한다.

실행: 네트워크만 필요.
    py -3 gdelt_day_size_gaps.py [YYYYMMDD]   # 기본: 2024-10-10
"""

import sys
import time
from datetime import timedelta

import requests

sys.path.insert(0, "../../data-pipeline")
from gdelt.catalog import iter_slots, parse_ts, format_ts, floor_to_slot  # noqa: E402

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"

# 명세 §11 "GDELT 결손". 처음 기록(2026-09-07)은 2025-06-13~07-04였다.
# 2026-09-16 이분 탐색(check_gap 아래)으로 경계를 15분 정밀도까지 좁혔다 — 실제
# 결손은 2025-06-14 18:00 ~ 2025-07-02 02:00 UTC 뿐이다. 아래 상수는 처음 기록
# 그대로 둔다 — check_gap() 의 목적 자체가 "기록된 경계가 아직 맞는지 주기적으로
# 재확인"이라, 여기를 새 값으로 바꾸면 다음 재확인 때 비교 기준이 사라진다.
KNOWN_GAP = ("20250613000000", "20250704234500")
#: 2026-09-16 이분 탐색으로 확인한 실제 경계 (아래 결과와 비교용).
CONFIRMED_GAP = ("20250614180000", "20250702020000")


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


def _find_start_boundary(exists_ts: str, missing_ts: str) -> tuple[str, str]:
    """`exists_ts`(더 이른 시각, 존재 확인됨) ~ `missing_ts`(더 늦은 시각, 404
    확인됨) 사이에서 결손이 시작되는 슬롯을 찾는다. exists_ts < missing_ts 여야 한다.

    반환: (결손 시작 직전 마지막 존재 슬롯, 결손 시작 첫 슬롯). 15분 격자라
    최대 log2(구간/15분)회 HEAD 호출로 끝난다.
    """
    lo, hi = parse_ts(exists_ts), parse_ts(missing_ts)  # lo=존재, hi=결손
    while (hi - lo) > timedelta(minutes=15):
        mid = floor_to_slot(lo + (hi - lo) / 2)
        if mid in (lo, hi):
            break
        if head_size(format_ts(mid)) is not None:
            lo = mid  # 존재 — 경계를 뒤로 민다
        else:
            hi = mid  # 결손 — 경계를 앞으로 당긴다
    return format_ts(lo), format_ts(hi)


def _find_end_boundary(missing_ts: str, exists_ts: str) -> tuple[str, str]:
    """`missing_ts`(더 이른 시각, 404 확인됨) ~ `exists_ts`(더 늦은 시각, 존재
    확인됨) 사이에서 결손이 끝나는 슬롯을 찾는다. missing_ts < exists_ts 여야 한다.

    반환: (결손 마지막 슬롯, 결손 끝난 뒤 첫 존재 슬롯).
    """
    lo, hi = parse_ts(missing_ts), parse_ts(exists_ts)  # lo=결손, hi=존재
    while (hi - lo) > timedelta(minutes=15):
        mid = floor_to_slot(lo + (hi - lo) / 2)
        if mid in (lo, hi):
            break
        if head_size(format_ts(mid)) is None:
            lo = mid  # 결손 — 경계를 뒤로 민다
        else:
            hi = mid  # 존재 — 경계를 앞으로 당긴다
    return format_ts(lo), format_ts(hi)


def check_gap() -> None:
    """기록된 결손 구간의 **정확한 경계**를 이분 탐색으로 다시 찾는다(15분 정밀도).

    5곳만 표본 찍던 이전 방식은 "구간 안이 아직 결손인가"만 봤지 "경계가 어디로
    옮겨갔는가"는 못 봤다 — 2026-09-16 실측에서 정각 경계 두 곳이 이미 존재로
    바뀌어 있던 걸 5점 표본으로는 못 잡을 뻔했다.
    """
    known_start, known_end = KNOWN_GAP
    print(f"\n기록된 결손 구간 {known_start}~{known_end} — 경계 이분 탐색 중...")

    start_still_missing = head_size(known_start) is None
    end_still_missing = head_size(known_end) is None
    if start_still_missing and end_still_missing:
        print("  기록된 경계 그대로 결손 — 처음 기록(2026-09-07) 이후 안 좁혀짐.")
        return

    # 기록된 양끝 중 존재로 바뀐 쪽이 있다 — 안쪽 지점(내부는 여전히 결손이라고
    # 가정)에서 시작해 양쪽 경계를 각각 찾는다.
    s, e = parse_ts(known_start), parse_ts(known_end)
    mid = format_ts(floor_to_slot(s + (e - s) / 2))
    if head_size(mid) is not None:
        print("  기록된 구간 전체가 지금은 존재한다 — 결손이 완전히 해소됐을 수 있다. 수동 재확인 필요.")
        return

    _, first_missing = _find_start_boundary(known_start, mid)
    last_missing, _ = _find_end_boundary(mid, known_end)
    print(f"  실제 결손: {first_missing} ~ {last_missing}")
    if (first_missing, last_missing) == CONFIRMED_GAP:
        print("  2026-09-16 확인값(CONFIRMED_GAP)과 일치.")
    else:
        print(f"  ⚠️ 2026-09-16 확인값({CONFIRMED_GAP})과 다르다 — 경계가 또 움직였다. "
              "명세 §11 갱신 필요.")


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "20241010"
    day_size(day)
    check_gap()


if __name__ == "__main__":
    main()
