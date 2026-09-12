"""Warehouse connection helper.

One function, one job. Everything in the project talks to DuckDB through here so
that the medallion schemas (bronze / silver / gold) are guaranteed to exist.

The medallion layers:
  bronze  raw landing zone, not one byte altered, replayable
  silver  cleaned and conformed, one row = one business event
  gold    serving layer: aggregates a metric, dashboard or model can consume directly
  ops     operational metadata: ingest log, change events, data-quality results
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
