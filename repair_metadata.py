#!/usr/bin/env python3
"""Repair existing outputs, including legacy filenames, without rebuilding CSV history."""
import argparse
from pathlib import Path
from filelock import FileLock
from config import cfg
from main import content_hash
from utils.atomic_io import read_json, write_json
from utils.csv_exporter import append_metadata_csv, remove_metadata_row
from utils.filesystem import setup_directories, get_image_files
from utils.metadata_ai import generate_metadata
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.quality import render_preview
from utils.tracking import record_asset

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--force', action='store_true', help='Refresh AI metadata even if cached')
    args = ap.parse_args(argv)
    setup_directories()
    pending = 0
    with FileLock(str(cfg.TRACKING_FOLDER / 'pipeline.lock'), timeout=0):
        manifest_path = cfg.TRACKING_FOLDER / 'pipeline_manifest.json'
        manifest = read_json(manifest_path, {'version': '3.0', 'assets': {}})
        seen = set()
        for source in get_image_files(cfg.INPUT_FOLDER) + get_image_files(cfg.INPUT_PROCESSED_FOLDER):
            digest = content_hash(source)
            if digest in seen:
                continue
            seen.add(digest)
            stage = manifest['assets'].get(digest)
            svg = Path(stage['svg']) if stage and stage.get('svg') else cfg.OUTPUT_SVG_FOLDER / (source.stem + '.svg')
            if not svg.exists():
                continue
            preview = cfg.PREVIEW_FOLDER / (svg.stem + '.png')
            render_preview(svg, preview)
            meta = generate_metadata(preview, force=args.force, filename=source.stem)
            if meta.get('source') != 'ai':
                pending += 1
                print(f"Needs metadata: {svg.name}")
                continue
            inject_svg_metadata(svg, meta['title'], meta['keywords'])
            eps = cfg.OUTPUT_EPS_FOLDER / (svg.stem + '.eps')
            if eps.exists():
                inject_eps_metadata(eps, meta['title'], meta['keywords'])
            # Legacy outputs have no QA evidence. Keep them in review until retraced.
            status = 'ready' if stage and stage.get('quality', {}).get('passed') else 'needs_review'
            for folder, name in [(cfg.OUTPUT_SVG_FOLDER, svg.name), (cfg.OUTPUT_EPS_FOLDER, eps.name)]:
                if folder == cfg.OUTPUT_EPS_FOLDER and not eps.exists():
                    continue
                append_metadata_csv(folder / ('metadata.csv' if status == 'ready' else 'review.csv'), name, meta['title'], meta['keywords'])
                remove_metadata_row(folder / ('review.csv' if status == 'ready' else 'metadata.csv'), name)
            if stage:
                stage.update(metadata=meta, status=status)
                write_json(manifest_path, manifest)
            record_asset(cfg.TRACKING_FOLDER / 'production_log.csv', svg.name, {'pipeline_status': status})
            print(f"Updated {svg.name}: {status}")
    print(f"Metadata still pending: {pending}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
