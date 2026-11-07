"""Stops real keys from being committed in .env.example.

.env.example is tracked by git (it is public on GitHub). Real keys go in .env only.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def test_env_example_has_no_secret_values():
    leaks = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if any(word in name.upper() for word in SECRET_NAMES) and value.strip():
            leaks.append(name.strip())
    assert not leaks, f"Remove these values from .env.example and put them in .env: {leaks}"
