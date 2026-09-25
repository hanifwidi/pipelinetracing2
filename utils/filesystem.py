# utils/filesystem.py
from pathlib import Path
from typing import List
from utils.logger import log
from config import cfg

# Define globally supported input formats
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

def setup_directories() -> None:
    """
    Validates and creates all necessary input, output, and cache directories
    defined in the configuration state.
    """
    directories = [
        cfg.INPUT_FOLDER,
        cfg.OUTPUT_SVG_FOLDER,
        cfg.OUTPUT_EPS_FOLDER,
        cfg.LOG_DIR,
        cfg.INPUT_PROCESSED_FOLDER,
        cfg.CACHE_DIR
    ]

    
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            log.debug(f"Validated directory footprint: {directory.resolve()}")
        except PermissionError:
            log.error(f"Permission denied when creating directory: {directory}")
            raise
        except Exception as e:
            log.error(f"Failed to create directory {directory}: {str(e)}")
            raise

def get_image_files(input_dir: Path) -> List[Path]:
    """
    Recursively scans the input directory for supported raster images.
    
    Args:
        input_dir (Path): The root directory to scan.
        
    Returns:
        List[Path]: A sorted list of absolute paths to discovered images.
    """
    if not input_dir.exists() or not input_dir.is_dir():
        log.error(f"Input directory is invalid or inaccessible: {input_dir.resolve()}")
        return []
        
    log.info(f"Scanning for raster images in: {input_dir.resolve()}")
    
    files = []
    # Iterate through all files recursively
    for path in input_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path.resolve())
            
    # Remove duplicates and sort for deterministic processing order
    unique_files = sorted(list(set(files)))
    
    if not unique_files:
        log.warning(f"No supported images {SUPPORTED_EXTENSIONS} found in {input_dir}")
    else:
        log.info(f"Discovered {len(unique_files)} valid image(s) for vectorization.")
        
    return unique_files