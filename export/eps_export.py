# export/eps_export.py
import subprocess
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def convert_svg_to_eps(svg_path: Path) -> bool:
    """
    Leverages the Inkscape CLI to convert the optimized SVG into a commercial-grade 
    EPS file suitable for Adobe Stock.
    
    Args:
        svg_path (Path): Path to the generated SVG file.
        
    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    if not cfg.EXPORT_EPS:
        return True
        
    output_eps = cfg.OUTPUT_EPS_FOLDER / f"{svg_path.stem}.eps"
    log.info(f"Initiating EPS conversion via Inkscape for: {output_eps.name}")
    
    # Standard Inkscape 1.0+ CLI arguments for EPS export
    command = [
        cfg.INKSCAPE_PATH,
        str(svg_path),
        "--export-type=eps",
        f"--export-filename={output_eps}"
    ]
    
    try:
        # Execute the command and capture output
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        log.debug(f"EPS conversion successful: {output_eps.name}")
        return True
        
    except FileNotFoundError:
        log.error("Inkscape executable not found. Ensure it is installed and in your system PATH.")
        # We return False but don't crash the pipeline, because the SVG is still valid.
        return False
        
    except subprocess.CalledProcessError as e:
        log.error(f"Inkscape failed to convert {svg_path.name}. Error: {e.stderr.strip()}")
        return False