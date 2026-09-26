#!/usr/bin/env python3
"""Add missing assets without overwriting production history."""
import argparse
from pathlib import Path
from utils.tracking import initialize_tracking, extract_niche_style_batch

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, default=Path("output_svg/metadata.csv"))
    ap.add_argument("--log", type=Path, default=Path("tracking/production_log.csv"))
    ap.add_argument("--niche")
    args = ap.parse_args(argv)
    added = initialize_tracking(args.metadata, args.log, args.niche)
    print(f"Added {added} assets. Existing history preserved: {args.log}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
