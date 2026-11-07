"""Settings in one place. Values come from .env when set."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "orders.db"))
POLICY_PATH = ROOT / "data" / "policy.md"

# The agent's "today". Fixed so trial-window answers match the test labels.
# Must match REFERENCE_DATE in data/seed_db.py.
TODAY = date.fromisoformat(os.getenv("AGENT_TODAY", "2026-11-06"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
