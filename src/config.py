"""Single source of truth for every path in the project.

任何脚本都不要自己拼路径 (never hardcode a path elsewhere) —— 全部从这里 import。
这条纪律的现实理由: 当你要把同一套 pipeline 从 Codespace 搬到 BigQuery 时,
只需要改这一个文件。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# `RE_DATA_DIR` lets you relocate all data without touching code.
DATA_DIR = Path(os.getenv("RE_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.getenv("RE_DB_PATH", DATA_DIR / "revenue.duckdb"))

SQL_DIR = REPO_ROOT / "sql"
DOCS_DIR = REPO_ROOT / "docs"


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet (idempotent)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
