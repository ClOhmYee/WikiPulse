"""ROOT SELECTION 회귀 (WP-137 → -186 에서 MVP 정본 1단계).

🔴 이 단계는 `spike` 를 바꾸지 않는다 — 고르기만 한다. 그래서 검사도 "무엇이 선택됐나"
만 본다. 임계·공식 검사는 `spike/tests/test_detector.py` 쪽이다.

고정 2개월 전체(1,104 스냅샷 · 22,080 root)가 PoC frozen set 과 정확히 일치하는지는
`tools/cluster-preview/verify_core_regression.py` 가 DB 에 붙어서 본다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from cluster.root_selection import (
    DEFAULT_COOLDOWN_HOURS,
    DEFAULT_LIMIT_PER_SNAPSHOT,
    RootSelectionConfig,
    select,
)

T0 = datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)


def hour(n: int) -> datetime:
    return T0 + timedelta(hours=n)


def rows(*items):
    """(시각, page_id, views) 를 계약 순서(시각 asc, 조회수 desc, page_id asc)로."""
    return sorted(items, key=lambda r: (r[0], -(r[2] or 0), r[1]))


def cut(**kw) -> RootSelectionConfig:
    """기본은 켜짐(20 / 24h). 테스트가 필요한 것만 덮는다."""
    return RootSelectionConfig(**kw)


# --- 기본값 ------------------------------------------------------------------

def test_기본값이_고정_2개월_산출물과_같은_값이다():
    """🔴 22,080 = 1,104 스냅샷 × 20 을 만든 값. 바꾸면 회귀가 깨진다."""
    assert DEFAULT_LIMIT_PER_SNAPSHOT == 20
    assert DEFAULT_COOLDOWN_HOURS == 24
    config = RootSelectionConfig()
    assert config.enabled is True
    assert (config.limit_per_snapshot, config.cooldown_hours) == (20, 24)


def test_둘_다_끄면_전부_통과한다():
    data = rows((hour(0), 1, 500), (hour(0), 2, 400), (hour(1), 1, 300))
    config = RootSelectionConfig(limit_per_snapshot=None, cooldown_hours=0)
    assert not config.enabled
    assert select(data, config) == {(hour(0), 1), (hour(0), 2), (hour(1), 1)}


# --- 1. views 내림차순 --------------------------------------------------------

def test_조회수_내림차순으로_고른다():
    """상한에 걸릴 때 남는 것은 조회수 큰 쪽이어야 한다."""
    data = rows((hour(0), 1, 100), (hour(0), 2, 9000), (hour(0), 3, 500))
    assert select(data, cut(limit_per_snapshot=1, cooldown_hours=0)) == {(hour(0), 2)}


def test_정렬_입력에_spike_score_가_없다():
    """🔴 `spike_score` 는 경로마다 단위가 달라 정렬 키로 못 쓴다 — 모듈 독스트링.

    선택 입력이 `(detected_at, page_id, views)` 3-튜플이라는 것으로 확인한다.
    """
    data = rows((hour(0), 1, 10), (hour(0), 2, 20))
    assert all(len(r) == 3 for r in data)
    assert select(data, cut(limit_per_snapshot=1, cooldown_hours=0)) == {(hour(0), 2)}


def test_views_None_은_뒤로_밀린다():
    """V7 이전 행은 views 가 NULL 이다. 앞에 오면 조회수 모르는 행이 상위를 먹는다."""
    data = rows((hour(0), 1, None), (hour(0), 2, 50))
    assert select(data, cut(limit_per_snapshot=1, cooldown_hours=0)) == {(hour(0), 2)}


# --- 2·3. 쿨다운과 상한 -------------------------------------------------------

def test_스냅샷당_상한을_지킨다():
    data = rows((hour(0), 1, 900), (hour(0), 2, 800), (hour(0), 3, 700),
                (hour(1), 4, 600), (hour(1), 5, 500))
    got = select(data, cut(limit_per_snapshot=2, cooldown_hours=0))
    assert got == {(hour(0), 1), (hour(0), 2), (hour(1), 4), (hour(1), 5)}


def test_쿨다운으로_빠진_자리를_다음_후보가_채운다():
    """🔴 상한은 '훑은 개수' 가 아니라 '선택된 개수' 다.

    "먼저 top-N 을 뽑고 중복을 버린다" 였다면 hour(1) 은 page2 하나로 끝난다.
    실제 규칙은 page1 을 건너뛰고 page2·page3 가 두 칸을 채우는 것이다.
    """
    data = rows((hour(0), 1, 900),
                (hour(1), 1, 900), (hour(1), 2, 800), (hour(1), 3, 700))
    got = select(data, cut(limit_per_snapshot=2))
    assert got == {(hour(0), 1), (hour(1), 2), (hour(1), 3)}


def test_정확히_20개를_채운다():
    """후보가 충분하면 시점마다 정확히 상한만큼. 고정 2개월이 전 시점 20 이었다."""
    data = rows(*[(hour(0), pid, 1000 - pid) for pid in range(1, 40)])
    got = select(data, cut())
    assert len(got) == 20
    assert {pid for _, pid in got} == set(range(1, 21))      # views 상위 20


def test_후보가_상한보다_적으면_있는_만큼만():
    data = rows(*[(hour(0), pid, 100 - pid) for pid in range(1, 6)])
    assert len(select(data, cut())) == 5


@pytest.mark.parametrize("limit,expected", [(1, 1), (2, 2), (5, 3)])
def test_상한이_후보보다_크면_있는_만큼만(limit, expected):
    data = rows((hour(0), 1, 300), (hour(0), 2, 200), (hour(0), 3, 100))
    got = select(data, cut(limit_per_snapshot=limit, cooldown_hours=0))
    assert len(got) == expected


# --- 4. 24h 경계 --------------------------------------------------------------

def test_쿨다운_안에서는_같은_문서를_다시_안_고른다():
    data = rows((hour(0), 1, 900), (hour(5), 1, 900), (hour(23), 1, 900))
    assert select(data, cut()) == {(hour(0), 1)}


def test_정확히_24시간_뒤는_다시_고른다():
    """🔴 경계는 `<` 다 — `detected_at - previous < window` 면 건너뛴다.

    즉 **정확히 24시간 뒤는 통과**한다.
    """
    data = rows((hour(0), 1, 900), (hour(24), 1, 900))
    assert select(data, cut()) == {(hour(0), 1), (hour(24), 1)}


def test_23시간_59분은_막힌다():
    data = [(T0, 1, 900), (T0 + timedelta(hours=23, minutes=59), 1, 900)]
    assert select(rows(*data), cut()) == {(T0, 1)}


def test_쿨다운은_달력_날짜가_아니라_되돌아보는_창이다():
    """08:00 에 뽑히면 다음 날 08:00 이후여야 한다 — 자정이 기준이 아니다."""
    data = rows((hour(8), 1, 900), (hour(25), 1, 900), (hour(32), 1, 900))
    # hour(25) 는 자정을 넘었지만 창(24h) 안이라 막힌다. hour(32) 는 통과.
    assert select(data, cut()) == {(hour(8), 1), (hour(32), 1)}


def test_쿨다운이_지나면_다시_고른다():
    data = rows((hour(0), 1, 900), (hour(24), 1, 900), (hour(48), 1, 900))
    assert select(data, cut()) == {(hour(0), 1), (hour(24), 1), (hour(48), 1)}


def test_반복_횟수가_많다고_영구_제외하지_않는다():
    """실측 근거: 110시간 초과 제외는 Dolly Parton·Colombia earthquake 를 전부 죽였다."""
    data = rows(*[(hour(24 * d), 1, 900) for d in range(30)])
    assert len(select(data, cut())) == 30, "장기 지속 문서가 살아 있어야 한다"


def test_증분_실행이_앞_구간_쿨다운을_이어받는다():
    """🔴 LIVE 는 한 시점씩 돈다. prior_picks 가 없으면 쿨다운이 통째로 무력화된다."""
    data = rows((hour(10), 1, 900), (hour(10), 2, 800))
    assert select(data, cut(limit_per_snapshot=1)) == {(hour(10), 1)}
    # page1 이 hour(0) 에 이미 뽑혔으면 창 안이라 건너뛰고 page2 가 그 칸을 채운다.
    got = select(data, cut(limit_per_snapshot=1), prior_picks={1: hour(0)})
    assert got == {(hour(10), 2)}


# --- 5·6. 결정성 --------------------------------------------------------------

def test_동점_tie_break_는_page_id_오름차순():
    data = rows((hour(0), 7, 500), (hour(0), 3, 500), (hour(0), 9, 500))
    assert select(data, cut(limit_per_snapshot=2, cooldown_hours=0)) == {
        (hour(0), 3), (hour(0), 7)}


def test_입력_순서를_바꿔도_같은_결과다():
    """🔴 호출자가 ORDER BY 를 빠뜨려도 조용히 다른 root 가 뽑히면 안 된다."""
    items = [(hour(1), 2, 800), (hour(0), 1, 900), (hour(1), 1, 900),
             (hour(0), 3, 700), (hour(1), 3, 700), (hour(0), 2, 800)]
    expected = select(rows(*items), cut(limit_per_snapshot=2))
    for shuffled in (items, list(reversed(items)), sorted(items, key=lambda r: r[1])):
        assert select(shuffled, cut(limit_per_snapshot=2)) == expected


def test_같은_입력이면_항상_같은_결과다():
    data = rows(*[(hour(h), pid, 1000 - pid) for h in range(3) for pid in range(1, 30)])
    assert select(data, cut()) == select(data, cut())


# --- 7. 동일성 기준 -----------------------------------------------------------

def test_문서_동일성은_page_id_다():
    """제목이 아니다 — 입력에 제목 자체가 없고 쿨다운 키도 page_id 다.

    제목이 바뀌어도(이동·정규화) page_id 가 같으면 한 문서다.
    """
    data = rows((hour(0), 42, 900), (hour(1), 42, 900))
    assert select(data, cut()) == {(hour(0), 42)}
    # page_id 가 다르면 제목이 무엇이든 별개 문서다.
    data = rows((hour(0), 42, 900), (hour(1), 43, 900))
    assert select(data, cut()) == {(hour(0), 42), (hour(1), 43)}


# --- 8. 경계 ------------------------------------------------------------------

def test_빈_선택과_컷_없음은_다르다():
    """None(컷 없음) 과 빈 집합(아무것도 안 고름) 이 섞이면 필터가 통째로 무력화된다."""
    assert select([], cut()) == set()
    assert RootSelectionConfig(limit_per_snapshot=None, cooldown_hours=0).enabled is False
    assert RootSelectionConfig(limit_per_snapshot=5, cooldown_hours=0).enabled is True
    assert RootSelectionConfig(limit_per_snapshot=None, cooldown_hours=1).enabled is True
