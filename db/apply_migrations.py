"""`db/migrations/V*.sql` 을 적용하고 무엇을 적용했는지 기록한다 (WP-131·-133).

    python db/apply_migrations.py                          # DATABASE_URL 에 적용
    python db/apply_migrations.py --dsn "postgresql://..."
    python db/apply_migrations.py --baseline 10            # 이미 적용된 DB 에 이력만 심는다
    python db/apply_migrations.py --grant-role user_wikipulse
    python db/apply_migrations.py --dry-run                # 무엇이 남았는지만 본다

왜 있나
    적용 방법이 세 갈래였다 — 로컬은 compose 의 initdb, CI 는 pgserver 픽스처,
    EC2 는 **사람이 psql 로 직접**. 셋째 때문에 2026-09-18 에 EC2 만 V7~V9 가 빠진 채
    돌고 있었고, 그때 백엔드 롤에 권한이 하나도 없다는 것도 같이 드러났다.
    이 스크립트가 "무엇을 적용했고 누구에게 권한을 줬는가" 를 한 곳에 둔다.

이력 (`schema_migration`)
    적용한 파일을 버전·체크섬과 함께 남긴다. 그래서 **다시 돌려도 안전하다** — 이미
    적용된 파일은 건너뛴다. 이력이 없던 시절 DB 는 `--baseline N` 으로 한 번 심는다.

    🔴 **체크섬이 다르면 멈춘다.** 이미 적용된 마이그레이션 파일을 나중에 고치면 DB 와
    저장소가 조용히 갈라진다 — 그 상태로 다음 배포가 지나가면 어느 쪽이 맞는지
    알 수 없게 된다. 고칠 일이 있으면 새 버전 파일을 만든다.

    ⚠️ **체크섬은 줄바꿈을 LF 로 정규화한 뒤 계산한다.** 안 그러면 같은 파일이 OS 마다
    다른 값이 된다. 2026-09-19 에 실제로 터졌다 — EC2 원장이 Windows 체크아웃
    (`core.autocrlf=true`)에서 CRLF 로 심겨 있어서, 리눅스 CI 가 V1 부터 "내용이
    바뀌었다"로 멈췄다. **내용은 같았고 줄바꿈만 달랐다.** 옛 CRLF 값은 한 번 알아보고
    정규화 값으로 고쳐 적는다. 재발은 `.gitattributes` 가 막는다.

    ⚠️ Flyway 를 대신하는 최소 구현이다. 롤백·리페어·베이스라인 검증 같은 건 없다.
    도구를 들일지는 WP-133 에서 정하고, 그때 호출부는 이 파일 하나만 본다.

권한 (`--grant-role`)
    애플리케이션 롤에 DML 권한을 준다. 🔴 **새로 만들 테이블까지 덮는다**
    (`ALTER DEFAULT PRIVILEGES`) — 마이그레이션마다 사람이 기억해서 GRANT 하는 구조면
    또 빠진다. 2026-09-18 에 EC2 API 가 전부 500 이었던 원인이 그것이다.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version    INTEGER     PRIMARY KEY,
    filename   TEXT        NOT NULL,
    checksum   TEXT        NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

#: 애플리케이션 롤이 받는 권한. DDL 은 안 준다 — 스키마 변경은 마이그레이션만 한다.
GRANT_SQL = """
GRANT USAGE ON SCHEMA public TO {role};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO {role};
"""


def version_of(path: pathlib.Path) -> int:
    """`V7__spike_view_metrics.sql` → 7."""
    return int(path.name.split("__")[0][1:])


def migration_files(directory: pathlib.Path = MIGRATIONS_DIR) -> list[pathlib.Path]:
    """V1, V2, … 버전 순서대로.

    🔴 문자열 정렬이 아니다 — 그러면 V10 이 V2 보다 먼저 와서 없는 테이블을 고치려 든다.
    """
    return sorted(directory.glob("V*__*.sql"), key=version_of)


def _lf_bytes(path: pathlib.Path) -> bytes:
    """줄바꿈을 LF 로 맞춘 파일 내용."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def checksum(path: pathlib.Path) -> str:
    """파일 내용의 sha256. 적용된 마이그레이션이 나중에 바뀌었는지 보는 값이다.

    🔴 줄바꿈을 LF 로 정규화하고 계산한다 — 안 그러면 Windows 체크아웃과 리눅스
       체크아웃이 같은 파일에 다른 값을 낸다 (모듈 독스트링 참고).
    """
    return hashlib.sha256(_lf_bytes(path)).hexdigest()


def crlf_checksum(path: pathlib.Path) -> str:
    """정규화 이전 방식으로 Windows 체크아웃이 남겼을 값.

    옛 원장을 알아보는 데만 쓴다. 새로 적을 때는 절대 쓰지 않는다.
    """
    return hashlib.sha256(_lf_bytes(path).replace(b"\n", b"\r\n")).hexdigest()


def rewrite_checksum(conn, version: int, value: str) -> None:
    """원장의 체크섬만 고쳐 적는다. 내용이 같다고 확인한 경우에만 부른다."""
    with conn.cursor() as cur:
        cur.execute("UPDATE schema_migration SET checksum = %s WHERE version = %s",
                    (value, version))


def applied_versions(conn) -> dict[int, str]:
    """이미 적용된 {버전: 체크섬}. 이력 테이블이 없으면 만든다."""
    with conn.cursor() as cur:
        cur.execute(LEDGER_DDL)
        cur.execute("SELECT version, checksum FROM schema_migration")
        return dict(cur.fetchall())


def pending(conn, directory: pathlib.Path = MIGRATIONS_DIR, *,
            repair: bool = True) -> list[pathlib.Path]:
    """아직 안 적용된 파일. 적용된 파일이 바뀌었으면 예외를 던진다.

    `repair` 가 거짓이면(= dry-run) 원장을 고치지 않고 무엇을 고칠지만 알린다.
    """
    done = applied_versions(conn)
    remaining = []
    for path in migration_files(directory):
        version = version_of(path)
        if version not in done:
            remaining.append(path)
            continue
        current = checksum(path)
        if done[version] == current:
            continue
        if done[version] == crlf_checksum(path):
            # 내용은 같고 줄바꿈만 CRLF 로 기록된 옛 원장이다. 막을 이유가 없고,
            # 그대로 두면 배포마다 같은 자리에서 멈춘다 — 한 번만 정규화해 적는다.
            if repair:
                rewrite_checksum(conn, version, current)
                print(f"원장 체크섬 정규화(CRLF → LF): {path.name}")
            else:
                print(f"[dry-run] 원장 체크섬 정규화 대상: {path.name}")
            continue
        raise SystemExit(
            f"🔴 이미 적용된 {path.name} 의 내용이 바뀌었다. DB 와 저장소가 갈라진다 — "
            "적용된 마이그레이션은 고치지 말고 새 버전 파일을 만든다."
        )
    return remaining


def record(conn, path: pathlib.Path) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migration (version, filename, checksum) VALUES (%s, %s, %s) "
            "ON CONFLICT (version) DO NOTHING",
            (version_of(path), path.name, checksum(path)))


def apply(conn, directory: pathlib.Path = MIGRATIONS_DIR, *, dry_run: bool = False) -> list[str]:
    """남은 마이그레이션을 적용하고 적용한 파일명을 돌려준다."""
    remaining = pending(conn, directory, repair=not dry_run)
    if dry_run:
        return [p.name for p in remaining]
    for path in remaining:
        print(f"적용 {path.name}")
        conn.execute(path.read_text(encoding="utf-8"))
        record(conn, path)
    return [p.name for p in remaining]


def baseline(conn, upto: int, directory: pathlib.Path = MIGRATIONS_DIR) -> list[str]:
    """V1..upto 를 **실행하지 않고** 적용된 것으로 기록한다.

    이력 테이블이 없던 시절에 손으로 적용한 DB(로컬 compose·EC2)를 위한 것이다.
    ⚠️ 실제로 적용돼 있는지는 확인하지 않는다 — 부르는 사람이 아는 값을 준다.
    """
    applied_versions(conn)          # 이력 테이블 보장
    marked = []
    for path in migration_files(directory):
        if version_of(path) <= upto:
            record(conn, path)
            marked.append(path.name)
    return marked


def grant(conn, role: str) -> None:
    """애플리케이션 롤에 DML 권한 + 앞으로 만들 테이블까지 (모듈 독스트링)."""
    if not role.isidentifier():
        raise SystemExit(f"롤 이름이 이상하다: {role!r}")
    with conn.cursor() as cur:
        cur.execute(GRANT_SQL.format(role=role))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="마이그레이션 적용·이력 (WP-133)")
    p.add_argument("dsn_positional", nargs="?", help="DSN (또는 --dsn / DATABASE_URL)")
    p.add_argument("--dsn", default="")
    p.add_argument("--baseline", type=int, metavar="N",
                   help="V1..N 을 실행하지 않고 적용됨으로 기록 (이력 없던 DB 용)")
    p.add_argument("--grant-role", metavar="ROLE",
                   help="이 롤에 DML 권한과 default privileges 를 준다")
    p.add_argument("--dry-run", action="store_true", help="남은 마이그레이션만 출력")
    # 🔴 배포 드리프트 감지용 (WP-193). `--dry-run` 은 남은 게 있어도 0 을
    #    돌려주므로 CI 가 못 잡는다. 2026-09-22 에 deploy:backend 가 취소되고 후속
    #    파이프라인이 그 잡을 안 만들어 V13 이 조용히 빠졌는데, 파이프라인은 초록이었다.
    p.add_argument("--fail-if-pending", action="store_true",
                   help="남은 마이그레이션이 있으면 비영으로 끝낸다 (--dry-run 을 포함)")
    p.add_argument("--dir", type=pathlib.Path, default=MIGRATIONS_DIR,
                   help="마이그레이션 디렉터리 (기본 db/migrations). 검사·실험용")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    dsn = args.dsn or args.dsn_positional or os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("DSN 이 없다 — 인자로 주거나 DATABASE_URL 을 설정한다", file=sys.stderr)
        return 2

    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        if args.baseline is not None:
            marked = baseline(conn, args.baseline, args.dir)
            print(f"이력만 기록: {len(marked)}개 (V1..V{args.baseline})")
            return 0

        dry_run = args.dry_run or args.fail_if_pending
        names = apply(conn, args.dir, dry_run=dry_run)
        if dry_run:
            print("남은 마이그레이션: " + (", ".join(names) if names else "없음"))
            if args.fail_if_pending and names:
                print(
                    "🔴 저장소에 있는 마이그레이션이 이 DB 에 적용되지 않았다.\n"
                    "   배포가 돌지 않았거나 중간에 취소된 것이다 (WP-193).\n"
                    "   `bash infra/apply-migrations.sh` 로 적용한다.",
                    file=sys.stderr)
                return 1
        else:
            print(f"마이그레이션 {len(names)}개 적용" + (f" ({', '.join(names)})" if names else " (변경 없음)"))

        if args.grant_role:
            if dry_run:
                # 🔴 dry-run 은 아무것도 안 바꾼다. 권한은 멱등이라 티가 안 나지만,
                #    "보기만 한다" 는 약속이 한 번 깨지면 다음 사람이 dry-run 을 못 믿는다.
                print(f"[dry-run] 권한 부여 대상: {args.grant_role}")
            else:
                grant(conn, args.grant_role)
                print(f"권한 부여: {args.grant_role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
