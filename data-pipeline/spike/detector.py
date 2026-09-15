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

절대 하한이 반드시 필요한 이유 (편집·조회수 양쪽)
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

#: 조회수 절대 하한 (WP-87, 2026-09-15 실측). 편집 쪽 MIN_ABSOLUTE_EDITS 의 대응물.
#:
#: 배수도 z 도 **상대값**이라, 평소 값이 아주 작으면 절대량이 무의미해도 통과한다.
#: `Hurricane_Helene` 2024-09 이 평소 1~3회/일이었는데 9/22 에 **8회**가 되자
#: `z 8.1 · 8.9배` 로 규칙을 통과했다 — 진짜 폭증은 9/25(719회)부터다.
#:
#: 사건 10건 전수 sweep (ai/signal-order/measure.py):
#:     하한 없음  Helene 9/22 오탐. 대조군 434 문서·일에서 4건 발동
#:     100        Helene 9/25 로 교정. 나머지 9건 값 불변. 대조군 3건
#:     500        100 과 완전히 동일
#:     1000       Helene 9/26, Strait_of_Hormuz 6/12 -> 6/13 (진짜 신호가 하루 늦는다)
#:
#: 100~500 구간이 평평해서 **아래쪽 끝**을 골랐다 — 재현율 여유를 남기는 쪽이다.
#: 500 도 현재 근거로는 똑같이 지지된다. 꼬리 문서 노이즈가 실제로 드러나면
#: 대조군을 키워 다시 재고 올린다.
#:
#: ⚠️ 문서 인기도에 비례하지 않는 **고정값**이다. 평소 100만 조회인 문서엔 영향이 없고
#: 꼬리 문서만 막는다 — 편집 쪽 하한 10 과 같은 성격이다.
#: 🔴 기존 문서 경로에만 걸린다. 신규 문서 경로는 조회수를 아예 안 본다(baseline 부재).
MIN_ABSOLUTE_VIEWS = 100
MIN_BASELINE_SAMPLE_DAYS = 7  # baseline 이 이보다 얇으면 신규 문서로 취급
#: 서로 다른 편집자 최소 수. 한 사람의 연속 편집(정리 작업·목록 갱신)을 급증에서 뺀다.
#: 실측 2026-09-15 (WP-85): 이 게이트 하나로 대조군 오탐 395 -> 101 건 (74% 감소),
#: 대상 재현율은 그대로였다. 명세 §3.2 2번의 "1인 반복 편집은 거른다"가 코드에 없던 부분이다.
MIN_DISTINCT_EDITORS = 2


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
    """기존 문서: **편집 통과 OR 조회수 통과** (2026-09-15, WP-90).

    ~~편집 통과 AND 조회수 통과~~ → OR. 사건 10건 실측(WP-86)에서 두 신호가
    서로 다른 문서 유형을 맡는 게 드러났다 — 기존 문서는 사람들이 **읽으러** 와서
    편집이 안 는다(조회수 6/6 · 편집 4/6, 그중 하나는 9일 지연). AND 면 그 2건을
    영영 못 잡는다.

    ⚠️ 잃는 것: "편집만 튀고 조회수가 안 따라오면 편집 전쟁·정리 작업으로 보고 버린다"는
    컷이 없어진다. **그 일은 편집자 하한(MIN_DISTINCT_EDITORS, WP-85)이 맡는다** —
    1인 연속 편집 오탐을 395건 → 101건으로 줄인 게 그 게이트다. 다만 이 대체는 리플레이로
    확인이 안 된다(편집 덤프에 조회수가 없어 views=None) — 조회수가 붙은 실환경에서 재확인.

    신규 문서 경로는 안 바뀐다. 조회수 baseline 이 **원리적으로 없어서**다(문서가 사건
    당일 생겨 이전 관측이 없다) — Milton·Air India 의 조회수 미탐은 임계 문제가 아니다.
    """
    edit_z = _z(window.edit_count, baseline.edit_ewma, baseline.edit_stddev)
    edit_pass = (
        edit_z is not None
        and edit_z >= EDIT_Z_THRESHOLD
        and window.edit_count >= MIN_ABSOLUTE_EDITS
        and window.editor_count >= MIN_DISTINCT_EDITORS
    )

    view_ratio, view_z = _view_signal(window, baseline)
    # 조회수 관문 = z AND 배수. 명세 §3.2 3번 문구 그대로다 —
    # ~~배수만 봤다~~ → view_stddev 가 생겨 z 를 낼 수 있게 됐다 (WP-90).
    view_pass = (
        view_ratio is not None
        and view_ratio >= MIN_VIEW_RATIO
        and view_z is not None
        and view_z >= VIEW_Z_THRESHOLD
        # 절대 하한. 배수·z 는 둘 다 상대값이라 평소가 1~3회인 문서는 8회로도 통과한다
        # (WP-87). 조회수가 단독 트리거가 된 뒤로 이 공백의 영향이 커졌다.
        and window.views is not None
        and window.views >= MIN_ABSOLUTE_VIEWS
    )

    if not (edit_pass or view_pass):
        return SpikeDecision(
            is_spike=False, is_new_page=False, edit_z=edit_z, view_ratio=view_ratio,
            spike_score=0.0,
            reason=(f"편집·조회수 둘 다 미달 (편집 z={edit_z}, count={window.edit_count}, "
                    f"editors={window.editor_count} / 조회수 {window.views}회, "
                    f"배수={view_ratio}, z={view_z})"),
        )

    if edit_pass and view_pass:
        reason = "편집·조회수 모두 통과(확정)"
    elif edit_pass:
        # 조회수가 아직 안 왔거나(None) 임계 미달. 둘을 구분해 적는다 —
        # 앞은 시간이 해결하고, 뒤는 이 윈도우에서 확정이 안 된다.
        reason = ("편집 통과, 조회수 판정 대기(감지됨)" if window.views is None
                  else f"편집 통과, 조회수 미달(배수={view_ratio}, z={view_z})")
    else:
        reason = "조회수 통과, 편집 판정 대기(감지됨)"

    return SpikeDecision(
        is_spike=True,
        is_new_page=False,
        edit_z=edit_z,
        view_ratio=view_ratio,
        # 점수는 통과한 신호만으로 낸다. 미달 신호를 섞으면 확정 건과 뒤섞여 정렬이 흐려진다.
        spike_score=_score(edit_z if edit_pass else None,
                           view_z if view_pass else None),
        reason=reason,
    )


def _view_signal(
    window: Window, baseline: Baseline
) -> tuple[float | None, float | None]:
    """조회수 배수와 z. 조회수가 없거나 기준선이 없으면 (None, None) 쪽으로 닫힌다."""
    if window.views is None or not baseline.view_ewma or baseline.view_ewma <= 0:
        return None, None
    ratio = window.views / baseline.view_ewma
    return ratio, _z(window.views, baseline.view_ewma, baseline.view_stddev)


def _score(edit_z: float | None, view_z: float | None) -> float:
    """급등도. 버블맵 버블 크기·피드 정렬에 쓴다. 통과한 신호만 넣는다(미통과는 None).

    두 신호를 **같은 단위(z)** 로 놓는다 (2026-09-15, WP-93).
    ~~조회수 쪽만 배수(view_ratio)를 썼다~~ → z 와 배수는 자릿수가 달라서, 조회수
    단독으로 통과한 **미확정** 건이 편집·조회수 다 통과한 **확정** 건을 밀어냈다:

        확정   edit_z=3, 배수=2   log1p(3)*(1+log1p(2)) = 2.91
        미확정 배수=20            log1p(20)             = 3.04   ← 더 높다

    `spike_score` 는 `cluster_member` 를 거쳐 `pulse_score` 가 되고 피드 정렬·버블
    크기를 정한다(명세 §7). 조회수 절대 하한이 아직 없어(WP-87) 평소 10회짜리
    꼬리 문서도 배수 수십이 쉽게 나오는데, 그런 게 상단을 먹었다.
    `view_stddev` 가 생겨(WP-90) 조회수도 z 를 낼 수 있게 된 게 전제다.

    식
        한쪽만  : log1p(z)
        둘 다   : (1+log1p(edit_z)) * (1+log1p(view_z)) - 1

    둘 다인 경우가 한쪽만인 경우로 **연속적으로 이어진다** — 한쪽이 0 이면 나머지
    log1p 와 같아진다. log1p 로 누르는 이유는 그대로다: z 5311 이 날것으로 들어가면
    버블 하나가 화면을 다 먹는다.

    ⚠️ **"확정이 항상 미확정보다 위"는 이 점수 하나로 보장되지 않는다.** 조회수 z 가
    압도적으로 크면 여전히 위로 갈 수 있다 — 다만 이제 같은 단위끼리의 비교다.
    그 보장이 필요하면 정렬 키를 `(상태, 점수)` 로 두는 게 맞다(§3.2 7번 3단계 상태).
    서빙 쪽 결정이라 여기서 정하지 않는다.

    ⚠️ **신규 문서 경로는 아예 다른 식이다** — `edit_count * sqrt(editor_count)`.
    Milton 최초 탐지가 26.46 인데 기존 문서 경로는 2~6 범위다. 원래부터 두 축이
    달랐고 -93 에서 건드리지 않았다(WP-93 "범위 밖").
    """
    import math

    edit_part = math.log1p(max(0.0, edit_z)) if edit_z is not None else 0.0
    view_part = math.log1p(max(0.0, view_z)) if view_z is not None else 0.0
    if edit_part and view_part:
        return round((1.0 + edit_part) * (1.0 + view_part) - 1.0, 3)
    return round(edit_part + view_part, 3)
