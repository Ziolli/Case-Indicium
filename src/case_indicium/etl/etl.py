from __future__ import annotations

import os

from case_indicium.etl.urls import refresh_2025_url_in_manifest
from case_indicium.etl.bronze_ingest import ingest_bronze_from_manifest

# Defaults can be overridden via environment variables or .env
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/srag.duckdb")
MANIFEST_PATH = os.getenv("DATA_URLS_PATH", "data/raw/data_urls.json")


def main() -> None:
    """ETL entrypoint for the bronze stage.

    Steps:
      1) Refresh the manifest so '2025' points to the latest 'Banco vivo' CSV.
      2) Ingest all years from the manifest into DuckDB bronze tables.
    """
    refresh_2025_url_in_manifest(MANIFEST_PATH)
    ingest_bronze_from_manifest(MANIFEST_PATH, DUCKDB_PATH)
    print(f"Bronze ETL completed. DuckDB at: {DUCKDB_PATH}")


if __name__ == "__main__":
    main()
