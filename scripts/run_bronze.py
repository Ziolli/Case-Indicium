"""
Runner: builds bronze.raw_all from manifest.
"""
from __future__ import annotations
from pathlib import Path
import os, sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from case_indicium.etl.bronze_ingest import build_bronze_from_manifest
from case_indicium.utils.config import DATA_URLS_PATH, DUCKDB_PATH

def main() -> None:
    build_bronze_from_manifest(DATA_URLS_PATH, db_path=DUCKDB_PATH)
    print("[runner] bronze done.")

if __name__ == "__main__":
    main()
