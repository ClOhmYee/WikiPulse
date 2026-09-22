"""급증 판정 수식. 순수 함수라 Spark 없이 테스트된다.

명세 v0.2 §3.2 2~3번의 **2단계 관문**을 수식으로 확정한다
(2026-09-18, WP-126. 문서분은 WP-118 에서 먼저 나갔다).

    1단계  사람 편집이 1건 이상 발생하면 조회수 검사 후보가 된다.
    2단계  조회수가 급등해야 `spike` 로 확정한다.

🔴 **1단계는 관문이 아니라 후보 선별이다.** 1단계만 통과한 문서는 `spike` 도 사용자
이슈도 아니다 — `DecisionStatus.PENDING_VIEWS`(후보 대기)로 두었다가 조회수가 도착하면
다시 판정한다. 조회수가 도착했는데 급등이 아니면 폐기한다.

~~편집 z≥3 AND 절대 편집수≥10 AND 편집자≥2~~ → **관문에서 뺐다** (명세 §3.2 2번:
"편집 z-score·편집 10건·편집자 2명 기준은 이 단계의 관문으로 사용하지 않는다").
상수는 아래에 남아 있지만 **판정에 안 쓰인다** — 왜 남겼는지는 그 자리에 적었다.

~~편집 통과 OR 조회수 통과~~ (WP-90) → 폐기. OR 은 "편집이 안 느는 사건
유형"(Hormuz)을 잡으려던 것인데, 2단계 계약은 그 문제를 **조회수를 최종 관문으로
올려서** 푼다 — 편집은 후보를 만드는 신호일 뿐이다.

1단계 대체 경로 (WP-210, **기본 꺼짐**)
    `detect(..., view_only_gate=True)` 를 주면 1단계가
        사람 편집 >= 1  **또는**  (조회수 >= 100 AND 모바일 비중 >= 25%)
    가 된다. 2단계(조회수 급등)는 그대로다.
    🔴 위의 폐기된 `-90` 과 다른 점은 **오른쪽 가지에 봇 필터가 붙어 있다**는 것이다.
       편집 관문이 사실상 유일한 봇 필터였기 때문에(`Roblox` 2026-08-10, 하루 478만
       조회·674배·모바일 0.1%), 그냥 열면 크롤러가 그대로 들어온다.
    왜 여는가: 기업 문서는 편집이 사건보다 느리다. 2026-08-19 Moderna–Merck Phase 3 는
       문서 5개가 60배까지 급등했는데 **당일 편집이 0건**이라 현행 1단계에서 탈락한다.
    근거·수치: `ai/spec-evidence/gate-review/RESULT.md`. 채택 여부는 WP-210.

조회수 관문 (명세 §3.2 3번 그대로)
    표본 있음  z >= 3  AND  평소의 2배 이상  AND  현재 조회수 >= 100   (셋 다)
    표본 없음  현재 조회수 >= 100                                     ← 0 에서의 급등
    "표본 없음" = 기준선이 없거나 `view_ewma` 가 0 이거나 표준편차를 못 내는 경우다.

조회수 임계 z=3 의 근거 (2026-09-08 실측, Strait of Hormuz 2025-06)
    평상시(사건 전 18일) 391 ± 55, z 범위 -1.3 ~ +1.9
    사건 시작(6/12) z = 11.2 (2.6배)  ·  정점(6/22) z = 5311 (746배)
    z >= 3 이 평상시 최대와 사건 최소 사이에 깨끗이 앉는다. 배수 2 는 6/12 의 2.6배가
    최저 신호라 거기서 왔다.

절대 하한 100 의 근거 (2026-09-15 실측, WP-87)
    배수도 z 도 **상대값**이라 평소 값이 작으면 절대량이 무의미해도 통과한다.
    `Hurricane_Helene` 이 평소 1~3회/일에서 **8회**가 되자 `z 8.1 · 8.9배` 로 통과했다
    — 진짜 폭증은 9/25(719회)부터다. 사건 10건 sweep 에서 100·500 결과가 같고
    1000 부터 진짜 신호가 깎여(Hormuz 6/12 → 6/13) 평평한 구간의 아래쪽 끝을 골랐다.

⚠️ **이 전환으로 편집 덤프만 재생하는 경로는 아무것도 확정하지 못한다.**
`views=None` 이 전부 후보 대기가 된다. 버그가 아니라 계약이다 — 명세 §3.2 9번이
리플레이도 시간별 조회수 원본을 쓰라고 정했다. WP-85 의 재현율 10/12 ·
대조군 오탐 49건 같은 수치는 **이 경로로 더는 못 잰다.**

⚠️ **편집자 하한이 관문에서 빠졌다.** 1인 연속 편집 오탐을 395 → 101건으로 줄였던
게이트다(WP-85). 새 계약은 그 일을 조회수 최종 관문이 대신한다고 본다 —
혼자 문서를 정리해도 조회수는 안 튀기 때문이다. **아직 실측으로 확인 안 됐다.**
조회수를 실제로 넣는 후속이 선 뒤에 재확인한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# 실측 기반 기본 임계. 운영하며 조정 가능하게 상수로 뺀다.

#: 1단계 관문 — 사람 편집 최소 건수. 봇 제외는 상류(producer·배치 집계)가 이미 한다.
#: 명세 §3.2 2번 "문서에 사람의 편집이 1건 이상 발생하면 조회수 검사 후보가 된다".
MIN_HUMAN_EDITS = 1

VIEW_Z_THRESHOLD = 3.0
MIN_VIEW_RATIO = 2.0      # 조회수 최소 배수. z 만으로는 부족(6/12 가 2.6배)

#: 조회수 절대 하한 (WP-87, 2026-09-15 실측). 2단계 관문의 세 조건 중 하나이고,
#: 표본이 없을 때는 **유일한 조건**이다 — 명세 §3.2 3번 "현재 조회수 >= 100 을 0에서의
#: 유의미한 급등으로 본다".
#:
#: 사건 10건 전수 sweep:
#:     하한 없음  `Hurricane_Helene` 이 평소 1~3회/일에서 8회로 통과(z 8.1·8.9배).
#:                대조군 434 문서·일에서 4건 발동
#:     100        Helene 이 9/25(719회)로 교정되고 나머지 9건 값 불변. 대조군 3건
#:     500        100 과 완전히 동일
#:     1000       Helene 9/26, `Strait_of_Hormuz` 6/12 -> 6/13 (진짜 신호가 하루 늦는다)
#: 100~500 이 평평해서 아래쪽 끝을 골랐다 — 재현율 여유를 남기는 쪽이다.
#:
#: ⚠️ 문서 인기도에 비례하지 않는 **고정값**이다. 평소 100만 조회 문서엔 영향이 없고
#: 꼬리 문서만 막는다.
MIN_ABSOLUTE_VIEWS = 100

#: 1단계 대체 경로(WP-210)의 모바일 비중 하한. **기본은 꺼짐**이고
#: `detect(..., view_only_gate=True)` 로 명시해야 열린다.
#:
#: 왜 필요한가
#:   사고 문서와 기업 문서는 편집 속도가 다르다. `Air India Flight 171` 은 분 단위로
#:   편집되지만 `Moderna` 는 임상 결과가 나와도 편집이 이틀 늦는다. 2026-08-19
#:   Moderna–Merck Phase 3 는 문서 5개가 동시 급등(60배)했는데 **당일 편집 0건**이라
#:   현행 1단계에서 통째로 탈락한다. 상장사 급등 후보 174건 중 편집 게이트 통과는 24%다.
#:
#: 🔴 왜 조회수만으로 열지 않고 모바일 비중을 같이 보나
#:   편집 게이트는 사실상 **유일한 봇 필터**였다. 빼기만 하면 `Roblox` 2026-08-10
#:   (하루 478만 조회·674배)이 그대로 1위로 올라온다 — 그건 데스크톱 단일 채널
#:   크롤러였다(모바일 0.1%, 평소 60%).
#:
#: 값 0.25 의 근거 (2026-09-22 실측, `ai/spec-evidence/gate-review/`)
#:   사건 52~64% (Air India 63.1 · Boeing 787 63.9 · Moderna 52.1 · MRNA-4157 53.5)
#:   봇   0.1~4% (Roblox 0.1 · Google 4.0 · Lowe's 2.4)
#:   겹치는 구간이 없어 그 사이 아무 데나 둘 수 있다. 사건 쪽 여유를 크게 남겼다.
#:   ⚠️ **기업 문서 174건 표본에서 나온 첫 컷이다.** 사건 문서 쪽 분포는 아직 안 쟀다.
MIN_MOBILE_RATIO = 0.25

#: 🔴 **아래 셋은 판정 관문이 아니다** (2026-09-18, WP-126).
#: 명세 §3.2 2번이 "편집 z-score·편집 10건·편집자 2명 기준은 이 단계의 관문으로
#: 사용하지 않는다" 로 못박았다. 지우지 않고 남긴 이유는 둘이다:
#:   1. `edit_z` 는 여전히 **진단값**으로 SpikeDecision 에 실려 로그·분석에 쓰인다
#:   2. 되돌릴 때 근거를 다시 찾지 않게 — 값의 실측 근거가 여기 붙어 있다
#: ⚠️ 새 코드에서 이 셋으로 무언가를 거르지 말 것. 거르면 명세와 갈린다.
EDIT_Z_THRESHOLD = 3.0    # ~~편집 z 관문~~ → 진단값 전용
MIN_ABSOLUTE_EDITS = 10   # ~~절대 편집수 관문~~ → 미사용
MIN_DISTINCT_EDITORS = 2  # ~~편집자 하한 관문(WP-85)~~ → 미사용

#: 조회수 기준선을 "표본 있음" 으로 볼 최소 관측일. 이보다 얇으면 z·배수를 못 믿고
#: 절대 하한(MIN_ABSOLUTE_VIEWS)만으로 판정한다 — 명세 §3.2 3번의 "표본이 없거나
#: 기준 조회수가 0이면" 에 해당한다.
#: ⚠️ ~~"신규 문서로 취급"~~ 이라는 표현을 버렸다. 명세는 **문서 생성 후 28일**을
#: 기준으로 말하는데 이 값은 **관측일 수**라 서로 다른 것이다. 생성 28일 미만 문서에
#: 생성 시각~현재 직전 구간만으로 기준선을 만드는 건 기준선 산출(baseline_rows) 책임이고,
#: detect() 는 받은 기준선이 얇은지만 본다.
MIN_BASELINE_SAMPLE_DAYS = 7


@dataclass(frozen=True)
class Baseline:
    """문서 × 시간대(0~23, UTC) 기준선. page_baseline 테이블 한 행."""
    edit_ewma: float
    edit_stddev: float | None
    view_ewma: float | None
    sample_days: int
    #: 조회수 가중 표준편차. None 이면 조회수 z 를 못 낸다 -> 조회수 단독 발동 안 함
    #: (WP-90). 기본값 None 인 이유는 -90 이전에 적재된 baseline 행에 이 값이
    #: 없어서다 — 그런 행은 조회수 관문이 닫힌 채로 동작한다(안전한 쪽).
    view_stddev: float | None = None

    @property
    def is_thin(self) -> bool:
        return self.sample_days < MIN_BASELINE_SAMPLE_DAYS


@dataclass(frozen=True)
class Window:
    """한 문서의 한 윈도우 관측치."""
    edit_count: int
    editor_count: int
    views: int | None  # 조회수는 늦게 와서 판정 시점엔 None 일 수 있다
    #: `views` 중 모바일 몫 (V15, WP-210). `views` 에 포함된 부분집합이다.
    #: None 은 **"모바일 0" 이 아니라 "안 쟀다"** — V15 이전 적재분이 그렇다.
    mobile_views: int | None = None

    @property
    def mobile_ratio(self) -> float | None:
        """모바일 비중 0.0~1.0. 안 쟀거나 조회수가 0/미도착이면 None."""
        if self.mobile_views is None or not self.views:
            return None
        return self.mobile_views / self.views


class DecisionStatus(str, Enum):
    """판정 결과 3상태 (명세 §3.2 3번).

    🔴 `PENDING_VIEWS` 를 `REJECTED` 와 합치면 **조회수가 늦게 오는 문서를 영영 못 잡는다.**
    합치는 순간 "아직 못 봤다" 와 "보고 아니었다" 가 같은 값이 돼서, 재판정 대상을
    고를 수 없다. 명세가 둘을 명시적으로 가른 이유다.
    """

    #: 2단계까지 통과. `spike` 로 저장한다.
    CONFIRMED = "confirmed"
    #: 1단계(편집)는 통과했는데 조회수가 아직 안 왔다. **저장하지 않는다.**
    #: 후보로 들고 있다가 조회수가 도착하면 다시 판정한다.
    PENDING_VIEWS = "pending_views"
    #: 편집이 없거나, 조회수가 도착했는데 급등이 아니다. 폐기한다.
    REJECTED = "rejected"


@dataclass(frozen=True)
class SpikeDecision:
    status: DecisionStatus
    is_new_page: bool
    edit_z: float | None
    view_ratio: float | None
    spike_score: float
    reason: str

    @property
    def is_spike(self) -> bool:
        """2단계까지 통과했는가. **후보 대기는 False 다.**

        ~~조회수가 없으면 편집만으로 True~~ → 2단계 계약에서 바뀌었다
        (2026-09-18, WP-126). 기존 소비자가 이 이름을 그대로 쓰되
        의미는 "확정" 하나로 좁아졌다.
        """
        return self.status is DecisionStatus.CONFIRMED

    @property
    def is_pending(self) -> bool:
        """조회수 도착을 기다리는 후보인가. 저장하지 말고 다시 판정할 대상이다."""
        return self.status is DecisionStatus.PENDING_VIEWS


def _z(value: float, mean: float, stddev: float | None) -> float | None:
    if stddev is None or stddev <= 0:
        return None
    return (value - mean) / stddev


def may_spike(window: Window) -> bool:
    """기준선을 **읽기 전에** "어떤 기준선이 와도 확정일 수 없는" 윈도우를 거른다.

    🔴 **판정이 아니다. 필요조건일 뿐이다** — `detect(...).is_spike` 가 참이면 이 함수도
    반드시 참이다(역은 성립하지 않는다). 임계값은 여기서 새로 정하지 않고 위 상수를
    그대로 본다 — 값을 복제하면 한쪽만 고쳐졌을 때 조용히 갈린다.

    왜 필요한가 (WP-109, bulk 리플레이)
        `SpikeRuntime.evaluate` 는 윈도우마다 `page_baseline` 을 먼저 읽는다. 문서 하나당
        왕복 1회라 60일 전체(문서 수백만)를 그대로 넣으면 왕복이 문서 수만큼 난다.

    근거 (2단계 계약, WP-126)
        확정은 1단계(편집 >= MIN_HUMAN_EDITS)와 2단계(조회수 >= MIN_ABSOLUTE_VIEWS)를
        **둘 다** 통과해야 한다. 어느 쪽 하한도 기준선과 무관한 절대값이라 여기서 본다.

    ⚠️ **조회수 미도착(None)은 통과시킨다.** 확정의 필요조건만 따지면 걸러도 되지만,
    그러면 후보 대기 윈도우가 기준선도 못 읽고 조용히 사라진다. 상위집합으로 두는 쪽이
    안전하다 — 프리필터는 상위집합이기만 하면 정확성이 깨지지 않는다.
    """
    if window.edit_count < MIN_HUMAN_EDITS:
        return False
    return window.views is None or window.views >= MIN_ABSOLUTE_VIEWS


def passes_first_gate(window: Window, *, view_only_gate: bool = False) -> bool:
    """1단계 관문 — 사람 편집, 또는(노브를 켰을 때) 봇이 아닌 조회수.

        기본           사람 편집 >= MIN_HUMAN_EDITS
        view_only_gate 위 **또는** (조회수 >= MIN_ABSOLUTE_VIEWS AND 모바일 >= 25%)

    🔴 **OR 의 오른쪽은 폐기된 `-90`(편집 OR 조회수) 부활이 아니다.** 거기서 뺀 것은
    "편집 없이 조회수만으로 통과"였고, 여기서는 그 자리에 **봇 필터**를 세운다.
    모바일 비중이 없으면(=안 쟀으면) 오른쪽 가지는 열리지 않는다 — 열어 주면 V15
    이전 적재분(mobile_views 기본 0)이 전부 봇으로 몰리거나, 반대로 측정 안 된 값이
    통과 근거가 된다.

    ⚠️ 조회수 미도착(None)은 오른쪽 가지를 **열지 않는다.** 편집이 없으면 판단 근거가
    아직 아무것도 없다 — 대기로 둘 값도 없어서 후보가 되지 못한다.
    """
    if window.edit_count >= MIN_HUMAN_EDITS:
        return True
    if not view_only_gate:
        return False
    ratio = window.mobile_ratio
    if ratio is None:
        return False
    return (window.views or 0) >= MIN_ABSOLUTE_VIEWS and ratio >= MIN_MOBILE_RATIO


def detect(window: Window, baseline: Baseline | None, *,
           view_only_gate: bool = False) -> SpikeDecision:
    """2단계 관문 판정 (명세 v0.2 §3.2 2~3번, WP-126).

        1단계  사람 편집 >= MIN_HUMAN_EDITS  ->  조회수 검사 후보
        2단계  조회수 급등                    ->  확정

    반환은 3상태다(`DecisionStatus`). 조회수 미도착은 **확정도 폐기도 아니다.**
    """
    if not passes_first_gate(window, view_only_gate=view_only_gate):
        ratio = window.mobile_ratio
        if view_only_gate and window.edit_count < MIN_HUMAN_EDITS and ratio is not None:
            why = (f"1단계 미통과 — 편집 {window.edit_count} · "
                   f"조회수 {window.views} · 모바일 {ratio:.1%}")
        else:
            why = f"1단계 미통과 — 사람 편집 {window.edit_count} < {MIN_HUMAN_EDITS}"
        return SpikeDecision(
            status=DecisionStatus.REJECTED,
            is_new_page=_thin(baseline),
            edit_z=_edit_z(window, baseline),
            view_ratio=None,
            spike_score=0.0,
            reason=why,
        )

    if window.views is None:
        # 1단계만 통과. 저장하지 않고 들고 있다가 조회수가 오면 다시 판정한다.
        return SpikeDecision(
            status=DecisionStatus.PENDING_VIEWS,
            is_new_page=_thin(baseline),
            edit_z=_edit_z(window, baseline),
            view_ratio=None,
            spike_score=0.0,
            reason="1단계 통과, 조회수 미도착 — 후보 대기",
        )

    return _judge_views(window, baseline)


def _judge_views(window: Window, baseline: Baseline | None) -> SpikeDecision:
    """2단계 — 조회수 급등 판정. 여기 오면 편집 1건 이상이고 조회수도 도착했다."""
    thin = _thin(baseline)
    edit_z = _edit_z(window, baseline)
    views = window.views or 0

    enough_absolute = views >= MIN_ABSOLUTE_VIEWS

    if thin or not baseline.view_ewma or baseline.view_ewma <= 0:
        # 표본이 없거나 기준 조회수가 0 — 명세 §3.2 3번: "현재 조회수 >= 100 을
        # 0에서의 유의미한 급등으로 본다". 배수·z 는 낼 수가 없다(0 으로 나눈다).
        return SpikeDecision(
            status=DecisionStatus.CONFIRMED if enough_absolute else DecisionStatus.REJECTED,
            is_new_page=thin,
            edit_z=edit_z,
            view_ratio=None,
            spike_score=_score(None, views) if enough_absolute else 0.0,
            reason=("조회수 기준선 없음 — 절대 하한 통과(0 에서의 급등)" if enough_absolute
                    else f"조회수 기준선 없음 — {views}회 < {MIN_ABSOLUTE_VIEWS}"),
        )

    ratio = views / baseline.view_ewma
    view_z = _z(views, baseline.view_ewma, baseline.view_stddev)

    if view_z is None:
        # 평균은 냈는데 표준편차를 못 낸다(관측 1일 등). 명세의 "표준편차를 계산할
        # 표본이 없" 는 경우로 본다 — z 는 빼고 배수·절대 하한만 요구한다.
        # ⚠️ 이건 명세 문장의 해석이다. 배수까지 버리면 평소 10회 문서가 100회로
        # 통과하는데, 그건 기준선을 들고도 안 쓰는 셈이라 더 느슨하다.
        passed = enough_absolute and ratio >= MIN_VIEW_RATIO
        return SpikeDecision(
            status=DecisionStatus.CONFIRMED if passed else DecisionStatus.REJECTED,
            is_new_page=thin,
            edit_z=edit_z,
            view_ratio=ratio,
            spike_score=_score(None, views) if passed else 0.0,
            reason=(f"표준편차 없음 — 배수 {ratio:.1f}·{views}회로 판정"
                    f"({'통과' if passed else '미달'})"),
        )

    passed = enough_absolute and ratio >= MIN_VIEW_RATIO and view_z >= VIEW_Z_THRESHOLD
    return SpikeDecision(
        status=DecisionStatus.CONFIRMED if passed else DecisionStatus.REJECTED,
        is_new_page=thin,
        edit_z=edit_z,
        view_ratio=ratio,
        spike_score=_score(view_z, views) if passed else 0.0,
        reason=("2단계 통과 — 조회수 급등 확정" if passed
                else f"조회수 미달 (배수={ratio:.1f}, z={view_z:.1f}, {views}회)"),
    )


def _thin(baseline: Baseline | None) -> bool:
    """조회수 기준선이 없거나 얇은가. `SpikeDecision.is_new_page` 로 나간다.

    ⚠️ 이름이 `is_new_page` 라 "신규 문서" 로 읽히지만 실제로는 **기준선 두께**다.
    명세가 말하는 "문서 생성 후 28일" 과 다른 축이다 — 오래된 문서도 관측이 드물면
    얇고(WP-88 실측: 1h 슬롯에서 도달률 4.8%), 그 경우 절대 하한만으로 판정한다.
    """
    return baseline is None or baseline.is_thin


def _edit_z(window: Window, baseline: Baseline | None) -> float | None:
    """편집 z — **진단값이다. 판정에 안 쓴다** (WP-126).

    로그·분석에서 "편집도 같이 튀었나" 를 보려고 계속 싣는다.

    🔴 **기준선이 없거나 얇으면 None 이다.** 얇은 표본(sample_days < 7)에서 낸 z 는
    숫자는 나오지만 통계적으로 의미가 없다 — 관측 두세 개로 낸 표준편차라 조금만
    튀어도 z 가 폭발한다. 숫자를 실어 보내면 로그를 읽는 사람이 그걸 신뢰한다.
    `spike.edit_z` 가 NULL 허용인 것도 이 경로 때문이다(V1).
    """
    if _thin(baseline):
        return None
    return _z(window.edit_count, baseline.edit_ewma, baseline.edit_stddev)


def _score(view_z: float | None, views: int) -> float:
    """급등도. 버블맵 버블 크기·피드 정렬에 쓴다.

    **조회수 급등 강도 중심**이다 (명세 §3.2 4번: "클러스터 `pulse_score` 는 조회수
    급등 강도를 중심으로 계산한다"). 편집은 2단계 계약에서 관문이 아니라 후보 신호라
    점수에서도 뺐다 — ~~편집 z 와 조회수 z 의 곱~~ (WP-93).

    z 를 못 내는 경우(표본 없음·표준편차 0)는 절대 조회수로 대신한다. 두 값이 단위가
    달라 한 축에 섞이는 문제가 -93 에서 지적됐는데, 여기서는 **log 를 씌운 뒤 같은
    스케일로 맞춘다** — z 든 조회수든 log1p 한 값이라 자릿수 차가 눌린다.

    log1p 로 누르는 이유는 그대로다: z 5311 이 날것으로 들어가면 버블 하나가 화면을
    다 먹는다.
    """
    import math

    if view_z is not None:
        return round(math.log1p(max(0.0, view_z)), 3)
    # 표본이 없어 z 가 없다. 절대 조회수로 — 100회면 4.6, 10만회면 11.5.
    return round(math.log1p(max(0, views)), 3)
