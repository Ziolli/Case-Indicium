# scripts/run_report.py
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime

from case_indicium.agent.generator import build_report
from case_indicium.agent.schemas import ReportInput

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="br", choices=["br"], help="Report scope (PoC supports 'br').")
    parser.add_argument("--out", default="reports", help="Output folder for markdown.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rpt = build_report(ReportInput(scope=args.scope, uf=None))
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_md = out_dir / f"report_{args.scope}_{ts}.md"
    out_md.write_text(rpt.report_md, encoding="utf-8")

    print(f"✅ Report saved: {out_md}")

if __name__ == "__main__":
    main()
