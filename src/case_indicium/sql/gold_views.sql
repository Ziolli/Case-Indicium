-- Gold views for SRAG (daily & monthly by UF)

CREATE SCHEMA IF NOT EXISTS gold;

-- DAILY metrics by UF
CREATE OR REPLACE VIEW gold.fct_daily_uf AS
WITH base AS (
  SELECT
    dt_notific::DATE AS day,
    uf,
    CASE WHEN uti_bool IS TRUE THEN 1 ELSE 0 END AS icu_case,
    CASE WHEN vacinado_bool IS TRUE THEN 1 ELSE 0 END AS vac_case,
    CASE WHEN pendente_60d IS TRUE THEN 1 ELSE 0 END AS pend_case,
    CASE WHEN evolucao_code IN (1,2,3) THEN 1 ELSE 0 END AS closed_case,
    CASE WHEN evolucao_code = 2 THEN 1 ELSE 0 END AS death_case,
    CASE WHEN evolucao_code IN (1,2,3) AND dt_notific <= CURRENT_DATE - INTERVAL 30 DAY
         THEN 1 ELSE 0 END AS closed_case_30d,
    CASE WHEN evolucao_code = 2 AND dt_notific <= CURRENT_DATE - INTERVAL 30 DAY
         THEN 1 ELSE 0 END AS death_case_30d,
    DATEDIFF('day', dt_sin_pri, dt_notific) AS lag_notif_days,
    DATEDIFF('day', dt_entuti, dt_saiduti)  AS icu_los_days
  FROM silver.cases
  WHERE dt_notific IS NOT NULL
),
agg AS (
  SELECT
    day, uf,
    COUNT(*)                        AS cases,
    SUM(death_case)                 AS deaths,
    SUM(icu_case)                   AS icu_cases,
    SUM(vac_case)                   AS vaccinated_cases,
    SUM(pend_case)                  AS pending_60d_cases,
    SUM(closed_case_30d)            AS closed_cases_30d,
    SUM(death_case_30d)             AS deaths_30d,
    MEDIAN(CASE WHEN lag_notif_days BETWEEN -30 AND 120 THEN lag_notif_days END)
                                      AS median_symptom_to_notification_days,
    MEDIAN(CASE WHEN icu_los_days BETWEEN 0 AND 60 THEN icu_los_days END)
                                      AS median_icu_los_days
  FROM base
  GROUP BY 1,2
),
rates AS (
  SELECT
    *,
    100.0 * deaths_30d / NULLIF(closed_cases_30d, 0) AS cfr_closed_30d_pct,
    100.0 * icu_cases / NULLIF(cases, 0)             AS icu_rate_pct,
    100.0 * vaccinated_cases / NULLIF(cases, 0)      AS vaccinated_rate_pct,
    100.0 * pending_60d_cases / NULLIF(cases, 0)     AS pending_60d_pct
  FROM agg
)
SELECT
  *,
  AVG(cases)  OVER (PARTITION BY uf ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS cases_ma7,
  AVG(deaths) OVER (PARTITION BY uf ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS deaths_ma7
FROM rates
ORDER BY day, uf;

-- MONTHLY metrics by UF
CREATE OR REPLACE VIEW gold.fct_monthly_uf AS
WITH base AS (
  SELECT
    DATE_TRUNC('month', dt_notific)::DATE AS month,
    uf,
    CASE WHEN uti_bool IS TRUE THEN 1 ELSE 0 END AS icu_case,
    CASE WHEN vacinado_bool IS TRUE THEN 1 ELSE 0 END AS vac_case,
    CASE WHEN pendente_60d IS TRUE THEN 1 ELSE 0 END AS pend_case,
    CASE WHEN evolucao_code IN (1,2,3) THEN 1 ELSE 0 END AS closed_case,
    CASE WHEN evolucao_code = 2 THEN 1 ELSE 0 END AS death_case,
    CASE WHEN evolucao_code IN (1,2,3) AND dt_notific <= CURRENT_DATE - INTERVAL 30 DAY
         THEN 1 ELSE 0 END AS closed_case_30d,
    CASE WHEN evolucao_code = 2 AND dt_notific <= CURRENT_DATE - INTERVAL 30 DAY
         THEN 1 ELSE 0 END AS death_case_30d,
    DATEDIFF('day', dt_sin_pri, dt_notific) AS lag_notif_days,
    DATEDIFF('day', dt_entuti, dt_saiduti)  AS icu_los_days
  FROM silver.cases
  WHERE dt_notific IS NOT NULL
),
agg AS (
  SELECT
    month, uf,
    COUNT(*)                        AS cases,
    SUM(death_case)                 AS deaths,
    SUM(icu_case)                   AS icu_cases,
    SUM(vac_case)                   AS vaccinated_cases,
    SUM(pend_case)                  AS pending_60d_cases,
    SUM(closed_case_30d)            AS closed_cases_30d,
    SUM(death_case_30d)             AS deaths_30d,
    MEDIAN(CASE WHEN lag_notif_days BETWEEN -30 AND 120 THEN lag_notif_days END)
                                      AS median_symptom_to_notification_days,
    MEDIAN(CASE WHEN icu_los_days BETWEEN 0 AND 60 THEN icu_los_days END)
                                      AS median_icu_los_days
  FROM base
  GROUP BY 1,2
)
SELECT
  *,
  100.0 * deaths_30d / NULLIF(closed_cases_30d, 0) AS cfr_closed_30d_pct,
  100.0 * icu_cases / NULLIF(cases, 0)             AS icu_rate_pct,
  100.0 * vaccinated_cases / NULLIF(cases, 0)      AS vaccinated_rate_pct,
  100.0 * pending_60d_cases / NULLIF(cases, 0)     AS pending_60d_pct
FROM agg
ORDER BY month, uf;
