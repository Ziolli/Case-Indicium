"""
Bronze ingestion: read CSVs (by year) and build bronze.raw_all.

Keeps data as raw as possible; no heavy transformations here.
"""
from __future__ import annotations

from typing import Dict, List, Tuple
from case_indicium.utils.config import (
    DUCKDB_PATH,
    SCHEMA_BRONZE,
    BRONZE_TABLE,
    DATA_URLS_PATH,
)
from case_indicium.utils.duck import connect
from case_indicium.utils.io import load_year_url_manifest


def build_bronze_from_manifest(manifest_path=DATA_URLS_PATH, *, db_path=DUCKDB_PATH) -> None:
    """
    Build bronze.raw_all by UNION ALL BY NAME over yearly CSVs (HTTP).

    Notes:
        - ALL_VARCHAR=TRUE: read all columns as TEXT in Bronze (robust to dirty values).
        - SAMPLE_SIZE=-1: scan full file for consistent parsing options.
        - DELIM=';': SIVEP CSVs usam ';' (padroniza leitura).
        - Tipagem/conversões ficam para a Silver.
    """
    manifest: Dict[str, str] = load_year_url_manifest(manifest_path)

    # (year, url) ordenado
    items: List[Tuple[int, str]] = sorted(((int(y), url) for y, url in manifest.items()),
                                          key=lambda t: t[0])

    # Monta cadeia de UNION ALL BY NAME lendo cada ano como VARCHAR
    selects: List[str] = []
    for year, url in items:
        selects.append(
            # header=true + all_varchar=true evita ConversionException
            f"""
            SELECT *, {year}::INT AS year
            FROM read_csv_auto(
              '{url}',
              HEADER=TRUE,
              DELIM=';',
              SAMPLE_SIZE=-1,
              ALL_VARCHAR=TRUE
            )
            """.strip()
        )

    union_sql = "\nUNION ALL BY NAME\n".join(selects)

    # Escreve tabela bronze.raw_all
    with connect(db_path, read_only=False, schema=SCHEMA_BRONZE) as con:
        con.execute(f"DROP TABLE IF EXISTS {BRONZE_TABLE};")
        con.execute(f"CREATE TABLE {BRONZE_TABLE} AS\n{union_sql};")

        n = con.execute(f"SELECT COUNT(*) FROM {BRONZE_TABLE};").fetchone()[0]
        print(f"[bronze] created {SCHEMA_BRONZE}.{BRONZE_TABLE} rows={n}")
