-- Table existence and counts
SELECT table_schema, table_name, row_count
FROM duckdb_tables()
WHERE table_schema IN ('bronze','silver','gold')
ORDER BY table_schema, table_name;

-- Date ranges in silver
SELECT
  MIN(dt_notific) AS min_dt,
  MAX(dt_notific) AS max_dt
FROM silver.cases;

-- Null ratios of important fields
SELECT
  SUM(dt_notific IS NULL) * 1.0 / COUNT(*) AS null_dt_notific_ratio,
  SUM(evolucao_code IS NULL) * 1.0 / COUNT(*) AS null_evolucao_ratio,
  SUM(uti_bool IS NULL) * 1.0 / COUNT(*) AS null_uti_ratio
FROM silver.cases;
