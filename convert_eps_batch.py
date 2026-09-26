#!/usr/bin/env python3
"""Convert existing SVGs through the same validated EPS exporter as the pipeline."""
import argparse
from pathlib import Path
from config import cfg
from export.eps_export import convert_svg_to_eps, find_inkscape, validate_eps
from utils.csv_exporter import append_metadata_csv
from utils.metadata_injector import inject_eps_metadata
from utils.tracking import read_table

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=cfg.OUTPUT_SVG_FOLDER)
    ap.add_argument("--output", type=Path, default=cfg.OUTPUT_EPS_FOLDER)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    find_inkscape()
    metadata, _ = read_table(args.input / "metadata.csv")
    mapping = {r['Filename']: r for r in metadata}
    success = failure = 0
    for svg in sorted(args.input.glob("*.svg")):
        eps = args.output / (svg.stem + ".eps")
        try:
            if eps.exists() and not args.overwrite:
                validate_eps(eps)
            elif not convert_svg_to_eps(svg, eps):
                raise RuntimeError("EPS export failed")
            if svg.name in mapping:
                row = mapping[svg.name]
                keywords = [k.strip() for k in row['Keywords'].split(',')]
                inject_eps_metadata(eps, row['Title'], keywords)
                append_metadata_csv(args.output / 'metadata.csv', eps.name, row['Title'], keywords, row.get('Category', ''))
            success += 1
        except Exception as exc:
            print(f"FAILED {svg.name}: {exc}"); failure += 1
    print(f"EPS: {success} valid, {failure} failed")
    return 1 if failure else 0

if __name__ == "__main__":
    raise SystemExit(main())
