-- Pod 0 / S4 — What is the compliance structure of this experiment?
--
-- This is the first query to run on any experiment data — NOT avg(outcome) by group.
-- Understand the design before looking at any result, so a dramatic number cannot
-- anchor your thinking.
--
-- Read four things off the output:
--   1. the allocation ratio, from pct_of_all       -> why is it not 50/50?
--   2. the compliance rate, from pct_within_arm    -> the denominator of a LATE
--   3. whether exposure = 1 ever occurs in control -> one- vs two-sided non-compliance
--   4. the control-arm base rate                   -> how brutal is the sample-size math?
--
-- On the two share columns: an aggregate may be nested inside a window function
-- because SQL evaluates GROUP BY and aggregation BEFORE window functions, so
-- sum(count(*)) OVER () means "add up the n of every group". Identical syntax in
-- BigQuery, Snowflake and Postgres.

SELECT
    treatment,
    exposure,
    count(*)                                                        AS n,
    round(100.0 * count(*) / sum(count(*)) OVER (), 3)              AS pct_of_all,
    round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY treatment), 3)
                                                                    AS pct_within_arm,
    round(avg(visit), 6)                                            AS visit_rate,
    round(avg(conversion), 6)                                       AS conversion_rate
FROM bronze.criteo_uplift
GROUP BY treatment, exposure
ORDER BY treatment, exposure
