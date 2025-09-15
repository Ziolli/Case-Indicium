from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure "src/" is on sys.path so absolute imports work even when running this file directly.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from case_indicium.etl.urls import refresh_2025_url_in_manifest
from case_indicium.etl.bronze_ingest import ingest_bronze_from_manifest


DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/srag.duckdb")
MANIFEST_PATH = os.environ.get("DATA_URLS_PATH", "data/raw/data_urls.json")


def main() -> None:
    """Orchestrate the Bronze ETL end-to-end.

    Steps:
        1) Refresh the '2025' (Banco vivo) URL in the JSON manifest via CKAN.
        2) Ingest all years from the manifest into DuckDB bronze tables:
           - srag.raw_<year>
           - srag.raw_all (UNION of all years)

    Environment variables:
        DUCKDB_PATH: Path to the DuckDB file (default: 'data/srag.duckdb').
        DATA_URLS_PATH: Path to the year->URL JSON (default: 'data/raw/data_urls.json').

    Returns:
        None. Writes tables into DuckDB and prints progress to stdout.
    """
    refresh_2025_url_in_manifest(MANIFEST_PATH)
    ingest_bronze_from_manifest(MANIFEST_PATH, DUCKDB_PATH)
    print(f"[ETL] Bronze completed. DuckDB at: {DUCKDB_PATH}")


if __name__ == "__main__":
    main()
