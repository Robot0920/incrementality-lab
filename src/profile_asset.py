"""Capability matrix for a warehouse table.

Answers one question: which analytical methods does this asset actually support? Six checks
decide it, and each one rules out a class of methods when it fails.

    grain     does one row equal the unit being reasoned about?
    variation is there treatment or exposure variation to exploit?
    outcome   is the outcome present, or only a proxy?
    time      are there timestamps or repeated observations?
    money     can outcomes be converted into currency?
    linkage   can this be joined to other entities or the other side of a market?

Run:
    python -m src.profile_asset bronze.criteo_uplift
    python -m src.profile_asset silver.campaign_day --id campaign_id --money-like spend,royalty
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.db import connect

TEMPORAL_TYPES = ("DATE", "TIME", "TIMESTAMP")
MONEY_TOKENS = (
    "price", "cost", "revenue", "amount", "spend", "margin",
    "royalty", "gmv", "payout", "fee", "value", "budget",
)


def column_stats(con, table: str) -> pd.DataFrame:
    """One row per column: type, null count, approximate cardinality, range."""
    schema = con.execute(f"DESCRIBE {table}").fetchall()
    selects = [
        f"""
        SELECT '{name}' AS column_name,
               '{dtype}' AS column_type,
               count(*) - count("{name}")            AS nulls,
               approx_count_distinct("{name}")       AS distinct_approx,
               CAST(min("{name}") AS VARCHAR)        AS min_value,
               CAST(max("{name}") AS VARCHAR)        AS max_value
        FROM {table}
        """
        for name, dtype, *_ in schema
    ]
    return con.sql(" UNION ALL ".join(selects)).df()


def capability_matrix(stats: pd.DataFrame, n_rows: int, id_col: str | None,
                      id_distinct: int | None, money_like: list[str]) -> list[tuple[str, str, str]]:
    """Return (check, verdict, evidence) triples."""
    out: list[tuple[str, str, str]] = []

    # grain -------------------------------------------------------------------
    if id_col is None:
        out.append(("grain", "UNVERIFIED", "no --id supplied; grain is an assumption"))
    elif id_distinct == n_rows:
        out.append(("grain", "PASS", f"{id_col} is unique across {n_rows:,} rows"))
    else:
        out.append(("grain", "FAIL",
                    f"{n_rows:,} rows but {id_distinct:,} distinct {id_col}; rates will have the wrong denominator"))

    # variation / outcome -----------------------------------------------------
    binary = stats[(stats.distinct_approx <= 2) & (stats.min_value.isin(["0", "false"]))]
    names = ", ".join(binary.column_name) or "none"
    verdict = "PASS" if len(binary) else "FAIL"
    out.append(("variation", verdict, f"binary columns available as flags or outcomes: {names}"))
    out.append(("outcome", verdict, "confirm which of the binary columns is the outcome of interest"))

    # time --------------------------------------------------------------------
    temporal = stats[stats.column_type.str.upper().str.contains("|".join(TEMPORAL_TYPES))]
    temporal = temporal[~temporal.column_name.str.startswith("_")]  # ignore lineage columns
    if len(temporal):
        out.append(("time", "PASS", f"temporal columns: {', '.join(temporal.column_name)}"))
    else:
        out.append(("time", "FAIL",
                    "no temporal column; rules out switchback, diff-in-diff, interrupted time "
                    "series, seasonality and sequential testing"))

    # money -------------------------------------------------------------------
    tokens = money_like or list(MONEY_TOKENS)
    monetary = stats[stats.column_name.str.lower().str.contains("|".join(tokens))]
    if len(monetary):
        out.append(("money", "PASS", f"monetary columns: {', '.join(monetary.column_name)}"))
    else:
        out.append(("money", "FAIL",
                    "no monetary column; rules out unit economics, break-even and opportunity sizing"))

    # linkage -----------------------------------------------------------------
    keys = stats[(stats.distinct_approx > max(10, 0.01 * n_rows)) & (stats.distinct_approx < n_rows)]
    if len(keys):
        out.append(("linkage", "PASS", f"candidate join keys: {', '.join(keys.column_name)}"))
    else:
        out.append(("linkage", "FAIL",
                    "no candidate join key; cannot be linked to other entities or the other side of a market"))

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("table", help="schema-qualified table name")
    ap.add_argument("--id", dest="id_col", default=None, help="column expected to be unique per row")
    ap.add_argument("--money-like", default="", help="comma-separated extra tokens that indicate currency")
    args = ap.parse_args()

    money_like = [t.strip().lower() for t in args.money_like.split(",") if t.strip()]

    con = connect(read_only=True)
    try:
        n_rows = con.execute(f"SELECT count(*) FROM {args.table}").fetchone()[0]
        stats = column_stats(con, args.table)
        id_distinct = None
        if args.id_col:
            id_distinct = con.execute(
                f'SELECT count(DISTINCT "{args.id_col}") FROM {args.table}'
            ).fetchone()[0]
    finally:
        con.close()

    print(f"\n{args.table}  —  {n_rows:,} rows, {len(stats)} columns\n")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(stats.to_string(index=False))

    print("\ncapability matrix\n")
    rows = capability_matrix(stats, n_rows, args.id_col, id_distinct, money_like)
    width = max(len(c) for c, _, _ in rows)
    for check, verdict, evidence in rows:
        print(f"  {check:<{width}}  {verdict:<10}  {evidence}")

    failed = [c for c, v, _ in rows if v == "FAIL"]
    print(f"\nblocked capabilities: {', '.join(failed) if failed else 'none'}\n")


if __name__ == "__main__":
    main()
