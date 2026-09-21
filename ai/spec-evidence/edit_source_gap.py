"""2026-09-01~09-17 편집 소스 공백의 대안 경로 실측 (WP-163).

`mediawiki_history` 월 덤프는 스냅샷 다음 달 초에 나오고 **마지막 달 파일이 잘려
있다.** 그래서 MVP 정본 historical 구간(2026-07-17~09-17) 중 뒤쪽이 편집 소스 없이
남는다. 조회수 raw 는 이미 EC2 에 있으므로 없는 것은 편집 쪽뿐이다.

이 스크립트가 재는 것은 네 가지다.

1. `--probe dump`      덤프가 실제로 어디까지 덮는가 (잘린 마지막 달 파일의 최대 시각)
2. `--probe rc-window` RecentChanges 가 과거로 얼마나 남아 있는가 (이분 탐색)
3. `--probe compare`   겹치는 구간에서 덤프 대비 API 의 candidate title 일치율
4. `--probe cadence`   덤프 공개 주기

⚠️ **표본 몇 점으로 경계를 정하지 않는다.** `rc-window` 는 하루 단위로 좁힌 뒤 분
단위까지 이분 탐색한다. 끝점 근처를 성기게 찍으면 두 표본이 우연히 같은 쪽에 들어가
"안 바뀌었다"는 오탐이 난다 (CLAUDE.md 작업 원칙, GDELT 결손 구간 사례).

⚠️ **빈 응답을 "없다"로 읽지 않는다.** 보존 밖 시각을 요청해도 API 는 빈 배열이
아니라 **가장 오래된 행**을 돌려준다. 그래서 `retained()` 는 개수가 아니라 요청
시각과 실제 첫 행의 **시차**로 판정한다.

인증 불필요한 공개 엔드포인트만 쓴다. 개인 절대경로·키 없음.

실행 (저장소 루트에서)::

    python ai/spec-evidence/edit_source_gap.py --probe cadence
    python ai/spec-evidence/edit_source_gap.py --probe dump --dump <tail.tsv.bz2>
    python ai/spec-evidence/edit_source_gap.py --probe rc-window
    PYTHONPATH=data-pipeline python ai/spec-evidence/edit_source_gap.py \
        --probe compare --dump <tail.tsv.bz2>

`compare` 만 저장소 코드(`batch.schema`·`producer.normalize`)를 쓴다 — 덤프 쪽
정답을 손으로 다시 짜면 계약이 갈리기 때문이다.
"""

from __future__ import annotations

import argparse
import bz2
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

USER_AGENT = "WikiPulse/0.1 (프로젝트 WikiPulse; contact via GitLab)"
API = "https://en.wikipedia.org/w/api.php"
DUMPS = "https://dumps.wikimedia.org/other/mediawiki_history"

#: 덤프 타임스탬프. 예: 2026-09-01 02:29:37.0 (UTC, 초 정밀도)
DUMP_TS = "%Y-%m-%d %H:%M:%S.%f"
API_TS = "%Y-%m-%dT%H:%M:%SZ"

#: 보존 판정 여유. 요청 시각과 첫 행이 이만큼 안에 들어오면 보존으로 본다.
#: enwiki ns0 는 초당 수 건이라 10분이면 넉넉하고, 30일 경계와는 세 자릿수 차이다.
RETAINED_SLACK_SEC = 600


#: 429 재시도 횟수. ⚠️ 실측에서 실제로 맞았다 (2026-09-21) — 연속 호출을 몇 백 건
#: 넘기면 MediaWiki 가 429 를 낸다. 덤프의 429 함정(169 B HTML 이 gzip 인 척)과
#: 달리 여기서는 예외로 올라오지만, 재시도가 없으면 긴 수집이 중간에 죽는다.
RETRY_ON_429 = 5


def _get(url: str, timeout: int = 90):
    delay = 2.0
    for attempt in range(RETRY_ON_429 + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == RETRY_ON_429:
                raise
            wait = float(exc.headers.get("Retry-After") or delay)
            print(f"  429 — {wait:.0f}초 쉬고 재시도 ({attempt + 1}/{RETRY_ON_429})",
                  file=sys.stderr)
            time.sleep(wait)
            delay *= 2
    raise RuntimeError("unreachable")


def _api(params: dict) -> dict:
    body = _get(API + "?" + urllib.parse.urlencode(
        dict(params, format="json", formatversion="2")))
    data = json.loads(body)
    if "error" in data:
        raise SystemExit(f"API error: {data['error']}")
    return data


def _paged(params: dict, key: str, extract):
    """continue 를 따라가며 전부 모은다. 호출 수도 같이 돌려준다 — 비용 추정용."""
    rows, cont, calls = [], {}, 0
    while True:
        data = _api(dict(params, **cont))
        rows.extend(extract(data["query"][key]))
        calls += 1
        if "continue" not in data:
            return rows, calls
        cont = data["continue"]
        time.sleep(0.2)


# --------------------------------------------------------------------------
# 1. 덤프가 어디까지 덮는가
# --------------------------------------------------------------------------

def probe_dump(path: str) -> None:
    """잘린 마지막 달 파일의 revision 최대 시각과 마지막 분의 밀도를 잰다.

    마지막 분이 앞 분들보다 눈에 띄게 적으면 **분 중간에서 잘린 것**이다. 그 분을
    통째로 신뢰하면 편집 수가 조용히 모자란다.
    """
    per_minute: dict[str, int] = {}
    entities: dict[str, int] = {}
    latest = ""
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            row = line.rstrip("\n").split("\t")
            if len(row) < 5:
                continue
            entity, ts = row[2], row[4]
            entities[entity] = entities.get(entity, 0) + 1
            if entity != "revision" or not ts:
                continue
            latest = max(latest, ts)
            per_minute[ts[:16]] = per_minute.get(ts[:16], 0) + 1

    total = sum(per_minute.values())
    print(f"revision 행 {total} / event_entity 분포 {entities}")
    print(f"revision 최대 시각 {latest}")
    tail = sorted(per_minute)[-6:]
    print("마지막 분 분포:")
    for minute in tail:
        print(f"  {minute}  {per_minute[minute]}")
    if len(tail) >= 2:
        last, prev = per_minute[tail[-1]], per_minute[tail[-2]]
        if last < prev * 0.8:
            print(f"⚠️ 마지막 분이 직전의 {last / prev:.0%} — 분 중간에서 잘렸다. "
                  f"그 분은 버리고 직전 분까지를 덤프 경계로 쓴다.")


# --------------------------------------------------------------------------
# 2. RecentChanges 가 과거로 얼마나 남아 있는가
# --------------------------------------------------------------------------

def _first_rc_at(when: datetime) -> datetime | None:
    data = _api({
        "action": "query", "list": "recentchanges", "rcnamespace": "0",
        "rcdir": "newer", "rcstart": when.strftime(API_TS), "rclimit": "1",
        "rcprop": "timestamp", "rctype": "edit|new",
    })
    rows = data["query"]["recentchanges"]
    if not rows:
        return None
    return datetime.strptime(rows[0]["timestamp"], API_TS).replace(tzinfo=timezone.utc)


def _retained(when: datetime) -> bool:
    """보존 여부. 🔴 행 개수가 아니라 **시차**로 본다 — 위 docstring 참고."""
    got = _first_rc_at(when)
    return got is not None and (got - when).total_seconds() < RETAINED_SLACK_SEC


def probe_rc_window(now: datetime) -> None:
    lo, hi = 1, 400                       # lo=보존 쪽, hi=미보존 쪽 (일 단위)
    print("=== 일 단위 이분 탐색 ===")
    while hi - lo > 1:
        mid = (lo + hi) // 2
        when = now - timedelta(days=mid)
        ok = _retained(when)
        print(f"  -{mid:3d}일 {when:%Y-%m-%d}: {'보존' if ok else '미보존'}")
        lo, hi = (mid, hi) if ok else (lo, mid)
        time.sleep(0.4)

    print("=== 분 단위 이분 탐색 ===")
    keep, drop = now - timedelta(days=lo), now - timedelta(days=hi)
    while (keep - drop).total_seconds() > 60:
        mid = drop + (keep - drop) / 2
        ok = _retained(mid)
        print(f"  {mid:%Y-%m-%d %H:%M}Z: {'보존' if ok else '미보존'}")
        keep, drop = (mid, drop) if ok else (keep, mid)
        time.sleep(0.4)

    oldest = _first_rc_at(drop)
    span = now - oldest if oldest else None
    print(f"\n경계: {drop:%Y-%m-%d %H:%M}Z 미보존 / {keep:%Y-%m-%d %H:%M}Z 보존")
    print(f"가장 오래된 조회 가능 행 {oldest}")
    if span:
        print(f"보존 폭 약 {span.days}일 {span.seconds // 3600}시간 "
              f"— 슬라이딩 창이라 매일 하루치가 떨어져 나간다")


# --------------------------------------------------------------------------
# 3. 덤프 대비 일치율
# --------------------------------------------------------------------------

def _dump_titles(path: str, start: datetime, end: datetime):
    """덤프 쪽 정답. 저장소의 `normalize_dump` 계약을 그대로 쓴다."""
    from batch.schema import field
    from producer.normalize import canonical_title

    every, human = set(), set()
    rows = bots = 0
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            row = line.rstrip("\n").split("\t")
            if field(row, "event_entity") != "revision":
                continue
            if field(row, "page_namespace_historical") != "0":
                continue
            raw = field(row, "event_timestamp")
            if not raw:
                continue
            when = datetime.strptime(raw, DUMP_TS).replace(tzinfo=timezone.utc)
            if not start <= when < end:
                continue
            title = field(row, "page_title_historical")
            if not title:
                continue
            name = canonical_title(title)
            rows += 1
            every.add(name)
            if field(row, "event_user_is_bot_by_historical"):
                bots += 1
            else:
                human.add(name)
    return every, human, rows, bots


def _rc_titles(start: datetime, end: datetime):
    from producer.normalize import canonical_title

    rows, calls = _paged({
        "action": "query", "list": "recentchanges", "rcnamespace": "0",
        "rcdir": "newer", "rcstart": start.strftime(API_TS),
        "rcend": end.strftime(API_TS), "rclimit": "max",
        "rcprop": "timestamp|user|flags|title", "rctype": "edit|new",
    }, "recentchanges", lambda rs: rs)
    every = {canonical_title(r["title"]) for r in rows}
    human = {canonical_title(r["title"]) for r in rows if not r.get("bot")}
    return every, human, len(rows), sum(1 for r in rows if r.get("bot")), calls


def _arv_titles(start: datetime, end: datetime):
    """allrevisions. 보존 제한이 없는 대신 **봇 플래그가 없다.**"""
    from producer.normalize import canonical_title

    rows, calls = _paged({
        "action": "query", "list": "allrevisions", "arvnamespace": "0",
        "arvdir": "newer", "arvstart": start.strftime(API_TS),
        "arvend": end.strftime(API_TS), "arvlimit": "max",
        "arvprop": "timestamp|user",
    }, "allrevisions",
        lambda ps: [(p["title"], r) for p in ps for r in p["revisions"]])
    return {canonical_title(t) for t, _ in rows}, len(rows), calls


def _report(label: str, ref: set, got: set) -> None:
    both = ref & got
    print(f"\n--- {label} ---")
    print(f"  덤프 {len(ref)} / API {len(got)} / 교집합 {len(both)}")
    print(f"  재현율 {len(both) / len(ref):.4f}  (덤프 제목 중 API 가 가진 비율)")
    if got:
        print(f"  정밀도 {len(both) / len(got):.4f}  (API 제목 중 덤프에 있는 비율)")
    print(f"  자카드 {len(both) / len(ref | got):.4f}")
    print(f"  덤프에만 {len(ref - got)}: {sorted(ref - got)[:5]}")
    print(f"  API에만  {len(got - ref)}: {sorted(got - ref)[:5]}")


def probe_compare(path: str, start: datetime, end: datetime) -> None:
    d_all, d_human, d_rows, d_bots = _dump_titles(path, start, end)
    print(f"덤프: revision ns0 {d_rows}행 (봇 {d_bots}, {d_bots / d_rows:.1%}) "
          f"/ 제목 {len(d_all)} / 비봇 제목 {len(d_human)}")

    rc_all, rc_human, rc_rows, rc_bots, rc_calls = _rc_titles(start, end)
    print(f"RC:   {rc_rows}행 (봇 {rc_bots}, {rc_bots / rc_rows:.1%}) "
          f"/ 제목 {len(rc_all)} / 비봇 제목 {len(rc_human)} / 호출 {rc_calls}")

    arv_all, arv_rows, arv_calls = _arv_titles(start, end)
    print(f"ARV:  {arv_rows}행 / 제목 {len(arv_all)} / 호출 {arv_calls} (봇 플래그 없음)")

    _report("RC 비봇  vs 덤프 비봇", d_human, rc_human)
    _report("RC 전체  vs 덤프 전체", d_all, rc_all)
    _report("ARV 전체 vs 덤프 전체", d_all, arv_all)
    _report("ARV 전체 vs 덤프 비봇", d_human, arv_all)

    hours = (end - start).total_seconds() / 3600
    print(f"\n비용: RC {rc_calls / hours:.0f} 호출/시간 — 하루 {rc_calls / hours * 24:.0f}")


# --------------------------------------------------------------------------
# 4. 덤프 공개 주기
# --------------------------------------------------------------------------

def probe_cadence(wiki: str = "enwiki") -> None:
    index = _get(DUMPS + "/").decode("utf-8", "replace")
    snapshots = sorted(set(re.findall(r'href="(\d{4}-\d{2})/"', index)))
    print(f"스냅샷 {len(snapshots)}개, 최근 4개: {snapshots[-4:]}")

    for snapshot in snapshots[-2:]:
        listing = _get(f"{DUMPS}/{snapshot}/{wiki}/").decode("utf-8", "replace")
        files = re.findall(
            rf'href="{snapshot}\.{wiki}\.(\d{{4}}-\d{{2}})\.tsv\.bz2">[^<]*</a>\s+'
            r'(\S+ \S+)\s+(\d+)', listing)
        months = [f for f in files if f[0] >= snapshot[:4] + "-01"]
        print(f"\n[{snapshot}] 파일 {len(files)}개")
        for month, released, size in months[-3:]:
            print(f"  {month}  공개 {released}  {int(size):,} B")
        if len(months) >= 2:
            last, prev = int(months[-1][2]), int(months[-2][2])
            print(f"  ⚠️ 마지막 달이 직전의 {last / prev:.2%} — 잘린 파일이다")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True,
                        choices=["dump", "rc-window", "compare", "cadence"])
    parser.add_argument("--dump", help="잘린 마지막 달 tsv.bz2 경로")
    parser.add_argument("--start", default="2026-09-01T01:00:00Z")
    parser.add_argument("--end", default="2026-09-01T02:00:00Z")
    parser.add_argument("--now", help="rc-window 기준 시각 (기본 현재 UTC)")
    args = parser.parse_args()

    if args.probe == "cadence":
        probe_cadence()
    elif args.probe == "rc-window":
        now = (datetime.strptime(args.now, API_TS).replace(tzinfo=timezone.utc)
               if args.now else datetime.now(timezone.utc))
        probe_rc_window(now)
    else:
        if not args.dump:
            parser.error("--dump 이 필요하다")
        start = datetime.strptime(args.start, API_TS).replace(tzinfo=timezone.utc)
        end = datetime.strptime(args.end, API_TS).replace(tzinfo=timezone.utc)
        if args.probe == "dump":
            probe_dump(args.dump)
        else:
            probe_compare(args.dump, start, end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
