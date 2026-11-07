"""SQLite connection helper."""

import sqlite3
from pathlib import Path

from returns_agent.config import DB_PATH


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found. Run: python data/seed_db.py")
    # check_same_thread=False: LangGraph may run nodes in a worker thread.
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con
