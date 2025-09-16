#!/usr/bin/env python
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
from case_indicium.agent.schemas import ReportInput
from case_indicium.agent.generator import build_report

def main():
    ap = argparse.ArgumentParser(description="Generate SRAG report (PoC).")
    ap.add_argument("--scope", choices=["br","uf"], default="br", help="Report scope")
    ap.add_argument("--uf", help="UF when scope=uf")
    ap.add_argument("--out", default=None, help="Output markdown path")
    args = ap.parse_args()

    if args.scope == "uf" and not args.uf:
        ap.error("--uf is required when scope=uf")

    out_dir = Path("reports"); out_dir.mkdir(parents=True, exist_ok=True)
    out_md = Path(args.out) if args.out else out_dir / f"report_{args.scope}_{datetime.now():%Y%m%d}.md"

    rpt = build_report(ReportInput(scope=args.scope, uf=args.uf))
    out_md.write_text(rpt.report_md, encoding="utf-8")
    print(f"Wrote {out_md}")
    for a in rpt.assets:
        print(f"Asset: {a}")

if __name__ == "__main__":
    main()
