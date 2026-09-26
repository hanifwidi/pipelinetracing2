#!/usr/bin/env python3
"""Archive only ready assets; --all explicitly opts into the old one-off behavior."""
import argparse
from filelock import FileLock
from config import cfg
from main import content_hash, _archive
from utils.atomic_io import read_json, write_json
from utils.filesystem import setup_directories, get_image_files

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--all', action='store_true', help='Archive every image, including unprocessed inputs')
    args = ap.parse_args(argv)
    setup_directories()
    moved = 0
    with FileLock(str(cfg.TRACKING_FOLDER / 'pipeline.lock'), timeout=0):
        path = cfg.TRACKING_FOLDER / 'pipeline_manifest.json'
        manifest = read_json(path, {'version': '3.0', 'assets': {}})
        for source in get_image_files(cfg.INPUT_FOLDER):
            digest = content_hash(source)
            stage = manifest['assets'].get(digest, {})
            if not args.all and stage.get('status') != 'ready':
                continue
            archived = _archive([str(source)], digest)
            if stage:
                stage['sources'] = list(dict.fromkeys(stage.get('sources', []) + archived))
            moved += 1
        write_json(path, manifest)
    print(f'Archived {moved} images')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
