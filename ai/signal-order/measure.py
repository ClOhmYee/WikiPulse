"""편집·조회수 신호 시차 전수 측정 (WP-86).

`spike.signal_lag` 을 사건 10건에 돌려 RESULT.md 의 표를 만든다. 사건 목록·기준일을
여기 박아 두는 이유는 **같은 수치를 다시 뽑을 수 있게** 하기 위해서다 (WP-53).

    cd data-pipeline && PYTHONIOENCODING=utf-8 python ../ai/signal-order/measure.py

사건 선정 기준
    로컬 편집 덤프가 있는 4개월(2024-09·2024-10·2025-05·2025-06) 안에서, 기존 문서와
    신규 문서를 섞어 골랐다. 덤프 밖 사건은 편집 신호를 잴 수 없다.

제목 형식
    아래 목록은 밑줄형인데 그대로 둬도 된다 (WP-91). `replay.aggregate` 가
    요청·레코드 제목을 둘 다 canonical 로 맞추므로 재생성 전(밑줄)·후(공백) 적재본
    어느 쪽에서도 같은 답이 나온다. AQS 도 두 형식 다 200 을 준다(2026-09-15 실측).

조회수 절대 하한 sweep
    detector 에는 조회수 절대 하한이 **없다**. 평소 1회/일 문서가 8회만 돼도 z 8 이
    나오는 걸 확인해서(Hurricane_Helene 2024-09-22), 하한을 넣으면 뭐가 달라지는지
    같이 잰다. 🔴 detector 는 이 스크립트에서 바꾸지 않는다 — 측정만 한다.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data-pipeline"))

from spike.replay import aggregate, read_edit_events          # noqa: E402
from spike.signal_lag import (                                 # noqa: E402
    BASELINE_WINDOW_DAYS,
    fetch_daily_views,
    first_edit_signal,
    first_view_signal,
)

DUMPS = Path("out/enwiki")

#: 조회수 절대 하한 후보. 0 = detector 현재 규칙(하한 없음).
VIEW_FLOORS = (0, 100, 500, 1000)

#: (편집 덤프 월들, 사건 기준일, [(문서, 문서유형, 사건 설명)])
SAMPLES = [
    (["2024-09"], date(2024, 9, 26), [
        ("Hassan_Nasrallah", "기존", "이스라엘 공습 사망 (9/27)"),
        ("Hurricane_Helene", "신규", "허리케인 상륙 (9/26)"),
    ]),
    (["2024-09", "2024-10"], date(2024, 10, 5), [
        ("Hurricane_Milton", "신규", "허리케인 발생 (10/5)"),
    ]),
    (["2024-09", "2024-10"], date(2024, 10, 16), [
        ("Liam_Payne", "기존", "사망 (10/16)"),
        ("Yahya_Sinwar", "기존", "사망 (10/16, 확인 10/17)"),
    ]),
    (["2025-05"], date(2025, 5, 7), [
        ("2025_India–Pakistan_conflict", "신규", "교전 시작 (5/7)"),
        ("Papal_conclave", "기존", "콘클라베 개시 (5/7)"),
    ]),
    (["2025-05", "2025-06"], date(2025, 6, 12), [
        ("Strait_of_Hormuz", "기존", "이란 봉쇄 위협 (6/13~)"),
        ("Air_India_Flight_171", "신규", "추락 (6/12)"),
        ("Boeing_787_Dreamliner", "기존", "추락 기종 (6/12)"),
    ]),
]


def run() -> list[dict]:
    rows = []
    for months, anchor, titles in SAMPLES:
        dirs = [DUMPS / m for m in months]
        names = [t for t, _, _ in titles]
        by_title = aggregate((e for d in dirs for e in read_edit_events(d)), set(names))
        edits = first_edit_signal(by_title, names)

        for title, kind, note in titles:
            series = fetch_daily_views(
                title,
                anchor - timedelta(days=BASELINE_WINDOW_DAYS + 7),
                anchor + timedelta(days=21),
            )
            edit = edits[title]
            row = {
                "title": title, "kind": kind, "note": note,
                "anchor": anchor.isoformat(),
                "edit_day": None if edit is None else edit.day.isoformat(),
                "edit_count": None if edit is None else edit.edit_count,
                "edit_editors": None if edit is None else edit.editor_count,
                "edit_is_new_page": None if edit is None else edit.is_new_page,
                "views": {},
            }
            for floor in VIEW_FLOORS:
                view = first_view_signal(
                    series,
                    not_before=anchor - timedelta(days=7),
                    min_absolute_views=floor,
                )
                row["views"][floor] = None if view is None else {
                    "day": view.day.isoformat(),
                    "views": view.views,
                    "baseline": round(view.baseline_mean, 1),
                    "ratio": round(view.ratio, 1),
                    "z": None if view.z is None else round(view.z, 1),
                    "lag_days": None if edit is None else (edit.day - view.day).days,
                }
            rows.append(row)
    return rows


#: 대조군 — 사건 문서가 아닌데 트래픽·편집이 많은 문서. 조회수를 독립 트리거로 쓸 때
#: 며칠이나 헛불이 나는지 재는 용도다.
#: ⚠️ WP-85 가 쓴 대조군 14개는 저장소에 목록이 안 남아 있다(README 에 일부 이름만).
#: 여기 목록은 그 성격(상시 편집·고트래픽 비사건 문서)을 따라 새로 고른 것이지 같은 집합이 아니다.
CONTROLS = [
    "Cat", "Association_football", "Deaths_in_2025", "List_of_people_named_Peter",
    "Timeline_of_science_fiction", "YouTube", "India", "Python_(programming_language)",
    "World_War_II", "Elizabeth_II", "Solar_System", "Chess", "Taylor_Swift", "The_Beatles",
]

#: 대조군 관찰 구간. 이 달에 특정 대형 사건이 몰려 있지 않은 쪽으로 잡았다.
CONTROL_FROM = date(2025, 5, 1)
CONTROL_TO = date(2025, 5, 31)


def control_view_triggers(floor: int) -> dict[str, list[str]]:
    """대조군에서 조회수 규칙이 발동한 날. 조회수를 1차로 올릴 때의 오탐 비용이다.

    편집 쪽 오탐(-85: 편집자 하한 적용 후 101건)과 같은 성격의 수치를 조회수 쪽에도
    만들어야 OR 전환 비용을 비교할 수 있다. 하루씩 끊어 세는 건 편집 쪽이 윈도우
    단위로 센 것과 입도가 달라서다 — 조회수는 애초에 일 단위라 더 잘게 못 센다.
    """
    triggers: dict[str, list[str]] = {}
    for title in CONTROLS:
        series = fetch_daily_views(
            title, CONTROL_FROM - timedelta(days=BASELINE_WINDOW_DAYS + 7), CONTROL_TO)
        days = []
        cursor = CONTROL_FROM
        while cursor <= CONTROL_TO:
            hit = first_view_signal(
                {d: v for d, v in series.items() if d <= cursor},
                not_before=cursor, min_absolute_views=floor,
            )
            if hit is not None and hit.day == cursor:
                days.append(cursor.isoformat())
            cursor += timedelta(days=1)
        triggers[title] = days
    return triggers


def as_table(rows: list[dict], floor: int) -> str:
    out = [
        f"조회수 절대 하한 = {floor}",
        f"{'문서':34s} {'유형':4s} {'조회수 신호':12s} {'배수':>8s} "
        f"{'편집 신호':12s} {'시차':>6s}",
    ]
    for r in rows:
        view = r["views"][floor]
        vday = "미탐" if view is None else view["day"]
        ratio = "-" if view is None else f"{view['ratio']:.1f}x"
        eday = "미탐" if r["edit_day"] is None else r["edit_day"]
        lag = "-" if view is None or r["edit_day"] is None else f"{view['lag_days']:+d}d"
        out.append(f"{r['title']:34s} {r['kind']:4s} {vday:12s} {ratio:>8s} "
                   f"{eday:12s} {lag:>6s}")
    return "\n".join(out)


def main() -> int:
    rows = run()
    for floor in VIEW_FLOORS:
        print()
        print(as_table(rows, floor))

    controls = {}
    print("\n대조군 조회수 오탐 (2025-05-01 ~ 05-31, 문서 14개 · 총 434 문서·일)")
    for floor in VIEW_FLOORS:
        hits = control_view_triggers(floor)
        controls[floor] = hits
        total = sum(len(v) for v in hits.values())
        pages = sum(1 for v in hits.values() if v)
        print(f"  하한 {floor:>5} : {total:>3} 건 · {pages}/{len(CONTROLS)} 문서")
        for title, days in hits.items():
            if days:
                print(f"      {title:32s} {', '.join(days)}")

    out = Path(__file__).with_name("measurements.json")
    out.write_text(json.dumps(
        {"events": rows, "controls": {str(k): v for k, v in controls.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n원자료: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
