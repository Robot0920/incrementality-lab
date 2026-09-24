"""Run one .sql file against the warehouse and print the result.

Convention: ONE statement per file. That is deliberate discipline, not laziness — one
file answers one question, the filename states the question, and the file can later be
promoted into a dbt model unchanged.

Run:
    python -m src.sqlrun sql/01_design_audit.sql
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.db import connect


def run(path: Path) -> pd.DataFrame:
    sql = path.read_text()
    con = connect(read_only=True)
    try:
        df = con.sql(sql).df()
    finally:
        con.close()
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path)
    parser.add_argument("--csv", type=Path, default=None, help="also write the result to a CSV")
    args = parser.parse_args()

    df = run(args.sql_file)
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(f"\n--- {args.sql_file} ---\n")
        print(df.to_string(index=False))
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\n[csv ] {args.csv}")


if __name__ == "__main__":
    main()
