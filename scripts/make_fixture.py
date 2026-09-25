"""Write a small deterministic sample of the reference dataset for code validation.

The full dataset is 297 MB and is never committed. A fixture lets SQL and estimator code
be exercised anywhere -- in CI, on a laptop, in review -- without it.

The fixture is for validating that code runs and returns the right shape. It is not for
producing results: a 50,000-row sample has roughly twenty times the sampling error of the
full file, and the rare exposed cell shrinks to about 1,500 rows. Any number quoted
anywhere in this repository comes from the full dataset.

    python scripts/make_fixture.py        # requires bronze.criteo_uplift to exist
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.db import connect

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "criteo_sample.parquet"
SOURCE = "bronze.criteo_uplift"
N_ROWS = 50_000
SEED = 42
MAX_BYTES = 15 * 1024 * 1024  # refuse to write something too large to belong in git


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = connect(read_only=True)
    try:
        total = con.execute(f"SELECT count(*) FROM {SOURCE}").fetchone()[0]
        # Reservoir sampling with a fixed seed is deterministic: the same rows every run,
        # so the fixture only changes when someone deliberately changes it.
        con.execute(
            f"""
            COPY (
                SELECT * FROM {SOURCE} USING SAMPLE {N_ROWS} ROWS (reservoir, {SEED})
            ) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
    finally:
        con.close()

    size = OUT.stat().st_size
    print(f"sampled {N_ROWS:,} of {total:,} rows -> {OUT.relative_to(Path.cwd())} "
          f"({size / 1e6:.1f} MB)")

    if size > MAX_BYTES:
        OUT.unlink()
        sys.exit(f"fixture is {size / 1e6:.1f} MB, above the {MAX_BYTES / 1e6:.0f} MB limit; "
                 f"lower N_ROWS and run again")

    # Report the cell counts so the fixture's composition is visible in the commit message.
    con = connect(read_only=True)
    try:
        cells = con.execute(
            f"SELECT treatment, exposure, count(*) FROM read_parquet('{OUT}') "
            f"GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
    finally:
        con.close()
    print("cell composition (treatment, exposure, n):")
    for row in cells:
        print(f"  {row[0]}  {row[1]}  {row[2]:>8,}")


if __name__ == "__main__":
    main()
