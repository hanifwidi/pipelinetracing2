"""Runtime defaults. CLI options override these values before workers start."""
import multiprocessing
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

@dataclass
class VectorFactoryConfig:
    INPUT_FOLDER: Path = Path("input")
    INPUT_PROCESSED_FOLDER: Path = Path("input_processed")
    OUTPUT_SVG_FOLDER: Path = Path("output_svg")
    OUTPUT_EPS_FOLDER: Path = Path("output_eps")
    PREVIEW_FOLDER: Path = Path("previews")
    TRACKING_FOLDER: Path = Path("tracking")
    QUARANTINE_FOLDER: Path = Path("quarantine")
    LOG_DIR: Path = Path("logs")
    CACHE_DIR: Path = Path("cache")
    USE_MULTIPROCESS: bool = True
    NUM_WORKERS: int = min(4, max(1, multiprocessing.cpu_count() - 1))
    METADATA_WORKERS: int = 1
    AI_REQUESTS_PER_MINUTE: int = 10
    AI_TIMEOUT: int = 30
    AI_RETRIES: int = 2
    AI_MAX_RETRY_WAIT: float = 180.0  # Total sleep budget per model/request.
    # Account-tested preference; environment variables override these defaults.
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_FALLBACK_MODELS: tuple = ("gemini-flash-latest", "gemini-3.7-flash")
    DEBUG_MODE: bool = False
    MAX_SIZE: int = 2048
    STRIP_CAPTIONS: bool = False
    GRID_ROWS: int = 4
    GRID_COLS: int = 4
    TARGET_MEGAPIXELS: float = 25.0
    MIN_MEGAPIXELS: float = 15.0
    MAX_MEGAPIXELS: float = 65.0
    MAX_FILE_MB: float = 45.0
    PREVIEW_WIDTH: int = 1024
    MAX_VISUAL_MAE: float = 0.10
    MAX_BBOX_DRIFT: float = 0.05
    OPTIMIZE_SVG: bool = True
    SVG_PRECISION: int = 3
    MERGE_ADJACENT_PATHS: bool = False
    REMOVE_DUPLICATE_NODES: bool = True
    EXPORT_EPS: bool = False
    INKSCAPE_PATH: str = "inkscape"
    # Retained for optional preprocessing modules, not all enabled in main.py.
    QUANTIZATION_METHOD: str = "kmeans"
    NUM_COLORS: int = 8
    DENOISE_KERNEL_SIZE: int = 5
    ENABLE_MORPHOLOGY: bool = True
    REMOVE_TEXT: bool = False
    OCR_LANGUAGES: List[str] = field(default_factory=lambda: ["en"])
    REMOVE_TINY_OBJECTS: bool = True
    MIN_COMPONENT_AREA: int = 25
    GEOMETRY_SIMPLIFICATION: str = "douglas_peucker"
    EPSILON_FACTOR: float = 0.002
    TRACE_MODE: str = "spline"
    VTRACER_COLOR_PRECISION: int = 6
    VTRACER_CORNER_THRESHOLD: int = 60
    VTRACER_SPECKLE_FILTERING: int = 4
    VTRACER_LAYER_DIFFERENCE: int = 16

cfg = VectorFactoryConfig()
