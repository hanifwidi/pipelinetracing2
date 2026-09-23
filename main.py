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

# --- 1. Preprocessing Engine ---
from preprocess.resize import resize_image
from preprocess.normalize import normalize_image
# from preprocess.remove_text import remove_text
from preprocess.quantization import quantize_colors
from preprocess.remove_noise import reduce_noise
from preprocess.morphology import apply_morphology
from preprocess.connected_components import remove_tiny_objects
from preprocess.edge_cleanup import cleanup_edges

# --- 2. Computational Geometry ---
from contour.geometry import optimize_geometry_for_tracing

# --- 3. Vector Tracing & Optimization ---
from tracing.vtracer_wrapper import trace_image_to_svg
from tracing.svg_optimizer import optimize_svg_tree
from tracing.merge_paths import merge_same_color_paths
from tracing.remove_duplicate_nodes import clean_duplicate_nodes

# --- 4. Export Pipeline ---
from export.svg_export import save_svg
from export.eps_export import convert_svg_to_eps


def process_pipeline(image_path: Path) -> bool:
    try:
        log.info(f"▶️ Starting pipeline for: {image_path.name}")
        
        # ==========================================
        # PHASE 1: LOAD & RESIZE ONLY
        # ==========================================
        # 1. Load and Resize (Ini aman dan perlu)
        img_array = resize_image(image_path, cfg.MAX_SIZE)
        
        # MATIKAN SEMUA FILTER OPENCV & GEOMETRY YANG MERUSAK GAMBAR
        # img_array = normalize_image(img_array)
        # img_array = quantize_colors(...)
        # img_array = reduce_noise(...)
        # img_array = apply_morphology(...)
        # img_array = remove_tiny_objects(...)
        # pristine_canvas = optimize_geometry_for_tracing(...)
        
        # ==========================================
        # PHASE 3: VECTORIZATION (LANGSUNG KE VTRACER)
        # ==========================================
        # Oper gambar hasil resize langsung ke mesin Rust
        raw_svg_string = trace_image_to_svg(img_array)
        
        # Biarkan DOM manipulation mati dulu untuk tes ini
        svg_tree = raw_svg_string
        
        # ==========================================
        # PHASE 4: DISK EXPORT
        # ==========================================
        saved_svg_path = save_svg(svg_tree, image_path.name)
            
        log.info(f"✅ Successfully completed: {image_path.name}")
        return True
        
    except Exception as e:
        log.error(f"❌ Pipeline failed for {image_path.name}: {str(e)}")
        return False


def parse_arguments() -> None:
    """Parses CLI arguments and mutates the global configuration state."""
    parser = argparse.ArgumentParser(
        description="Vector Factory V2 - Production Image to SVG Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument("--input", type=str, help="Path to input directory containing raster images")
    parser.add_argument("--workers", type=int, help="Number of CPU cores to utilize")
    parser.add_argument("--colors", type=int, choices=[4, 6, 8, 12, 16, 32], help="Number of colors for vector quantization")
    parser.add_argument("--svg-only", action="store_true", help="Skip EPS conversion")
    parser.add_argument("--eps", action="store_true", help="Enable Adobe Stock EPS export via Inkscape")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    
    args = parser.parse_args()
    
    if args.input:
        cfg.INPUT_FOLDER = Path(args.input)
    if args.workers:
        cfg.NUM_WORKERS = args.workers
    if args.colors:
        cfg.NUM_COLORS = args.colors
    if args.svg_only:
        cfg.EXPORT_EPS = False
    if args.eps:
        cfg.EXPORT_EPS = True
    if args.debug:
        cfg.DEBUG_MODE = True


def main():
    """Application entry point."""
    parse_arguments()
    setup_directories()
    
    log.info("🚀 Booting Vector Factory V2 Pipeline")
    log.info(f"⚙️ Config: Workers={cfg.NUM_WORKERS}, Colors={cfg.NUM_COLORS}, EPS Export={cfg.EXPORT_EPS}")
    
    images = get_image_files(cfg.INPUT_FOLDER)
    if not images:
        log.error("Aborting: No valid raster images found in the input directory.")
        sys.exit(1)

    start_time = time.time()
    success_count = 0
    total_images = len(images)
    
    # Progress UI
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        
        task = progress.add_task("[cyan]Processing Vectors...", total=total_images)
        
        if cfg.USE_MULTIPROCESS and cfg.NUM_WORKERS > 1:
            log.info(f"⚡ Scaling horizontally across {cfg.NUM_WORKERS} parallel workers.")
            with Pool(processes=cfg.NUM_WORKERS) as pool:
                # Use imap_unordered for maximum throughput; order doesn't matter
                for is_success in pool.imap_unordered(process_pipeline, images):
                    if is_success:
                        success_count += 1
                    progress.advance(task)
        else:
            log.info("🐌 Running in strictly single-threaded mode.")
            for img_path in images:
                if process_pipeline(img_path):
                    success_count += 1
                progress.advance(task)

    elapsed = time.time() - start_time
    log.info(f"🏁 Vector Factory Session Complete!")
    log.info(f"📊 Yield: {success_count}/{total_images} vectors generated successfully in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    main()