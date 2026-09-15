"""EWMA 가중치·비교 검증 (WP-59). Spark 없이 돈다."""

from __future__ import annotations

import math

import pytest

from spike.ewma import (
    DEFAULT_HALFLIFE_DAYS,
    Observation,
    ewma_mean_std,
    weight,
)
from spike.ewma_compare import summarize


# ---------------------------------------------------------------- 가중치

def test_반감기마다_절반():
    assert weight(0, 14) == 1.0
    assert weight(14, 14) == pytest.approx(0.5)
    assert weight(28, 14) == pytest.approx(0.25)


def test_반감기_비양수는_거부():
    with pytest.raises(ValueError):
        weight(1, 0)


# ---------------------------------------------------------------- 평균·표준편차

def test_빈_관측은_mean0_std_None():
    assert ewma_mean_std([]) == (0.0, None)


def test_단일_관측은_std_0():
    mean, std = ewma_mean_std([Observation(0, 7.0)])
    assert mean == 7.0 and std == 0.0


def test_반감기_크면_단순평균에_수렴():
    obs = [Observation(0, 2.0), Observation(28, 4.0)]
    mean, _ = ewma_mean_std(obs, halflife_days=1e9)   # 사실상 균등 가중
    assert mean == pytest.approx(3.0)                  # 단순평균


def test_최근값이_더_무겁다():
    # 최근 10, 28일 전 0. 반감기 14 → 옛값 무게 0.25.
    obs = [Observation(0, 10.0), Observation(28, 0.0)]
    mean, _ = ewma_mean_std(obs, halflife_days=14.0)
    # (10*1 + 0*0.25) / (1 + 0.25) = 8.0  > 단순평균 5.0
    assert mean == pytest.approx(8.0)


def test_균등가중_모집단_표준편차():
    obs = [Observation(0, 2.0), Observation(0, 4.0)]   # 같은 나이 → 균등
    mean, std = ewma_mean_std(obs, halflife_days=DEFAULT_HALFLIFE_DAYS)
    assert mean == pytest.approx(3.0)
    assert std == pytest.approx(1.0)                   # sqrt(((1)+(1))/2)


# ---------------------------------------------------------------- 비교 하네스

def _row(title, hour, day, edits):
    return {"wiki": "enwiki", "title": title, "hour_of_day": hour,
            "window_start": f"{day}T{hour % 24:02d}:00:00", "edit_count": edits}


def test_summarize_후보별_슬롯_집계():
    # 한 슬롯(hour_of_day=0)에 두 주 관측: 최근(2025-06-09) 10, 옛날(2025-05-26) 0
    rows = [_row("Iran", 0, "2025-06-09", 10), _row("Iran", 0, "2025-05-26", 0)]
    out = summarize(rows, candidates=(14.0, 1e9))
    assert out[14.0]["slots"] == 1
    assert out[1e9]["mean_ewma"] == pytest.approx(5.0)     # 큰 반감기 → 단순평균
    # 작은 반감기는 최근값(10)을 더 실어 단순평균(5)과 벌어진다
    assert out[14.0]["mean_abs_diff_vs_simple"] > out[1e9]["mean_abs_diff_vs_simple"]


def test_summarize_빈입력():
    out = summarize([], candidates=(14.0,))
    assert out[14.0]["slots"] == 0
