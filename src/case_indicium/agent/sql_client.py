from __future__ import annotations
import duckdb as ddb
from pathlib import Path
import os

def resolve_db_path() -> Path:
    p = os.getenv("DUCKDB_PATH", "data/srag.duckdb")
    path = Path(p)
    if not path.is_absolute():
        # ascend to repo root by pyproject.toml
        cur = Path.cwd()
        while cur != cur.parent and not (cur / "pyproject.toml").exists():
            cur = cur.parent
        path = cur / path
    return path

class SQLClient:
    """Minimal DuckDB read-only client."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else resolve_db_path()
        if not self.db_path.exists():
            raise FileNotFoundError(f"DuckDB not found at {self.db_path}")
        self.con = ddb.connect(str(self.db_path), read_only=True)

    def df(self, sql: str, params: dict | None = None):
        return self.con.execute(sql, params or {}).df()

    def close(self):
        self.con.close()
