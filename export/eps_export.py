"""Inkscape is the SVG interpreter; Ghostscript validates the resulting EPS."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from config import cfg
from utils.logger import log
from utils.svg_tools import harden_for_adobe, parse_svg, pixel_length, serialize_svg, ICON_TYPES

def find_inkscape():
    for candidate in [cfg.INKSCAPE_PATH, shutil.which("inkscape"), "/Applications/Inkscape.app/Contents/MacOS/inkscape"]:
        if candidate and (shutil.which(str(candidate)) or Path(candidate).is_file()):
            return shutil.which(str(candidate)) or str(candidate)
    raise RuntimeError("Inkscape CLI is required. Install Inkscape or set INKSCAPE_PATH in config.py.")

def validate_eps(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 30:
        raise ValueError("EPS output is missing or empty")
    head = path.read_bytes()[:8192]
    if not head.startswith(b"%!PS-Adobe-") or b"EPSF" not in head.splitlines()[0]:
        raise ValueError("Output is not an EPS document")
    bounds = re.search(rb"%%BoundingBox:\s*([-\d]+)\s+([-\d]+)\s+([-\d]+)\s+([-\d]+)", head)
    if not bounds or int(bounds[3]) <= int(bounds[1]) or int(bounds[4]) <= int(bounds[2]):
        raise ValueError("EPS has no valid bounding box")
    width, height = int(bounds[3]) - int(bounds[1]), int(bounds[4]) - int(bounds[2])
    area = width * height / 1_000_000
    if cfg.ASSET_TYPE in ICON_TYPES:
        minimum = cfg.ICON_SHEET_MIN_SIZE if cfg.ASSET_TYPE == "icon-sheet" else cfg.ICON_MIN_SIZE
        if not all(minimum <= side <= cfg.ICON_MAX_SIZE for side in (width, height)):
            raise ValueError(f"EPS icon artboard sides must be {minimum}-{cfg.ICON_MAX_SIZE} points")
    elif not cfg.MIN_MEGAPIXELS <= area <= cfg.MAX_MEGAPIXELS:
        raise ValueError(f"EPS artboard is {area:.2f} MP in PostScript points")
    gs = shutil.which("gs") or shutil.which("gswin64c")
    if gs:
        result = subprocess.run([gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=nullpage", str(path)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise ValueError("EPS interpreter validation failed: " + (result.stdout + result.stderr)[-600:])
    return True

def _preserve_icon_artboard(path, width, height):
    """Cairo can crop EPS DSC bounds to ink, even with export-area-page."""
    data = Path(path).read_bytes()
    bounds = re.search(rb"^%%BoundingBox: ([\d-]+) ([\d-]+) ([\d-]+) ([\d-]+)$", data, re.MULTILINE)
    if not bounds:
        raise ValueError("EPS bounding box is missing")
    left, bottom, right, top = map(int, bounds.groups())
    if left < -1 or bottom < -1 or right > width + 1 or top > height + 1:
        raise ValueError("EPS artwork extends outside the intended icon artboard")
    # Expand only the declared canvas; do not add a painted background or alter paths.
    for key in ("BoundingBox", "PageBoundingBox", "HiResBoundingBox"):
        pattern = rb"^%%" + key.encode("ascii") + rb":[^\r\n]+"
        replacement = f"%%{key}: 0 0 {width} {height}".encode("ascii")
        data = re.sub(pattern, replacement, data, flags=re.MULTILINE)
    Path(path).write_bytes(data)

def convert_svg_to_eps(svg_path, eps_path=None):
    svg_path = Path(svg_path)
    eps_path = Path(eps_path) if eps_path else cfg.OUTPUT_EPS_FOLDER / (svg_path.stem + ".eps")
    eps_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".eps", dir=eps_path.parent)
    os.close(fd)
    prepared = Path(tmp).with_suffix(".svg")
    try:
        # SVG pixels are 1/96 inch; EPS points are 1/72 inch. Preserve the
        # requested numeric artboard dimensions in EPS/Illustrator points.
        tree = parse_svg(harden_for_adobe(svg_path.read_bytes()))
        root = tree.getroot()
        width, height = round(pixel_length(root.get("width"))), round(pixel_length(root.get("height")))
        root.set("width", format(pixel_length(root.get("width")), ".12g") + "pt")
        root.set("height", format(pixel_length(root.get("height")), ".12g") + "pt")
        prepared.write_bytes(serialize_svg(tree))
        result = subprocess.run([find_inkscape(), str(prepared), "--export-type=eps", "--export-area-page", f"--export-filename={tmp}"], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Inkscape EPS conversion failed")
        if cfg.ASSET_TYPE in ICON_TYPES:
            _preserve_icon_artboard(tmp, width, height)
        validate_eps(tmp)
        if Path(tmp).stat().st_size > cfg.MAX_FILE_MB * 1_000_000:
            raise ValueError("EPS exceeds the configured maximum file size")
        os.replace(tmp, eps_path)
        return True
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        log.error("EPS conversion failed for %s: %s", svg_path.name, exc)
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)
        prepared.unlink(missing_ok=True)
