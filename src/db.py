"""Warehouse connection helper.

One function, one job. Everything in the project talks to DuckDB through here so
that the medallion schemas (bronze / silver / gold) are guaranteed to exist.

Medallion 层的含义 (记住这三层, 面试常问):
  bronze  = 原始落地, 不改一个字节, 可重放 (raw, append-only, replayable)
  silver  = 清洗 + 语义化, 一行一个业务事件 (cleaned, conformed, one row = one event)
  gold    = 可直接给指标/dashboard/模型用的聚合宽表 (serving layer)
"""

from __future__ import annotations

import duckdb

from src.config import DB_PATH, ensure_dirs

SCHEMAS = ("bronze", "silver", "gold", "ops")


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the project warehouse, creating the medallion schemas on first use."""
    ensure_dirs()
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    if not read_only:
        for schema in SCHEMAS:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return con
