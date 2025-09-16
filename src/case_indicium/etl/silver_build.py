"""
Silver build: normalize and curate fields from bronze.raw_all to silver.cases.
"""
from __future__ import annotations

import duckdb

from case_indicium.utils.config import (
    DUCKDB_PATH,
    SCHEMA_BRONZE,
    SCHEMA_SILVER,
    BRONZE_TABLE,
    SILVER_TABLE,
    PENDING_DAYS,
)
from case_indicium.utils.duck import connect


def _column_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str, column: str) -> bool:
    """
    Check if a column exists in schema.table.

    Returns:
        True if column exists.
    """
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
          AND column_name = ?
        """,
        [schema, table, column],
    ).fetchone()
    return bool(row)


def build_silver_cases(*, db_path=DUCKDB_PATH) -> None:
    """
    Create/replace silver.cases with parsed dates, labels, flags and age bands.

    Returns:
        None. Writes silver.cases atomically via a temp table.
    """
    with connect(db_path, read_only=False, schema=SCHEMA_SILVER) as con:
        # need to read from bronze.*
        con.execute(f"SET schema '{SCHEMA_BRONZE}';")
        has_dt_encerra = _column_exists(con, SCHEMA_BRONZE, BRONZE_TABLE, "DT_ENCERRA")
        con.execute(f"SET schema '{SCHEMA_SILVER}';")

        dt_encerra_expr = (
            """
            COALESCE(
              TRY_STRPTIME(CAST(DT_ENCERRA AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
              TRY_CAST(DT_ENCERRA AS DATE)
            )
            """
            if has_dt_encerra
            else "NULL"
        )

        con.execute(f"DROP TABLE IF EXISTS {SILVER_TABLE}_tmp;")
        con.execute(
            f"""
            CREATE TABLE {SILVER_TABLE}_tmp AS
            WITH src AS (
              SELECT *
              FROM {SCHEMA_BRONZE}.{BRONZE_TABLE}
            ),
            parsed AS (
              SELECT
                -- Dates
                COALESCE(
                  TRY_STRPTIME(CAST(DT_NOTIFIC AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                  TRY_CAST(DT_NOTIFIC AS DATE)
                ) AS dt_notific,
                COALESCE(
                  TRY_STRPTIME(CAST(DT_SIN_PRI AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                  TRY_CAST(DT_SIN_PRI AS DATE)
                ) AS dt_sin_pri,
                COALESCE(
                  TRY_STRPTIME(CAST(DT_EVOLUCA AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                  TRY_CAST(DT_EVOLUCA AS DATE)
                ) AS dt_evoluca,
                {dt_encerra_expr} AS dt_encerra,

                -- Time keys
                TRY_CAST(SEM_NOT AS INTEGER)    AS sem_not,
                EXTRACT('year' FROM
                  COALESCE(
                    TRY_STRPTIME(CAST(DT_NOTIFIC AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                    TRY_CAST(DT_NOTIFIC AS DATE)
                  )
                )::INT AS ano_notific,
                DATE_TRUNC('month',
                  COALESCE(
                    TRY_STRPTIME(CAST(DT_NOTIFIC AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                    TRY_CAST(DT_NOTIFIC AS DATE)
                  )
                ) AS mes_notific,

                -- Outcomes
                TRY_CAST(EVOLUCAO AS INTEGER)   AS evolucao_code,
                CASE TRY_CAST(EVOLUCAO AS INTEGER)
                  WHEN 1 THEN 'CURA'
                  WHEN 2 THEN 'OBITO'
                  WHEN 3 THEN 'OBITO_OUTRAS'
                  WHEN 9 THEN 'IGNORADO'
                  ELSE NULL
                END AS evolucao_label,
                TRY_CAST(CLASSI_FIN AS INTEGER) AS classi_fin,

                -- ICU
                CASE
                  WHEN TRY_CAST(UTI AS INTEGER) = 1 THEN TRUE
                  WHEN TRY_CAST(UTI AS INTEGER) = 2 THEN FALSE
                  ELSE NULL
                END AS uti_bool,
                COALESCE(
                  TRY_STRPTIME(CAST(DT_ENTUTI AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                  TRY_CAST(DT_ENTUTI AS DATE)
                ) AS dt_entuti,
                COALESCE(
                  TRY_STRPTIME(CAST(DT_SAIDUTI AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                  TRY_CAST(DT_SAIDUTI AS DATE)
                ) AS dt_saiduti,

                -- Vaccination
                CASE
                  WHEN TRY_CAST(VACINA_COV AS INTEGER) = 1 THEN TRUE
                  WHEN TRY_CAST(VACINA_COV AS INTEGER) = 2 THEN FALSE
                  ELSE NULL
                END AS vacinado_bool,

                -- Demographics
                TRY_CAST(NU_IDADE_N AS INTEGER) AS idade,
                CASE
                  WHEN TRY_CAST(NU_IDADE_N AS INTEGER) IS NULL THEN NULL
                  WHEN TRY_CAST(NU_IDADE_N AS INTEGER) < 5 THEN '0-4'
                  WHEN TRY_CAST(NU_IDADE_N AS INTEGER) BETWEEN 5 AND 17 THEN '5-17'
                  WHEN TRY_CAST(NU_IDADE_N AS INTEGER) BETWEEN 18 AND 39 THEN '18-39'
                  WHEN TRY_CAST(NU_IDADE_N AS INTEGER) BETWEEN 40 AND 59 THEN '40-59'
                  ELSE '60+'
                END AS faixa_etaria,
                UPPER(TRIM(CS_SEXO))            AS sexo,
                UPPER(TRIM(SG_UF_NOT))          AS uf,

                -- Flags
                CASE WHEN TRY_CAST(EVOLUCAO AS INTEGER) = 2 THEN TRUE ELSE FALSE END AS is_obito,
                CASE
                  WHEN COALESCE(
                    TRY_STRPTIME(CAST(DT_NOTIFIC AS VARCHAR), ['%d/%m/%Y','%Y-%m-%d']),
                    TRY_CAST(DT_NOTIFIC AS DATE)
                  ) <= CURRENT_DATE - INTERVAL {PENDING_DAYS} DAY
                  AND (TRY_CAST(EVOLUCAO AS INTEGER) IS NULL
                       OR TRY_CAST(EVOLUCAO AS INTEGER) = 9
                       OR {dt_encerra_expr} IS NULL)
                  THEN TRUE ELSE FALSE
                END AS pendente_60d
              FROM src
            )
            SELECT * FROM parsed;
            """
        )

        con.execute(f"DROP TABLE IF EXISTS {SILVER_TABLE};")
        con.execute(f"ALTER TABLE {SILVER_TABLE}_tmp RENAME TO {SILVER_TABLE};")
        n = con.execute(f"SELECT COUNT(*) FROM {SILVER_TABLE};").fetchone()[0]
        print(f"[silver] created {SCHEMA_SILVER}.{SILVER_TABLE} rows={n}")
