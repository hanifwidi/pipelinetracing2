# export/ghostscript_export.py
import subprocess
import shutil
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def convert_svg_to_eps_ghostscript(svg_path: Path, eps_path: Path) -> bool:
    """
    Convert SVG ke EPS menggunakan Ghostscript (lebih cepat & stabil dari Inkscape).
    """
    # Check apakah Ghostscript tersedia
    gs_path = shutil.which("gs")
    if not gs_path:
        log.error("Ghostscript tidak ditemukan! Install dengan: brew install ghostscript")
        return False
    
    try:
        # Ghostscript command untuk convert SVG ke EPS
        command = [
            gs_path,
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=eps2write",  # Output EPS level 2
            f"-sOutputFile={eps_path}",
            str(svg_path)
        ]
        
        log.debug(f"Running Ghostscript: {' '.join(command)}")
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60  # Timeout 60 detik per file
        )
        
        if result.returncode != 0:
            log.error(f"Ghostscript failed: {result.stderr}")
            return False
        
        log.info(f"EPS generated via Ghostscript: {eps_path.name}")
        return True
        
    except subprocess.TimeoutExpired:
        log.error(f"Ghostscript timeout: {svg_path.name}")
        return False
    except Exception as e:
        log.error(f"Ghostscript error: {e}")
        return False