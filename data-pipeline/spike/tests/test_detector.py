"""급증 판정 수식 테스트. 실측 데이터로 오탐·미탐을 잡는다.

숫자는 2026-09-08 에 Wikimedia 에서 직접 받은 것이다.
"""

from __future__ import annotations

import statistics

import pytest

from spike.detector import (
    EDIT_Z_THRESHOLD,
    MIN_ABSOLUTE_EDITS,
    Baseline,
    Window,
    detect,
)

# --- Strait of Hormuz 조회수 실측 (2025-06, per-article API) ---
# 사건 전 18일 baseline
HORMUZ_BASELINE_VIEWS = [
    426, 433, 494, 383, 358, 377, 363, 363, 418, 483,
    433, 366, 324, 319, 326, 338, 355, 481,
]
HORMUZ_MU = statistics.mean(HORMUZ_BASELINE_VIEWS)      # 391
HORMUZ_SD = statistics.pstdev(HORMUZ_BASELINE_VIEWS)    # 55
# 사건 구간 조회수
HORMUZ_EVENT = {
    "2025-06-11": 481,     # 사건 전날 (정상)
    "2025-06-12": 1007,    # 첫 신호 z=11.2
    "2025-06-13": 9836,    # z=172
    "2025-06-22": 291824,  # 정점 z=5311
}


def view_z(views: int) -> float:
    return (views - HORMUZ_MU) / HORMUZ_SD


def test_평상시_조회수는_z_임계_아래다():
    """오탐 확인. 평상시 최대 z 가 3 을 넘으면 안 된다."""
    zs = [view_z(v) for v in HORMUZ_BASELINE_VIEWS]
    assert max(zs) < EDIT_Z_THRESHOLD, f"평상시 최대 z={max(zs):.1f} 가 임계를 넘음"


def test_사건_첫날부터_z_임계를_넘는다():
    """미탐 확인. 사건 시작(6/12)이 잡혀야 한다."""
    assert view_z(HORMUZ_EVENT["2025-06-12"]) >= EDIT_Z_THRESHOLD
    assert view_z(HORMUZ_EVENT["2025-06-22"]) >= EDIT_Z_THRESHOLD


def test_사건_전날은_안_잡힌다():
    assert view_z(HORMUZ_EVENT["2025-06-11"]) < EDIT_Z_THRESHOLD


# --- detect() 통합: 기존 문서 (Strait of Hormuz 를 편집 신호로 대입) ---

def hormuz_baseline(sample_days: int = 28) -> Baseline:
    return Baseline(
        edit_ewma=HORMUZ_MU,
        edit_stddev=HORMUZ_SD,
        view_ewma=HORMUZ_MU,
        sample_days=sample_days,
    )


def test_기존문서_평상시는_급증이_아니다():
    d = detect(Window(edit_count=420, editor_count=5, views=420), hormuz_baseline())
    assert not d.is_spike
    assert not d.is_new_page


def test_기존문서_사건은_편집조회수_모두_통과하면_확정():
    d = detect(
        Window(edit_count=9836, editor_count=50, views=291824),
        hormuz_baseline(),
    )
    assert d.is_spike
    assert d.edit_z >= EDIT_Z_THRESHOLD
    assert d.view_ratio >= 2.0
    assert "확정" in d.reason


def test_조회수가_아직_없으면_감지됨_상태로_통과():
    """조회수는 늦게 온다. 편집만 통과하면 감지됨(is_spike=True, view 없음)."""
    d = detect(
        Window(edit_count=9836, editor_count=50, views=None),
        hormuz_baseline(),
    )
    assert d.is_spike
    assert d.view_ratio is None
    assert "감지됨" in d.reason


def test_편집은_튀는데_조회수가_안_따라오면_확정_안됨():
    """편집 전쟁·정리 작업 걸러내기. 편집 z 는 높지만 조회수가 평소."""
    d = detect(
        Window(edit_count=5000, editor_count=2, views=400),  # 조회수 평소
        hormuz_baseline(),
    )
    assert not d.is_spike
    assert d.view_ratio < 2.0


def test_얇은_baseline_은_절대하한이_막는다():
    """평소 편집 0~1 인 문서가 2건에 z 폭발하는 걸 절대 하한으로 막는다."""
    thin = Baseline(edit_ewma=0.5, edit_stddev=0.5, view_ewma=10, sample_days=28)
    # z 는 3을 넘지만 절대 편집수가 MIN 미만
    d = detect(Window(edit_count=3, editor_count=1, views=100), thin)
    assert not d.is_spike


# --- 신규 문서 (Hurricane Milton 같은 사건 당일 생성) ---

def test_신규문서는_절대편집수로_판정한다():
    """baseline 이 없다(sample_days 부족). Milton 은 생성 당일 40편집."""
    d = detect(Window(edit_count=40, editor_count=15, views=None), baseline=None)
    assert d.is_spike
    assert d.is_new_page
    assert d.edit_z is None


def test_신규문서_편집이_적으면_급증_아니다():
    d = detect(Window(edit_count=3, editor_count=2, views=None), baseline=None)
    assert not d.is_spike
    assert d.is_new_page


def test_얇은_baseline_도_신규문서로_취급():
    thin = Baseline(edit_ewma=1, edit_stddev=1, view_ewma=5, sample_days=3)
    d = detect(Window(edit_count=15, editor_count=8, views=None), thin)
    assert d.is_new_page  # sample_days < 7


# --- 점수 ---

def test_급등도는_두_신호가_클수록_크다():
    small = detect(Window(edit_count=15, editor_count=5, views=1000), hormuz_baseline())
    big = detect(Window(edit_count=9836, editor_count=50, views=291824), hormuz_baseline())
    assert big.spike_score > small.spike_score


def test_극단값이_점수를_지배하지_않는다():
    """z=5311 이 그대로면 한 버블이 화면을 먹는다. log 로 눌렀는지."""
    d = detect(Window(edit_count=291824, editor_count=100, views=291824), hormuz_baseline())
    # log1p(5311) ~ 8.6. 곱해도 세 자릿수를 넘지 않는다.
    assert d.spike_score < 100
