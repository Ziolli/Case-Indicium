"""
Central SQL definitions used by the reporting agent.

Design goals
------------
- Anchor all rolling windows to the last available date in the dataset (as_of).
- Be robust to missing recent data (COALESCE, guarded divisions).
- Never average UF-level percentages for national numbers (always re-aggregate numerators/denominators).
- Keep UF-scoped variants parameterized via $uf.
"""


SQL_AS_OF_DATES = """
-- Last available day/month in Gold
WITH last_day AS (
  SELECT MAX(day) AS max_day FROM gold.fct_daily_uf
),
last_month AS (
  SELECT DATE_TRUNC('month', MAX(month)) AS max_month FROM gold.fct_monthly_uf
)
SELECT
  (SELECT max_day   FROM last_day)   AS as_of_day,
  (SELECT max_month FROM last_month) AS as_of_month;
"""

# -----------------------------
# Growth (7d vs previous 7d) - BR
# -----------------------------

SQL_GROWTH_7D_BR = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
),
d AS (
  SELECT day, SUM(cases) AS cases
  FROM gold.fct_daily_uf
  GROUP BY day
),
w AS (
  SELECT
    COALESCE(SUM(CASE WHEN d.day > a.d - INTERVAL 7 DAY
                      AND d.day <= a.d THEN d.cases END), 0) AS cases_7d,
    COALESCE(SUM(CASE WHEN d.day > a.d - INTERVAL 14 DAY
                      AND d.day <= a.d - INTERVAL 7 DAY THEN d.cases END), 0) AS cases_prev_7d
  FROM d
  CROSS JOIN as_of a
)
SELECT
  cases_7d,
  cases_prev_7d,
  CASE WHEN cases_prev_7d > 0
       THEN 100.0 * (cases_7d - cases_prev_7d) / cases_prev_7d
       ELSE NULL
  END AS growth_7d_pct
FROM w;
"""

# -----------------------------
# Growth (7d vs previous 7d) - UF
# -----------------------------

SQL_GROWTH_7D_UF = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
),
d AS (
  SELECT day, SUM(cases) AS cases
  FROM gold.fct_daily_uf
  WHERE uf = $uf
  GROUP BY day
),
w AS (
  SELECT
    COALESCE(SUM(CASE WHEN d.day > a.d - INTERVAL 7 DAY
                      AND d.day <= a.d THEN d.cases END), 0) AS cases_7d,
    COALESCE(SUM(CASE WHEN d.day > a.d - INTERVAL 14 DAY
                      AND d.day <= a.d - INTERVAL 7 DAY THEN d.cases END), 0) AS cases_prev_7d
  FROM d
  CROSS JOIN as_of a
)
SELECT
  cases_7d,
  cases_prev_7d,
  CASE WHEN cases_prev_7d > 0
       THEN 100.0 * (cases_7d - cases_prev_7d) / cases_prev_7d
       ELSE NULL
  END AS growth_7d_pct
FROM w;
"""

# -----------------------------
# KPIs 30d (CFR on closed, ICU%, Vaccinated%) - BR
# -----------------------------

SQL_KPIS_30D_BR = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
),
agg AS (
  SELECT
    COALESCE(SUM(closed_cases_30d), 0)  AS closed_cases_30d,
    COALESCE(SUM(deaths_30d), 0)        AS deaths_30d,
    COALESCE(SUM(cases), 0)             AS cases_30d,
    COALESCE(SUM(icu_cases), 0)         AS icu_cases_30d,
    COALESCE(SUM(vaccinated_cases), 0)  AS vaccinated_cases_30d
  FROM gold.fct_daily_uf t
  CROSS JOIN as_of a
  WHERE t.day > a.d - INTERVAL 30 DAY AND t.day <= a.d
)
SELECT
  agg.cases_30d,
  agg.icu_cases_30d,
  agg.vaccinated_cases_30d,
  agg.closed_cases_30d,
  agg.deaths_30d,
  CASE WHEN agg.closed_cases_30d > 0
       THEN 100.0 * agg.deaths_30d / agg.closed_cases_30d
       ELSE NULL END AS cfr_closed_30d_pct,
  CASE WHEN agg.cases_30d > 0
       THEN 100.0 * agg.icu_cases_30d / agg.cases_30d
       ELSE NULL END AS icu_rate_30d_pct,
  CASE WHEN agg.cases_30d > 0
       THEN 100.0 * agg.vaccinated_cases_30d / agg.cases_30d
       ELSE NULL END AS vaccinated_rate_30d_pct
FROM agg;
"""

# -----------------------------
# KPIs 30d (CFR on closed, ICU%, Vaccinated%) - UF
# -----------------------------

SQL_KPIS_30D_UF = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
),
agg AS (
  SELECT
    COALESCE(SUM(closed_cases_30d), 0)  AS closed_cases_30d,
    COALESCE(SUM(deaths_30d), 0)        AS deaths_30d,
    COALESCE(SUM(cases), 0)             AS cases_30d,
    COALESCE(SUM(icu_cases), 0)         AS icu_cases_30d,
    COALESCE(SUM(vaccinated_cases), 0)  AS vaccinated_cases_30d
  FROM gold.fct_daily_uf t
  CROSS JOIN as_of a
  WHERE t.uf = $uf
    AND t.day > a.d - INTERVAL 30 DAY AND t.day <= a.d
)
SELECT
  agg.cases_30d,
  agg.icu_cases_30d,
  agg.vaccinated_cases_30d,
  agg.closed_cases_30d,
  agg.deaths_30d,
  CASE WHEN agg.closed_cases_30d > 0
       THEN 100.0 * agg.deaths_30d / agg.closed_cases_30d
       ELSE NULL END AS cfr_closed_30d_pct,
  CASE WHEN agg.cases_30d > 0
       THEN 100.0 * agg.icu_cases_30d / agg.cases_30d
       ELSE NULL END AS icu_rate_30d_pct,
  CASE WHEN agg.cases_30d > 0
       THEN 100.0 * agg.vaccinated_cases_30d / agg.cases_30d
       ELSE NULL END AS vaccinated_rate_30d_pct
FROM agg;
"""

# -----------------------------
# Daily series (last 30d) - BR
# -----------------------------

SQL_DAILY_30D_BR = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
)
SELECT t.day, SUM(t.cases) AS cases
FROM gold.fct_daily_uf t
CROSS JOIN as_of a
WHERE t.day > a.d - INTERVAL 30 DAY AND t.day <= a.d
GROUP BY t.day
ORDER BY t.day;
"""

# -----------------------------
# Daily series (last 30d) - UF
# -----------------------------

SQL_DAILY_30D_UF = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d
  FROM gold.fct_daily_uf
)
SELECT t.day, SUM(t.cases) AS cases
FROM gold.fct_daily_uf t
CROSS JOIN as_of a
WHERE t.uf = $uf
  AND t.day > a.d - INTERVAL 30 DAY AND t.day <= a.d
GROUP BY t.day
ORDER BY t.day;
"""

# -----------------------------
# Monthly series (last 12 months) - BR
# -----------------------------

SQL_MONTHLY_12M_BR = """
WITH as_of AS (
  SELECT COALESCE(DATE_TRUNC('month', MAX(month)), DATE_TRUNC('month', CURRENT_DATE)) AS m
  FROM gold.fct_monthly_uf
)
SELECT t.month, SUM(t.cases) AS cases
FROM gold.fct_monthly_uf t
CROSS JOIN as_of a
WHERE t.month >= a.m - INTERVAL 11 MONTH
  AND t.month <= a.m
GROUP BY t.month
ORDER BY t.month;
"""

# -----------------------------
# Monthly series (last 12 months) - UF
# -----------------------------

SQL_MONTHLY_12M_UF = """
WITH as_of AS (
  SELECT COALESCE(DATE_TRUNC('month', MAX(month)), DATE_TRUNC('month', CURRENT_DATE)) AS m
  FROM gold.fct_monthly_uf
)
SELECT t.month, SUM(t.cases) AS cases
FROM gold.fct_monthly_uf t
CROSS JOIN as_of a
WHERE t.uf = $uf
  AND t.month >= a.m - INTERVAL 11 MONTH
  AND t.month <= a.m
GROUP BY t.month
ORDER BY t.month;
"""

# -----------------------------
# Rankings auxiliares (opcional)
# -----------------------------

SQL_TOP_UF_CASES_30D = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d FROM gold.fct_daily_uf
)
SELECT uf, SUM(cases) AS cases_30d
FROM gold.fct_daily_uf t
CROSS JOIN as_of a
WHERE t.day > a.d - INTERVAL 30 DAY AND t.day <= a.d
GROUP BY uf
ORDER BY cases_30d DESC;
"""

SQL_CFR_UF_90D = """
WITH as_of AS (
  SELECT COALESCE(MAX(day), CURRENT_DATE) AS d FROM gold.fct_daily_uf
),
agg AS (
  SELECT uf,
         COALESCE(SUM(closed_cases_30d), 0) AS closed_cases_30d,
         COALESCE(SUM(deaths_30d), 0)       AS deaths_30d
  FROM gold.fct_daily_uf t
  CROSS JOIN as_of a
  WHERE t.day > a.d - INTERVAL 90 DAY AND t.day <= a.d
  GROUP BY uf
)
SELECT uf,
       CASE WHEN closed_cases_30d > 0
            THEN 100.0 * deaths_30d / closed_cases_30d
            ELSE NULL END AS cfr_closed_30d_pct
FROM agg
ORDER BY cfr_closed_30d_pct DESC NULLS LAST;
"""
