"""2단계 관문 판정 테스트 (명세 v0.2 §3.2 2~3번, WP-126).

    1단계  사람 편집 >= 1  ->  조회수 검사 후보
    2단계  조회수 급등      ->  확정

숫자는 2026-09-08 에 Wikimedia 에서 직접 받은 것이다 (Strait of Hormuz 2025-06).

🔴 이 파일이 계약의 실행 가능한 정의다. ~~편집 OR 조회수~~(WP-90) 시절
테스트는 걷어냈다 — 그 계약에서 참이던 것들이 지금은 거짓이다.
"""

from __future__ import annotations

import statistics

from spike import detector
from spike.detector import (
    MIN_ABSOLUTE_VIEWS,
    MIN_HUMAN_EDITS,
    MIN_VIEW_RATIO,
    VIEW_Z_THRESHOLD,
    Baseline,
    DecisionStatus,
    Window,
    detect,
    may_spike,
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
    assert max(zs) < VIEW_Z_THRESHOLD, f"평상시 최대 z={max(zs):.1f} 가 임계를 넘음"


def test_사건_첫날부터_z_임계를_넘는다():
    """미탐 확인. 사건 시작(6/12)이 잡혀야 한다."""
    assert view_z(HORMUZ_EVENT["2025-06-12"]) >= VIEW_Z_THRESHOLD
    assert view_z(HORMUZ_EVENT["2025-06-22"]) >= VIEW_Z_THRESHOLD


def test_사건_전날은_안_잡힌다():
    assert view_z(HORMUZ_EVENT["2025-06-11"]) < VIEW_Z_THRESHOLD


# --- detect() 통합: 2단계 관문 ---

def hormuz_baseline(sample_days: int = 28) -> Baseline:
    return Baseline(
        edit_ewma=HORMUZ_MU,
        edit_stddev=HORMUZ_SD,
        view_ewma=HORMUZ_MU,
        sample_days=sample_days,
        view_stddev=HORMUZ_SD,
    )


# ---------------------------------------------------------------- 1단계

def test_편집이_없으면_조회수가_아무리_튀어도_후보가_아니다():
    """1단계가 후보를 만든다. 편집 0 이면 조회수를 볼 필요가 없다."""
    d = detect(Window(edit_count=0, editor_count=0, views=291_824), hormuz_baseline())
    assert d.status is DecisionStatus.REJECTED
    assert "1단계" in d.reason


def test_사람_편집_1건이면_후보가_된다():
    """🔴 ~~z>=3 AND >=10건 AND 편집자>=2~~ → **1건**이면 된다.

    명세 §3.2 2번: "편집 z-score·편집 10건·편집자 2명 기준은 이 단계의 관문으로
    사용하지 않는다". 편집 1건·편집자 1명이어도 조회수가 튀면 확정이다.
    """
    d = detect(Window(edit_count=MIN_HUMAN_EDITS, editor_count=1, views=291_824),
               hormuz_baseline())
    assert d.status is DecisionStatus.CONFIRMED


# ---------------------------------------------------------------- 2단계

def test_조회수가_안_오면_확정도_폐기도_아니다():
    """🔴 계약의 핵심. ~~편집만으로 '감지됨'~~ → **후보 대기**다.

    확정과 섞으면 조회수를 안 본 문서가 이슈로 나가고, 폐기와 섞으면 조회수가 늦게
    오는 문서를 영영 못 잡는다. 두 실패가 반대 방향이라 상태를 셋으로 둔다.
    """
    d = detect(Window(edit_count=50, editor_count=9, views=None), hormuz_baseline())
    assert d.status is DecisionStatus.PENDING_VIEWS
    assert not d.is_spike          # 저장하면 안 된다
    assert d.is_pending            # 재판정 대상이다
    assert d.spike_score == 0.0    # 점수는 확정된 뒤에만 의미가 있다


def test_조회수가_도착했는데_급등이_아니면_폐기한다():
    """대기가 아니라 폐기다 — 다시 볼 이유가 없다."""
    d = detect(Window(edit_count=5_000, editor_count=40, views=420), hormuz_baseline())
    assert d.status is DecisionStatus.REJECTED
    assert not d.is_pending


def test_편집이_아무리_튀어도_조회수가_관문이다():
    """~~편집 통과 OR 조회수 통과~~(WP-90) 폐기 확인.

    편집 z 가 수백이어도 조회수가 평소면 확정되지 않는다. 편집 전쟁·정리 작업을
    거르던 편집자 하한(WP-85)의 자리를 이 관문이 대신한다.
    """
    d = detect(Window(edit_count=9_836, editor_count=50, views=430), hormuz_baseline())
    assert d.status is DecisionStatus.REJECTED
    assert d.edit_z > 100          # 편집은 확실히 튀었는데도


def test_조회수_관문은_배수와_z와_절대량_셋_다_본다():
    """명세 §3.2 3번 "z >= 3 AND 평소의 2배 이상 AND 현재 조회수 100 이상"."""
    base = hormuz_baseline()

    assert detect(Window(1, 1, 1_007), base).status is DecisionStatus.CONFIRMED

    # 배수만 모자람 — z 는 넘지만 2배 미만
    near = int(HORMUZ_MU * 1.5)
    d = detect(Window(1, 1, near), base)
    assert d.view_ratio < MIN_VIEW_RATIO
    assert d.status is DecisionStatus.REJECTED


def test_변동이_큰_문서는_배수를_넘어도_z가_막는다():
    volatile = Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=1_000,
                        sample_days=28, view_stddev=5_000)
    d = detect(Window(1, 1, 3_000), volatile)
    assert d.view_ratio >= MIN_VIEW_RATIO
    assert d.status is DecisionStatus.REJECTED


def test_꼬리_문서는_절대_하한이_막는다():
    """평소 1~3회/일이던 `Hurricane_Helene` 이 8회로 통과했었다 (WP-87)."""
    tail = Baseline(edit_ewma=0.5, edit_stddev=0.5, view_ewma=2,
                    sample_days=28, view_stddev=0.8)
    d = detect(Window(1, 1, 8), tail)
    assert d.view_ratio >= MIN_VIEW_RATIO      # 배수·z 는 넘는데도
    assert d.status is DecisionStatus.REJECTED


def test_인기_문서는_절대_하한에_영향_안_받는다():
    popular = Baseline(edit_ewma=100, edit_stddev=10, view_ewma=50_000,
                       sample_days=28, view_stddev=5_000)
    assert detect(Window(1, 1, 500_000), popular).status is DecisionStatus.CONFIRMED
    assert detect(Window(1, 1, 55_000), popular).status is DecisionStatus.REJECTED


# ---------------------------------------------------------------- 표본이 없을 때

def test_기준선이_없으면_절대_하한만으로_판정한다():
    """명세 §3.2 3번: "표본이 없거나 기준 조회수가 0이면 현재 조회수 >= 100 을
    0에서의 유의미한 급등으로 본다".

    ~~기준선이 없으면 조회수 관문을 닫는다~~(WP-90) → 열렸다. 사건 당일
    생긴 문서가 대부분 여기 걸리는데, 닫아 두면 그 문서를 영영 못 잡는다.
    """
    assert detect(Window(1, 1, MIN_ABSOLUTE_VIEWS), None).status is DecisionStatus.CONFIRMED
    assert detect(Window(1, 1, MIN_ABSOLUTE_VIEWS - 1), None).status is DecisionStatus.REJECTED


def test_기준_조회수가_0이어도_같은_규칙이다():
    zero = Baseline(edit_ewma=5, edit_stddev=2, view_ewma=0, sample_days=28,
                    view_stddev=0)
    assert detect(Window(1, 1, 500), zero).status is DecisionStatus.CONFIRMED
    assert detect(Window(1, 1, 50), zero).status is DecisionStatus.REJECTED


def test_얇은_기준선도_절대_하한만으로_판정한다():
    thin = Baseline(edit_ewma=5, edit_stddev=2, view_ewma=1_000, sample_days=3,
                    view_stddev=100)
    d = detect(Window(1, 1, 500), thin)
    assert d.is_new_page                          # 기준선이 얇다는 표시
    assert d.status is DecisionStatus.CONFIRMED   # 배수 0.5 인데도 — 절대 하한만 본다


def test_표준편차를_못_내면_배수와_절대량으로_판정한다():
    """⚠️ 명세 문장의 **해석**이다 (detector `_judge_views` 주석).

    평균은 있는데 표준편차가 없으면 z 를 못 낸다. 배수까지 버리면 기준선을 들고도
    안 쓰는 셈이라 더 느슨해져서, 배수는 유지한다.
    """
    no_sd = Baseline(edit_ewma=5, edit_stddev=2, view_ewma=1_000, sample_days=28,
                     view_stddev=None)
    assert detect(Window(1, 1, 5_000), no_sd).status is DecisionStatus.CONFIRMED   # 5배
    assert detect(Window(1, 1, 1_200), no_sd).status is DecisionStatus.REJECTED    # 1.2배


# ---------------------------------------------------------------- 프리필터

def test_may_spike_는_확정의_상위집합이다():
    """🔴 이게 깨지면 bulk 리플레이(WP-109)가 **진짜 급증을 조용히 버린다.**"""
    base = hormuz_baseline()
    cases = [
        Window(0, 0, 291_824), Window(1, 1, 291_824), Window(1, 1, 50),
        Window(50, 9, None), Window(9_836, 50, 430),
    ]
    for w in cases:
        if detect(w, base).is_spike:
            assert may_spike(w), w


def test_may_spike_는_조회수_미도착을_안_버린다():
    """후보 대기가 프리필터에서 사라지면 재판정 대상이 없어진다."""
    assert may_spike(Window(edit_count=1, editor_count=1, views=None))
    assert not may_spike(Window(edit_count=0, editor_count=0, views=None))


# ---------------------------------------------------------------- 점수

def test_점수는_조회수_급등_강도로_낸다():
    """명세 §3.2 4번 — `pulse_score` 는 조회수 급등 강도 중심이다."""
    base = hormuz_baseline()
    weak = detect(Window(1, 1, 1_007), base)        # z 11
    strong = detect(Window(1, 1, 291_824), base)    # z 5311
    assert 0 < weak.spike_score < strong.spike_score


def test_극단값이_점수를_지배하지_않는다():
    """z 5311 이 날것으로 들어가면 버블 하나가 화면을 다 먹는다."""
    base = hormuz_baseline()
    assert detect(Window(1, 1, 291_824), base).spike_score < 20


def test_편집은_점수에_안_들어간다():
    """편집은 관문도 아니고 점수도 아니다 — 후보를 만드는 신호일 뿐이다."""
    base = hormuz_baseline()
    few = detect(Window(1, 1, 291_824), base)
    many = detect(Window(9_836, 50, 291_824), base)
    assert few.spike_score == many.spike_score


# ------------------------- 1단계 대체 경로 (WP-210, 기본 꺼짐)

def test_노브가_꺼져_있으면_편집_없는_윈도우는_탈락한다():
    """🔴 기본값이 안 바뀌는 것을 고정한다. 이 테스트가 깨지면 계약이 조용히 바뀐 것이다."""
    w = Window(edit_count=0, editor_count=0, views=6_893, mobile_views=3_594)
    assert detector.passes_first_gate(w) is False
    assert detect(w, None).status is DecisionStatus.REJECTED


def test_모바일이_충분하면_편집_없이도_1단계를_통과한다():
    """2026-08-19 Moderna — 60배 급등인데 당일 편집 0건, 모바일 52.1%."""
    w = Window(edit_count=0, editor_count=0, views=6_893, mobile_views=3_594)
    assert detector.passes_first_gate(w, view_only_gate=True) is True
    assert detect(w, None, view_only_gate=True).status is DecisionStatus.CONFIRMED


def test_데스크톱_단일_채널_급등은_노브를_켜도_탈락한다():
    """🔴 Roblox 2026-08-10 — 하루 478만 조회(674배)인데 모바일 0.1% 인 크롤러다.

    편집 관문이 사실상 유일한 봇 필터였다. 그냥 열면 이게 1위로 올라온다.
    """
    w = Window(edit_count=0, editor_count=0, views=4_781_244, mobile_views=3_746)
    assert detector.passes_first_gate(w, view_only_gate=True) is False
    d = detect(w, None, view_only_gate=True)
    assert d.status is DecisionStatus.REJECTED
    assert "모바일" in d.reason


def test_모바일을_안_잰_윈도우는_오른쪽_가지를_열지_않는다():
    """⚠️ V15 이전 적재분은 mobile_views 가 None 이다 — '모바일 0' 이 아니라 '미측정'.

    열어 주면 안 잰 값이 통과 근거가 되고, 0 으로 치면 과거 구간이 전부 봇이 된다.
    """
    w = Window(edit_count=0, editor_count=0, views=500_000, mobile_views=None)
    assert detector.passes_first_gate(w, view_only_gate=True) is False


def test_조회수_하한을_못_넘으면_모바일이_높아도_탈락한다():
    w = Window(edit_count=0, editor_count=0, views=99, mobile_views=90)
    assert detector.passes_first_gate(w, view_only_gate=True) is False


def test_조회수_미도착이면_오른쪽_가지는_안_열린다():
    """편집도 없고 조회수도 없으면 판단 근거가 아무것도 없다 — 대기로 둘 값도 없다."""
    w = Window(edit_count=0, editor_count=0, views=None, mobile_views=None)
    assert detector.passes_first_gate(w, view_only_gate=True) is False


def test_편집이_있으면_모바일과_무관하게_기존대로_간다():
    """노브를 켜도 왼쪽 가지는 그대로다. 골든데이 경로가 안 바뀌는 것을 고정한다."""
    w = Window(edit_count=3, editor_count=2, views=657_119, mobile_views=414_126)
    assert detector.passes_first_gate(w, view_only_gate=True) is True
    assert detector.passes_first_gate(w) is True
