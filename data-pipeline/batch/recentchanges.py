"""RecentChanges 로 편집 원본을 시간 단위로 받아 둔다 (WP-164).

`mediawiki_history` 2026-09 스냅샷이 공개되기 전 구간을 메우는 **보험 수집**이다.
근거와 대안 비교는 `docs/validation/2026-09-21-edit-source-gap.md`.

🔴 **기한이 있다.** RecentChanges 보존은 30일 슬라이딩이라 받지 않고 두면 뒤에서부터
사라진다. 반면 덤프는 그보다 **늦게** 나온다 — 두 창이 어긋나는 며칠은 어느 쪽으로도
복구할 수 없다.

이 모듈은 **raw 를 그대로 남기는 것까지만** 한다. candidate title 생성은 하지 않는다.
다시 받을 시한이 없는 데이터라 가공 실수와 수집을 분리한다.

설계 결정과 이유
    - **시간당 파일 하나.** 중간에 죽어도 그 시간만 다시 받는다. 조회수도 시간
      버킷이라 하류 조인 단위와 같다.
    - **`.part` 로 쓰고 끝나면 rename.** 죽은 순간의 반쪽 파일이 완료로 보이지 않는다.
      ⚠️ 덤프 429 함정(169 B HTML 이 gzip 인 척)과 같은 실패 형태를 여기서 미리 막는다.
    - **`rcid` 로 시간 안에서 중복 제거.** continue 재시도가 겹칠 수 있다.
    - **끝 경계는 배타.** `rcend` 포함 여부가 API 쪽 계약이라 믿지 않고 직접 `< end`
      로 자른다. 안 그러면 이음매에서 한 행이 두 시간에 들어간다.
    - **429 지수 백오프.** WP-163 실측에서 실제로 맞았다(`Retry-After` 43~46).
      9,400호출짜리 수집을 재시도 없이 돌리면 중간에 죽는다.

수집 계약 (덤프 경로와 같은 축)
    enwiki · namespace 0 · `edit|new` · 봇 판정은 **RC 의 `bot` 플래그**.
    🔴 `list=allrevisions` 로 갈아타지 않는다 — 보존 제한이 없는 대신 봇 플래그가
    없고, 이 구간 편집의 45.8% 가 봇이라 1차 관문(명세 §3.2)이 무력해진다.

⚠️ **RC 는 현재 제목을 준다.** 덤프의 `page_title_historical`(사건 당시 제목)과
다르다. 덤프 대비 2.1% 차이가 거의 전부 대량 문서 이동에서 나온다 — manifest 에
`title_basis` 로 남긴다.

실행::

    python -m batch.recentchanges --start 2026-09-01T02:00:00Z \\
        --end 2026-09-18T00:00:00Z --out data/recentchanges-164

    python -m batch.recentchanges --verify --out data/recentchanges-164
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "WikiPulse/0.1 (프로젝트 WikiPulse; contact via GitLab)"
TS = "%Y-%m-%dT%H:%M:%SZ"

#: 한 번에 요청할 행 수. 익명 호출 상한이 500 이다.
PAGE_LIMIT = "max"

#: 호출 사이 기본 간격. `--delay` 로 조정한다.
#:
#: 🔴 **간격을 벌려도 429 는 안 줄어든다** (2026-09-21 실측). 0.5초에서 2시간·39호출에
#: 429 3번, 2.0초에서 3시간·40호출에 4번이다. 간격이 4배인데 빈도가 그대로라는 건
#: 제한이 **간격이 아니라 총량 예산**이라는 뜻이다 — 익명 호출은 분당 약 11회로
#: 수렴한다. 그래서 delay 를 더 벌리는 것은 대책이 아니고, 백오프가 실질 페이서다.
#: 실측 처리량은 시간당 파일 하나에 74~94초라 406시간이면 8~11시간이 든다.
#:
#: ⚠️ 호출 수를 줄이는 길도 없다. `rclimit` 상한이 익명 500 이고 5000 은
#: `apihighlimits` (봇·관리자) 권한이 있어야 한다. 병렬화도 같은 IP 예산을 나눠 쓸
#: 뿐이라 총 시간이 줄지 않는다.
CALL_DELAY_SEC = 2.0

#: 429 재시도 횟수. 초과하면 그 시간은 실패로 남기고 다음 시간으로 넘어간다 —
#: 전체를 세우지 않는다. 실패한 시간은 `--verify` 가 잡아내고 다시 돌리면 된다.
RETRY_ON_429 = 6

#: 수집할 필드. `flags` 가 봇 판정을 준다 — 빼면 이 수집물이 쓸모없어진다.
RC_PROPS = "timestamp|user|userid|flags|title|ids|sizes"


class HourFailed(RuntimeError):
    """그 시간만 실패. 전체 수집은 계속한다."""


def _fetch(params: dict) -> tuple[dict, int]:
    """(응답, 429 를 맞은 횟수). 429 는 지수 백오프로 재시도한다."""
    delay, throttled = 2.0, 0
    query = urllib.parse.urlencode(dict(params, format="json", formatversion="2"))
    for attempt in range(RETRY_ON_429 + 1):
        request = urllib.request.Request(f"{API}?{query}",
                                         headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response), throttled
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == RETRY_ON_429:
                raise HourFailed(f"HTTP {exc.code}") from exc
            wait = float(exc.headers.get("Retry-After") or delay)
            throttled += 1
            print(f"    429 — {wait:.0f}초 대기 ({attempt + 1}/{RETRY_ON_429})",
                  file=sys.stderr, flush=True)
            time.sleep(wait)
            delay *= 2
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == RETRY_ON_429:
                raise HourFailed(str(exc)) from exc
            time.sleep(delay)
            delay *= 2
    raise HourFailed("unreachable")


def fetch_hour(start: datetime, delay: float = CALL_DELAY_SEC) -> tuple[list[dict], int, int]:
    """한 시간치 전부. (행, 호출 수, 429 횟수). 끝 경계는 배타로 자른다."""
    end = start + timedelta(hours=1)
    base = {
        "action": "query", "list": "recentchanges", "rcnamespace": "0",
        "rcdir": "newer", "rcstart": start.strftime(TS), "rcend": end.strftime(TS),
        "rclimit": PAGE_LIMIT, "rcprop": RC_PROPS, "rctype": "edit|new",
    }
    by_id: dict[int, dict] = {}
    cont, calls, throttled = {}, 0, 0
    while True:
        data, hit = _fetch(dict(base, **cont))
        calls += 1
        throttled += hit
        if "error" in data:
            raise HourFailed(str(data["error"]))
        for row in data["query"]["recentchanges"]:
            if row["timestamp"] >= end.strftime(TS):
                continue                      # 끝 경계 배타 — 위 docstring 참고
            by_id[row["rcid"]] = row          # continue 재시도 중복 제거
        if "continue" not in data:
            break
        cont = data["continue"]
        time.sleep(delay)
    rows = sorted(by_id.values(), key=lambda r: (r["timestamp"], r["rcid"]))
    return rows, calls, throttled


def hour_path(root: Path, start: datetime) -> Path:
    return root / "enwiki" / f"{start:%Y/%m/%d}" / f"{start:%H}.ndjson.gz"


def write_hour(path: Path, rows: list[dict]) -> int:
    """`.part` 에 쓰고 끝나면 rename. 반쪽 파일이 완료로 보이지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    with gzip.open(part, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    part.replace(path)
    return path.stat().st_size


def hours(start: datetime, end: datetime):
    current = start
    while current < end:
        yield current
        current += timedelta(hours=1)


def collect(start: datetime, end: datetime, root: Path,
            delay: float = CALL_DELAY_SEC) -> int:
    manifest = root / "manifest.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    planned = list(hours(start, end))
    done = skipped = failed = 0
    rows_total = calls_total = throttled_total = 0
    began = time.time()

    print(f"구간 {start:%Y-%m-%d %H:%M}Z ~ {end:%Y-%m-%d %H:%M}Z, {len(planned)}시간",
          flush=True)
    for index, hour in enumerate(planned, 1):
        path = hour_path(root, hour)
        if path.exists():
            skipped += 1
            continue
        try:
            rows, calls, throttled = fetch_hour(hour, delay)
        except HourFailed as exc:
            failed += 1
            print(f"  [{index}/{len(planned)}] {hour:%Y-%m-%d %H}Z 실패: {exc}",
                  file=sys.stderr, flush=True)
            _append(manifest, {"hour": hour.strftime(TS), "status": "failed",
                               "error": str(exc),
                               "fetched_at": datetime.now(timezone.utc).strftime(TS)})
            continue
        size = write_hour(path, rows)
        done += 1
        rows_total += len(rows)
        calls_total += calls
        throttled_total += throttled
        _append(manifest, {
            "hour": hour.strftime(TS), "status": "ok", "rows": len(rows),
            "calls": calls, "throttled": throttled, "bytes": size,
            "first_ts": rows[0]["timestamp"] if rows else None,
            "last_ts": rows[-1]["timestamp"] if rows else None,
            "bots": sum(1 for r in rows if r.get("bot")),
            "title_basis": "current",   # ⚠️ 덤프는 historical 이다
            "fetched_at": datetime.now(timezone.utc).strftime(TS),
        })
        if index % 24 == 0 or index == len(planned):
            rate = done / max(time.time() - began, 1) * 3600
            print(f"  [{index}/{len(planned)}] {hour:%Y-%m-%d %H}Z "
                  f"누적 {rows_total:,}행 · {calls_total}호출 · 429 {throttled_total} "
                  f"({rate:.0f}시간/시간)", flush=True)
        time.sleep(delay)

    print(f"\n완료 {done} · 건너뜀 {skipped} · 실패 {failed} / {len(planned)}시간")
    print(f"행 {rows_total:,} · 호출 {calls_total:,} · 429 {throttled_total} "
          f"· {time.time() - began:.0f}초")
    if failed:
        print("⚠️ 실패한 시간이 있다. 같은 명령을 다시 돌리면 그 시간만 받는다.")
    return 1 if failed else 0


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def verify(start: datetime, end: datetime, root: Path) -> int:
    """구멍을 찾는다. **파일 존재만 보지 않는다** — 빈 시간과 결손은 다르다."""
    missing, empty, rows_total, bots_total = [], [], 0, 0
    for hour in hours(start, end):
        path = hour_path(root, hour)
        if not path.exists():
            missing.append(hour)
            continue
        count = bots = 0
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                count += 1
                bots += bool(row.get("bot"))
        rows_total += count
        bots_total += bots
        if count == 0:
            empty.append(hour)

    planned = len(list(hours(start, end)))
    print(f"시간 {planned - len(missing)}/{planned} · 행 {rows_total:,} "
          f"· 봇 {bots_total:,} ({bots_total / rows_total:.1%})" if rows_total
          else f"시간 {planned - len(missing)}/{planned} · 행 0")
    leftover = list(root.rglob("*.part"))
    if leftover:
        print(f"⚠️ `.part` {len(leftover)}개 — 중단된 흔적이다: {leftover[:3]}")
    if empty:
        print(f"⚠️ 0행 시간 {len(empty)}개: {[f'{h:%m-%d %H}' for h in empty[:5]]} "
              f"— enwiki ns0 가 시간당 1만 행대라 0 은 정상이 아니다")
    if missing:
        print(f"🔴 결손 {len(missing)}시간: {[f'{h:%m-%d %H}' for h in missing[:10]]}")
        return 1
    print("결손 없음")
    return 1 if (empty or leftover) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-09-01T02:00:00Z")
    parser.add_argument("--end", default="2026-09-18T00:00:00Z")
    parser.add_argument("--out", default="data/recentchanges-164")
    parser.add_argument("--delay", type=float, default=CALL_DELAY_SEC,
                        help="호출 사이 간격(초). 낮추면 429 가 늘어 되레 느리다")
    parser.add_argument("--verify", action="store_true",
                        help="받지 않고 결손만 확인한다")
    args = parser.parse_args()

    start = datetime.strptime(args.start, TS).replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, TS).replace(tzinfo=timezone.utc)
    if start >= end:
        parser.error("--start 가 --end 보다 앞서야 한다")
    root = Path(args.out)
    if args.verify:
        return verify(start, end, root)
    return collect(start, end, root, args.delay)


if __name__ == "__main__":
    sys.exit(main())
