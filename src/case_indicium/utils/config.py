"""
Global configuration for Case Indicium.

Centralizes paths, schema/table names, and tunable parameters.
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root: .../Case-Indicium
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Data
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", DATA_DIR / "srag.duckdb"))

# Schemas
SCHEMA_BRONZE = "bronze"
SCHEMA_SILVER = "silver"
SCHEMA_GOLD = "gold"

# Tables (without schema)
BRONZE_TABLE = "raw_all"
SILVER_TABLE = "cases"

# Parameters (can be overridden via env)
CENSOR_DAYS = int(os.getenv("CENSOR_DAYS", "30"))
PENDING_DAYS = int(os.getenv("PENDING_DAYS", "60"))
MA_WINDOW = int(os.getenv("MA_WINDOW", "7"))

# Manifests
DATA_URLS_PATH = Path(os.getenv("DATA_URLS_PATH", RAW_DIR / "data_urls.json"))
