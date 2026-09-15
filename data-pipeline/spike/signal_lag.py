"""편집 신호와 조회수 신호의 시차 측정 (WP-86).

명세 §3.2 2~3번은 **편집으로 1차 판정하고 조회수로 2차 확정**한다. 그런데 리플레이
회귀 검증(WP-61)에서 `Strait_of_Hormuz` 는 조회수가 6/12, 편집이 6/23 으로
**편집이 11일 늦었다**. 근거가 Hormuz·Milton 2건뿐이라 사건을 늘려 시차를 잰다.

무엇을 재나
    한 문서에 대해 두 신호가 각각 **처음 임계를 넘는 날**을 구하고 그 차를 낸다.

        lag_days = (편집 최초 탐지일) - (조회수 최초 탐지일)

    양수면 편집이 늦다(= 현재 순서가 불리한 사건), 음수면 편집이 빠르다.

임계는 건드리지 않는다
    🔴 `detector.py` 의 확정 임계(WP-38)를 그대로 불러 쓴다. 이 모듈은
    측정만 한다 — 값이 안 맞아도 여기서 조정하지 않는다(리플레이와 같은 규칙).

두 신호의 입도가 다르다 (⚠️ 해석에 반드시 필요)
    편집은 덤프라 **시간 단위**, 조회수는 AQS per-article API 라 **일 단위**다.
    시간별 문서 조회수는 `other/pageviews` 덤프뿐이고 봇 구분이 없다(spike/README).
    그래서 시차는 **일 단위로만** 비교한다 — 편집 탐지 시각도 날짜로 내린다.
    이 비대칭은 §11 Hormuz 행(조회수 일 단위·편집 시간 단위)과 같은 조건이라
    기존 수치와 그대로 비교된다.

⚠️ 편집 baseline 은 덤프 경계에서 잘린다
    덤프가 월 단위라 월초 사건은 28일 창을 못 채운다. 창이 얇으면 `detect()` 가
    신규 문서 경로(절대 편집수 10건)로 보내는데, 이건 z 경로보다 **무르다** —
    즉 편집 쪽에 유리하게 잰다. 그런데도 편집이 늦게 나오면 그 결론은 더 단단하다.
    조회수 baseline 은 API 라 월 경계가 없다(항상 28일 확보).

사용법
    python -m spike.signal_lag --edits ./out/enwiki/2025-06 \
        --title Strait_of_Hormuz --title Air_India_Flight_171 --event-date 2025-06-12

    조회수는 wikimedia.org AQS 를 부른다. 응답은 data/cache/pageviews 에 캐시해
    같은 문서를 다시 부르지 않는다(rate limit 대비 — WP-77 에서 실제로 걸렸다).

제목 형식
    밑줄·공백 아무 형태로나 준다 (WP-91). 편집 덤프 쪽은 `replay.aggregate` 가
    canonical 로 맞춰 비교하고, AQS 는 **두 형식 다 200 을 준다**(2026-09-15 실측).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .baseline_rows import BASELINE_WINDOW_DAYS
from .detector import MIN_VIEW_RATIO, VIEW_Z_THRESHOLD
from .ewma import DEFAULT_HALFLIFE_DAYS, Observation, ewma_mean_std
from .replay import aggregate, first_detection, read_edit_events, replay_title

from producer.normalize import canonical_title  # noqa: E402  (spike -> producer 는 기존 경로)

#: AQS per-article 일별 조회수. agent=user 로 봇·크롤러를 뺀다(편집 쪽 봇 제외와 짝).
AQS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/{project}/all-access/user/{title}/daily/{start}/{end}"
)

#: 위키미디어는 User-Agent 없는 요청을 막는다. 연락처를 넣는 게 그쪽 정책이다.
USER_AGENT = "WikiPulse/0.1 (WikiPulse; https://github.com/ClOhmYee/WikiPulse)"

#: 응답 캐시. 같은 문서를 두 번 부르지 않는다.
CACHE_DIR = Path("data/cache/pageviews")

#: 연속 호출 간 최소 간격(초). AQS 는 초당 100 요청까지 허용하지만 여유를 둔다.
REQUEST_INTERVAL_SEC = 0.2

_last_request_at = 0.0


@dataclass(frozen=True)
class ViewSignal:
    """조회수가 처음 임계를 넘은 날."""
    day: date
    views: int
    baseline_mean: float
    z: float | None
    ratio: float


@dataclass(frozen=True)
class EditSignal:
    """편집이 처음 임계를 넘은 시점. 비교는 날짜로만 한다."""
    window_start: str
    edit_count: int
    editor_count: int
    edit_z: float | None
    is_new_page: bool

    @property
    def day(self) -> date:
        return date.fromisoformat(self.window_start[:10])


@dataclass(frozen=True)
class LagResult:
    """한 문서의 두 신호 시차. §11 에 적는 값이 여기서 나온다."""
    title: str
    event_date: date | None
    view: ViewSignal | None
    edit: EditSignal | None

    @property
    def lag_days(self) -> int | None:
        """편집 탐지일 - 조회수 탐지일. 양수면 편집이 늦다."""
        if self.view is None or self.edit is None:
            return None
        return (self.edit.day - self.view.day).days


def fetch_daily_views(
    title: str,
    start: date,
    end: date,
    *,
    project: str = "en.wikipedia",
    cache_dir: Path = CACHE_DIR,
) -> dict[date, int]:
    """AQS 일별 조회수를 {날짜: 조회수} 로. 없는 날은 키가 없다(0 과 구분).

    조회수가 0 인 날과 데이터가 없는 날은 다르다 — API 는 후자를 아예 안 준다.
    0 으로 채우면 baseline 이 눌려 z 가 부풀므로 채우지 않는다.
    """
    global _last_request_at

    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = urllib.parse.quote(title, safe="")
    cache_file = cache_dir / f"{project}_{safe}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    if cache_file.exists():
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        url = AQS_URL.format(
            project=project, title=safe, start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}"
        )
        elapsed = time.monotonic() - _last_request_at
        if elapsed < REQUEST_INTERVAL_SEC:
            time.sleep(REQUEST_INTERVAL_SEC - elapsed)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        _last_request_at = time.monotonic()
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

    series: dict[date, int] = {}
    for item in payload.get("items", []):
        stamp = item["timestamp"]           # "YYYYMMDD00"
        day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        series[day] = int(item["views"])
    return series


def first_view_signal(
    series: dict[date, int],
    *,
    halflife_days: float = DEFAULT_HALFLIFE_DAYS,
    window_days: int = BASELINE_WINDOW_DAYS,
    not_before: date | None = None,
    min_absolute_views: int = 0,
) -> ViewSignal | None:
    """조회수가 처음 `z>=3 AND 배수>=2` 를 넘은 날.

    각 날짜마다 **그 이전 28일**로 기준선을 만든다(편집 쪽 baseline_at 과 같은 규칙:
    판정 대상은 자기 기준선에 안 들어간다). 창에 관측이 2일 미만이면 건너뛴다 —
    표준편차가 0 이라 z 가 무한이 된다.

    not_before 를 주면 그날 이후만 본다. 관측 구간 앞부분의 무관한 급등을
    사건 신호로 오인하지 않기 위해서다(호출자가 사건 전 며칠까지 허용할지 정한다).

    min_absolute_views 는 **측정용 실험 손잡이**다. 기본 0 = 하한 없음 —
    `detector.py` 의 현재 조회수 판정에는 절대 하한이 없고, 이 함수는 그 규칙을
    그대로 재현해야 한다. 🔴 여기에 기본값을 넣어 detector 와 다른 판정을 만들지 않는다.
    하한을 넣었을 때 무엇이 달라지는지 재려고 파라미터로만 연다
    (평소 1회/일 문서가 8회로 z 8 을 내는 경우 — Hurricane_Helene 2024-09-22).
    """
    for day in sorted(series):
        if not_before is not None and day < not_before:
            continue
        oldest = day - timedelta(days=window_days)
        prior = [(d, v) for d, v in series.items() if oldest <= d < day]
        if len(prior) < 2:
            continue

        mean, stddev = ewma_mean_std(
            [Observation((day - d).days, float(v)) for d, v in prior], halflife_days
        )
        if mean <= 0:
            continue

        views = series[day]
        ratio = views / mean
        z = None if not stddev or stddev <= 0 else (views - mean) / stddev
        if (z is not None and z >= VIEW_Z_THRESHOLD and ratio >= MIN_VIEW_RATIO
                and views >= min_absolute_views):
            return ViewSignal(day=day, views=views, baseline_mean=mean, z=z, ratio=ratio)
    return None


def first_edit_signal(
    by_title: dict[str, list],
    titles: Sequence[str],
    *,
    halflife_days: float = DEFAULT_HALFLIFE_DAYS,
) -> dict[str, EditSignal | None]:
    """집계된 관측에서 문서별 최초 급증 시점을 낸다.

    판정은 `spike.replay` 를 그대로 쓴다 — 리플레이와 다른 답이 나오면 안 된다.
    집계(`aggregate`)는 호출자가 한 번만 한다 — 덤프가 문서당 150 MB × shard 라
    여기서 다시 읽으면 같은 파일을 두 번 훑는다.
    """
    out: dict[str, EditSignal | None] = {}
    for title in titles:
        # by_title 키는 canonical(공백형)이다. 반환 dict 는 **호출자가 준 제목 그대로**
        # 키를 둔다 — 호출자가 자기 목록으로 다시 찾을 수 있어야 한다 (WP-91).
        observations = by_title.get(canonical_title(title), [])
        if not observations:
            out[title] = None
            continue
        first = first_detection(replay_title(observations, halflife_days))
        out[title] = None if first is None else EditSignal(
            window_start=first.window_start,
            edit_count=first.edit_count,
            editor_count=first.editor_count,
            edit_z=first.decision.edit_z,
            is_new_page=first.decision.is_new_page,
        )
    return out


def measure(
    edits_dirs: Sequence[Path],
    titles: Sequence[str],
    *,
    event_date: date | None = None,
    view_lookback_days: int = BASELINE_WINDOW_DAYS + 7,
    view_lookahead_days: int = 21,
    halflife_days: float = DEFAULT_HALFLIFE_DAYS,
    min_absolute_views: int = 0,
) -> list[LagResult]:
    """문서별로 두 신호의 최초 시점과 시차를 낸다.

    조회수 구간은 event_date 기준 [−(lookback), +lookahead]. event_date 가 없으면
    편집 덤프에서 관측된 첫 날을 기준으로 잡는다.
    """
    by_title = aggregate(_read_all(edits_dirs), set(titles))
    edit_signals = first_edit_signal(by_title, titles, halflife_days=halflife_days)
    # event_date 를 안 줬을 때의 기준점 = 덤프 내 첫 편집일. 키는 canonical 이다.
    observed_days = {t: min(o.day for o in obs) for t, obs in by_title.items() if obs}

    results = []
    for title in titles:
        anchor = event_date or observed_days.get(canonical_title(title))
        if anchor is None:
            results.append(LagResult(title, event_date, None, edit_signals[title]))
            continue

        start = anchor - timedelta(days=view_lookback_days)
        end = anchor + timedelta(days=view_lookahead_days)
        try:
            series = fetch_daily_views(title, start, end)
        except urllib.error.HTTPError as exc:
            print(f"  ⚠️ {title}: 조회수 API {exc.code} — 건너뜀", file=sys.stderr)
            results.append(LagResult(title, anchor, None, edit_signals[title]))
            continue

        # 사건 7일 전부터 본다. 그 앞의 무관한 급등을 사건 신호로 세지 않는다.
        view = first_view_signal(
            series, halflife_days=halflife_days, not_before=anchor - timedelta(days=7),
            min_absolute_views=min_absolute_views,
        )
        results.append(LagResult(title, anchor, view, edit_signals[title]))
    return results


def _read_all(edits_dirs: Sequence[Path]):
    """여러 월 덤프를 이어 읽는다.

    ⚠️ 한 달치만 읽으면 월초 사건의 28일 기준선이 잘려 기존 문서도 `is_thin` 이 되고
    신규 문서 경로(절대 편집수)로 빠진다 — z 경로가 아예 실행되지 않는다.
    사건 전월을 같이 주면 창이 채워진다. 28일 창 자체는 baseline_at 이 거르므로
    범위 밖 달을 더 줘도 판정은 안 변한다(읽는 시간만 는다).
    """
    for edits_dir in edits_dirs:
        yield from read_edit_events(edits_dir)


def format_results(results: Iterable[LagResult]) -> str:
    lines = []
    for r in results:
        lines.append(f"\n[{r.title}]  사건 기준일 {r.event_date}")
        if r.view is None:
            lines.append("  조회수 : 탐지 없음")
        else:
            z = "-" if r.view.z is None else f"{r.view.z:.1f}"
            lines.append(
                f"  조회수 : {r.view.day}  {r.view.views:,} 회 "
                f"(평소 {r.view.baseline_mean:,.0f} · {r.view.ratio:.1f}배 · z {z})"
            )
        if r.edit is None:
            lines.append("  편집   : 탐지 없음")
        else:
            z = "-" if r.edit.edit_z is None else f"{r.edit.edit_z:.1f}"
            kind = "신규문서" if r.edit.is_new_page else "기존문서"
            lines.append(
                f"  편집   : {r.edit.window_start}  {r.edit.edit_count} 편집 "
                f"· 편집자 {r.edit.editor_count} · z {z} · {kind}"
            )
        lag = r.lag_days
        if lag is None:
            lines.append("  시차   : 한쪽이 없어 계산 불가")
        else:
            verdict = "편집이 늦다" if lag > 0 else ("조회수가 늦다" if lag < 0 else "같은 날")
            lines.append(f"  시차   : {lag:+d}일 ({verdict})")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="편집·조회수 신호 시차 측정 (WP-86)")
    p.add_argument("--edits", action="append", required=True,
                   help="편집 적재본 디렉터리 (-56). 여러 번 주면 이어 읽는다 — "
                        "월초 사건은 전월을 같이 줘야 28일 기준선이 찬다")
    p.add_argument("--title", action="append", default=[], required=True,
                   help="측정할 문서. 밑줄·공백 아무 형태로나 준다. 여러 번 줄 수 있다")
    p.add_argument("--event-date", help="사건 기준일 YYYY-MM-DD. 없으면 덤프 첫 편집일")
    p.add_argument("--halflife-days", type=float, default=DEFAULT_HALFLIFE_DAYS)
    p.add_argument("--min-views", type=int, default=0,
                   help="조회수 절대 하한(실험용). 기본 0 = detector 현재 규칙 그대로")
    p.add_argument("--json", action="store_true", help="결과를 JSON 으로")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    edits_dirs = [Path(d) for d in args.edits]
    missing = [d for d in edits_dirs if not d.exists()]
    if missing:
        print(f"--edits 경로 없음: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2

    results = measure(
        edits_dirs,
        args.title,
        event_date=date.fromisoformat(args.event_date) if args.event_date else None,
        halflife_days=args.halflife_days,
        min_absolute_views=args.min_views,
    )

    if args.json:
        print(json.dumps([{
            "title": r.title,
            "event_date": None if r.event_date is None else r.event_date.isoformat(),
            "view_day": None if r.view is None else r.view.day.isoformat(),
            "view_views": None if r.view is None else r.view.views,
            "view_ratio": None if r.view is None else round(r.view.ratio, 2),
            "view_z": None if r.view is None or r.view.z is None else round(r.view.z, 2),
            "edit_window": None if r.edit is None else r.edit.window_start,
            "edit_count": None if r.edit is None else r.edit.edit_count,
            "edit_editors": None if r.edit is None else r.edit.editor_count,
            "edit_is_new_page": None if r.edit is None else r.edit.is_new_page,
            "lag_days": r.lag_days,
        } for r in results], ensure_ascii=False, indent=2))
    else:
        print(format_results(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
