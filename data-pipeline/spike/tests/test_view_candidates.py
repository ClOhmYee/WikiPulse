"""조회수 후보 생산 테스트 (WP-210).

`detector` 쪽 테스트가 "이 윈도우를 통과시키나" 를 고정한다면, 여기는
**"그런 윈도우가 애초에 후보로 만들어지나"** 를 고정한다. 둘이 짝이라 한쪽만 있으면
아무 동작도 안 바뀐다 — 실제로 한 번 그렇게 만들었다.
"""

from __future__ import annotations

from batch.pageview_hourly import PageviewHourly, aggregate
from spike.view_candidates import passes, safe_row_floor, scan_titles, select

TS = "2026-08-19T13:00:00"


def row(title: str, views: int, mobile: int) -> PageviewHourly:
    return PageviewHourly("enwiki", title, TS, views, mobile)


# ---------------------------------------------------------------- 통과 규칙

def test_모바일이_충분한_급등은_후보가_된다():
    """2026-08-19 Moderna — 편집 0건이라 편집 스트림에는 아예 안 뜬다."""
    assert passes(row("Moderna", 6_893, 3_594)) is True


def test_데스크톱_단일_채널은_후보가_아니다():
    """🔴 Roblox 2026-08-10. 이걸 막는 게 이 경로의 존재 이유의 절반이다."""
    assert passes(row("Roblox", 4_781_244, 3_746)) is False


def test_조회수_하한_미만은_후보가_아니다():
    assert passes(row("Water", 99, 99)) is False
    assert passes(row("Water", 100, 99)) is True


def test_모바일_경계값은_통과다():
    assert passes(row("Edge", 1_000, 250)) is True     # 정확히 25%
    assert passes(row("Edge", 1_000, 249)) is False


def test_조회수가_0_이면_후보가_아니다():
    """비율이 None 이라 판단 근거가 없다 — 0 으로 치면 봇으로 잘못 단정한다."""
    assert passes(row("Ghost", 0, 0)) is False


def test_select_는_통과분만_순서대로_준다():
    rows = [row("Moderna", 6_893, 3_594), row("Roblox", 4_781_244, 3_746),
            row("Merck & Co.", 1_982, 1_100)]
    assert [r.title for r in select(rows)] == ["Moderna", "Merck & Co."]


# ---------------------------------------------------------------- 1패스 문턱

def test_1패스_문턱은_project_수로_나눈_올림이다():
    """🔴 추측이 아니라 산수다.

    enwiki 의 project 는 `en`·`en.m` 둘뿐이라, 합이 100 이상이면 둘 중 하나가 반드시
    50 이상이다. 그래서 50 미만 행만 버리면 통과 대상은 하나도 안 샌다.
    """
    assert safe_row_floor("enwiki") == 50


def test_1패스는_문턱_넘는_행이_있는_제목만_남긴다():
    lines = [
        "en Moderna 3299 0",          # 넘는다
        "en.m Moderna 3594 0",
        "en Water 10 0",              # 양쪽 다 못 넘는다 — 합쳐도 18 < 100
        "en.m Water 8 0",
        "en.m Tiny 60 0",             # 모바일만 넘는다
    ]
    assert scan_titles(lines, "enwiki") == frozenset({"Moderna", "Tiny"})


def test_1패스가_버린_문서는_합쳐도_하한에_못_미친다():
    """문턱의 안전성을 값으로 고정한다 — 경계에서 새면 조용히 후보를 잃는다."""
    floor = safe_row_floor("enwiki")
    lines = [f"en Borderline {floor - 1} 0", f"en.m Borderline {floor - 1} 0"]
    assert scan_titles(lines, "enwiki") == frozenset()
    total = sum(int(line.split(" ")[2]) for line in lines)
    assert total < 100          # 버려도 통과 대상이 아니었다


def test_경계_바로_위는_1패스를_통과한다():
    floor = safe_row_floor("enwiki")
    lines = [f"en Borderline {floor} 0", f"en.m Borderline 51 0"]
    assert scan_titles(lines, "enwiki") == frozenset({"Borderline"})
    rows = list(aggregate(lines, "enwiki", TS, titles=frozenset({"Borderline"})))
    assert rows[0].views == floor + 51
    assert passes(rows[0]) is True


def test_대문은_후보가_아니다():
    """🔴 한 시간에 38만 조회(모바일 28.5%)라 봇 필터로는 안 걸린다.

    편집 경로에서는 문제가 된 적이 없다 — 대문은 편집 스트림 후보로 안 올라온다.
    조회수로 문을 여는 순간 매 시간 1위로 들어왔다.
    """
    assert passes(row("Main Page", 384_709, 109_641)) is False
