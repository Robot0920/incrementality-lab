"""Check the estimators against a case whose answer is already known.

At `observability = 1.0` the covariates reveal the confounding trait exactly, so conditional
ignorability holds and the modelled counterfactual is identified. Any bias that remains is
estimation error, not identification error.

Every boosted estimator is run under three configurations:

    def   scikit-learn's defaults for min_samples_leaf (20) and l2_regularization (0)
    reg   min_samples_leaf = 500, l2_regularization = 1.0, chosen by hand
    sel   chosen by held-out log-loss in src/select_hyperparameters.py, separately for the
          outcome and propensity models, never against the known effect

The first two are defensible choices a competent team might make without thinking hard
about either. Reporting them side by side answers a question that matters more than any
single number: **does the choice of hyperparameters move the answer as much as the choice
of estimator?** The third asks the follow-up: **does choosing responsibly narrow the
range?**

Estimators that do not involve boosting -- the naive comparison, ITT, LATE, and the
logistic Level 1 -- are computed once, since the configuration cannot affect them.

    python -m src.validate_estimators
    python -m src.validate_estimators --n 600000 --reps 6 --observability 1.0
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from src.estimators import (
    BOOSTED_DEFAULTS,
    BOOSTED_REGULARISED,
    OUTCOME_KWARGS,
    PROPENSITY_KWARGS,
    aipw_both,
    itt,
    late,
    modelled_counterfactual,
    naive_delivered_vs_control,
)
from src.simulate import simulate

# (outcome-model config, propensity-model config). The first two share one config for both,
# which is what a single BOOSTED_KWARGS forced; the third uses the pair chosen by held-out
# log-loss in src/select_hyperparameters.py.
CONFIGS = {
    "def": (BOOSTED_DEFAULTS, BOOSTED_DEFAULTS),
    "reg": (BOOSTED_REGULARISED, BOOSTED_REGULARISED),
    "sel": (OUTCOME_KWARGS, PROPENSITY_KWARGS),
}


def run_all(p, folds: int, seed: int) -> tuple[dict[str, tuple[float, str]], dict]:
    """Every estimator on one simulated population, boosted ones under both configs."""
    out: dict[str, tuple[float, str]] = {}
    diagnostics: dict = {}

    for est in (
        naive_delivered_vs_control(p.outcome, p.assigned, p.delivered),
        itt(p.outcome, p.assigned),
        late(p.outcome, p.assigned, p.delivered),
        modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered, model="logistic"),
    ):
        out[est.method] = (est.value, est.targets)

    for label, (outcome_kwargs, propensity_kwargs) in CONFIGS.items():
        plain, hajek = aipw_both(p.x, p.outcome, p.assigned, p.delivered,
                                 folds=folds, seed=seed, boosted_kwargs=outcome_kwargs,
                                 propensity_kwargs=propensity_kwargs)
        for est in (
            modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered,
                                    model="boosted", boosted_kwargs=outcome_kwargs),
            modelled_counterfactual(p.x, p.outcome, p.assigned, p.delivered,
                                    model="boosted", calibrate=True, seed=seed,
                                    boosted_kwargs=outcome_kwargs),
            plain,
            hajek,
        ):
            out[f"{est.method}@{label}"] = (est.value, est.targets)
        diagnostics[f"max_weight@{label}"] = hajek.diagnostics["max_weight"]
        diagnostics[f"clipped@{label}"] = hajek.diagnostics["clipped_propensities"]

    return out, diagnostics


def pass_at(observability: float, n: int, reps: int, folds: int, base_seed: int) -> None:
    print(f"\n{'=' * 86}\nobservability = {observability:.2f}   n = {n:,}   "
          f"replicates = {reps}   folds = {folds}\n{'=' * 86}")

    collected: dict[str, list[float]] = {}
    truths: dict[str, float] = {}
    last_diagnostics: dict = {}
    started = time.time()

    for r in range(reps):
        p = simulate(n=n, observability=observability, seed=base_seed + r)
        truth = {"true_effect": p.true_effect, "true_itt": p.true_itt}
        values, last_diagnostics = run_all(p, folds, seed=base_seed + r)
        for method, (value, target) in values.items():
            collected.setdefault(method, []).append(value)
            truths[method] = truth[target]

    print(f"\n{'estimator':<34} {'estimate':>11} {'truth':>11} {'bias':>11} "
          f"{'rel bias':>9} {'std err':>10} {'bias in SE':>11}")
    print("-" * 102)
    summary: dict[str, tuple[float, float, float]] = {}
    for method, values in collected.items():
        arr = np.array(values)
        truth = truths[method]
        bias = arr.mean() - truth
        se = arr.std(ddof=1) / np.sqrt(arr.size) if arr.size > 1 else float("nan")
        in_se = bias / se if se and np.isfinite(se) and se > 0 else float("nan")
        summary[method] = (bias, se, bias / truth)
        print(f"{method:<34} {arr.mean():>+11.6f} {truth:>+11.6f} {bias:>+11.6f} "
              f"{bias / truth:>+8.1%} {se:>10.6f} {in_se:>+11.1f}")

    print(f"\n  elapsed {time.time() - started:.0f}s")
    if last_diagnostics:
        print("\n  AIPW weight diagnostics (last replicate)")
        for key, value in last_diagnostics.items():
            print(f"    {key:<22} {value}")

    # How much does the configuration move each estimator, relative to how much the
    # estimators differ from one another? If the first is comparable to the second, the
    # method does not have a single answer.
    print("\n  sensitivity to configuration, at fixed estimator")
    labels = list(CONFIGS)
    print(f"    {'':<28}" + "".join(f"{lab:>12}" for lab in labels) + f"{'swing':>10}")
    for stem in ("level2_boosted", "level2_boosted_calibrated",
                 "level3_aipw_plain", "level3_aipw_hajek"):
        rows = [summary.get(f"{stem}@{lab}") for lab in labels]
        if all(rows):
            values = [r[2] for r in rows]
            print(f"    {stem:<28}" + "".join(f"{v:>+11.1%} " for v in values)
                  + f"{max(values) - min(values):>9.1%}")

    spread_across_estimators = max(
        abs(v[2]) for k, v in summary.items() if k.startswith(("level1", "level2", "level3"))
    ) - min(
        abs(v[2]) for k, v in summary.items() if k.startswith(("level1", "level2", "level3"))
    )
    print(f"\n    spread across estimators and configs combined: {spread_across_estimators:.1%}")

    if observability >= 0.999:
        print("\n  self-check at full observability: which estimators are unbiased?")
        for method, (bias, se, _) in summary.items():
            if method.startswith(("level2", "level3")):
                verdict = "unbiased" if abs(bias) < 2 * se else "BIASED"
                print(f"    {method:<34} {verdict:<10} bias {bias:+.6f} against SE {se:.6f}")
        print("    (level1_logistic is expected to be biased here: its functional form is\n"
              "     wrong by construction, and that is why it is in the study)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=600_000)
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--observability", type=float, nargs="*", default=[1.0])
    args = ap.parse_args()
    for obs in args.observability:
        pass_at(obs, args.n, args.reps, args.folds, args.seed)
    print()


if __name__ == "__main__":
    main()
