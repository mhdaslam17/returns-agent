import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EMAILS_PATH = ROOT / "evals" / "emails.json"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "data" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def seed():
    return _load_seed_module()


@pytest.fixture(scope="session")
def db(seed, tmp_path_factory):
    """A fresh copy of the fake database for each test run."""
    path = seed.build(tmp_path_factory.mktemp("db") / "orders.db")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture
def fresh_con(seed, tmp_path):
    """A new database for one test. Use it when the test writes (refunds)."""
    from returns_agent.db import connect

    con = connect(seed.build(tmp_path / "orders.db"))
    yield con
    con.close()


@pytest.fixture(scope="session")
def emails():
    return json.loads(EMAILS_PATH.read_text(encoding="utf-8"))
