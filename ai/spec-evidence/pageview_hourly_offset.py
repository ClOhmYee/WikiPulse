"""§11 "시간별 조회수 덤프" 행 재현 (WP-127).

두 가지를 잰다. 둘 다 파일명 시각을 윈도우 **끝**으로 읽는다는 전제를 검증한다.

    align  : 시간별 덤프 값 == 일별 `pageview_complete` 의 같은 시간 값인가.
             한 시간 밀려 읽으면 여기서 어긋난다. 기본 대상은 2025-06-12
             `Air India Flight 171`(사고 08:09 UTC, 문서 생성 08:58:02 UTC) —
             시간 프로파일이 3 -> 24,669 로 4자리 튀어서 한 칸만 밀려도 드러난다.
    delay  : 지금 시각 기준으로 어느 구간까지 공개됐는지 재서 공개 지연을 구한다.
             ⚠️ 윈도우 **끝** 기준이다. 시작 기준으로 재면 한 시간 짧게 나온다.

실행 (네트워크만 필요. 일별 덤프가 568 MB 라 align 은 몇 분 걸린다):
    py -3 pageview_hourly_offset.py delay
    py -3 pageview_hourly_offset.py align                      # 기본 대상
    py -3 pageview_hourly_offset.py align --date 2025-06-12 \
        --hours 8,9,10,22,23 --title "Air India Flight 171" --cache ./pv

⚠️ 일별은 `agent=user` 파일 하나만 본다. 시간별 덤프에는 agent 가 없어서
   (위키미디어가 감지한 봇은 upstream 에서 빠지지만 어느 agent 였는지는 안 준다)
   두 값이 정확히 같을 이유는 없다 — 여기서 보는 것은 **어느 시간 칸에 붙느냐**다.
   그래서 절대값이 아니라 "어느 칸에서 가장 가까운가"로 판정한다.

⚠️ 병렬로 받으면 dumps.wikimedia.org 가 **429** 를 준다(2026-09-21 실측 — 4개
   동시에서 2개가 429). 429 는 gzip 이 아니라 HTML 이라 파일은 만들어지고 크기만
   169 B 다. 그래서 직렬로 받고 크기·매직바이트를 확인한다.
"""

import argparse
import gzip
import sys
import time
import urllib.request
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "../../data-pipeline")

from batch.pageview import aggregate as aggregate_daily  # noqa: E402
from batch.pageview import project_for  # noqa: E402
from batch.pageview_hourly import aggregate as aggregate_hourly  # noqa: E402
from batch.pageview_hourly import filename_hour, ts_hour_from_filename  # noqa: E402

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"

HOURLY_BASE = "https://dumps.wikimedia.org/other/pageviews"
DAILY_BASE = "https://dumps.wikimedia.org/other/pageview_complete"

WIKI = "enwiki"

#: 기본 검증 대상. 프로파일이 4자리 튀는 문서라 한 칸만 밀려도 드러난다.
DEFAULT_DATE = "2025-06-12"
DEFAULT_TITLE = "Air India Flight 171"
DEFAULT_HOURS = (8, 9, 10, 22, 23)

#: gzip 매직바이트. 429 응답(HTML)을 파일 크기만으로 가려내지 않는다.
GZIP_MAGIC = b"\x1f\x8b"


def hourly_url(ts_hour: str) -> str:
    """윈도우 시작 → 그 구간을 담은 파일 URL. 파일명 시각은 윈도우 끝이다."""
    date, hour = filename_hour(ts_hour)
    return f"{HOURLY_BASE}/{date[:4]}/{date[:4]}-{date[4:6]}/pageviews-{date}-{hour}0000.gz"


def daily_url(date: str, agent: str = "user") -> str:
    ymd = date.replace("-", "")
    return f"{DAILY_BASE}/{date[:4]}/{date[:7]}/pageviews-{ymd}-{agent}.bz2"


def fetch(url: str, dest: Path) -> Path | None:
    """직렬 다운로드 + 캐시. 404 는 None(아직 안 나온 구간), 429 는 재시도."""
    if dest.exists() and dest.stat().st_size > 1024:
        return dest
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                dest.write_bytes(response.read())
            return dest
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"429 가 계속된다: {url}")


def hourly_views(path: Path, ts_hour: str, title: str) -> int:
    """한 시간 파일에서 한 문서의 조회수. 데스크톱+모바일은 aggregate 가 합친다."""
    # 앞 2바이트만 읽는다 — `read_bytes()[:2]` 는 55 MB 를 통째로 올려놓고 2바이트를 본다.
    with path.open("rb") as raw:
        magic = raw.read(2)
    if magic != GZIP_MAGIC:
        raise RuntimeError(f"gzip 이 아니다(429 HTML 인지 확인): {path}")
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        rows = list(aggregate_hourly(handle, WIKI, ts_hour, titles=frozenset({title})))
    return rows[0].views if rows else 0


def daily_profile(path: Path, date: str, title: str) -> dict[int, int]:
    """일별 `agent=user` 덤프에서 한 문서의 시간 프로파일 {hour: views}.

    🔴 **줄을 미리 거른 뒤 `aggregate` 에 넣는다.** `batch.pageview.aggregate` 는
       (title, hour) 를 dict 로 전부 누적하는데, 하루 덤프 전체를 그냥 흘리면 키가
       수천만 개라 메모리를 다 먹고 끝나지 않는다(2026-09-21 실측 — 25분 넘게 안
       끝나 죽였다). 모듈 독스트링이 "검증 슬라이스용"이라고 적어 둔 이유다.

    ⚠️ 전처리 비교는 `title.replace(" ", "_")` 정확 일치다. `canonical_title` 의
       연속 밑줄 축약까지는 안 본다 — 한 문서를 겨냥한 검증이라 충분하고, 50M 줄에
       함수를 부르면 이 스크립트가 몇 배 느려진다. 남은 판정은 aggregate 가 한다.
    """
    import bz2

    wanted = {title, title.replace(" ", "_")}

    def only_target(handle: Iterable[str]) -> Iterator[str]:
        for line in handle:
            parts = line.split(" ", 2)
            if len(parts) > 1 and parts[1] in wanted:
                yield line

    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        rows = aggregate_daily(only_target(handle), project_for(WIKI), WIKI, "user", date)
        return {
            int(row.ts_hour[11:13]): row.views
            for row in rows
            if row.title == title
        }


def run_align(date: str, hours: tuple[int, ...], title: str, cache: Path) -> int:
    cache.mkdir(parents=True, exist_ok=True)

    daily_path = fetch(daily_url(date), cache / f"daily-{date}-user.bz2")
    if daily_path is None:
        print(f"일별 덤프가 없다: {date}")
        return 1
    profile = daily_profile(daily_path, date, title)
    if not profile:
        print(f"일별 덤프에 {title!r} 가 없다 — 제목·날짜를 확인한다")
        return 1

    print(f"대상 : {title}  ({date}, enwiki ns0)")
    print("일별 `pageview_complete` agent=user 프로파일 (0 인 시간 생략)")
    print("   " + "  ".join(f"{h:02d}시={profile[h]}" for h in sorted(profile)[:8]))
    print()
    print(f"{'윈도우(UTC)':<22}{'파일':<30}{'시간별':>10}{'일별 같은 시간':>16}"
          f"{'일별 +1h':>12}  판정")

    verdict = 0
    for hour in hours:
        ts_hour = f"{date}T{hour:02d}:00:00"
        url = hourly_url(ts_hour)
        name = url.rsplit("/", 1)[-1]
        path = fetch(url, cache / f"h-{name}")
        if path is None:
            print(f"[{hour:02d}:00~{hour + 1:02d}:00)".ljust(22) + f"{name:<30}"
                  + "404 — 아직 안 나온 구간")
            continue
        # 파일명 -> 윈도우 시작 왕복이 맞는지도 같이 확인한다.
        assert ts_hour_from_filename(name) == ts_hour, (name, ts_hour)

        measured = hourly_views(path, ts_hour, title)
        same = profile.get(hour, 0)
        shifted = profile.get(hour + 1, 0)
        # 절대값이 아니라 어느 칸에 더 가까운지로 본다(agent 구성이 달라 값은 안 같다).
        ok = abs(measured - same) <= abs(measured - shifted)
        verdict |= 0 if ok else 1
        print(f"[{hour:02d}:00~{hour + 1:02d}:00)".ljust(22) + f"{name:<30}"
              + f"{measured:>10,}{same:>16,}{shifted:>12,}  "
              + ("일치" if ok else "⚠️ 한 시간 밀렸다"))

    print()
    print("판정 기준: 시간별 값이 일별의 **같은 시간** 칸에 더 가까워야 한다.")
    print("  '일별 +1h' 쪽에 가까우면 파일명을 윈도우 시작으로 잘못 읽은 것이다.")
    return verdict


def run_delay(probe_hours: int = 8) -> int:
    """지금부터 거슬러 올라가며 404 가 끝나는 지점을 찾아 공개 지연을 잰다."""
    now = datetime.now(timezone.utc)
    print(f"기준 시각 {now:%Y-%m-%dT%H:%M:%SZ}")
    print(f"{'윈도우(UTC)':<24}{'파일':<30}{'공개(Last-Modified)':<26}지연(윈도우 끝 기준)")

    for back in range(1, probe_hours + 1):
        end = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=back - 1)
        start = end - timedelta(hours=1)
        ts_hour = start.strftime("%Y-%m-%dT%H:00:00")
        url = hourly_url(ts_hour)
        name = url.rsplit("/", 1)[-1]
        request = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                published = response.headers.get("Last-Modified", "")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                print(f"{start:%Y-%m-%dT%H}:00~{end:%H}:00".ljust(24) + f"{name:<30}"
                      + "404 — 아직 안 나옴")
                continue
            raise
        stamp = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z").replace(
            tzinfo=timezone.utc
        )
        minutes = int((stamp - end).total_seconds() // 60)
        print(f"{start:%Y-%m-%dT%H}:00~{end:%H}:00".ljust(24) + f"{name:<30}"
              + f"{stamp:%Y-%m-%dT%H:%M:%SZ}".ljust(26) + f"+{minutes}분")

    print()
    print("⚠️ 지연은 윈도우 **끝** 기준이다. 시작 기준으로 읽으면 한 시간 짧게 나온다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    align = sub.add_parser("align", help="시간별 값 == 일별 같은 시간 값인지 대조")
    align.add_argument("--date", default=DEFAULT_DATE)
    align.add_argument("--title", default=DEFAULT_TITLE)
    align.add_argument("--hours", default=",".join(str(h) for h in DEFAULT_HOURS),
                       help="윈도우 **시작** 시각들(UTC), 쉼표 구분")
    align.add_argument("--cache", default="./pv", help="덤프 캐시 폴더")

    delay = sub.add_parser("delay", help="공개 지연 측정(HEAD 만)")
    delay.add_argument("--probe-hours", type=int, default=8)

    args = parser.parse_args()
    if args.mode == "align":
        hours = tuple(int(h) for h in args.hours.split(","))
        return run_align(args.date, hours, args.title, Path(args.cache))
    return run_delay(args.probe_hours)


if __name__ == "__main__":
    raise SystemExit(main())
