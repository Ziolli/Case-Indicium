"""
Runner: creates/refreshes Gold views (daily/monthly by UF).
"""
from __future__ import annotations

from pathlib import Path
import sys
import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from case_indicium.utils.config import DUCKDB_PATH

def main() -> None:
    sql_path = SRC / "case_indicium" / "sql" / "gold_views.sql"
    sql = sql_path.read_text(encoding="utf-8")
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute(sql)
    con.close()
    print("[runner] gold views created: gold.fct_daily_uf, gold.fct_monthly_uf")

if __name__ == "__main__":
    main()
