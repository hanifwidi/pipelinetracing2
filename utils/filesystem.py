from pathlib import Path
from config import cfg

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

def setup_directories():
    for name in ("INPUT_FOLDER", "INPUT_PROCESSED_FOLDER", "OUTPUT_SVG_FOLDER", "OUTPUT_EPS_FOLDER", "PREVIEW_FOLDER", "TRACKING_FOLDER", "QUARANTINE_FOLDER", "LOG_DIR", "CACHE_DIR"):
        getattr(cfg, name).mkdir(parents=True, exist_ok=True)

def get_image_files(input_dir):
    input_dir = Path(input_dir).resolve()
    if not input_dir.is_dir():
        return []
    excluded = [getattr(cfg, name).resolve() for name in ("INPUT_PROCESSED_FOLDER", "OUTPUT_SVG_FOLDER", "OUTPUT_EPS_FOLDER", "PREVIEW_FOLDER", "TRACKING_FOLDER", "QUARANTINE_FOLDER", "CACHE_DIR")]
    excluded = [p for p in excluded if p != input_dir]
    return sorted(p.resolve() for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not any(p.resolve().is_relative_to(e) for e in excluded))
