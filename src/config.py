"""Single source of truth for every path in the project.

No script builds a path of its own; everything imports from here. The practical reason
for the discipline: when this pipeline moves from a Codespace to BigQuery, exactly one
file has to change.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# `RE_DATA_DIR` lets you relocate all data without touching code.
DATA_DIR = Path(os.getenv("RE_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.getenv("RE_DB_PATH", DATA_DIR / "incrementality.duckdb"))

SQL_DIR = REPO_ROOT / "sql"
DOCS_DIR = REPO_ROOT / "docs"


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet (idempotent)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
