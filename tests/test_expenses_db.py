import asyncio
import importlib
import os
import shutil
import sqlite3
import tempfile
import unittest

main_module = importlib.import_module("test_remote_server.main")


class ExpenseDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = main_module.DB_PATH
        main_module.DB_PATH = os.path.join(self.temp_dir, "expenses.db")
        os.makedirs(os.path.dirname(main_module.DB_PATH), exist_ok=True)
        main_module.init_db()

    def tearDown(self):
        main_module.DB_PATH = self.original_db_path
        try:
            with sqlite3.connect(self.original_db_path) as connection:
                connection.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.Error:
            pass
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except OSError:
            pass

    def test_multiple_expenses_persist(self):
        asyncio.run(
            main_module.add_expense("2024-01-01", 10.5, "Food", "Lunch", "first")
        )
        asyncio.run(
            main_module.add_expense("2024-01-02", 20.0, "Travel", "Bus", "second")
        )

        rows = asyncio.run(main_module.list_expenses("2024-01-01", "2024-12-31"))
        self.assertEqual(len(rows), 2)

        with sqlite3.connect(main_module.DB_PATH) as connection:
            persisted = connection.execute(
                "SELECT id, date, amount, category, note FROM expenses ORDER BY id"
            ).fetchall()

        self.assertEqual(len(persisted), 2)
        self.assertEqual(persisted[0][1], "2024-01-01")
        self.assertEqual(persisted[1][1], "2024-01-02")

    def test_db_path_falls_back_when_preferred_dir_is_invalid(self):
        base_dir = tempfile.mkdtemp()
        invalid_parent = os.path.join(base_dir, "blocked")
        with open(invalid_parent, "w", encoding="utf-8") as handle:
            handle.write("not a directory")

        candidate = os.path.join(invalid_parent, "expenses.db")
        original_env = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = candidate
        try:
            resolved = main_module.resolve_db_path()
            self.assertNotEqual(candidate, resolved)
            self.assertTrue(os.path.exists(os.path.dirname(resolved)))
        finally:
            if original_env is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = original_env
            shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
