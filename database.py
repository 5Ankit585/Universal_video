import sqlite3
import os
import threading

DB_PATH = "history.db"


class HistoryDB:

    def __init__(self):
        self.lock = threading.Lock()
        self.create_table()

    def get_connection(self):
        return sqlite3.connect(DB_PATH, check_same_thread=False)

    def create_table(self):
        with self.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                path TEXT,
                type TEXT,
                quality TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

    def add_entry(self, title, path, filetype, quality):
        with self.lock:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO downloads (title, path, type, quality) VALUES (?, ?, ?, ?)",
                    (title, path, filetype, quality)
                )

    def get_all(self):
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT title, path, type, quality, date FROM downloads ORDER BY date DESC"
            )
            return cursor.fetchall()