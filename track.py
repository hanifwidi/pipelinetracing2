#!/usr/bin/env python3
"""Report actual downloads and observed demand; no earnings forecast."""
import argparse
import json
from datetime import date
from pathlib import Path
from utils.tracking import build_report

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", nargs="?", choices=["report"], default="report")
    ap.add_argument("--log", type=Path, default=Path("tracking/production_log.csv"))
    ap.add_argument("--as-of", type=date.fromisoformat)
    ap.add_argument("--min-assets", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.min_assets < 1:
        ap.error("--min-assets must be positive")
    if not args.log.exists():
        ap.error("Production log not found; run init_tracking.py first")
    report = build_report(args.log, args.as_of, args.min_assets)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'NICHE':<18}{'ASSETS':>7}{'ACC':>6}{'REJ':>6}{'DL':>8}{'DL/ASSET/30D':>15}{'USD*':>10}  VERDICT")
        for niche, row in sorted(report.items()):
            recent = row['downloads_per_observed_asset_30d']
            rate = '-' if recent is None else f"{recent:.2f}"
            royalty = '-' if not row['royalty_known'] else f"{row['royalty_usd']:.2f}"
            print(f"{niche:<18}{row['assets']:>7}{row['accepted']:>6}{row['rejected']:>6}{row['downloads']:>8}{rate:>15}{royalty:>10}  {row['verdict']}")
        print("* USD includes reported royalties only. 30-day rates require dated observations; EXPAND TEST is a heuristic.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
