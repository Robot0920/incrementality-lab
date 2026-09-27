"""A data-generating process with a known treatment effect.

The headline study asks whether a modelled counterfactual recovers the truth. On real data
the truth is known once, at one set of conditions. Here it is known at every point of a
parameter grid, which is what makes it possible to say *when* a method fails rather than
only *whether* it failed on one dataset.

Structure, mirroring the reference experiment:

    activity          a latent trait that drives both delivery and the outcome.
                      This is the confounder. Nothing else in the design is confounded.
    assignment        a fair coin, independent of everything. This is what randomisation
                      buys, and it is why the intention-to-treat estimate is unbiased.
    delivery          only possible for assigned units, and more likely for active ones.
                      Post-treatment and selected, exactly as an ad auction behaves.
    outcome           baseline rises with activity; delivery adds a constant effect.

Calibration: the default parameters are not hand-tuned. They are solved for by
`scripts/calibrate_simulator.py`, which matches three moments measured on the reference
dataset -- a 3.604% delivery rate, a 0.1194% baseline among units never delivered to, and a
2.1837% baseline among those delivered to. The control rate of 0.1938% is not fitted and
closes on its own, which is the check that the calibration is consistent. Calibrating to
observed moments is what separates a simulation from an invention.

`observability` is the knob that matters. It sets how much of the latent activity the
analyst's covariates reveal: 1.0 means the confounder is fully measured, 0.0 means it is
entirely hidden. Real covariates are never at 1.0, and the study is about what that costs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit


@dataclass(frozen=True)
class Population:
    """One simulated experiment. Arrays are aligned and one row is one unit."""

    x: np.ndarray                    # observed covariates, shape (n, n_features)
    activity: np.ndarray             # the latent confounder, never shown to an estimator
    assigned: np.ndarray             # randomised 0/1
    delivered: np.ndarray            # 0/1, only ever 1 where assigned == 1
    outcome: np.ndarray              # 0/1
    baseline_probability: np.ndarray # P(outcome) had this unit not been delivered to.
                                     # The ground-truth counterfactual an estimator is
                                     # trying to recover, and never visible to one.
    true_effect: float       # effect of delivery on the outcome probability
    delivery_rate: float     # realised P(delivered = 1 | assigned = 1)

    @property
    def true_itt(self) -> float:
        """The effect of being assigned, diluted by everyone who was never delivered to."""
        return self.true_effect * self.delivery_rate


def simulate(
    n: int = 500_000,
    *,
    treat_share: float = 0.85,
    true_effect: float = 0.032,
    delivery_intercept: float = -5.1321,   # solved by scripts/calibrate_simulator.py
    selection_strength: float = 2.2022,    #   against three moments of the real data
    baseline_intercept: float = -8.4780,
    activity_on_outcome: float = 2.1542,
    observability: float = 0.60,
    n_noise_features: int = 4,
    seed: int = 0,
) -> Population:
    """Draw one experiment.

    delivery_intercept and selection_strength control how often delivery happens and how
    strongly it prefers active units. baseline_intercept and activity_on_outcome control
    the outcome rate and how strongly it also depends on activity -- the two together are
    what make delivery look effective when it is not.
    """
    rng = np.random.default_rng(seed)

    activity = rng.standard_normal(n)

    # Covariates reveal the confounder only partially. corr(x0, activity) = sqrt(observability).
    signal = np.sqrt(observability) * activity + np.sqrt(1.0 - observability) * rng.standard_normal(n)
    noise = rng.standard_normal((n, n_noise_features))
    x = np.column_stack([signal, noise])

    assigned = (rng.random(n) < treat_share).astype(np.int8)

    delivery_propensity = expit(delivery_intercept + selection_strength * activity)
    delivered = (assigned == 1) & (rng.random(n) < delivery_propensity)
    delivered = delivered.astype(np.int8)

    baseline = expit(baseline_intercept + activity_on_outcome * activity)
    outcome_probability = np.clip(baseline + true_effect * delivered, 0.0, 1.0)
    outcome = (rng.random(n) < outcome_probability).astype(np.int8)

    realised_delivery = float(delivered[assigned == 1].mean())
    return Population(x, activity, assigned, delivered, outcome, baseline,
                      true_effect, realised_delivery)


def describe(p: Population) -> str:
    """The moments worth checking against the reference dataset."""
    control = p.outcome[p.assigned == 0]
    treated = p.outcome[p.assigned == 1]
    exposed = p.outcome[p.delivered == 1]
    unexposed_treated = p.outcome[(p.assigned == 1) & (p.delivered == 0)]

    # What delivered units would have converted at with no delivery. Available here only
    # because the simulator knows it; no estimator ever sees this column.
    #
    # The comparison group is assigned-but-undelivered, NOT everyone undelivered. The
    # control arm never had the chance to be delivered to, so it still contains the
    # high-activity units that delivery would have taken; including it raises the
    # comparison baseline and pushes the ratio down. Computing it the loose way gives
    # 16.7x against a true 18.3x -- the same quantity, two different populations, no error
    # raised. This is the `population` field of a metric specification doing real damage.
    delivered = p.delivered == 1
    assigned_undelivered = (p.assigned == 1) & (p.delivered == 0)
    baseline_of_delivered = p.baseline_probability[delivered].mean()
    baseline_of_rest = p.baseline_probability[assigned_undelivered].mean()

    return (
        f"  n                        {p.outcome.size:,}\n"
        f"  assigned share           {p.assigned.mean():.3f}\n"
        f"  delivery rate            {p.delivery_rate:.4%}\n"
        f"  control outcome rate     {control.mean():.4%}\n"
        f"  treated outcome rate     {treated.mean():.4%}\n"
        f"  delivered outcome rate   {exposed.mean():.4%}\n"
        f"  assigned-undelivered     {unexposed_treated.mean():.4%}\n"
        f"  delivered baseline ratio {baseline_of_delivered / baseline_of_rest:.1f}x"
        f"   (vs assigned-undelivered)\n"
        f"  true effect on delivered {p.true_effect:.4%}\n"
        f"  true intention-to-treat  {p.true_itt:.4%}"
    )


if __name__ == "__main__":
    print("\ncalibration check -- compare against docs/01_data_dictionary.md\n")
    print(describe(simulate(n=2_000_000, seed=1)))
    print()
