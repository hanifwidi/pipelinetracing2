#!/usr/bin/env python3
"""Embed EPS XMP with ExifTool and validate the result before replacing the file."""
import argparse
import shutil
from pathlib import Path
from config import cfg
from utils.metadata_injector import inject_eps_metadata
from utils.tracking import read_table

def inject_to_eps(eps_path, title, keywords):
    return inject_eps_metadata(eps_path, title, keywords)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, default=cfg.OUTPUT_SVG_FOLDER / 'metadata.csv')
    ap.add_argument("--eps-dir", type=Path, default=cfg.OUTPUT_EPS_FOLDER)
    args = ap.parse_args(argv)
    if not shutil.which('exiftool'):
        ap.error('ExifTool is required for embedded EPS metadata. The CSV remains usable without it.')
    rows, _ = read_table(args.metadata)
    failures = 0
    for row in rows:
        eps = args.eps_dir / (Path(row['Filename']).stem + '.eps')
        if not eps.exists():
            continue
        try:
            if not inject_to_eps(eps, row['Title'], [k.strip() for k in row['Keywords'].split(',')]):
                failures += 1
        except Exception as exc:
            print(f"FAILED {eps.name}: {exc}"); failures += 1
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
