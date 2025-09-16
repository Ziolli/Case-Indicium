"""
DuckDB helpers: robust connections with schema selection and optional retries.
"""
from __future__ import annotations

import time
from typing import Optional
import duckdb


def connect(
    db_path: str | bytes | "os.PathLike[str] | os.PathLike[bytes]",
    *,
    read_only: bool = False,
    schema: Optional[str] = None,
    retries: int = 6,
    wait_seconds: float = 1.25,
) -> duckdb.DuckDBPyConnection:
    """
    Connect to DuckDB, optionally set active schema, and retry if locked.

    Args:
        db_path: DuckDB file path.
        read_only: Open in read-only mode.
        schema: If provided, ensures the schema exists (when not read-only)
            and sets it as the active schema.
        retries: Number of lock retries (writer lock).
        wait_seconds: Backoff between retries.

    Returns:
        A DuckDB connection positioned at the requested schema.
    """
    last_exc = None
    for _ in range(max(1, retries)):
        try:
            con = duckdb.connect(str(db_path), read_only=read_only)
            if schema:
                if not read_only:
                    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
                con.execute(f"SET schema '{schema}';")
            return con
        except duckdb.IOException as exc:
            last_exc = exc
            if "lock" in str(exc).lower():
                time.sleep(wait_seconds)
                continue
            raise
    raise RuntimeError(f"DuckDB locked: {last_exc}") from last_exc
