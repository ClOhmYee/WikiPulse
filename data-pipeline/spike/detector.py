"""급증 판정 수식 (WP-38). 순수 함수라 Spark 없이 테스트된다.

명세 §3.2 의 "편집 급증 AND 조회수 급등" 을 수식으로 확정한다.

실측으로 정한 것 (2026-09-08, Strait of Hormuz 2025-06 조회수)
    평상시(사건 전 18일): 조회수 391 ± 55, z 범위 -1.3 ~ +1.9
    사건 시작(6/12):       z = 11.2  (2.6배)  ← 첫 신호
    정점(6/22):            z = 5311  (746배)
    z >= 3 이 평상시 최대(1.9)와 사건 최소(11.2) 사이에 깨끗이 앉는다.
    오탐 없이 사건을 다 잡는다. → 편집·조회수 임계 z = 3.

급증에는 두 종류가 있다 (Milton 실측에서 드러남)
    1. 기존 문서 급증  — baseline 이 있다. z-score 로 판정.
    2. 신규 문서       — baseline 이 없다(문서가 방금 생김). z 계산 불가.
                         절대 편집수·조회수 하한으로 판정한다.

편집자 하한이 필요한 이유 (2026-09-15 실측, WP-85)
    편집 수만 보면 한 사람이 문서를 몰아서 정리한 것과 여러 사람이 사건을 고치는 것이
    구분되지 않는다. 실덤프 4개월(2025-05·06, 2024-09·10)로 재생해 보니 상시 편집
    문서(목록·타임라인·TV 시즌)가 대조군 14개 전부에서 오탐을 냈고 총 395건이었다.
    `editor_count >= 2` 하나를 걸자 101건으로 줄었고(74% 감소) 대상 재현율은 그대로였다.
    명세 §3.2 2번의 "1인 반복 편집은 거른다"가 여태 코드에 없던 부분이다.

절대 하한이 반드시 필요한 이유
    평소 편집이 0~1 건인 문서는 표준편차가 작아 2건만 돼도 z 가 폭발한다.
    Strait of Hormuz 6/12 도 2.6배(작은 배수)지만 z 11 인 건 baseline 이
    안정적이라 그렇다. 얇은 baseline 은 절대 하한이 막는다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 실측 기반 기본 임계. 운영하며 조정 가능하게 상수로 뺀다.
EDIT_Z_THRESHOLD = 3.0
VIEW_Z_THRESHOLD = 3.0
MIN_ABSOLUTE_EDITS = 10   # 얇은 baseline 오탐 방지. 신규 문서 판정에도 쓴다.
MIN_VIEW_RATIO = 2.0      # 조회수 최소 배수. z 만으로는 부족(6/12 가 2.6배)
MIN_BASELINE_SAMPLE_DAYS = 7  # baseline 이 이보다 얇으면 신규 문서로 취급
#: 서로 다른 편집자 최소 수. 한 사람의 연속 편집(정리 작업·목록 갱신)을 급증에서 뺀다.
#: 실측 2026-09-15 (WP-85): 이 게이트 하나로 대조군 오탐 395 -> 101 건 (74% 감소),
#: 대상 재현율은 그대로였다. 명세 §3.2 2번의 "1인 반복 편집은 거른다"가 코드에 없던 부분이다.
MIN_DISTINCT_EDITORS = 2


@dataclass(frozen=True)
class Baseline:
    """문서 × 요일·시간대 기준선. page_baseline 테이블 한 행."""
    edit_ewma: float
    edit_stddev: float | None
    view_ewma: float | None
    sample_days: int

    @property
    def is_thin(self) -> bool:
        return self.sample_days < MIN_BASELINE_SAMPLE_DAYS


@dataclass(frozen=True)
class Window:
    """한 문서의 한 윈도우 관측치."""
    edit_count: int
    editor_count: int
    views: int | None  # 조회수는 늦게 와서 판정 시점엔 None 일 수 있다


@dataclass(frozen=True)
class SpikeDecision:
    is_spike: bool
    is_new_page: bool
    edit_z: float | None
    view_ratio: float | None
    spike_score: float
    reason: str


def _z(value: float, mean: float, stddev: float | None) -> float | None:
    if stddev is None or stddev <= 0:
        return None
    return (value - mean) / stddev


def detect(window: Window, baseline: Baseline | None) -> SpikeDecision:
    """급증 여부와 점수를 판정한다.

    baseline 이 None 이거나 얇으면 신규 문서 경로(절대 하한).
    조회수(window.views)가 None 이면 편집만으로 1차 판정한다 — 조회수는
    늦게 오므로, 그 사이는 '감지됨' 상태로 두고 나중에 확정한다.
    """
    new_page = baseline is None or baseline.is_thin

    if new_page:
        return _detect_new_page(window)
    return _detect_existing_page(window, baseline)


def _detect_new_page(window: Window) -> SpikeDecision:
    """baseline 이 없다. 절대 편집수 + (있으면) 조회수 하한으로."""
    enough_edits = window.edit_count >= MIN_ABSOLUTE_EDITS
    enough_editors = window.editor_count >= MIN_DISTINCT_EDITORS
    edits_ok = enough_edits and enough_editors
    # 신규 문서는 조회수 baseline 도 없어 배수를 못 낸다. 편집으로만 1차 판정.
    score = float(window.edit_count) * max(1, window.editor_count) ** 0.5
    return SpikeDecision(
        is_spike=edits_ok,
        is_new_page=True,
        edit_z=None,
        view_ratio=None,
        spike_score=score if edits_ok else 0.0,
        reason=("신규 문서 절대 편집수 통과" if edits_ok
                else f"신규 문서지만 편집 {window.edit_count} < {MIN_ABSOLUTE_EDITS}"
                if not enough_edits
                else f"신규 문서지만 편집자 {window.editor_count} < {MIN_DISTINCT_EDITORS}"),
    )


def _detect_existing_page(window: Window, baseline: Baseline) -> SpikeDecision:
    edit_z = _z(window.edit_count, baseline.edit_ewma, baseline.edit_stddev)

    # 편집 1차 관문: z 임계 AND 절대 하한 AND 편집자 하한. 셋 다 넘어야 한다.
    edit_pass = (
        edit_z is not None
        and edit_z >= EDIT_Z_THRESHOLD
        and window.edit_count >= MIN_ABSOLUTE_EDITS
        and window.editor_count >= MIN_DISTINCT_EDITORS
    )
    if not edit_pass:
        return SpikeDecision(
            is_spike=False, is_new_page=False, edit_z=edit_z, view_ratio=None,
            spike_score=0.0,
            reason=(f"편집 미달 (z={edit_z}, count={window.edit_count}, "
                    f"editors={window.editor_count})"),
        )

    # 조회수 2차 관문. 아직 조회수가 안 왔으면(None) 보류 — 편집만 통과한 상태.
    view_ratio = None
    if window.views is not None and baseline.view_ewma and baseline.view_ewma > 0:
        view_ratio = window.views / baseline.view_ewma

    if view_ratio is None:
        # 편집은 통과, 조회수 대기. 감지됨 상태로 내보내되 아직 확정 아님.
        return SpikeDecision(
            is_spike=True, is_new_page=False, edit_z=edit_z, view_ratio=None,
            spike_score=_score(edit_z, None),
            reason="편집 통과, 조회수 판정 대기(감지됨)",
        )

    view_pass = view_ratio >= MIN_VIEW_RATIO
    return SpikeDecision(
        is_spike=view_pass,
        is_new_page=False,
        edit_z=edit_z,
        view_ratio=view_ratio,
        spike_score=_score(edit_z, view_ratio) if view_pass else 0.0,
        reason=("편집·조회수 모두 통과(확정)" if view_pass
                else f"편집 통과했으나 조회수 배수 {view_ratio:.1f} < {MIN_VIEW_RATIO}"),
    )


def _score(edit_z: float, view_ratio: float | None) -> float:
    """급등도. 버블맵 버블 크기·피드 정렬에 쓴다.

    편집 z 와 조회수 배수를 로그로 눌러 곱한다 — z 5311 같은 값이 그대로면
    한 버블이 화면을 다 먹는다. log1p 로 완만하게.
    """
    import math

    edit_part = math.log1p(max(0.0, edit_z))
    view_part = math.log1p(max(0.0, view_ratio)) if view_ratio is not None else 0.0
    # 조회수가 아직 없으면 편집만으로. 있으면 두 신호의 곱(둘 다 커야 크다).
    if view_ratio is None:
        return round(edit_part, 3)
    return round(edit_part * (1.0 + view_part), 3)
