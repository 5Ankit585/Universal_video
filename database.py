"""
database.py  —  SQLite download history
"""

import sqlite3
import os

# On Render, keep the DB in /tmp so it's writable
_DEFAULT_PATH = "/tmp/history.db" if os.environ.get("RENDER") else "history.db"


class HistoryDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or _DEFAULT_PATH
        self._init()

    def _init(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    title   TEXT,
                    path    TEXT,
                    type    TEXT,
                    quality TEXT,
                    date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def add_entry(self, title: str, path: str, filetype: str, quality: str):
        try:
            with sqlite3.connect(self.db_path) as c:
                c.execute(
                    "INSERT INTO downloads (title, path, type, quality) VALUES (?,?,?,?)",
                    (title, path, filetype, quality),
                )
        except Exception:
            pass  # Never crash the download just because history failed

    def get_all(self):
        try:
            with sqlite3.connect(self.db_path) as c:
                return c.execute(
                    "SELECT title, path, type, quality, date FROM downloads ORDER BY date DESC"
                ).fetchall()
        except Exception:
            return []

    def clear(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM downloads")