"""Spark 윈도우 행 -> PageWindow 매핑과 출처 계약 (WP-100). Spark·DB 없이 돈다.

여기서 고정하는 계약:
  - 타임스탬프는 epoch 초로 건너오고 tz-aware UTC 로 복원된다
  - `window_end` 는 **실제 값**을 쓴다 (window_start + 1h 로 다시 계산하지 않는다)
  - 조회수는 `None` = 미수집이다 (0 으로 꾸미지 않는다)
  - `spike.source` 는 명시해야 하고 두 값 중 하나여야 한다

실 Spark 마이크로배치 왕복은 `spike/tests/test_live_spike_pg.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from batch.historical_windows import WINDOW_HOURS
from spike.spike_sink import SPIKE_SOURCES, require_source
from streaming.live_spike import LIVE_SOURCE, page_window_from_row

UTC = timezone.utc

#: 2024-10-06T19:00:00Z. 리플레이 회귀가 쓰는 Hurricane Milton 구간과 같은 시각대다.
WINDOW_START_EPOCH = 1728241200
WINDOW_START = datetime(2024, 10, 6, 19, tzinfo=UTC)


def row(**over):
    base = {
        "wiki": "enwiki",
        "title": "Hurricane Milton",
        "window_start_epoch": WINDOW_START_EPOCH,
        "window_end_epoch": WINDOW_START_EPOCH + 3600,
        "edit_count": 23,
        "editor_count": 7,
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ 타임스탬프

def test_epoch_초가_tz_aware_UTC로_복원된다():
    """🔴 PySpark 의 datetime 을 그대로 쓰면 KST 장비에서 9시간 밀린 naive 가 온다.

    실측(2026-09-15): UTC 19:00 이 `datetime(2024, 10, 7, 4, 0)` tzinfo=None 으로 왔다.
    그래서 경계를 epoch 초로 잡았다 — 시간대 개념이 없는 순간값이다.
    """
    w = page_window_from_row(row())
    assert w.window_start == WINDOW_START
    assert w.window_start.tzinfo is not None
    assert w.window_start.utcoffset() == timedelta(0)
    # 9시간 밀린 값이 아니다.
    assert w.window_start.hour == 19


def test_실제_window_end를_쓴다_재계산하지_않는다():
    """WINDOW_SIZE 는 환경변수라 WINDOW_HOURS 상수와 갈릴 수 있다.

    갈리면 `detected_at`(= window_end)이 에러 없이 어긋난다. 소스가 준 값이 이긴다.
    """
    # 30분짜리 윈도우 — WINDOW_HOURS(1시간)와 일부러 다르게.
    w = page_window_from_row(row(window_end_epoch=WINDOW_START_EPOCH + 1800))
    assert w.window_end == WINDOW_START + timedelta(minutes=30)
    assert w.window_end != w.window_start + timedelta(hours=WINDOW_HOURS)


def test_window_end가_start보다_뒤가_아니면_막는다():
    with pytest.raises(ValueError, match="window_end"):
        page_window_from_row(row(window_end_epoch=WINDOW_START_EPOCH))


# ------------------------------------------------------------------ 제목·집계값

def test_제목을_canonical로_맞춘다():
    """LIVE 는 공백형을 주지만 계약은 읽는 지점에서 맞추는 것이다 (WP-92)."""
    assert page_window_from_row(row(title="Hurricane_Milton")).title == "Hurricane Milton"


def test_편집수와_편집자수를_그대로_옮긴다():
    w = page_window_from_row(row(edit_count=44, editor_count=12))
    assert (w.edit_count, w.editor_count) == (44, 12)


def test_editor_count가_NULL이면_0으로_읽는다():
    """approx_count_distinct 가 NULL 을 낼 일은 없지만, 0 과 None 을 섞지 않는다."""
    assert page_window_from_row(row(editor_count=None)).editor_count == 0


# ------------------------------------------------------------------ 조회수 미수집

def test_조회수는_미수집_None이다_0으로_꾸미지_않는다():
    """🔴 `wiki.edits` 에 조회수 필드가 없다. 0 은 '진짜 0회' 와 구분되지 않는다.

    `detect()` 계약상 None 이 "조회수 판정 대기" 이고 편집만으로 1차 판정한다.
    """
    w = page_window_from_row(row())
    assert w.views is None
    assert w.as_detector_window().views is None


# ------------------------------------------------------------------ 출처 계약

def test_LIVE_경로의_라벨은_live다():
    assert LIVE_SOURCE == "live"
    assert LIVE_SOURCE in SPIKE_SOURCES


def test_허용된_출처만_통과한다():
    assert require_source("live") == "live"
    assert require_source("replay") == "replay"


@pytest.mark.parametrize("bad", ["LIVE", "Live", "", "stream", "historical", None])
def test_잘못된_출처는_거부한다(bad):
    """V5 의 CHECK 제약과 같은 목록이다. 대소문자도 다르면 다른 값이다."""
    with pytest.raises(ValueError, match="spike.source"):
        require_source(bad)
