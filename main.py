# main.py
import argparse
import sys
import time
from pathlib import Path
from multiprocessing import Pool
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, BarColumn, TextColumn

# --- Core Configurations & Utilities ---
from config import cfg
from utils.logger import log
from utils.filesystem import setup_directories, get_image_files
from utils.quarantine import move_to_quarantine

# --- 1. Preprocessing Engine ---
from preprocess.resize import resize_image
from preprocess.normalize import normalize_image
from preprocess.quantization import quantize_colors
from preprocess.remove_noise import reduce_noise
from preprocess.morphology import apply_morphology
from preprocess.connected_components import remove_tiny_objects
from preprocess.edge_cleanup import cleanup_edges

# --- 2. Computational Geometry ---
from contour.geometry import optimize_geometry_for_tracing

# --- 3. Vector Tracing & Optimization ---
from tracing.vtracer_wrapper import trace_image_to_svg
from tracing.svg_optimizer import optimize_svg
from tracing.merge_paths import merge_adjacent_paths
from tracing.remove_duplicate_nodes import remove_duplicate_nodes

# --- 4. Export Engine ---
from export.svg_export import export_svg
from export.eps_export import export_eps

# --- 5. NEW FEATURES ---
from utils.adaptive_tuner import analyze_image_complexity, get_adaptive_vtracer_params
from utils.metadata_ai import generate_metadata
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.csv_exporter import append_metadata_csv
from export.ghostscript_export import convert_svg_to_eps_ghostscript


def process_single_image(image_path: Path):
    """Process satu gambar dengan pipeline lengkap + error handling."""
    try:
        log.info(f"Processing: {image_path.name}")
        start_time = time.time()
        
        # ===== PHASE 1: PREPROCESSING =====
        log.info("Phase 1: Preprocessing...")
        img_array = resize_image(image_path)
        
        # Opsional: Aktifkan jika perlu preprocessing
        # img_array = normalize_image(img_array)
        # img_array = quantize_colors(img_array, cfg.NUM_COLORS, cfg.QUANTIZATION_METHOD)
        # img_array = reduce_noise(img_array, cfg.DENOISE_KERNEL_SIZE)
        # if cfg.ENABLE_MORPHOLOGY:
        #     img_array = apply_morphology(img_array)
        # img_array = remove_tiny_objects(img_array, cfg.MIN_COMPONENT_AREA)
        # img_array = cleanup_edges(img_array)
        
        # ===== PHASE 2: ADAPTIVE TUNING =====
        log.info("Phase 2: Adaptive parameter tuning...")
        complexity = analyze_image_complexity(img_array)
        vtracer_params = get_adaptive_vtracer_params(complexity)
        
        # ===== PHASE 3: TRACING =====
        log.info("Phase 3: Vector tracing (VTracer)...")
        svg_content = trace_image_to_svg(img_array, vtracer_params)
        
        # ===== PHASE 4: SVG OPTIMIZATION =====
        log.info("Phase 4: SVG optimization...")
        svg_content = optimize_svg(svg_content)
        if cfg.MERGE_ADJACENT_PATHS:
            svg_content = merge_adjacent_paths(svg_content)
        if cfg.REMOVE_DUPLICATE_NODES:
            svg_content = remove_duplicate_nodes(svg_content)
        
        # ===== PHASE 5: METADATA GENERATION =====
        log.info("Phase 5: Generating metadata (AI)...")
        metadata = generate_metadata(image_path)
        title = metadata["title"]
        keywords = metadata["keywords"]
        
        # ===== PHASE 6: EXPORT SVG + INJECT METADATA =====
        log.info("Phase 6: Exporting SVG with metadata...")
        svg_path = cfg.OUTPUT_SVG_FOLDER / f"{image_path.stem}.svg"
        export_svg(svg_content, svg_path)
        inject_svg_metadata(svg_path, title, keywords)
        
        # ===== PHASE 7: EXPORT EPS =====
        if cfg.EXPORT_EPS:
            log.info("Phase 7: Exporting EPS...")
            eps_path = cfg.OUTPUT_EPS_FOLDER / f"{image_path.stem}.eps"
            
            # Gunakan Ghostscript jika tersedia, fallback ke Inkscape
            success = convert_svg_to_eps_ghostscript(svg_path, eps_path)
            if not success:
                log.warning("Ghostscript failed, fallback ke Inkscape...")
                export_eps(svg_path, eps_path)
            
            # Inject metadata ke EPS
            inject_eps_metadata(eps_path, title, keywords)
        
        # ===== PHASE 8: CSV BACKUP =====
        csv_path = cfg.OUTPUT_SVG_FOLDER / "metadata.csv"
        append_metadata_csv(csv_path, f"{image_path.stem}.svg", title, keywords)
        
        elapsed = time.time() - start_time
        log.info(f"✅ Completed: {image_path.name} in {elapsed:.2f}s")
        
    except Exception as e:
        log.error(f"❌ Failed to process {image_path.name}: {e}")
        # Quarantine system: pindahkan file yang gagal
        move_to_quarantine(image_path, str(e))


def main():
    parser = argparse.ArgumentParser(description="Vector Factory V2 - Image to Vector Pipeline")
    parser.add_argument("--input", type=str, help="Input folder path")
    parser.add_argument("--output-svg", type=str, help="Output SVG folder")
    parser.add_argument("--output-eps", type=str, help="Output EPS folder")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.add_argument("--eps", action="store_true", help="Enable EPS export")
    
    args = parser.parse_args()
    
    # Override config jika ada argumen CLI
    if args.input:
        cfg.INPUT_FOLDER = Path(args.input)
    if args.output_svg:
        cfg.OUTPUT_SVG_FOLDER = Path(args.output_svg)
    if args.output_eps:
        cfg.OUTPUT_EPS_FOLDER = Path(args.output_eps)
    if args.workers:
        cfg.NUM_WORKERS = args.workers
    if args.eps:
        cfg.EXPORT_EPS = True
    
    # Setup directories
    setup_directories()
    
    # Get all image files
    image_files = get_image_files(cfg.INPUT_FOLDER)
    
    if not image_files:
        log.error(f"No images found in {cfg.INPUT_FOLDER}")
        sys.exit(1)
    
    log.info(f"Found {len(image_files)} images to process")
    log.info(f"Using {cfg.NUM_WORKERS} workers")
    
    # Process images
    start_time = time.time()
    
    if cfg.USE_MULTIPROCESS and cfg.NUM_WORKERS > 1:
        # Multiprocessing mode
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Processing images...", total=len(image_files))
            
            with Pool(cfg.NUM_WORKERS) as pool:
                for _ in pool.imap_unordered(process_single_image, image_files):
                    progress.update(task, advance=1)
    else:
        # Single process mode
        for img_path in image_files:
            process_single_image(img_path)
    
    elapsed = time.time() - start_time
    log.info(f"🎉 Pipeline completed in {elapsed:.2f}s")
    log.info(f"SVG output: {cfg.OUTPUT_SVG_FOLDER}")
    if cfg.EXPORT_EPS:
        log.info(f"EPS output: {cfg.OUTPUT_EPS_FOLDER}")


if __name__ == "__main__":
    main()