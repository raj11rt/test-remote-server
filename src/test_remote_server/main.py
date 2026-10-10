import json
import os
import sqlite3
import tempfile

import aiosqlite
from fastmcp import FastMCP

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.environ.get("APP_DATA_DIR", os.path.join(PROJECT_ROOT, ".data"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")


def resolve_db_path() -> str:
    candidates = []
    env_path = os.environ.get("DB_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(os.path.join(DATA_DIR, "expenses.db"))
    candidates.append(
        os.path.join(tempfile.gettempdir(), "test_remote_server", "expenses.db")
    )

    for candidate in candidates:
        directory = os.path.dirname(candidate) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            test_file = os.path.join(directory, ".write_test")
            with open(test_file, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(test_file)
            return candidate
        except OSError:
            continue

    return os.path.join(tempfile.gettempdir(), "test_remote_server", "expenses.db")


DB_PATH = resolve_db_path()
print(f"Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")


def init_db() -> None:
    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO expenses(date, amount, category) VALUES (?, ?, ?)",
                ("2000-01-01", 0, "test"),
            )
            connection.execute("DELETE FROM expenses WHERE category = 'test'")
            print("Database initialized successfully with write access")
    except sqlite3.Error as exc:
        print(f"Database initialization error: {exc!s}")
        raise


init_db()


@mcp.tool()
async def add_expense(
    date: str, amount: float, category: str, subcategory: str = "", note: str = ""
):
    """Add a new expense entry to the database."""
    try:
        async with aiosqlite.connect(DB_PATH) as connection:
            cursor = await connection.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note),
            )
            expense_id = cursor.lastrowid
            await connection.commit()
            return {
                "status": "success",
                "id": expense_id,
                "message": "Expense added successfully",
            }
    except aiosqlite.Error as exc:
        if "readonly" in str(exc).lower():
            return {
                "status": "error",
                "message": "Database is in read-only mode. Check file permissions.",
            }
        return {"status": "error", "message": f"Database error: {exc!s}"}


@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    """List expense entries within an inclusive date range."""
    try:
        async with aiosqlite.connect(DB_PATH) as connection:
            cursor = await connection.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date),
            )
            columns = [column[0] for column in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    except aiosqlite.Error as exc:
        return {"status": "error", "message": f"Error listing expenses: {exc!s}"}


@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str | None = None):
    """Summarize expenses by category within an inclusive date range."""
    try:
        async with aiosqlite.connect(DB_PATH) as connection:
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cursor = await connection.execute(query, params)
            columns = [column[0] for column in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    except aiosqlite.Error as exc:
        return {"status": "error", "message": f"Error summarizing expenses: {exc!s}"}


@mcp.resource("expense:///categories", mime_type="application/json")
def categories() -> str:
    default_categories = {
        "categories": [
            "Food & Dining",
            "Transportation",
            "Shopping",
            "Entertainment",
            "Bills & Utilities",
            "Healthcare",
            "Travel",
            "Education",
            "Business",
            "Other",
        ]
    }

    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return json.dumps(default_categories, indent=2)
    except (OSError, json.JSONDecodeError) as exc:
        return json.dumps({"error": f"Could not load categories: {exc!s}"}, indent=2)


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    mcp.run(transport="http", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
