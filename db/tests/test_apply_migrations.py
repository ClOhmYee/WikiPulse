"""마이그레이션 적용·이력 검증 (WP-133).

이 파일은 conftest 의 `conn` 픽스처를 **안 쓴다** — 그 픽스처는 이미 V1~V10 이 적재된
DB 를 주는데, 여기서는 빈 DB 에 스크립트가 무엇을 하는지를 봐야 한다. 그래서 pgserver 를
직접 띄운다.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pgserver = pytest.importorskip("pgserver", reason="pgserver 미설치")
psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import apply_migrations as am  # noqa: E402


@pytest.fixture()
def blank(tmp_path_factory):
    """빈 PostgreSQL. 테스트마다 새로 띄운다 — 이력 테이블 상태가 곧 검사 대상이라 공유 못 한다.

    DSN 을 `conn.uri` 로 같이 달아 둔다. CLI(main) 를 부르는 검사가 필요해서다.
    """
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pg")))
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        conn.uri = server.get_uri()
        yield conn


@pytest.fixture()
def tiny(tmp_path):
    """마이그레이션 두 개짜리 디렉터리. 진짜 스키마를 안 써야 검사가 빨라진다."""
    (tmp_path / "V1__one.sql").write_text("CREATE TABLE one (id int);", encoding="utf-8")
    (tmp_path / "V2__two.sql").write_text("CREATE TABLE two (id int);", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- 순서

def test_버전_숫자로_정렬한다():
    """🔴 문자열 정렬이면 V10 이 V2 앞에 온다 — 없는 테이블을 고치려 들고 거기서 멈춘다."""
    names = [p.name for p in am.migration_files()]
    versions = [am.version_of(p) for p in am.migration_files()]
    assert versions == sorted(versions)
    assert names[-1].startswith("V10") or am.version_of(am.migration_files()[-1]) >= 10


# ---------------------------------------------------------------- 적용·이력

def test_적용하고_이력을_남긴다(blank, tiny):
    assert am.apply(blank, tiny) == ["V1__one.sql", "V2__two.sql"]

    with blank.cursor() as cur:
        cur.execute("SELECT version, filename FROM schema_migration ORDER BY version")
        assert cur.fetchall() == [(1, "V1__one.sql"), (2, "V2__two.sql")]


def test_다시_돌려도_안전하다(blank, tiny):
    """🔴 배포가 매번 부르는 스크립트다. 두 번째 실행이 ALTER 중복으로 깨지면 못 쓴다."""
    am.apply(blank, tiny)
    assert am.apply(blank, tiny) == []          # 남은 게 없다


def test_새_파일만_적용한다(blank, tiny):
    am.apply(blank, tiny)
    (tiny / "V3__three.sql").write_text("CREATE TABLE three (id int);", encoding="utf-8")

    assert am.apply(blank, tiny) == ["V3__three.sql"]


def test_적용된_파일이_바뀌면_멈춘다(blank, tiny):
    """DB 와 저장소가 조용히 갈라지는 자리다. 새 버전 파일을 만들라고 세운다."""
    am.apply(blank, tiny)
    (tiny / "V1__one.sql").write_text("CREATE TABLE one (id int, extra int);", encoding="utf-8")

    with pytest.raises(SystemExit, match="바뀌었다"):
        am.apply(blank, tiny)


def test_dry_run은_적용하지_않는다(blank, tiny):
    assert am.apply(blank, tiny, dry_run=True) == ["V1__one.sql", "V2__two.sql"]

    with blank.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migration")
        assert cur.fetchone()[0] == 0


# ---------------------------------------------------------------- 줄바꿈 정규화

SAME_CONTENT = b"CREATE TABLE one (id int);\n-- \xed\x95\x9c\xea\xb8\x80 \xec\xa3\xbc\xec\x84\x9d\n"


def test_체크섬은_줄바꿈에_영향받지_않는다(tmp_path):
    """같은 내용이면 Windows 체크아웃과 리눅스 체크아웃이 같은 값을 내야 한다."""
    lf = tmp_path / "V1__lf.sql"
    crlf = tmp_path / "V1__crlf.sql"
    lf.write_bytes(SAME_CONTENT)
    crlf.write_bytes(SAME_CONTENT.replace(b"\n", b"\r\n"))

    assert am.checksum(lf) == am.checksum(crlf)
    assert am.crlf_checksum(lf) == am.crlf_checksum(crlf)
    assert am.checksum(lf) != am.crlf_checksum(lf)      # 옛 방식과는 달라야 알아본다


@pytest.fixture()
def 여러줄_V1(tiny):
    """LF 와 CRLF 가 실제로 다른 값을 내는 파일.

    🔴 한 줄짜리 파일로는 이 검사가 조용히 무의미해진다 — 줄바꿈이 없으면 두 방식이
       같은 값을 낸다. 2026-09-19 에 이 테스트를 처음 쓸 때 실제로 그렇게 통과했다.
    """
    path = tiny / "V1__one.sql"
    path.write_bytes(b"CREATE TABLE one (id int);\n-- \xed\x95\x9c\xea\xb8\x80\n")
    assert am.checksum(path) != am.crlf_checksum(path)
    return path


def test_CRLF로_심긴_옛_원장을_알아보고_고쳐_적는다(blank, tiny, 여러줄_V1):
    """🔴 2026-09-19 에 EC2 배포가 멈춘 자리다.

    원장을 Windows 체크아웃(core.autocrlf=true)에서 심어 CRLF 로 계산된 값이 들어 있었고,
    리눅스 CI 는 LF 로 계산해 V1 부터 "내용이 바뀌었다"로 멈췄다. 내용은 같았다.
    """
    am.apply(blank, tiny)
    path = 여러줄_V1
    with blank.cursor() as cur:
        cur.execute("UPDATE schema_migration SET checksum = %s WHERE version = 1",
                    (am.crlf_checksum(path),))

    assert am.apply(blank, tiny) == []                  # 멈추지 않는다

    with blank.cursor() as cur:
        cur.execute("SELECT checksum FROM schema_migration WHERE version = 1")
        assert cur.fetchone()[0] == am.checksum(path)   # 정규화 값으로 고쳐 적었다


def test_dry_run은_원장_체크섬도_안_고친다(blank, tiny, 여러줄_V1, capsys):
    """"보기만 한다" 는 약속은 이 수습 경로에도 그대로 적용된다."""
    am.apply(blank, tiny)
    old = am.crlf_checksum(여러줄_V1)
    with blank.cursor() as cur:
        cur.execute("UPDATE schema_migration SET checksum = %s WHERE version = 1", (old,))

    assert am.apply(blank, tiny, dry_run=True) == []

    with blank.cursor() as cur:
        cur.execute("SELECT checksum FROM schema_migration WHERE version = 1")
        assert cur.fetchone()[0] == old
    assert "[dry-run]" in capsys.readouterr().out


# ---------------------------------------------------------------- baseline

def test_baseline은_실행하지_않고_기록만_한다(blank, tiny):
    """이력이 없던 시절 손으로 적용한 DB(로컬·EC2) 용이다."""
    assert am.baseline(blank, 1, tiny) == ["V1__one.sql"]

    with blank.cursor() as cur:
        cur.execute("SELECT to_regclass('one') IS NULL")   # 실행은 안 됐다
        assert cur.fetchone()[0] is True
    assert am.apply(blank, tiny, dry_run=True) == ["V2__two.sql"]   # V1 은 건너뛴다


# ---------------------------------------------------------------- 권한

def test_권한을_주고_앞으로_만들_테이블까지_덮는다(blank, tiny):
    """🔴 2026-09-18 에 EC2 API 가 전부 500 이었던 원인이 이 누락이다.

    마이그레이션마다 사람이 기억해서 GRANT 하는 구조면 또 빠진다 — default privileges 로
    **그 뒤에 만들어질 테이블**까지 덮는지가 핵심이다.
    """
    blank.execute("CREATE ROLE app_role")
    am.apply(blank, tiny)
    am.grant(blank, "app_role")

    with blank.cursor() as cur:
        cur.execute("SELECT has_table_privilege('app_role', 'one', 'SELECT')")
        assert cur.fetchone()[0] is True

    # 권한을 준 **뒤에** 생긴 테이블도 읽을 수 있어야 한다.
    (tiny / "V3__later.sql").write_text("CREATE TABLE later (id int);", encoding="utf-8")
    am.apply(blank, tiny)
    with blank.cursor() as cur:
        cur.execute("SELECT has_table_privilege('app_role', 'later', 'SELECT')")
        assert cur.fetchone()[0] is True


def test_dry_run은_권한도_안_준다(blank, tiny, capsys):
    """🔴 "보기만 한다" 는 약속이 한 번 깨지면 다음 사람이 dry-run 을 못 믿는다."""
    blank.execute("CREATE ROLE dry_role")
    am.apply(blank, tiny)
    assert am.main(["--dsn", blank.uri, "--dir", str(tiny),
                    "--dry-run", "--grant-role", "dry_role"]) == 0

    with blank.cursor() as cur:
        cur.execute("SELECT has_table_privilege('dry_role', 'one', 'SELECT')")
        assert cur.fetchone()[0] is False
    assert "[dry-run]" in capsys.readouterr().out


def test_이상한_롤_이름은_막는다(blank):
    """롤 이름은 식별자 자리에 들어가 파라미터 바인딩이 안 된다 — 모양을 먼저 본다."""
    with pytest.raises(SystemExit):
        am.grant(blank, "app_role; DROP TABLE spike")


# ---------------------------------------------------------------- 실제 스키마

def test_진짜_마이그레이션_전부가_빈_DB에_적용된다(blank):
    """V1~V10 을 순서대로 실제로 적용해 본다 — CI 와 배포가 이 경로를 쓴다."""
    applied = am.apply(blank)

    assert len(applied) == len(am.migration_files())
    with blank.cursor() as cur:
        cur.execute("SELECT to_regclass('spike_candidate') IS NOT NULL, "
                    "to_regclass('page_intro') IS NOT NULL")
        assert cur.fetchone() == (True, True)
