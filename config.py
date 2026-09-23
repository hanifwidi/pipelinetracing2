# config.py
import multiprocessing
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

@dataclass
class VectorFactoryConfig:
    """
    Central configuration state for the Vector Factory V2 Pipeline.
    All parameters are strictly typed and can be overridden via CLI.
    """
    
    # Project Structure Paths
    INPUT_FOLDER: Path = Path("input")
    OUTPUT_SVG_FOLDER: Path = Path("output_svg")
    OUTPUT_EPS_FOLDER: Path = Path("output_eps")
    LOG_DIR: Path = Path("logs")
    CACHE_DIR: Path = Path("cache")
    
    # System & Multiprocessing
    USE_MULTIPROCESS: bool = True
    NUM_WORKERS: int = multiprocessing.cpu_count()
    DEBUG_MODE: bool = False
    
    # Step 2: Resize Parameters
    MAX_SIZE: int = 2048
    
    # Step 3: Adaptive Color Quantization
    QUANTIZATION_METHOD: str = "kmeans"  # Options: kmeans, median_cut, octree
    NUM_COLORS: int = 8  # Supported: 4, 6, 8, 12, 16, 32
    
    # Step 4: Noise Reduction Parameters
    DENOISE_KERNEL_SIZE: int = 5
    ENABLE_MORPHOLOGY: bool = True
    
    # Step 5: Text Removal (OCR)
    REMOVE_TEXT: bool = False
    OCR_LANGUAGES: List[str] = field(default_factory=lambda: ['en'])
    
    # Step 6 & 7: Clean Up & Connected Components
    REMOVE_TINY_OBJECTS: bool = True
    MIN_COMPONENT_AREA: int = 25  # Minimum pixel area to retain
    
    # Step 8 & 9: Contour & Geometry Simplification
    GEOMETRY_SIMPLIFICATION: str = "douglas_peucker"
    EPSILON_FACTOR: float = 0.002
    
    # Step 10: VTracer Auto-Tuning Defaults (will be dynamically adjusted)
    TRACE_MODE: str = "spline"  # Options: spline, polygon
    VTRACER_COLOR_PRECISION: int = 6
    VTRACER_CORNER_THRESHOLD: int = 60
    VTRACER_SPECKLE_FILTERING: int = 4
    VTRACER_LAYER_DIFFERENCE: int = 16
    
    # Step 11 & 12: SVG Geometry Optimization
    SVG_PRECISION: int = 3
    MERGE_ADJACENT_PATHS: bool = True
    REMOVE_DUPLICATE_NODES: bool = True
    
    # Step 13: Export Pipeline
    EXPORT_EPS: bool = False
    INKSCAPE_PATH: str = "inkscape"  # Assumes inkscape is available in system PATH

# Instantiate global configuration state
cfg = VectorFactoryConfig()