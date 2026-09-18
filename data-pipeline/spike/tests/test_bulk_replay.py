"""연속 구간 bulk 리플레이 (WP-109). DB 없이 돈다.

여기서 고정하는 계약:
  - `may_spike` 사전필터는 **무손실(lossless)** 이다 — 적용 전후의 최종 판정 집합이
    100% 같다. 격자 전수 + 난수 corpus + 런타임 왕복(저장된 행) 세 층위로 확인한다.
    이게 깨지면 bulk 경로가 급증을 조용히 놓친다
  - 제목 목록을 받지 않는다 — 구간 안의 모든 문서가 들어간다
  - `--since/--until` 은 경계 포함이고, 구간 밖은 세기만 하고 판정하지 않는다
  - 출처는 항상 'replay'

실 PostgreSQL 왕복은 `test_bulk_replay_pg.py`.
"""

from __future__ import annotations

import gzip
import itertools
import json
import random
from dataclasses import astuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from spike.bulk_replay import (
    SOURCE,
    BulkCounts,
    candidate_windows,
    in_range,
    read_windows,
    state_key,
)
from spike.detector import Baseline, Window, detect, may_spike
from spike.runtime import PageWindow, SpikeRuntime

UTC = timezone.utc


# --- may_spike 가 정말 필요조건인가 (가장 중요한 계약) ----------------------

def _baselines():
    """판정 분기를 전부 훑는 기준선 목록. None(없음)·얇음·두꺼움·조회수 유무."""
    return [
        None,
        Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=None, sample_days=3),
        Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=None, sample_days=30),
        Baseline(edit_ewma=0.1, edit_stddev=0.05, view_ewma=None, sample_days=30),
        Baseline(edit_ewma=1.0, edit_stddev=None, view_ewma=None, sample_days=30),
        Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=10.0, view_stddev=2.0,
                 sample_days=30),
        Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=0.5, view_stddev=0.1,
                 sample_days=30),
    ]


def _grid_windows():
    """임계 상수마다 경계 바로 아래·위를 포함한 격자. 조회수는 None 도 넣는다."""
    edit_counts = [0, 1, 2, 9, 10, 11, 50, 5000]
    editor_counts = [0, 1, 2, 3, 20]
    view_counts = [None, 0, 1, 99, 100, 101, 100_000]
    return [
        Window(edit_count=e, editor_count=u, views=v)
        for e, u, v in itertools.product(edit_counts, editor_counts, view_counts)
    ]


# 🔴 사전필터가 무손실인가 — 적용 전후 판정 집합이 같은가 (이 Story 의 핵심 계약)

def test_prefilter_is_lossless_on_grid():
    """같은 (윈도우, 기준선) 집합에 대해 **사전필터 적용 전후의 최종 판정이 100% 같다**.

    `is_spike` 만이 아니라 `SpikeDecision` 전체(edit_z·view_ratio·spike_score·reason)를
    대조한다 — 점수가 달라지면 버블 크기·정렬이 조용히 바뀐다.
    사전필터가 거른 입력은 "급증 아님" 으로 간주하고, 그것도 원본과 같아야 한다.
    """
    mismatches = []
    filtered_out_but_spike = []
    compared = 0

    for window in _grid_windows():
        for baseline in _baselines():
            compared += 1
            without_prefilter = detect(window, baseline)      # 지금까지의 경로
            if may_spike(window):
                with_prefilter = detect(window, baseline)     # bulk 경로(통과분만 판정)
            else:
                with_prefilter = None                         # bulk 경로(판정 자체를 안 함)
                if without_prefilter.is_spike:
                    filtered_out_but_spike.append((window, baseline, without_prefilter))
                continue
            if astuple(with_prefilter) != astuple(without_prefilter):
                mismatches.append((window, baseline))

    assert not filtered_out_but_spike, (
        f"사전필터가 급증을 걸렀다 ({len(filtered_out_but_spike)}건): "
        f"{filtered_out_but_spike[:3]}")
    assert not mismatches, f"통과분의 판정이 갈렸다: {mismatches[:3]}"
    assert compared >= 1500, f"격자가 너무 작다 ({compared})"


def test_prefilter_is_lossless_on_random_corpus():
    """난수 corpus 로 폭을 넓힌다. 씨앗 고정이라 재현된다.

    격자는 경계값만 본다 — 실제 덤프는 그 사이 값이 대부분이라 한 층 더 깐다.
    """
    rng = random.Random(20260917)
    baselines = _baselines()
    kept_spikes, all_spikes = [], []

    for i in range(20_000):
        window = Window(
            edit_count=rng.randint(0, 200),
            editor_count=rng.randint(0, 30),
            views=rng.choice([None, 0, rng.randint(0, 5_000)]),
        )
        baseline = baselines[i % len(baselines)]
        decision = detect(window, baseline)
        if decision.is_spike:
            all_spikes.append((i, astuple(decision)))
        if may_spike(window):
            kept = detect(window, baseline)
            if kept.is_spike:
                kept_spikes.append((i, astuple(kept)))

    assert kept_spikes == all_spikes
    assert all_spikes, "corpus 에서 급증이 한 건도 안 나왔다 — 대조가 무의미하다"


class _FakeBaselines:
    """`BaselineRepository` 대역. (wiki, title, hour) -> Baseline."""

    def __init__(self, slots):
        self.slots = slots
        self.lookups = 0

    def get(self, wiki, title, hour_of_day):
        self.lookups += 1
        return self.slots.get((wiki, title, hour_of_day))

    def invalidate(self):
        pass


class _RecordingSink:
    """`SpikeSink` 대역. 저장 호출을 그대로 모은다 — 최종 산출물 대조용."""

    def __init__(self):
        self.saved = []

    def save(self, *, wiki, title, window_start, detected_at, edit_count, decision,
             views=None, view_baseline=None):
        self.saved.append((wiki, title, window_start, detected_at, edit_count,
                           astuple(decision)))
        return len(self.saved)


def test_runtime_persists_identical_rows_with_and_without_prefilter():
    """런타임 왕복 대조 — `spike` 에 **저장되는 행**이 사전필터 유무와 무관하게 같다.

    bulk_replay 가 실제로 하는 일(기준선 조회 → detect → 저장)을 그대로 돌린다.
    곁들여 왕복 수가 실제로 줄어드는지도 확인한다 — 안 줄면 사전필터를 둘 이유가 없다.
    """
    rng = random.Random(4609)
    base_ts = datetime(2024, 9, 1, tzinfo=UTC)
    slots = {}
    rows = []
    for i in range(3_000):
        title = f"Doc {i % 400}"
        hour = i % 24
        window = PageWindow(
            wiki="enwiki", title=title,
            window_start=base_ts + timedelta(hours=i),
            edit_count=rng.randint(0, 60),
            editor_count=rng.randint(0, 8),
            views=rng.choice([None, 0, rng.randint(0, 800)]),
        )
        rows.append(window)
        if i % 3 == 0:
            slots[("enwiki", title, window.window_start.hour)] = Baseline(
                edit_ewma=rng.uniform(0.2, 8.0),
                edit_stddev=rng.choice([None, rng.uniform(0.1, 4.0)]),
                view_ewma=rng.choice([None, 0.0, rng.uniform(1.0, 200.0)]),
                view_stddev=rng.choice([None, rng.uniform(0.5, 50.0)]),
                sample_days=rng.choice([1, 6, 7, 28]),
            )

    full_sink, full_baselines = _RecordingSink(), _FakeBaselines(slots)
    SpikeRuntime(full_baselines, full_sink).process_all(rows)

    pre_sink, pre_baselines = _RecordingSink(), _FakeBaselines(slots)
    SpikeRuntime(pre_baselines, pre_sink).process_all(
        w for w in rows if may_spike(w.as_detector_window()))

    assert pre_sink.saved == full_sink.saved
    assert full_sink.saved, "저장된 급증이 0건이면 대조가 무의미하다"
    assert pre_baselines.lookups < full_baselines.lookups, (
        "사전필터가 기준선 왕복을 줄이지 못했다 — 둘 이유가 없다")


def test_may_spike_is_a_necessary_condition():
    """`detect(...).is_spike` 인데 `may_spike` 가 거짓인 조합이 하나라도 있으면 실패.

    🔴 이 테스트가 bulk 경로의 사전필터를 정당화한다. 임계값이 바뀌면 여기서 먼저 깨진다.
    """
    edit_counts = [0, 1, 2, 9, 10, 11, 50, 5000]
    editor_counts = [0, 1, 2, 3, 20]
    view_counts = [None, 0, 1, 99, 100, 101, 100_000]

    checked = 0
    for edits, editors, views in itertools.product(edit_counts, editor_counts, view_counts):
        window = Window(edit_count=edits, editor_count=editors, views=views)
        for baseline in _baselines():
            checked += 1
            if detect(window, baseline).is_spike:
                assert may_spike(window), (
                    f"급증인데 사전필터가 걸렀다: {window} / {baseline}")
    assert checked > 500      # 격자가 통째로 비면 테스트가 무의미해진다


def test_may_spike_actually_filters_something():
    """전부 통과시키면 필터가 아니다 — 실제로 거르는지 확인."""
    quiet = Window(edit_count=3, editor_count=1, views=5)
    assert not may_spike(quiet)
    assert not detect(quiet, None).is_spike


def test_may_spike_keeps_view_only_candidate():
    """편집은 적지만 조회수 하한을 넘는 윈도우는 통과해야 한다(조회수 단독 경로)."""
    window = Window(edit_count=1, editor_count=1, views=500)
    assert may_spike(window)


# --- 구간 필터 --------------------------------------------------------------

@pytest.mark.parametrize("window_start,expected", [
    ("2024-09-01T00:00:00", True),     # since 경계 포함
    ("2024-09-07T23:00:00", True),     # until 경계 포함
    ("2024-08-31T23:00:00", False),
    ("2024-09-08T00:00:00", False),
])
def test_in_range_boundaries(window_start, expected):
    assert in_range(window_start, date(2024, 9, 1), date(2024, 9, 7)) is expected


def test_in_range_open_ended():
    assert in_range("1999-01-01T00:00:00", None, None) is True


# --- 읽기·후보 생성 ---------------------------------------------------------

def _write_shard(directory: Path, rows: list[dict], name: str = "part-00000.jsonl.gz"):
    directory.mkdir(parents=True, exist_ok=True)
    with gzip.open(directory / name, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _row(title, window_start, edit_count, editor_count=3, views=0):
    return {"wiki": "enwiki", "title": title, "window_start": window_start,
            "hour_of_day": int(window_start[11:13]), "edit_count": edit_count,
            "editor_count": editor_count, "views": views}


def test_read_windows_reads_all_shards(tmp_path):
    _write_shard(tmp_path, [_row("A", "2024-09-01T00:00:00", 12)], "part-00000.jsonl.gz")
    _write_shard(tmp_path, [_row("B", "2024-09-01T01:00:00", 13)], "part-00001.jsonl.gz")
    titles = sorted(row["title"] for row in read_windows(tmp_path))
    assert titles == ["A", "B"]


def test_candidate_windows_counts_every_outcome(tmp_path):
    """2단계 계약의 프리필터 (WP-126).

    ~~편집 10건·편집자 2명 미달은 사전필터 탈락~~ → **1단계는 편집 1건이면 통과**다.
    거르는 건 둘뿐이다: 편집 0건, 그리고 조회수가 도착했는데 절대 하한 미달.
    """
    _write_shard(tmp_path, [
        _row("Loud", "2024-09-02T05:00:00", 40, editor_count=9),    # 통과
        _row("Quiet", "2024-09-02T06:00:00", 2, editor_count=1),    # 통과 — 편집 1건 이상
        _row("Solo", "2024-09-02T07:00:00", 40, editor_count=1),    # 통과 — 편집자 하한 없음
        _row("NoEdit", "2024-09-02T08:00:00", 0, editor_count=0),   # 1단계 탈락
        _row("TinyViews", "2024-09-02T09:00:00", 5, views=30),      # 조회수 절대 하한 미달
        _row("Early", "2024-08-30T05:00:00", 40, editor_count=9),   # 구간 밖
    ])
    counts = BulkCounts()
    windows = list(candidate_windows(read_windows(tmp_path), counts,
                                     since=date(2024, 9, 1), until=date(2024, 9, 30)))

    assert [w.title for w in windows] == ["Loud", "Quiet", "Solo"]
    assert counts.read == 6
    assert counts.out_of_range == 1
    assert counts.skipped_prefilter == 2
    # 구간 표시는 **프리필터 통과분**만 갱신한다 — 탈락한 TinyViews(09:00)는 안 든다
    assert counts.earliest_window == "2024-09-02T05:00:00"
    assert counts.latest_window == "2024-09-02T07:00:00"


def test_candidate_windows_takes_every_title(tmp_path):
    """제목 목록을 받지 않는다 — 구간 안의 문서는 전부 후보다."""
    _write_shard(tmp_path, [
        _row(f"Doc {i}", "2024-09-02T05:00:00", 15) for i in range(50)
    ])
    counts = BulkCounts()
    windows = list(candidate_windows(read_windows(tmp_path), counts))
    assert len(windows) == 50
    assert counts.skipped_prefilter == 0


def test_candidate_windows_canonicalizes_title(tmp_path):
    """덤프 세대가 섞여도(밑줄형) PageWindow 가 공백형으로 맞춘다."""
    _write_shard(tmp_path, [_row("Hurricane_Milton", "2024-10-07T14:00:00", 23)])
    counts = BulkCounts()
    windows = list(candidate_windows(read_windows(tmp_path), counts))
    assert [w.title for w in windows] == ["Hurricane Milton"]


# --- 출처·상태 --------------------------------------------------------------

def test_source_is_replay():
    assert SOURCE == "replay"


def test_state_key_distinguishes_chunks(tmp_path):
    a = state_key(tmp_path, date(2024, 9, 1), date(2024, 9, 7))
    b = state_key(tmp_path, date(2024, 9, 8), date(2024, 9, 14))
    assert a != b
    assert state_key(tmp_path, None, None) == f"{tmp_path.as_posix()}|-|-"
