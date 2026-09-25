# main.py
import shutil
import argparse
import sys
import time
import os
import re                                          # ← TAMBAH DI TOP
import importlib
from pathlib import Path
from multiprocessing import Pool
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, BarColumn, TextColumn

from config import cfg
from utils.logger import log
from utils.filesystem import setup_directories, get_image_files
from utils.quarantine import move_to_quarantine
from utils.label_stripper import strip_captions

# --- Preprocessing ---
from preprocess.resize import resize_image

# --- Fitur baru ---
from utils.adaptive_tuner import analyze_image_complexity, get_adaptive_vtracer_params
from utils.metadata_ai import generate_metadata
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.csv_exporter import append_metadata_csv
from export.ghostscript_export import convert_svg_to_eps_ghostscript


# ══════════ UNIVERSAL MODULE ADAPTER ══════════
def _fn(mod_name, preferred):
    mod = importlib.import_module(mod_name)
    for n in preferred:
        if callable(getattr(mod, n, None)):
            return getattr(mod, n)
    for n in dir(mod):
        o = getattr(mod, n)
        if callable(o) and not n.startswith("_") and getattr(o, "__module__", "") == mod.__name__:
            return o
    raise ImportError(f"Tidak ada callable di {mod_name}")


def _call(fn, variants):
    errs = []
    for args in variants:
        try:
            return fn(*args)
        except Exception as e:
            errs.append(e)
    raise RuntimeError(f"Semua varian pemanggilan {fn.__name__} gagal: {errs[-1]}")
# ══════════════════════════════════════════════


# ══════════ HARDENING FUNCTION (Adobe Stock compliance) ══════════
def harden_for_adobe(svg_text: str) -> str:
    """
    Paksa SVG memenuhi standar Adobe Stock:
    1. Dimensi intrinsik 5000px (preview jadi 25MP, aman dari flag <15MP)
    2. Anti-aliasing hint (mengatasi "didn't use anti-aliasing")
    """
    svg_text = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"',  r'\1 width="5000"',  svg_text, count=1)
    svg_text = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r'\1 height="5000"', svg_text, count=1)
    if 'shape-rendering=' not in svg_text:
        svg_text = svg_text.replace('<svg ', '<svg shape-rendering="geometricPrecision" ', 1)
    return svg_text
# ═════════════════════════════════════════════════════════════════


def process_single_image(image_path: Path):
    try:
        log.info(f"Processing: {image_path.name}")
        start = time.time()

        # PHASE 1: PREPROCESS
        img_array = resize_image(image_path)
        img_array = strip_captions(img_array)

        # PHASE 2: ADAPTIVE TUNING
        complexity = analyze_image_complexity(img_array)
        vparams = get_adaptive_vtracer_params(complexity)

        # PHASE 3: TRACING
        trace_fn = _fn("tracing.vtracer_wrapper", ["trace_image_to_svg"])
        svg_content = _call(trace_fn, [(img_array, vparams), (img_array,)])

        # PHASE 4: SVG OPTIMIZATION (default OFF untuk isolasi bug)
        if os.getenv("SKIP_OPT", "1") == "1":
            log.info("Phase 4: skipped (mode isolasi bug)")
        else:
            opt_fn = _fn("tracing.svg_optimizer", ["optimize_svg"])
            svg_content = _call(opt_fn, [(svg_content,), (svg_content, cfg.SVG_PRECISION)])
            if cfg.MERGE_ADJACENT_PATHS:
                merge_fn = _fn("tracing.merge_paths", ["merge_adjacent_paths"])
                svg_content = _call(merge_fn, [(svg_content,)])
            if cfg.REMOVE_DUPLICATE_NODES:
                dedup_fn = _fn("tracing.remove_duplicate_nodes", ["remove_duplicate_nodes"])
                svg_content = _call(dedup_fn, [(svg_content,)])

        # PHASE 5: METADATA AI
        meta = generate_metadata(image_path)
        title, keywords = meta["title"], meta["keywords"]

        # PHASE 6: EXPORT SVG
        svg_out = cfg.OUTPUT_SVG_FOLDER / f"{image_path.stem}.svg"
        svg_out.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(svg_content, bytes):
            svg_out.write_bytes(svg_content)
        else:
            svg_out.write_text(svg_content, encoding="utf-8")
        log.info(f"SVG saved: {svg_out.name} ({svg_out.stat().st_size // 1024} KB)")
        inject_svg_metadata(svg_out, title, keywords)

        # PHASE 6.5: HARDEN FOR ADOBE STOCK                          # ← TAMBAH DI SINI
        try:
            svg_text = svg_out.read_text(encoding="utf-8")
            svg_text = harden_for_adobe(svg_text)
            svg_out.write_text(svg_text, encoding="utf-8")
            log.info(f"Hardened: {svg_out.name} (5000px + anti-aliasing)")
        except Exception as e:
            log.warning(f"Hardening failed: {svg_out.name}: {e}")

        # PHASE 7: EPS (optional)
        if cfg.EXPORT_EPS:
            eps_out = cfg.OUTPUT_EPS_FOLDER / f"{image_path.stem}.eps"
            if not convert_svg_to_eps_ghostscript(svg_out, eps_out):
                eps_fn = _fn("export.eps_export", ["export_eps", "convert_svg_to_eps", "svg_to_eps"])
                _call(eps_fn, [(svg_out, eps_out), (str(svg_out), str(eps_out))])
            inject_eps_metadata(eps_out, title, keywords)

        # PHASE 8: CSV BACKUP
        append_metadata_csv(cfg.OUTPUT_SVG_FOLDER / "metadata.csv",
                            f"{image_path.stem}.svg", title, keywords)

        # PHASE 9: ARCHIVE PROCESSED INPUT
        if os.getenv("SKIP_ARCHIVE", "0") != "1":
            dest = cfg.INPUT_PROCESSED_FOLDER / image_path.name
            if dest.exists():
                stem = image_path.stem
                suffix = image_path.suffix
                ts = int(time.time())
                dest = cfg.INPUT_PROCESSED_FOLDER / f"{stem}_{ts}{suffix}"
            shutil.move(str(image_path), str(dest))
            log.info(f"Archived: {image_path.name} → input_processed/")

        log.info(f"✅ Completed: {image_path.name} in {time.time()-start:.2f}s")

    except Exception as e:
        log.error(f"❌ Failed: {image_path.name}: {e}")
        move_to_quarantine(image_path, str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--eps", action="store_true")
    ap.add_argument("--no-archive", action="store_true",
                    help="Keep processed inputs in input/ folder")
    args = ap.parse_args()

    if args.input: cfg.INPUT_FOLDER = Path(args.input)
    if args.workers: cfg.NUM_WORKERS = args.workers
    if args.eps: cfg.EXPORT_EPS = True
    if args.no_archive: os.environ["SKIP_ARCHIVE"] = "1"

    setup_directories()
    images = get_image_files(cfg.INPUT_FOLDER)
    if not images:
        log.error(f"No images in {cfg.INPUT_FOLDER}"); sys.exit(1)

    log.info(f"Found {len(images)} images | workers: {cfg.NUM_WORKERS}")

    if cfg.USE_MULTIPROCESS and cfg.NUM_WORKERS > 1:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), TimeElapsedColumn()) as progress:
            task = progress.add_task("Tracing...", total=len(images))
            with Pool(cfg.NUM_WORKERS) as pool:
                for _ in pool.imap_unordered(process_single_image, images):
                    progress.update(task, advance=1)
    else:
        for img in images:
            process_single_image(img)

    log.info("🎉 Pipeline completed")


if __name__ == "__main__":
    main()