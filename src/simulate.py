"""A data-generating process with a known treatment effect.

The headline study asks whether a modelled counterfactual recovers the truth. On real data
the truth is known once, at one set of conditions. Here it is known at every point of a
parameter grid, which is what makes it possible to say *when* a method fails rather than
only *whether* it failed once.

Structure, mirroring the reference experiment:

    activity          a latent trait driving both delivery and the outcome. The confounder.
    modifier          an observed covariate, independent of activity, that changes how much
                      activity matters. It is what creates a genuine interaction.
    assignment        a fair coin, independent of everything. This is what randomisation
                      buys, and why the intention-to-treat estimate is unbiased.
    delivery          possible only for assigned units, and more likely for active ones.
                      Post-treatment and selected, exactly as an ad auction behaves.
    outcome           baseline rises with activity, curves in it, and interacts with the
                      modifier; delivery adds a constant effect on the probability scale.

Curvature and interaction are present on purpose. Without them the baseline would be
exactly logistic-linear in the latent trait, a logistic regression would already have the
right functional form, and the three estimator levels in docs/04_estimator_selection.md
would be indistinguishable. Their strength is a design knob, not a calibration target.

`observability` is the axis the study sweeps: how much of the latent activity the
covariates reveal. 1.0 means the confounder is fully measured, 0.0 that it is entirely
hidden. Real covariates are never at 1.0, and the study is about what that costs.

Calibration: `delivery_intercept`, `selection_strength`, `baseline_intercept` and
`activity_on_outcome` are solved by scripts/calibrate_simulator.py against three moments of
the reference dataset. They are not hand-tuned.

The two logit functions below are the single definition of this process. Every script that
needs the population -- the calibrator, the convergence check -- imports them rather than
restating the formula, so the sampled and integrated versions cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit

# Solved by scripts/calibrate_simulator.py; see the header there for the targets.
DELIVERY_INTERCEPT = -4.4672
SELECTION_STRENGTH = 1.6958
BASELINE_INTERCEPT = -8.1531
ACTIVITY_ON_OUTCOME = 1.0284

# Design knobs, chosen rather than fitted. They set how much functional-form error a
# linear-in-logit model makes, which is what separates estimator Level 1 from Level 2.
CURVATURE = 0.35
INTERACTION = 0.60

N_NOISE_FEATURES = 4
TRUE_EFFECT = 0.032          # effect of delivery on the outcome probability
TREAT_SHARE = 0.85


def delivery_logit(activity, delivery_intercept=DELIVERY_INTERCEPT,
                   selection_strength=SELECTION_STRENGTH):
    """Log-odds that an assigned unit is actually delivered to."""
    return delivery_intercept + selection_strength * activity


def baseline_logit(activity, modifier, baseline_intercept=BASELINE_INTERCEPT,
                   activity_on_outcome=ACTIVITY_ON_OUTCOME,
                   curvature=CURVATURE, interaction=INTERACTION):
    """Log-odds of the outcome in the absence of delivery.

    Three terms beyond the intercept: linear in activity, curved in activity, and an
    interaction between activity and an observed modifier. A logistic regression on the
    observed covariates can represent the first and not the other two.
    """
    return (
        baseline_intercept
        + activity_on_outcome * activity
        + curvature * (activity**2 - 1.0)      # centred, so the intercept keeps its meaning
        + interaction * activity * modifier
    )


@dataclass(frozen=True)
class Population:
    """One simulated experiment. Arrays are aligned and one row is one unit."""

    x: np.ndarray                     # observed covariates: [signal, modifier, noise...]
    activity: np.ndarray              # the latent confounder, never shown to an estimator
    assigned: np.ndarray              # randomised 0/1
    delivered: np.ndarray             # 0/1, only ever 1 where assigned == 1
    outcome: np.ndarray               # 0/1
    baseline_probability: np.ndarray  # P(outcome) had this unit not been delivered to:
                                      # the ground-truth counterfactual, never visible
                                      # to an estimator
    true_effect: float
    delivery_rate: float              # realised P(delivered = 1 | assigned = 1)

    @property
    def true_itt(self) -> float:
        """The effect of being assigned, diluted by everyone never delivered to."""
        return self.true_effect * self.delivery_rate


def simulate(
    n: int = 500_000,
    *,
    observability: float = 0.60,
    true_effect: float = TRUE_EFFECT,
    treat_share: float = TREAT_SHARE,
    curvature: float = CURVATURE,
    interaction: float = INTERACTION,
    n_noise_features: int = N_NOISE_FEATURES,
    seed: int = 0,
) -> Population:
    """Draw one experiment."""
    rng = np.random.default_rng(seed)

    activity = rng.standard_normal(n)
    modifier = rng.standard_normal(n)

    # The covariates reveal the confounder only partially: corr(signal, activity) is
    # sqrt(observability). The modifier is observed exactly; the rest is noise the model
    # can overfit to.
    signal = (np.sqrt(observability) * activity
              + np.sqrt(1.0 - observability) * rng.standard_normal(n))
    noise = rng.standard_normal((n, n_noise_features))
    x = np.column_stack([signal, modifier, noise])

    assigned = (rng.random(n) < treat_share).astype(np.int8)
    delivered = ((assigned == 1) & (rng.random(n) < expit(delivery_logit(activity)))).astype(np.int8)

    baseline = expit(baseline_logit(activity, modifier, curvature=curvature,
                                    interaction=interaction))
    outcome = (rng.random(n) < np.clip(baseline + true_effect * delivered, 0.0, 1.0)).astype(np.int8)

    return Population(x, activity, assigned, delivered, outcome, baseline,
                      true_effect, float(delivered[assigned == 1].mean()))


def describe(p: Population) -> str:
    """The moments worth checking against the reference dataset."""
    control = p.outcome[p.assigned == 0]
    treated = p.outcome[p.assigned == 1]
    exposed = p.outcome[p.delivered == 1]
    assigned_undelivered = (p.assigned == 1) & (p.delivered == 0)

    # The comparison group is assigned-but-undelivered, NOT everyone undelivered. The
    # control arm never had the chance to be delivered to, so it still contains the
    # high-activity units that delivery would have taken; including it raises the
    # comparison baseline and pushes the ratio down. Computed the loose way this reads
    # 16.7x against a true 18.3x -- the same quantity, two different populations, and
    # nothing raises an error.
    baseline_of_delivered = p.baseline_probability[p.delivered == 1].mean()
    baseline_of_rest = p.baseline_probability[assigned_undelivered].mean()

    return (
        f"  n                        {p.outcome.size:,}\n"
        f"  assigned share           {p.assigned.mean():.3f}\n"
        f"  delivery rate            {p.delivery_rate:.4%}\n"
        f"  control outcome rate     {control.mean():.4%}\n"
        f"  treated outcome rate     {treated.mean():.4%}\n"
        f"  delivered outcome rate   {exposed.mean():.4%}\n"
        f"  assigned-undelivered     {p.outcome[assigned_undelivered].mean():.4%}\n"
        f"  delivered baseline ratio {baseline_of_delivered / baseline_of_rest:.1f}x"
        f"   (vs assigned-undelivered)\n"
        f"  true effect on delivered {p.true_effect:.4%}\n"
        f"  true intention-to-treat  {p.true_itt:.4%}"
    )


if __name__ == "__main__":
    print("\ncalibration check -- compare against docs/01_data_dictionary.md\n")
    print(describe(simulate(n=2_000_000, seed=1)))
    print()
