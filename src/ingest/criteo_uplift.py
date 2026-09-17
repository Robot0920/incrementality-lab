"""Pod 0 / S3 — ingest the Criteo-UPLIFT v2.1 randomized advertising experiment.

Why this dataset is the spine of our causal work
------------------------------------------------
It is one of the very few PUBLIC logs of a real large-scale randomized experiment:
13,979,592 users, randomly assigned to `treatment` (ad campaign on) or control,
with 12 anonymized features plus three outcome columns.

The column that makes it special is `exposure`: being *assigned* to treatment is not the
same as actually *seeing* the ad. That gap is our product's hardest measurement problem —
an artist turning Amplify on is not the same as the algorithm actually promoting them —
and it is exactly what separates ITT from LATE.

Caveat recorded in docs/02_data_dictionary.md: the authors sub-sampled non-uniformly to
hide the true incrementality levels, so the METHODS here transfer but the effect
magnitudes are not real-world business numbers.

Run:
    python -m src.ingest.criteo_uplift            # download (once) + load to bronze
    python -m src.ingest.criteo_uplift --force    # re-download and rebuild
"""

from __future__ import annotations

import argparse
import time

import requests
from tqdm import tqdm

from src.config import RAW_DIR, ensure_dirs
from src.db import connect

SOURCE_URL = "https://go.criteo.net/criteo-research-uplift-v2.1.csv.gz"
# Keep the filename identical to the URL's basename, so a file you downloaded in a
# browser can simply be dropped into data/raw/ and will be picked up as-is.
RAW_FILE = RAW_DIR / SOURCE_URL.rsplit("/", 1)[-1]
TABLE = "bronze.criteo_uplift"

# Published figures we assert against, so a silently truncated download
# can never become a silently wrong analysis.
EXPECTED_ROWS = 13_979_592
MIN_BYTES = 250_000_000  # published size is ~297 MB gzipped


def download(force: bool = False) -> None:
    """Stream the gzipped CSV to disk with a progress bar."""
    ensure_dirs()
    if RAW_FILE.exists() and not force:
        size_mb = RAW_FILE.stat().st_size / 1e6
        if RAW_FILE.stat().st_size >= MIN_BYTES:
            print(f"[skip] {RAW_FILE.name} already present ({size_mb:.0f} MB)")
            return
        print(f"[warn] {RAW_FILE.name} is only {size_mb:.0f} MB — truncated, re-downloading")

    print(f"[get ] {SOURCE_URL}")
    started = time.time()
    with requests.get(SOURCE_URL, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(RAW_FILE, "wb") as fh, tqdm(
            total=total or None, unit="B", unit_scale=True, unit_divisor=1024
        ) as bar:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                bar.update(len(chunk))

    size_mb = RAW_FILE.stat().st_size / 1e6
    print(f"[ok  ] {size_mb:.0f} MB in {time.time() - started:.0f}s")
    if RAW_FILE.stat().st_size < MIN_BYTES:
        raise RuntimeError(f"download looks truncated: {size_mb:.0f} MB < {MIN_BYTES/1e6:.0f} MB")


def load_bronze() -> int:
    """Load the raw CSV into bronze, unmodified except for lineage columns.

    The one rule of bronze: no transformation beyond load metadata. Start cleaning here
    and you permanently lose the ability to answer "what did the source actually send?"
    — which is step 1 of every root cause analysis.
    """
    con = connect()
    print(f"[load] -> {TABLE}")
    # The interpolated values here are module-level constants, not user input, so string
    # interpolation is safe. Anything reaching this from outside the repo must instead be
    # passed as a query parameter (con.execute(sql, [value])) to avoid SQL injection.
    # _loaded_at uses the database's own now() rather than a Python timestamp: fewer
    # timezone and formatting failure modes, and the value is consistent across rows.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLE} AS
        SELECT
            *,
            '{SOURCE_URL}' AS _source,
            now()          AS _loaded_at
        FROM read_csv_auto('{RAW_FILE}', header = true)
        """
    )
    rows = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]

    # --- ingestion gate: fail loudly, never silently ------------------------
    status = "pass" if rows == EXPECTED_ROWS else "row_count_mismatch"
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.ingest_log (
            loaded_at     TIMESTAMP,
            table_name    VARCHAR,
            source        VARCHAR,
            rows_loaded   BIGINT,
            rows_expected BIGINT,
            status        VARCHAR
        )
        """
    )
    con.execute(
        "INSERT INTO ops.ingest_log VALUES (now(), ?, ?, ?, ?, ?)",
        [TABLE, SOURCE_URL, rows, EXPECTED_ROWS, status],
    )

    print(con.sql(f"DESCRIBE {TABLE}").df().to_string(index=False))
    print(f"\n[rows] {rows:,} loaded / {EXPECTED_ROWS:,} expected -> {status}")
    if status != "pass":
        print("[warn] row count differs from the published figure — investigate before analyzing")
    con.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download and rebuild the table")
    args = parser.parse_args()
    download(force=args.force)
    load_bronze()


if __name__ == "__main__":
    main()
