#!/usr/bin/env python3
"""Import dated observations; ambiguous title matches are skipped."""
import argparse
from pathlib import Path
from utils.tracking import import_downloads

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scrape", nargs="?", type=Path)
    ap.add_argument("--metadata", type=Path, default=Path("output_svg/metadata.csv"))
    ap.add_argument("--log", type=Path, default=Path("tracking/production_log.csv"))
    args = ap.parse_args(argv)
    if args.scrape is None:
        candidates = sorted(Path('.').glob('adobe_scrape_*.csv'))
        if not candidates:
            ap.error("Provide a scrape CSV; no adobe_scrape_*.csv was found")
        args.scrape = candidates[-1]
    counts = import_downloads(args.scrape, args.metadata, args.log)
    print(" | ".join(f"{k}: {v}" for k, v in counts.items()))
    return 1 if counts['invalid'] else 0

if __name__ == "__main__":
    raise SystemExit(main())
