"""Run with uv run --with pgserver --with 'psycopg[binary]' python tools/test_local_migrations.py."""
from pathlib import Path
import sys
import tempfile
import unittest

import pgserver
import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db"))
from apply_migrations import migration_files, version_of
from migrate_local import migrate


class LocalMigrationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = pgserver.get_server(tempfile.mkdtemp(prefix="wikipulse-migration-test-"))
        cls.admin = psycopg.connect(cls.server.get_uri(), autocommit=True)
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()
        cls.server.cleanup()

    def setUp(self):
        type(self).counter += 1
        self.name = f"migration_test_{self.counter}"
        self.admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.name)))
        self.db = psycopg.connect(self.server.get_uri(), dbname=self.name, autocommit=True)

    def tearDown(self):
        self.db.close()
        self.admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(self.name)))

    def legacy(self):
        for path in migration_files():
            if version_of(path) <= 14:
                self.db.execute(path.read_text(encoding="utf-8"))
        self.db.execute("INSERT INTO member(email,display_name) VALUES ('Legacy@example.com','Legacy')")

    def test_fresh_and_repeat(self):
        self.assertEqual(len(migrate(self.db)), len(migration_files()))
        self.assertEqual(migrate(self.db), [])
        self.assertIsNotNone(self.db.execute("SELECT to_regclass('spring_session')").fetchone()[0])

    def test_legacy_requires_explicit_baseline(self):
        self.legacy()
        with self.assertRaisesRegex(RuntimeError, "no migration history"):
            migrate(self.db)
        self.assertIsNone(self.db.execute("SELECT to_regclass('schema_migration')").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT count(*) FROM member").fetchone()[0], 1)

    def test_legacy_upgrade_preserves_data(self):
        self.legacy()
        migrate(self.db, legacy_baseline=14)
        self.assertEqual(self.db.execute("SELECT email FROM member").fetchone()[0], "Legacy@example.com")
        self.assertEqual(migrate(self.db), [])

    def test_collision_rolls_back_schema_and_history(self):
        self.legacy()
        self.db.execute("INSERT INTO member(email,display_name) VALUES ('legacy@example.com','Collision')")
        with self.assertRaises(psycopg.errors.RaiseException):
            migrate(self.db, legacy_baseline=14)
        self.assertEqual(self.db.execute("SELECT count(*) FROM member").fetchone()[0], 2)
        self.assertIsNone(self.db.execute("SELECT to_regclass('schema_migration')").fetchone()[0])
        self.assertIsNone(self.db.execute("SELECT to_regclass('spring_session')").fetchone()[0])

    def test_invalid_baseline(self):
        self.legacy()
        with self.assertRaises(ValueError):
            migrate(self.db, legacy_baseline=999)

    def test_checksum_mismatch_stops(self):
        migrate(self.db)
        self.db.execute("UPDATE schema_migration SET checksum='changed' WHERE version=1")
        with self.assertRaises(SystemExit):
            migrate(self.db)


if __name__ == "__main__":
    unittest.main()
