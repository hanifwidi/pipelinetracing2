# main.py
import argparse
import sys
import time
import importlib
from pathlib import Path
from multiprocessing import Pool
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, BarColumn, TextColumn

from config import cfg
from utils.logger import log
from utils.filesystem import setup_directories, get_image_files
from utils.quarantine import move_to_quarantine

# --- Preprocessing (nama fungsi sesuai main.py asli kamu) ---
from preprocess.resize import resize_image

# --- Fitur baru (file buatan kita, nama pasti) ---
from utils.adaptive_tuner import analyze_image_complexity, get_adaptive_vtracer_params
from utils.metadata_ai import generate_metadata
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.csv_exporter import append_metadata_csv
from export.ghostscript_export import convert_svg_to_eps_ghostscript


# ══════════ UNIVERSAL MODULE ADAPTER ══════════
# Mendeteksi nama fungsi apa pun di dalam modul repo kamu.
def _fn(mod_name, preferred):
    mod = importlib.import_module(mod_name)
    for n in preferred:
        if callable(getattr(mod, n, None)):
            return getattr(mod, n)
    for n in dir(mod):  # fallback: fungsi publik pertama milik modul itu
        o = getattr(mod, n)
        if callable(o) and not n.startswith("_") and getattr(o, "__module__", "") == mod.__name__:
            return o
    raise ImportError(f"Tidak ada callable di {mod_name}")


def _call(fn, variants):
    errs = []
    for args in variants:  # coba beberapa varian tanda tangan
        try:
            return fn(*args)
        except Exception as e:
            errs.append(e)
    raise RuntimeError(f"Semua varian pemanggilan {fn.__name__} gagal: {errs[-1]}")
# ══════════════════════════════════════════════


def process_single_image(image_path: Path):
    try:
        log.info(f"Processing: {image_path.name}")
        start = time.time()

        # PHASE 1: PREPROCESS (resize saja; filter lain opsional)
        img_array = resize_image(image_path)

        # PHASE 2: ADAPTIVE TUNING
        complexity = analyze_image_complexity(img_array)
        vparams = get_adaptive_vtracer_params(complexity)

        # PHASE 3: TRACING (adapter: pakai custom params kalau wrapper sudah di-update)
        trace_fn = _fn("tracing.vtracer_wrapper", ["trace_image_to_svg"])
        svg_content = _call(trace_fn, [(img_array, vparams), (img_array,)])

                # PHASE 4: SVG OPTIMIZATION (default OFF dulu untuk isolasi bug)
        import os
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
        # PHASE 6: EXPORT SVG (direct write — modul export asli minta file handle)
        svg_out = cfg.OUTPUT_SVG_FOLDER / f"{image_path.stem}.svg"
        svg_out.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(svg_content, bytes):
            svg_out.write_bytes(svg_content)
        else:
            svg_out.write_text(svg_content, encoding="utf-8")
        log.info(f"SVG saved: {svg_out.name} ({svg_out.stat().st_size // 1024} KB)")
        inject_svg_metadata(svg_out, title, keywords)

        # PHASE 7: EPS (Ghostscript dulu, fallback Inkscape modul aslimu)
        if cfg.EXPORT_EPS:
            eps_out = cfg.OUTPUT_EPS_FOLDER / f"{image_path.stem}.eps"
            if not convert_svg_to_eps_ghostscript(svg_out, eps_out):
                eps_fn = _fn("export.eps_export", ["export_eps", "convert_svg_to_eps", "svg_to_eps"])
                _call(eps_fn, [(svg_out, eps_out), (str(svg_out), str(eps_out))])
            inject_eps_metadata(eps_out, title, keywords)

        # PHASE 8: CSV BACKUP
        append_metadata_csv(cfg.OUTPUT_SVG_FOLDER / "metadata.csv",
                            f"{image_path.stem}.svg", title, keywords)

        log.info(f"✅ Completed: {image_path.name} in {time.time()-start:.2f}s")

    except Exception as e:
        log.error(f"❌ Failed: {image_path.name}: {e}")
        move_to_quarantine(image_path, str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--eps", action="store_true")
    args = ap.parse_args()

    if args.input: cfg.INPUT_FOLDER = Path(args.input)
    if args.workers: cfg.NUM_WORKERS = args.workers
    if args.eps: cfg.EXPORT_EPS = True

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