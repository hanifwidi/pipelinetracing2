"""Image-to-vector production pipeline with explicit stages and resumable tracing."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import cv2
from filelock import FileLock, Timeout
from PIL import Image
from rich.progress import Progress
from config import cfg
from export.eps_export import convert_svg_to_eps, find_inkscape
from export.svg_export import save_svg
from preprocess.resize import resize_image
from tracing.vtracer_wrapper import trace_image_to_svg
from tracing.icon_trace import trace_icon_source, IconSourceNeedsReview
from tracing.svg_optimizer import optimize_svg_tree
from tracing.merge_paths import merge_same_color_paths
from tracing.remove_duplicate_nodes import clean_duplicate_nodes
from utils.adaptive_tuner import analyze_image_complexity, get_adaptive_vtracer_params
from utils.atomic_io import atomic_write, read_json, write_json
from utils.csv_exporter import append_metadata_csv, remove_metadata_row
from utils.filesystem import setup_directories, get_image_files
from utils.label_stripper import strip_captions
from utils.logger import log
from utils.metadata_ai import generate_metadata, _clean_metadata
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.quality import inspect_svg, render_preview
from utils.quarantine import move_to_quarantine
from utils.svg_tools import harden_for_adobe, parse_svg, ICON_TYPES
from utils.tracking import record_asset

PIPELINE_VERSION = "3.1-icons"


def content_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracing_signature():
    names = ["MAX_SIZE", "STRIP_CAPTIONS", "GRID_ROWS", "GRID_COLS", "OPTIMIZE_SVG", "SVG_PRECISION", "MERGE_ADJACENT_PATHS", "REMOVE_DUPLICATE_NODES", "TARGET_MEGAPIXELS", "ASSET_TYPE", "ICON_MAX_SIZE", "ICON_MIN_SIZE", "ICON_SHEET_MIN_SIZE"]
    values = {key: getattr(cfg, key) for key in names}
    values.update(version=PIPELINE_VERSION, vtracer=importlib.metadata.version("vtracer"))
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]


def initialize_worker(settings):
    # Explicit transfer also works with the spawn start method on macOS/Windows.
    cfg.__dict__.update(settings)
    cv2.setNumThreads(1)
    os.environ.setdefault("RAYON_NUM_THREADS", "1")


def process_single_image(job):
    start = time.monotonic()
    path = Path(job["sources"][0])
    folder = cfg.CACHE_DIR / "tracing" / job["asset_id"] / job["signature"]
    folder.mkdir(parents=True, exist_ok=True)
    reference, raw_svg = folder / "reference.png", folder / "raw.svg"
    alpha_path, analysis_path = folder / "expected_alpha.png", folder / "analysis.json"
    icon_mode = cfg.ASSET_TYPE in ICON_TYPES
    try:
        trace_info = read_json(analysis_path, {})
        if not isinstance(trace_info, dict) or not isinstance(trace_info.get("analysis"), dict) or not isinstance(trace_info.get("source_issues"), list):
            trace_info = {}
    except (ValueError, OSError):
        trace_info = {}
    cache_hit = raw_svg.exists() and reference.exists() and bool(trace_info) and not job.get("force")
    if cache_hit:
        try:
            parse_svg(raw_svg.read_bytes())
            with Image.open(reference) as im:
                im.verify()
            if icon_mode and not trace_info["source_issues"]:
                with Image.open(alpha_path) as im:
                    im.verify()
        except Exception as exc:
            log.warning("Rebuilding invalid trace cache: %s", type(exc).__name__)
            cache_hit = False
    if not cache_hit:
        image = resize_image(path, cfg.MAX_SIZE)
        if cfg.STRIP_CAPTIONS:
            if image.shape[0] < cfg.GRID_ROWS or image.shape[1] < cfg.GRID_COLS:
                raise ValueError("Caption grid exceeds image dimensions")
            image = strip_captions(image, cfg.GRID_ROWS, cfg.GRID_COLS)
        analysis = analyze_image_complexity(image)
        params = get_adaptive_vtracer_params(analysis)
        source_issues = []
        if icon_mode:
            alpha_path.unlink(missing_ok=True)
            try:
                svg, expected_alpha = trace_icon_source(image, analysis, params)
                Image.fromarray(expected_alpha).save(alpha_path)
            except IconSourceNeedsReview as exc:
                source_issues.append(str(exc))
                log.warning("Icon source needs review: %s", exc)
                svg = trace_image_to_svg(image, params)
        else:
            svg = trace_image_to_svg(image, params)
        Image.fromarray(image).save(reference)
        atomic_write(raw_svg, svg)
        trace_info = {"analysis": analysis, "source_issues": source_issues}
        write_json(analysis_path, trace_info)
    svg = raw_svg.read_text(encoding="utf-8")
    if cfg.OPTIMIZE_SVG:
        svg = optimize_svg_tree(svg)
        svg = merge_same_color_paths(svg)
        svg = clean_duplicate_nodes(svg)
    svg = harden_for_adobe(svg)
    svg_path = cfg.OUTPUT_SVG_FOLDER / (job["basename"] + ".svg")
    save_svg(svg, path.name, svg_path)
    preview = cfg.PREVIEW_FOLDER / (job["basename"] + ".png")
    render_preview(svg_path, preview)
    quality = inspect_svg(svg_path, preview, reference,
                          alpha_reference=alpha_path if alpha_path.exists() else None)
    quality["warnings"].extend(trace_info["source_issues"])
    quality["passed"] = not quality["warnings"]
    eps_path = None
    if cfg.EXPORT_EPS:
        eps_path = cfg.OUTPUT_EPS_FOLDER / (job["basename"] + ".eps")
        if not convert_svg_to_eps(svg_path, eps_path):
            raise RuntimeError("EPS export/validation failed")
    result = {**job, "svg": str(svg_path.resolve()), "eps": str(eps_path.resolve()) if eps_path else None,
              "preview": str(preview.resolve()), "reference": str(reference.resolve()), "quality": quality,
              "asset_type": cfg.ASSET_TYPE, "analysis": trace_info["analysis"],
              "alpha_reference": str(alpha_path.resolve()) if alpha_path.exists() else None,
              "trace_cache_hit": cache_hit, "production_seconds": round(time.monotonic()-start, 3)}
    write_json(cfg.PREVIEW_FOLDER / (job["basename"] + ".qa.json"), quality)
    return result


def _load_manual(path):
    if not path:
        return {}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for row in rows:
        key = row["Filename"]
        if key in result:
            raise ValueError(f"Duplicate metadata filename: {key}")
        result[key] = {**_clean_metadata({"title": row["Title"], "keywords": [v.strip() for v in row["Keywords"].split(",")]}), "source": "manual", "category": row.get("Category", "")}
    return result


def _metadata(stage, manual, force):
    keys = [Path(stage["svg"]).name]
    if stage.get("unique_source_name"):
        keys += [Path(stage["sources"][0]).name]
    for key in keys:
        if key in manual:
            return manual[key]
    return generate_metadata(Path(stage["preview"]), force=force, filename=Path(stage["sources"][0]).stem)


def _archive(sources, asset_id):
    archived = []
    for source in map(Path, sources):
        target = cfg.INPUT_PROCESSED_FOLDER / f"{source.stem}__{asset_id[:12]}{source.suffix}"
        if target.exists():
            if content_hash(target) != asset_id:
                target = cfg.INPUT_PROCESSED_FOLDER / f"{source.stem}__{asset_id}{source.suffix}"
                if target.exists() and content_hash(target) != asset_id:
                    raise FileExistsError(target)
            if target.exists():
                source.unlink()
            else:
                shutil.move(str(source), str(target))
        else:
            shutil.move(str(source), str(target))
        archived.append(str(target.resolve()))
    return archived


def finalize(stage, meta, no_archive):
    svg = Path(stage["svg"])
    valid_meta = meta.get("source") in {"ai", "manual"}
    status = "needs_metadata" if not valid_meta else "ready" if stage["quality"]["passed"] else "needs_review"
    if valid_meta:
        clean = _clean_metadata(meta)
        inject_svg_metadata(svg, clean["title"], clean["keywords"])
        if stage.get("eps"):
            stage["eps_metadata_embedded"] = inject_eps_metadata(Path(stage["eps"]), clean["title"], clean["keywords"])
    if svg.stat().st_size > cfg.MAX_FILE_MB * 1_000_000 or (stage.get("eps") and Path(stage["eps"]).stat().st_size > cfg.MAX_FILE_MB * 1_000_000):
        raise ValueError("Final file exceeds the size limit after metadata injection")
    stage.update(status=status, metadata=meta)
    for folder, extension in [(cfg.OUTPUT_SVG_FOLDER, ".svg"), (cfg.OUTPUT_EPS_FOLDER, ".eps")]:
        if extension == ".eps" and not stage.get("eps"):
            continue
        name = stage["basename"] + extension
        if status == "ready":
            append_metadata_csv(folder / "metadata.csv", name, meta["title"], meta["keywords"], meta.get("category", ""))
            remove_metadata_row(folder / "review.csv", name)
        else:
            append_metadata_csv(folder / "review.csv", name, meta["title"], meta.get("keywords", []), meta.get("category", ""))
            remove_metadata_row(folder / "metadata.csv", name)
    record_asset(cfg.TRACKING_FOLDER / "production_log.csv", svg.name,
                 {"asset_id": stage["asset_id"], "pipeline_status": status, "production_seconds": stage["production_seconds"]})
    if status == "ready" and not no_archive:
        stage["sources"] = _archive(stage["sources"], stage["asset_id"])
    return stage


def resume_metadata(args, manifest, manifest_path, manual):
    """Resume saved pending assets without tracing or revisiting ready assets."""
    stages = [dict(s) for s in manifest["assets"].values() if s.get("status") == "needs_metadata"]
    if not stages:
        log.info("No assets with status needs_metadata")
        return 0
    counts, failures = Counter(), 0
    with ThreadPoolExecutor(max_workers=cfg.METADATA_WORKERS) as pool:
        pending = {}
        for stage in stages:
            try:
                svg = Path(stage["svg"])
                parse_svg(svg.read_bytes())
                if stage.get("eps") and not Path(stage["eps"]).is_file():
                    raise ValueError("Saved EPS is missing; restore it or run tracing normally")
                if not isinstance(stage.get("quality", {}).get("passed"), bool):
                    raise ValueError("Saved QA result is missing; run tracing normally")
                preview = Path(stage["preview"])
                if not preview.is_file():
                    render_preview(svg, preview)
                # Check preview even if manual metadata is used, to keep QA inputs valid.
                with Image.open(preview) as im:
                    im.verify()
                pending[pool.submit(_metadata, stage, manual, args.force_metadata)] = stage
            except Exception as exc:
                failures += 1
                log.error("Cannot resume %s: %s", stage.get("basename", "asset"), exc)
        for future in as_completed(pending):
            stage = pending[future]
            try:
                meta = future.result()
                no_archive = args.no_archive
                # Never archive an input that has been replaced since tracing.
                if not no_archive:
                    sources = stage.get("sources", [])
                    intact = bool(sources) and all(Path(p).is_file() and content_hash(p) == stage["asset_id"] for p in sources)
                    if not intact:
                        log.warning("%s: source missing/changed; keeping inputs in place", stage["basename"])
                        no_archive = True
                stage = finalize(stage, meta, no_archive)
                manifest["assets"][stage["asset_id"]] = stage
                write_json(manifest_path, manifest)
                counts[stage["status"]] += 1
            except Exception as exc:
                # Keep the original needs_metadata entry and input on repair errors.
                failures += 1
                log.error("Metadata resume failed for %s: %s", stage.get("basename", "asset"), type(exc).__name__)
    log.info("Metadata resume | ready=%d | needs_metadata=%d | needs_review=%d | errors=%d",
             counts["ready"], counts["needs_metadata"], counts["needs_review"], failures)
    return 1 if failures else 0


def run_pipeline(args):
    setup_directories()
    manual = _load_manual(args.metadata_csv)
    manifest_path = cfg.TRACKING_FOLDER / "pipeline_manifest.json"
    manifest = read_json(manifest_path, {"version": PIPELINE_VERSION, "assets": {}})
    if args.resume_metadata:
        return resume_metadata(args, manifest, manifest_path, manual)
    find_inkscape()  # Fail before processing inputs if previews cannot be rendered.
    images = get_image_files(cfg.INPUT_FOLDER)
    if not images:
        log.info("No pending images in %s", cfg.INPUT_FOLDER)
        return 0
    jobs = {}
    name_counts = Counter(p.name for p in images)
    for image in images:
        digest = content_hash(image)
        if digest in jobs:
            jobs[digest]["sources"].append(str(image)); continue
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", image.stem).strip("_")[:100] or "asset"
        saved = manifest["assets"].get(digest, {})
        jobs[digest] = {"asset_id": digest, "basename": saved.get("basename", f"{stem}__{digest[:12]}"),
                       "sources": [str(image)], "signature": tracing_signature(), "force": args.force,
                       "unique_source_name": name_counts[image.name] == 1}
    settings = asdict(cfg)
    initialize_worker(settings)
    failures = 0
    states = Counter()

    def store(stage):
        manifest["assets"][stage["asset_id"]] = stage
        write_json(manifest_path, manifest)

    def fail(job, exc):
        nonlocal failures
        failures += 1
        failed = {**job, "status": "failed", "error": str(exc)}
        # A failed rerun must not leave a stale upload-ready CSV row.
        remove_metadata_row(cfg.OUTPUT_SVG_FOLDER / "metadata.csv", job["basename"] + ".svg")
        remove_metadata_row(cfg.OUTPUT_EPS_FOLDER / "metadata.csv", job["basename"] + ".eps")
        store(failed)
        log.error("Failed %s: %s", job["basename"], exc)
        for source in job["sources"]:
            if Path(source).exists():
                move_to_quarantine(Path(source), str(exc))

    with ThreadPoolExecutor(max_workers=cfg.METADATA_WORKERS) as metadata_pool, Progress() as progress:
        task = progress.add_task("Tracing / metadata / validation", total=len(jobs))
        pending = {}
        def enqueue(stage):
            pending[metadata_pool.submit(_metadata, stage, manual, args.force_metadata)] = stage
        if cfg.USE_MULTIPROCESS and cfg.NUM_WORKERS > 1:
            with ProcessPoolExecutor(max_workers=min(cfg.NUM_WORKERS, len(jobs)), mp_context=multiprocessing.get_context("spawn"), initializer=initialize_worker, initargs=(settings,)) as pool:
                futures = {pool.submit(process_single_image, job): job for job in jobs.values()}
                for future in as_completed(futures):
                    try:
                        enqueue(future.result())
                    except Exception as exc:
                        fail(futures[future], exc); progress.advance(task)
        else:
            for job in jobs.values():
                try:
                    enqueue(process_single_image(job))
                except Exception as exc:
                    fail(job, exc); progress.advance(task)
        for future in as_completed(pending):
            stage = pending[future]
            try:
                stage = finalize(stage, future.result(), args.no_archive)
                states[stage["status"]] += 1
                store(stage)
            except Exception as exc:
                fail(stage, exc)
            progress.advance(task)
    log.info("Finished | ready=%d | needs_metadata=%d | needs_review=%d | failed=%d", states['ready'], states['needs_metadata'], states['needs_review'], failures)
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path)
    ap.add_argument("--workers", type=int, default=cfg.NUM_WORKERS)
    ap.add_argument("--metadata-workers", type=int, default=cfg.METADATA_WORKERS)
    ap.add_argument("--ai-rpm", type=int, default=cfg.AI_REQUESTS_PER_MINUTE)
    ap.add_argument("--eps", action="store_true")
    ap.add_argument("--no-archive", action="store_true", default=os.getenv("SKIP_ARCHIVE") == "1")
    ap.add_argument("--skip-opt", action="store_true", default=os.getenv("SKIP_OPT") == "1")
    ap.add_argument("--strip-captions", action="store_true")
    ap.add_argument("--grid", default="4x4", help="Caption grid, e.g. 4x4 or 3x5")
    ap.add_argument("--asset-type", choices=("illustration", *ICON_TYPES), default=cfg.ASSET_TYPE,
                    help="Icon modes treat a flat white source background and white holes as negative space")
    ap.add_argument("--target-mp", type=float, default=None,
                    help="Default 25 for illustrations; 16 capped at 4000px per side for icons")
    ap.add_argument("--max-size", type=int, default=cfg.MAX_SIZE)
    ap.add_argument("--metadata-csv", type=Path, help="Reviewed metadata; bypass AI for matching filenames")
    ap.add_argument("--resume-metadata", action="store_true", help="Only repair saved needs_metadata assets; do not trace or touch ready assets")
    ap.add_argument("--force", action="store_true", help="Rebuild tracing cache")
    ap.add_argument("--force-metadata", action="store_true", help="Regenerate cached AI metadata")
    args = ap.parse_args(argv)
    if min(args.workers, args.metadata_workers, args.ai_rpm, args.max_size) < 1:
        ap.error("Workers, rate limit, and maximum image size must be positive")
    try:
        rows, cols = map(int, args.grid.lower().split("x"))
        if min(rows, cols) < 1:
            raise ValueError()
    except ValueError:
        ap.error("--grid must have positive rows x columns, e.g. 4x4")
    if args.target_mp is None:
        args.target_mp = 16.0 if args.asset_type in ICON_TYPES else cfg.TARGET_MEGAPIXELS
    if not math.isfinite(args.target_mp) or args.target_mp <= 0:
        ap.error("--target-mp must be positive and finite")
    if args.asset_type in ICON_TYPES:
        if args.target_mp > 16:
            ap.error("Icon profiles support at most 16 MP and 4000px per side")
    elif not cfg.MIN_MEGAPIXELS <= args.target_mp <= cfg.MAX_MEGAPIXELS:
        ap.error("Illustration --target-mp must be between 15 and 65")
    if args.input:
        cfg.INPUT_FOLDER = args.input
    cfg.NUM_WORKERS, cfg.METADATA_WORKERS = args.workers, args.metadata_workers
    cfg.AI_REQUESTS_PER_MINUTE = args.ai_rpm
    cfg.EXPORT_EPS = args.eps
    cfg.ASSET_TYPE = args.asset_type
    cfg.OPTIMIZE_SVG = not args.skip_opt
    cfg.STRIP_CAPTIONS, cfg.GRID_ROWS, cfg.GRID_COLS = args.strip_captions, rows, cols
    cfg.TARGET_MEGAPIXELS, cfg.MAX_SIZE = args.target_mp, args.max_size
    cfg.TRACKING_FOLDER.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(cfg.TRACKING_FOLDER / "pipeline.lock"), timeout=0):
            return run_pipeline(args)
    except Timeout:
        log.error("Another pipeline or metadata repair is using this workspace")
        return 1
    except Exception as exc:
        log.error("Pipeline stopped: %s", exc)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
