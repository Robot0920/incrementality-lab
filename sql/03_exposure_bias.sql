-- Pod 0 / S4 — Proving exposure bias instead of asserting it.
--
-- The naive estimate (exposed users vs the control arm) conditions on `exposure`,
-- which is a POST-TREATMENT variable produced by the ad-serving system. Exposed
-- users are the active, biddable ones — they were already more likely to convert.
--
-- Randomisation lets us back out the hidden baseline of those users:
--
--   control_rate = pi * (complier baseline) + (1 - pi) * (never-taker outcome)
--
-- because the control arm contains the same pi share of would-be-compliers, and a
-- treated-but-unexposed user received nothing, so their outcome IS their baseline
-- (this is the exclusion restriction).
--
-- Consistency check built into the output:
--     effect_on_compliers_direct  ==  late  (from 02_itt_and_late.sql)
-- If those two columns disagree, one of the assumptions above is broken.

WITH cell AS (
    SELECT
        treatment,
        exposure,
        count(*)::DOUBLE        AS n,
        avg(visit)::DOUBLE      AS v,
        avg(conversion)::DOUBLE AS k
    FROM bronze.criteo_uplift
    GROUP BY treatment, exposure
),
p AS (
    SELECT
        (SELECT n FROM cell WHERE treatment = 0)                    AS n_c,
        (SELECT v FROM cell WHERE treatment = 0)                    AS v_c,
        (SELECT k FROM cell WHERE treatment = 0)                    AS k_c,
        (SELECT n FROM cell WHERE treatment = 1 AND exposure = 1)   AS n_te,
        (SELECT v FROM cell WHERE treatment = 1 AND exposure = 1)   AS v_te,
        (SELECT k FROM cell WHERE treatment = 1 AND exposure = 1)   AS k_te,
        (SELECT n FROM cell WHERE treatment = 1 AND exposure = 0)   AS n_tn,
        (SELECT v FROM cell WHERE treatment = 1 AND exposure = 0)   AS v_tn,
        (SELECT k FROM cell WHERE treatment = 1 AND exposure = 0)   AS k_tn
),
d AS (
    SELECT
        *,
        n_te / (n_te + n_tn)                          AS pi,
        (n_te * v_te + n_tn * v_tn) / (n_te + n_tn)   AS v_t,
        (n_te * k_te + n_tn * k_tn) / (n_te + n_tn)   AS k_t
    FROM p
),
m AS (
    SELECT 'visit'      AS outcome, v_c AS p_c, v_t AS p_t, v_te AS p_te, v_tn AS p_tn, pi FROM d
    UNION ALL
    SELECT 'conversion' AS outcome, k_c AS p_c, k_t AS p_t, k_te AS p_te, k_tn AS p_tn, pi FROM d
)
SELECT
    outcome,
    round(p_c,   6)                                    AS control_rate,
    round(p_tn,  6)                                    AS treated_unexposed_rate,  -- lower than control on purpose
    round(p_te,  6)                                    AS exposed_rate,
    round(p_te - p_c, 6)                               AS naive_effect,            -- never report this
    round(p_t - p_c, 6)                                AS itt,
    round((p_t - p_c) / pi, 6)                         AS late,
    round((p_c - (1 - pi) * p_tn) / pi, 6)             AS implied_complier_baseline,
    round(p_te - (p_c - (1 - pi) * p_tn) / pi, 6)      AS effect_on_compliers_direct,
    round(((p_c - (1 - pi) * p_tn) / pi) / p_tn, 2)    AS complier_baseline_ratio,  -- how selected they are
    round(100.0 * ((p_te - p_c) / ((p_t - p_c) / pi) - 1), 1) AS naive_overstates_pct
FROM m
ORDER BY outcome
