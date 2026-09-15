"""`page_baseline` → detect() → `spike` 실 PostgreSQL 왕복 (WP-94).

`test_runtime.py` 의 대역 검사는 호출 계약까지만 본다. "같은 윈도우를 두 번 판정해도
행이 안 는다"·"신규 문서 edit_z 가 NULL 로 들어간다"·"TIMESTAMPTZ 가 안 밀린다" 는
실 DB 가 있어야 확인된다 — 그래서 파일을 나눴다(`test_baseline_sink_pg.py` 와 같은 이유).

돌리는 법 — 저장소 루트에서 개발 스택을 띄우고:

    docker compose up -d postgres
    cd data-pipeline && .venv/Scripts/python.exe -m pytest spike/tests/test_spike_runtime_pg.py

DATABASE_URL 이 있으면 그걸 쓰고, 없으면 docker-compose 기본 DSN 으로 붙는다.
붙지 못하면 skip 한다.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

import pytest

from spike.baseline_repository import BaselineRepository
from spike.baseline_rows import build_rows
from spike.baseline_sink import load
from spike.detector import EDIT_Z_THRESHOLD, MIN_ABSOLUTE_EDITS, MIN_BASELINE_SAMPLE_DAYS
from spike.runtime import PageWindow, SpikeRuntime
from spike.spike_sink import SpikeSink

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

#: docker-compose.yml 의 개발 기본값. 운영 자격증명이 아니다.
DEFAULT_DSN = "postgresql://wikipulse:wikipulse@localhost:5432/wikipulse"

UTC = timezone.utc
WINDOW_START = datetime(2024, 10, 6, 19, tzinfo=UTC)


@pytest.fixture()
def conn():
    dsn = os.environ.get("DATABASE_URL") or DEFAULT_DSN
    try:
        connection = psycopg.connect(dsn, connect_timeout=5)
    except psycopg.OperationalError as err:
        pytest.skip(f"PostgreSQL 연결 불가 — docker compose up -d postgres ({err})")
    with connection:
        yield connection


@pytest.fixture()
def title(conn):
    """테스트마다 고유 문서. 끝나면 지운다(spike·page_baseline 은 FK CASCADE).

    ⚠️ 이름에 밑줄을 쓰지 않는다. 런타임이 제목을 canonical(공백형)로 맞추므로
    `__pytest_abc` 를 주면 DB 에는 `pytest abc` 로 들어가 검증 질의가 0행이 된다.
    (`test_밑줄_제목도_공백형으로_적재된다` 가 그 변환 자체를 따로 본다.)
    """
    name = f"PyTest Fixture {uuid.uuid4().hex[:12]}"
    yield name
    with conn.cursor() as cur:
        cur.execute("DELETE FROM wiki_page WHERE wiki = %s AND title LIKE %s",
                    ("enwiki", name.replace("_", " ") + "%"))
    conn.commit()


def runtime(conn) -> SpikeRuntime:
    return SpikeRuntime(BaselineRepository(conn), SpikeSink(conn))


def window(title, edits=MIN_ABSOLUTE_EDITS, editors=2, start=WINDOW_START):
    return PageWindow(wiki="enwiki", title=title, window_start=start,
                      edit_count=edits, editor_count=editors, views=None)


def seed_baseline(conn, title, *, edit_ewma, edit_stddev, sample_days,
                  hour_of_day=WINDOW_START.hour):
    """`baseline_sink.load` 로 실제 행을 넣는다 — 직접 INSERT 하지 않는다.

    `build_rows` 가 계산한 값을 그대로 쓰려고 관측을 역산하는 대신, 필요한 통계가
    나오도록 관측 2개를 만든다: 평균 m, 표준편차 s 는 {m-s, m+s} 에서 나온다.
    sample_days 는 서로 다른 날짜 수다.
    """
    rows = build_rows(
        [{"wiki": "enwiki", "title": title, "hour_of_day": hour_of_day,
          "window_start": f"2024-09-{day:02d}T{hour_of_day:02d}:00:00",
          "edit_count": value, "views": None}
         for day, value in zip(range(1, sample_days + 1),
                               _values(edit_ewma, edit_stddev, sample_days))],
        as_of=date(2024, 9, sample_days),
        halflife_days=10_000,      # 사실상 균등 가중 — 기대값을 손으로 계산할 수 있게
    )
    load(conn, rows)
    return rows


def _values(mean, stddev, n):
    """평균 mean · 모집단 표준편차 stddev 를 내는 관측 n 개(균등 가중 기준)."""
    half = n // 2
    return [mean - stddev] * half + [mean + stddev] * half + ([mean] if n % 2 else [])


def count_spikes(conn, title) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM spike s JOIN wiki_page p ON p.id = s.page_id "
                    "WHERE p.wiki=%s AND p.title=%s", ("enwiki", title))
        return cur.fetchone()[0]


def read_spike(conn, title):
    with conn.cursor() as cur:
        cur.execute("SELECT s.detected_at, s.window_start, s.edit_count, s.edit_z, "
                    "s.view_ratio, s.spike_score "
                    "FROM spike s JOIN wiki_page p ON p.id = s.page_id "
                    "WHERE p.wiki=%s AND p.title=%s", ("enwiki", title))
        return cur.fetchone()


# ---------------------------------------------------------------- 적재

def test_급증이_spike에_적재된다(conn, title):
    outcome = runtime(conn).process(window(title))
    conn.commit()
    assert outcome.decision.is_spike is True
    assert count_spikes(conn, title) == 1


def test_미탐은_적재되지_않는다(conn, title):
    outcome = runtime(conn).process(window(title, edits=MIN_ABSOLUTE_EDITS - 1))
    conn.commit()
    assert outcome.decision.is_spike is False
    assert count_spikes(conn, title) == 0


def test_같은_윈도우를_두_번_판정해도_행이_안_늘어난다(conn, title):
    runtime(conn).process(window(title))
    conn.commit()
    assert count_spikes(conn, title) == 1

    runtime(conn).process(window(title))         # 재실행
    conn.commit()
    assert count_spikes(conn, title) == 1        # UNIQUE (page_id, window_start)


def test_다른_윈도우는_각각_한_행(conn, title):
    rt = runtime(conn)
    rt.process(window(title))
    rt.process(window(title, start=WINDOW_START.replace(hour=20)))
    conn.commit()
    assert count_spikes(conn, title) == 2


# ---------------------------------------------------------------- 컬럼 계약

def test_신규_문서_경로는_edit_z가_NULL로_들어간다(conn, title):
    runtime(conn).process(window(title))
    conn.commit()
    detected_at, window_start, edit_count, edit_z, view_ratio, score = read_spike(conn, title)
    assert edit_z is None                  # 기준선이 없어 z 를 못 낸다
    assert view_ratio is None              # 조회수도 없다
    assert edit_count == MIN_ABSOLUTE_EDITS
    assert score > 0


def test_타임스탬프가_UTC로_들어간다(conn, title):
    """naive 로 넣으면 세션 시간대로 해석돼 9시간 밀리는데 에러가 안 난다."""
    runtime(conn).process(window(title))
    conn.commit()
    detected_at, window_start, *_ = read_spike(conn, title)
    assert window_start.astimezone(UTC) == WINDOW_START
    assert detected_at.astimezone(UTC) == WINDOW_START.replace(hour=20)


def test_wiki_page는_한_행만_만든다(conn, title):
    runtime(conn).process(window(title))
    runtime(conn).process(window(title))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM wiki_page WHERE wiki=%s AND title=%s",
                    ("enwiki", title))
        assert cur.fetchone()[0] == 1


def test_밑줄_제목도_공백형으로_적재된다(conn, title):
    """덤프 원형(밑줄)으로 들어와도 `wiki_page` 에는 canonical 한 행만 남는다.

    갈리면 같은 문서가 두 page_id 를 갖고, 기준선과 급증이 서로 다른 행에 붙는다.
    """
    underscore = title.replace(" ", "_")
    runtime(conn).process(window(underscore))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM wiki_page WHERE wiki=%s AND title IN (%s, %s)",
                    ("enwiki", title, underscore))
        assert [r[0] for r in cur.fetchall()] == [title]


# ------------------------------------------- 기존 문서 z 경로 (실 DB 기준선을 읽는다)

def test_적재된_기준선을_읽어_기존_문서_z경로로_판정한다(conn, title):
    """🔴 이 스토리의 관통 검사.

    `baseline_sink.load` 로 실제 `page_baseline` 행을 만들고, 런타임이 그걸 읽어
    z 를 내는지 본다. 메모리에서 기준선을 다시 만들면 이 값이 안 나온다.
    """
    seed_baseline(conn, title, edit_ewma=2.0, edit_stddev=1.0,
                  sample_days=MIN_BASELINE_SAMPLE_DAYS + 7)
    conn.commit()

    # 적재된 기준선이 기대대로인지 먼저 확인 — 아니면 아래 z 비교가 의미 없다.
    # ⚠️ 정확히 2.0/1.0 은 아니다. seed_baseline 이 반감기를 아주 크게 줘 '사실상 균등'
    # 가중으로 만들 뿐 완전 균등은 아니라서다(0.5**(13/10000) ≈ 0.99910). 여기서 보는 건
    # 값의 소수점이 아니라 **그 기준선이 판정에 쓰였는가** 다.
    baseline = BaselineRepository(conn).get("enwiki", title, WINDOW_START.hour)
    assert baseline is not None
    assert baseline.is_thin is False
    assert baseline.edit_ewma == pytest.approx(2.0, rel=1e-3)
    assert baseline.edit_stddev == pytest.approx(1.0, rel=1e-3)

    outcome = runtime(conn).process(window(title, edits=20, editors=5))
    conn.commit()

    assert outcome.baseline_source == "db"
    assert outcome.decision.is_new_page is False        # 기존 문서 경로
    assert outcome.decision.edit_z >= EDIT_Z_THRESHOLD
    assert outcome.decision.is_spike is True

    # 🔴 z 가 **DB 에서 읽은 그 기준선**으로 계산됐는지. 메모리에서 다시 만든 값이면
    # (리플레이 baseline_at 처럼 창이 다르면) 이 항등식이 깨진다.
    expected_z = (20 - baseline.edit_ewma) / baseline.edit_stddev
    assert outcome.decision.edit_z == pytest.approx(expected_z)
    assert outcome.baseline is not None

    _, _, _, edit_z, _, _ = read_spike(conn, title)
    assert edit_z == pytest.approx(expected_z)          # 신규 경로와 달리 NULL 이 아니다


def test_얇은_기준선은_신규_문서_경로로_간다(conn, title):
    seed_baseline(conn, title, edit_ewma=2.0, edit_stddev=1.0,
                  sample_days=MIN_BASELINE_SAMPLE_DAYS - 1)
    conn.commit()

    outcome = runtime(conn).process(window(title, edits=20, editors=5))
    conn.commit()

    assert outcome.baseline_source == "thin"
    assert outcome.decision.is_new_page is True
    assert outcome.decision.edit_z is None
