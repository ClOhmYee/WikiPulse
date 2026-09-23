"""Transactional local Docker migrations, including explicitly baselined legacy volumes."""
import argparse
import os

import psycopg

from apply_migrations import MIGRATIONS_DIR, apply, baseline, migration_files, version_of


def migrate(conn, directory=MIGRATIONS_DIR, legacy_baseline=None):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(211, 15)")
        ledger = conn.execute("SELECT to_regclass('public.schema_migration')").fetchone()[0]
        populated = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public')"
        ).fetchone()[0]
        if not ledger and populated:
            if legacy_baseline is None:
                raise RuntimeError(
                    "Existing database has no migration history. Preserve the volume; "
                    "verify the last fully applied version N, then run "
                    "docker compose run --rm migrate --baseline N. "
                    "See docker/README.md."
                )
            if legacy_baseline not in {version_of(p) for p in migration_files(directory)}:
                raise ValueError("Baseline must be an existing migration version")
            baseline(conn, legacy_baseline, directory)
        elif legacy_baseline is not None:
            raise RuntimeError("--baseline is only for an existing database without history")
        return apply(conn, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=int)
    args = parser.parse_args()
    with psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as conn:
        names = migrate(conn, legacy_baseline=args.baseline)
    print(f"Applied {len(names)} migrations")


if __name__ == "__main__":
    main()
