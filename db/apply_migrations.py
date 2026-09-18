"""`db/migrations/V*.sql` 을 버전 순서대로 적용한다 (WP-131).

    python db/apply_migrations.py "postgresql://user:pw@host:5432/wikipulse"
    DATABASE_URL=... python db/apply_migrations.py

왜 있나
    지금까지 마이그레이션을 적용하는 방법이 세 갈래였다 — 로컬은 compose 의 initdb,
    CI 는 pgserver 픽스처(`db/tests/conftest.py`), EC2 는 **사람이 psql 로 직접**.
    셋째 때문에 2026-09-18 에 EC2 만 V7~V9 가 빠진 채로 돌고 있었다(WP-133).
    이 스크립트가 "파일을 순서대로 적용한다" 를 한 곳에 둔다 — CI 잡과 배포가 같은 것을 쓴다.

⚠️ **Flyway 가 아니다.** 적용 이력을 남기지 않으므로 **이미 적용된 파일을 다시 돌리면
   실패한다**(`ALTER TABLE ... ADD COLUMN` 은 중복이면 에러). 빈 DB 를 만드는 용도다.
   운영 DB 에 증분 적용하는 도구는 WP-133 에서 정한다 — 그때 이 스크립트가
   이력 테이블을 갖든 Flyway 로 바뀌든 호출부는 그대로 둘 수 있게 여기 한 곳만 본다.
"""

from __future__ import annotations

import os
import pathlib
import sys

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"


def migration_files(directory: pathlib.Path = MIGRATIONS_DIR) -> list[pathlib.Path]:
    """V1, V2, … 버전 순서대로. Flyway 규칙(`V<n>__`)을 파일명 숫자로 정렬한다.

    🔴 문자열 정렬이 아니다 — 그러면 V10 이 V2 보다 먼저 와서 없는 테이블을 고치려 든다.
    """
    return sorted(directory.glob("V*__*.sql"),
                  key=lambda p: int(p.name.split("__")[0][1:]))


def apply(dsn: str, directory: pathlib.Path = MIGRATIONS_DIR) -> int:
    """전부 적용하고 적용한 파일 수를 돌려준다. 하나라도 실패하면 예외가 그대로 올라간다."""
    import psycopg

    files = migration_files(directory)
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in files:
            print(f"적용 {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))
    return len(files)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dsn = args[0] if args else os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("DSN 이 없다 — 인자로 주거나 DATABASE_URL 을 설정한다", file=sys.stderr)
        return 2
    count = apply(dsn)
    print(f"마이그레이션 {count}개 적용 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
