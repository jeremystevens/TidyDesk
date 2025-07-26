from datetime import datetime
from pathlib import Path
import sqlite3

DB_PATH = Path("file_index.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT,
            new_path TEXT,
            file_type TEXT,
            moved_at TEXT,
            tags TEXT
        )''')
        conn.commit()

def insert_into_db(original_name, new_path, file_type, tags):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO files (original_name, new_path, file_type, moved_at, tags) VALUES (?, ?, ?, ?, ?)',
                  (original_name, new_path, file_type, datetime.now().isoformat(), tags))
        conn.commit()

def update_tags_in_db(filename, tags):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('UPDATE files SET tags = ? WHERE original_name = ?', (tags, filename))
        conn.commit()

def delete_file_record(filename):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM files WHERE original_name = ?", (filename,))
        conn.commit()