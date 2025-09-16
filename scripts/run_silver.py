"""
Runner: builds silver.cases from bronze.raw_all.
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from case_indicium.etl.silver_build import build_silver_cases

def main() -> None:
    build_silver_cases()
    print("[runner] silver done.")

if __name__ == "__main__":
    main()
