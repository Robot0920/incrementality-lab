-- Pod 0 / S4 — What is the compliance structure of this experiment?
--
-- 这是拿到任何实验数据后的第一条查询, 不是 avg(outcome) by group。
-- Read three things off the output:
--   1. the randomization ratio      -> why is it not 50/50?
--   2. whether exposure = 1 ever occurs in control
--                                   -> one-sided vs two-sided non-compliance
--   3. the conversion base rate     -> how brutal is your sample-size math?

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
