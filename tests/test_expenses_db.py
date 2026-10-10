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


if __name__ == "__main__":
    unittest.main()
