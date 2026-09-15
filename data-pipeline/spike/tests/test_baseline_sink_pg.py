"""page_baseline upsert 멱등성 — 실 PostgreSQL 검증 (WP-60).

`test_baseline_rows.py` 의 SQL 검사는 문자열·파라미터까지만 본다. "같은 입력을 두 번
돌려도 행이 늘지 않는다" 는 실제 DB 가 있어야 확인된다 — 그래서 파일을 나눴다.
같은 파일에 두면 DB 없는 환경에서 함께 skip 되어 계약이 깨져도 아무도 모른다
(batch/tests/test_edit_event_schema.py 와 같은 이유).

돌리는 법 — 저장소 루트에서 개발 스택을 띄우고:

    docker compose up -d postgres
    cd data-pipeline && .venv/Scripts/python.exe -m pytest spike/tests/test_baseline_sink_pg.py

DATABASE_URL 이 있으면 그걸 쓰고, 없으면 docker-compose 기본 DSN 으로 붙는다.
붙지 못하면 skip 한다.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from spike.baseline_rows import build_rows
from spike.baseline_sink import load

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

#: docker-compose.yml 의 개발 기본값. 운영 자격증명이 아니다.
DEFAULT_DSN = "postgresql://wikipulse:wikipulse@localhost:5432/wikipulse"


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
    """테스트마다 고유 문서. 끝나면 지운다(page_baseline 은 FK CASCADE 로 따라 지워진다)."""
    name = f"__pytest_{uuid.uuid4().hex[:12]}"
    yield name
    with conn.cursor() as cur:
        cur.execute("DELETE FROM wiki_page WHERE wiki = %s AND title = %s", ("enwiki", name))
    conn.commit()


def windows(title, edits, views=None, day="2025-06-09", hour_of_day=0):
    return [{"wiki": "enwiki", "title": title, "hour_of_day": hour_of_day,
             "window_start": f"{day}T00:00:00", "edit_count": edits, "views": views}]


def count_rows(conn, title) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM page_baseline b "
            "JOIN wiki_page p ON p.id = b.page_id WHERE p.wiki=%s AND p.title=%s",
            ("enwiki", title))
        return cur.fetchone()[0]


def read_row(conn, title):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT b.edit_ewma, b.edit_stddev, b.view_ewma, b.sample_days, b.updated_at "
            "FROM page_baseline b JOIN wiki_page p ON p.id = b.page_id "
            "WHERE p.wiki=%s AND p.title=%s", ("enwiki", title))
        return cur.fetchone()


def test_같은_입력_두_번이면_행이_안_늘어난다(conn, title):
    rows = build_rows(windows(title, 4, views=10), as_of=date(2025, 6, 9))
    assert load(conn, rows) == 1
    assert count_rows(conn, title) == 1

    assert load(conn, rows) == 1          # 두 번째 적재
    assert count_rows(conn, title) == 1   # PK 충돌로 갱신 — 늘지 않는다


def test_재적재가_값을_갱신하고_updated_at을_올린다(conn, title):
    load(conn, build_rows(windows(title, 4, views=10), as_of=date(2025, 6, 9)))
    before = read_row(conn, title)
    assert before[0] == pytest.approx(4.0) and before[2] == pytest.approx(10.0)

    # 같은 (page_id, hour_of_day) 에 다른 값
    load(conn, build_rows(windows(title, 9, views=99), as_of=date(2025, 6, 9)))
    after = read_row(conn, title)
    assert count_rows(conn, title) == 1
    assert after[0] == pytest.approx(9.0)      # edit_ewma 갱신
    assert after[2] == pytest.approx(99.0)     # view_ewma 갱신
    assert after[4] >= before[4]               # updated_at 갱신


def test_wiki_page도_중복되지_않는다(conn, title):
    rows = build_rows(windows(title, 4), as_of=date(2025, 6, 9))
    load(conn, rows)
    load(conn, rows)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM wiki_page WHERE wiki=%s AND title=%s",
                    ("enwiki", title))
        assert cur.fetchone()[0] == 1          # 자연키 UNIQUE (wiki, title)


def test_여러_슬롯이_각각_한_행(conn, title):
    src = windows(title, 3, hour_of_day=0) + windows(title, 5, hour_of_day=5)
    rows = build_rows(src, as_of=date(2025, 6, 9))
    assert len(rows) == 2
    load(conn, rows)
    load(conn, rows)
    assert count_rows(conn, title) == 2        # 슬롯당 한 행, 재적재해도 그대로


def test_edit_stddev_None이_NULL로_들어간다(conn, title):
    """관측 하나면 stddev 0.0. 조회수가 없으면 view_ewma 는 NULL 이어야 한다."""
    rows = build_rows(windows(title, 4, views=None), as_of=date(2025, 6, 9))
    assert rows[0].view_ewma is None
    load(conn, rows)
    stored = read_row(conn, title)
    assert stored[1] == pytest.approx(0.0)     # edit_stddev (관측 1개 → 0)
    assert stored[2] is None                   # view_ewma NULL
