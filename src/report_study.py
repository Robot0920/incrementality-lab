"""Read every sweep result on disk and report it.

Separate from src/run_study.py so the grid can be extended without recomputing what already
exists: the runner writes per-replicate estimates, this merges every `study_raw*.csv` in
`results/` and derives everything else. It is also what the readout dashboard will read.

Three outputs:

    relative bias by observability        where each estimator sits, and how fast it moves
    decision-flip rate at two thresholds  the primary outcome: how often the estimate leads
                                          to the wrong decision
    the actionable threshold              the lowest observability at which the best
                                          modelled estimator's flip rate falls below 5%,
                                          which is the pre-registered bar in
                                          docs/03_study_design.md

    python -m src.report_study
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from src.run_study import THRESHOLDS, flip_rate

RESULTS = Path(__file__).resolve().parents[1] / "results"
FLIP = RESULTS / "flip_curve.csv"
FLIP_BAR = 0.05            # the pre-registered decision-flip bar
HEADLINE = "level3_aipw_hajek@sel"
DECISION_THRESHOLD = 1.25  # declining is correct; a flip means shipping anyway


def load() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(RESULTS.glob("study_raw*.csv")):
        with path.open() as fh:
            for row in csv.DictReader(fh):
                rows.append({
                    "observability": float(row["observability"]),
                    "replicate": int(row["replicate"]),
                    "estimator": row["estimator"],
                    "estimate": float(row["estimate"]),
                    "truth": float(row["truth"]),
                })
        print(f"  loaded {path.name}")
    if not rows:
        raise SystemExit("no results/study_raw*.csv found; run python -m src.run_study first")
    return rows


def main() -> None:
    print()
    rows = load()
    grid = sorted({r["observability"] for r in rows}, reverse=True)
    estimators = list(dict.fromkeys(r["estimator"] for r in rows))
    print(f"\n  {len(rows):,} rows   {len(grid)} grid points   {len(estimators)} estimators")

    def series(method: str, observability: float) -> tuple[np.ndarray, float]:
        matching = [r for r in rows
                    if r["estimator"] == method and r["observability"] == observability]
        return np.array([r["estimate"] for r in matching]), matching[0]["truth"]

    header = "".join(f"{o:>10.2f}" for o in grid)

    print(f"\n{'=' * (36 + 10 * len(grid))}\nrelative bias, by observability"
          f"\n{'=' * (36 + 10 * len(grid))}")
    print(f"{'estimator':<34}{header}")
    print("-" * (34 + 10 * len(grid)))
    for method in estimators:
        cells = "".join(
            f"{series(method, o)[0].mean() / series(method, o)[1] - 1:>+9.1%} " for o in grid
        )
        print(f"{method:<34}{cells}")

    for threshold, note in ((DECISION_THRESHOLD, "declining is correct; a flip means shipping anyway"),
                            (0.5, "shipping is correct; a flip means declining anyway")):
        print(f"\n{'=' * (36 + 10 * len(grid))}\ndecision-flip rate at threshold {threshold} "
              f"({note})\n{'=' * (36 + 10 * len(grid))}")
        print(f"{'estimator':<34}{header}")
        print("-" * (34 + 10 * len(grid)))
        for method in estimators:
            cells = "".join(
                f"{flip_rate(*series(method, o), threshold):>9.0%} " for o in grid
            )
            print(f"{method:<34}{cells}")

    # Intervals for the headline estimator, where the reader most needs them.
    print(f"\n  {HEADLINE}: bias with a 95% interval across replicates")
    for o in grid:
        estimates, truth = series(HEADLINE, o)
        bias = estimates.mean() - truth
        half = 1.96 * estimates.std(ddof=1) / np.sqrt(estimates.size)
        print(f"    observability {o:>5.2f}   {bias / truth:>+8.1%}   "
              f"[{(bias - half) / truth:>+7.1%}, {(bias + half) / truth:>+7.1%}]   "
              f"n = {estimates.size}")

    with FLIP.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["observability", "estimator", "threshold", "flip_rate"])
        for o in grid:
            for method in estimators:
                estimates, truth = series(method, o)
                for threshold in THRESHOLDS:
                    writer.writerow([o, method, threshold,
                                     flip_rate(estimates, truth, threshold)])
    print(f"\n  wrote {FLIP}")

    # The number a stakeholder would actually ask for.
    modelled = [m for m in estimators if m.startswith(("level1", "level2", "level3"))]
    print(f"\n  how much covariate coverage is needed before ANY modelled estimator clears"
          f" the pre-registered {FLIP_BAR:.0%} flip bar at threshold {DECISION_THRESHOLD}?")
    cleared = False
    for o in sorted(grid):
        best = min((flip_rate(*series(m, o), DECISION_THRESHOLD), m) for m in modelled)
        status = "clears" if best[0] < FLIP_BAR else "fails"
        print(f"    observability {o:>5.2f}   best modelled flip rate {best[0]:>5.0%}  "
              f"{status:<7} ({best[1]})")
        cleared = cleared or best[0] < FLIP_BAR
    if not cleared:
        print("\n    no grid point clears it. A randomised holdout is required outright.")
    print()


if __name__ == "__main__":
    main()
