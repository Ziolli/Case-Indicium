from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import duckdb


def _is_remote(url: str) -> bool:
    """Return True if the URL refers to a remote resource (http/https/s3)."""
    return url.startswith(("http://", "https://", "s3://"))


def ingest_bronze_from_manifest(manifest_path: str | Path, duckdb_path: str | Path) -> None:
    """Create/replace Bronze tables in DuckDB from a year->URL manifest.

    It creates one table per year (e.g., `raw_2019`) and a union table `raw_all`.
    We set the active schema to `srag` to avoid the catalog/schema ambiguity.

    Args:
        manifest_path: Path to the JSON mapping year strings to CSV URLs.
        duckdb_path: Path to the DuckDB database file to write to.

    Returns:
        None. Tables are created/overwritten inside the DuckDB database.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        duckdb.Error: If any DuckDB statement fails.
        json.JSONDecodeError: If the manifest is invalid JSON.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    years_sorted = sorted(manifest.keys(), key=int)

    con = duckdb.connect(str(duckdb_path))

    # Create the schema and set it as the active schema to avoid ambiguity.
    con.execute("CREATE SCHEMA IF NOT EXISTS srag;")
    con.execute("SET schema 'srag';")

    if any(_is_remote(u) for u in manifest.values()):
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")

    raw_tables: List[str] = []

    for year in years_sorted:
        url = manifest[year]
        print(f"[bronze] {year} <- {url}")
        con.execute(f"""
            CREATE OR REPLACE TABLE raw_{int(year)} AS
            SELECT
              CAST({int(year)} AS INTEGER) AS year,
              '{url}'::TEXT AS source_url,
              now()::TIMESTAMP AS ingested_at,
              *
            FROM read_csv_auto(
              '{url}',
              header = true,
              sample_size = -1,
              ignore_errors = true
            );
        """)
        raw_tables.append(f"raw_{year}")

    union_sql = " \nUNION ALL\n".join(f"SELECT * FROM {t}" for t in raw_tables)
    con.execute(f"CREATE OR REPLACE TABLE raw_all AS {union_sql};")

    con.close()
