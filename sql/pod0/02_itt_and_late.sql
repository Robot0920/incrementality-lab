-- Pod 0 / S4 — The two estimates you are allowed to report: ITT and LATE.
--
-- ITT  (Intention-To-Treat)  = control vs the WHOLE treatment arm, exposed or not.
--                              Answers: "if we turn this on, what happens overall?"
--                              -> this is the launch decision.
-- LATE (Local ATE, = CACE)   = ITT / compliance_rate, valid under one-sided
--                              non-compliance + the exclusion restriction.
--                              Answers: "how strong is the effect on those we actually reach?"
--                              -> this judges creative / algorithm quality and pricing.
--
-- Note on the CI for LATE: dividing the ITT bounds by the compliance rate treats
-- compliance as known. With n = 14M that is harmless, but the textbook-correct way
-- is a delta-method / Wald-ratio interval. 我们先用近似, 到 Pod 1 再做严格版。

WITH arm AS (
    SELECT
        treatment,
        count(*)::DOUBLE        AS n,
        avg(visit)::DOUBLE      AS visit_rate,
        avg(conversion)::DOUBLE AS conv_rate,
        avg(exposure)::DOUBLE   AS compliance_rate
    FROM bronze.criteo_uplift
    GROUP BY treatment
),
w AS (
    SELECT
        (SELECT n               FROM arm WHERE treatment = 0) AS n_c,
        (SELECT n               FROM arm WHERE treatment = 1) AS n_t,
        (SELECT visit_rate      FROM arm WHERE treatment = 0) AS v_c,
        (SELECT visit_rate      FROM arm WHERE treatment = 1) AS v_t,
        (SELECT conv_rate       FROM arm WHERE treatment = 0) AS k_c,
        (SELECT conv_rate       FROM arm WHERE treatment = 1) AS k_t,
        (SELECT compliance_rate FROM arm WHERE treatment = 1) AS pi
),
m AS (
    SELECT 'visit'      AS outcome, n_c, n_t, v_c AS p_c, v_t AS p_t, pi FROM w
    UNION ALL
    SELECT 'conversion' AS outcome, n_c, n_t, k_c AS p_c, k_t AS p_t, pi FROM w
),
e AS (
    SELECT
        *,
        p_t - p_c                                                AS itt,
        sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)      AS se
    FROM m
)
SELECT
    outcome,
    round(p_c, 6)                          AS control_rate,
    round(p_t, 6)                          AS treated_rate,
    round(itt, 6)                          AS itt_abs,
    round(100.0 * itt / p_c, 2)            AS itt_rel_pct,
    round(itt - 1.96 * se, 6)              AS itt_ci_lo,
    round(itt + 1.96 * se, 6)              AS itt_ci_hi,
    round(itt / se, 1)                     AS z_stat,          -- with n=14M this is theater
    round(pi, 5)                           AS compliance_rate,
    round(itt / pi, 6)                     AS late_abs,
    round((itt - 1.96 * se) / pi, 6)       AS late_ci_lo,
    round((itt + 1.96 * se) / pi, 6)       AS late_ci_hi
FROM e
ORDER BY outcome
