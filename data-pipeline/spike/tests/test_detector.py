"""급증 판정 수식 테스트. 실측 데이터로 오탐·미탐을 잡는다.

숫자는 2026-09-08 에 Wikimedia 에서 직접 받은 것이다.
"""

from __future__ import annotations

import statistics

import pytest

from spike.detector import (
    EDIT_Z_THRESHOLD,
    MIN_ABSOLUTE_EDITS,
    MIN_VIEW_RATIO,
    VIEW_Z_THRESHOLD,
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
        view_stddev=HORMUZ_SD,
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


def test_편집만_통과하면_감지됨이고_확정은_아니다():
    """~~편집만 튀고 조회수가 안 따라오면 버린다~~ → **감지됨으로 통과한다**
    (2026-09-15, WP-90. 기존 문서 경로가 AND → OR).

    편집 전쟁·정리 작업을 거르는 일은 **편집자 하한**(MIN_DISTINCT_EDITORS)이 맡는다 —
    조회수가 그 역할을 겸하면 `Strait_of_Hormuz` 처럼 편집이 안 느는 사건을 통째로
    놓친다(사건 10건 실측, WP-86). 아래 테스트가 그 대체를 고정한다.
    """
    d = detect(
        Window(edit_count=5000, editor_count=2, views=400),  # 조회수 평소
        hormuz_baseline(),
    )
    assert d.is_spike                      # OR 이므로 편집만으로 통과
    assert d.view_ratio < MIN_VIEW_RATIO
    assert "확정" not in d.reason          # 다만 확정은 아니다


def test_편집_전쟁은_편집자_하한이_거른다():
    """한 사람이 5,000번 고쳐도 급증이 아니다. OR 전환으로 조회수 컷이 빠진 자리를
    이 게이트가 메운다 (WP-85)."""
    d = detect(
        Window(edit_count=5000, editor_count=1, views=400),
        hormuz_baseline(),
    )
    assert not d.is_spike
    assert "editors=1" in d.reason


def test_조회수만_튀어도_통과한다():
    """`Strait_of_Hormuz` 유형. 사건 정점에도 편집은 시간당 8건이라 하한 10 미달인데
    조회수는 746배 폭증했다 — AND 였으면 영영 못 잡는다 (WP-86)."""
    d = detect(
        Window(edit_count=8, editor_count=3, views=291824),   # 편집 하한 미달
        hormuz_baseline(),
    )
    assert d.is_spike
    assert d.view_ratio >= MIN_VIEW_RATIO
    assert "조회수 통과" in d.reason


def test_조회수는_배수와_z_를_둘_다_넘어야_한다():
    """~~배수만 봤다~~ → z 도 본다 (WP-90). 조회수가 단독 트리거가 되면서
    "평소의 2배"만으로 발동하면 안 되기 때문이다.

    변동이 원래 큰 문서는 배수가 2를 넘어도 z 가 안 나온다.
    """
    volatile = Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=1000,
                        sample_days=28, view_stddev=5000)   # 표준편차가 평균의 5배
    d = detect(Window(edit_count=1, editor_count=1, views=3000), volatile)
    assert d.view_ratio >= MIN_VIEW_RATIO       # 배수는 3배
    assert not d.is_spike                        # 그런데 z 가 임계 미만


def test_view_stddev_가_없으면_조회수_단독_발동을_안_한다():
    """🔴 -90 이전에 적재된 baseline 행에는 view_stddev 가 없다(NULL).

    그런 행에서 z 를 못 내는데 배수만으로 발동시키면, 마이그레이션 직후 재적재 전까지
    오탐이 쏟아진다. 안전한 쪽(발동 안 함)으로 닫힌다.
    """
    legacy = Baseline(edit_ewma=HORMUZ_MU, edit_stddev=HORMUZ_SD,
                      view_ewma=HORMUZ_MU, sample_days=28)   # view_stddev 기본 None
    d = detect(Window(edit_count=8, editor_count=3, views=291824), legacy)
    assert not d.is_spike
    assert d.view_ratio >= MIN_VIEW_RATIO       # 배수는 충분한데도


def test_조회수_단독_통과의_점수는_조회수만으로_낸다():
    """편집 z 가 None 인 채로 점수를 내야 한다 — 통과 안 한 신호를 섞지 않는다."""
    d = detect(Window(edit_count=8, editor_count=3, views=291824), hormuz_baseline())
    assert d.is_spike and d.spike_score > 0


def test_얇은_baseline_은_절대하한이_막는다():
    """평소 편집 0~1 인 문서가 2건에 z 폭발하는 걸 절대 하한으로 막는다.

    ⚠️ 조회수는 평소 수준으로 둔다. OR 전환(WP-90) 후에는 조회수가 단독으로
    발동할 수 있어서, 조회수를 튀게 두면 **편집 하한을 검사하는 이 테스트가 조회수 때문에
    통과/실패한다.** 한 테스트가 한 관문만 보게 격리한다.
    """
    thin = Baseline(edit_ewma=0.5, edit_stddev=0.5, view_ewma=10, sample_days=28,
                    view_stddev=2)
    # 편집 z 는 3을 넘지만 절대 편집수가 MIN 미만. 조회수는 평소(10 -> 12, 1.2배).
    d = detect(Window(edit_count=3, editor_count=1, views=12), thin)
    assert not d.is_spike


def test_조회수_절대_하한은_아직_없다():
    """🔴 알려진 공백 — WP-87.

    평소 10회 보던 문서가 100회가 되면 배수 10·z 45 로 통과한다. 절대량은 100회다.
    편집 쪽 MIN_ABSOLUTE_EDITS 에 해당하는 게 조회수 쪽엔 없다. OR 전환으로 조회수가
    단독 트리거가 되면서 이 공백의 영향이 커졌다 — 이 테스트는 **현재 동작을 드러내
    두는 것**이지 이 동작이 옳다는 뜻이 아니다.
    """
    tiny = Baseline(edit_ewma=0.5, edit_stddev=0.5, view_ewma=10, sample_days=28,
                    view_stddev=2)
    d = detect(Window(edit_count=1, editor_count=1, views=100), tiny)
    assert d.is_spike        # 100회짜리 신호가 통과한다 (-87 에서 하한을 논의 중)


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
