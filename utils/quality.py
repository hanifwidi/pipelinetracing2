"""Technical checks plus a rendered comparison; passing is not Adobe approval."""
import math
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from config import cfg
from export.eps_export import find_inkscape
from utils.svg_tools import parse_svg, pixel_length, SVG_NS

def render_preview(svg_path, png_path, width=None):
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([find_inkscape(), str(svg_path), "--export-type=png", "--export-area-page", f"--export-width={width or cfg.PREVIEW_WIDTH}", f"--export-filename={png_path}"], capture_output=True, text=True, timeout=90)
    if result.returncode or not png_path.exists():
        raise RuntimeError("Preview rendering failed: " + result.stderr[-600:])
    with Image.open(png_path) as im:
        im.verify()
    return png_path

def _rgb(path, size=None):
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        rgb = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    if size:
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    return np.asarray(rgb, dtype=np.float32) / 255

def _bbox(array):
    ys, xs = np.where(np.min(array, axis=2) < 0.92)
    if not len(xs):
        return None
    h, w = array.shape[:2]
    return [float(xs.min()/w), float(ys.min()/h), float((xs.max()+1)/w), float((ys.max()+1)/h)]

def inspect_svg(svg_path, preview_path, reference_path):
    svg_path = Path(svg_path)
    root = parse_svg(svg_path.read_bytes()).getroot()
    width, height = pixel_length(root.get("width")), pixel_length(root.get("height"))
    mp = width * height / 1_000_000
    if not cfg.MIN_MEGAPIXELS <= mp <= cfg.MAX_MEGAPIXELS:
        raise ValueError(f"Artboard is {mp:.2f} MP, outside allowed range")
    if not root.get("viewBox"):
        raise ValueError("SVG viewBox is missing")
    if svg_path.stat().st_size > cfg.MAX_FILE_MB * 1_000_000:
        raise ValueError("SVG is too large")
    if list(root.iter(f"{{{SVG_NS}}}image")):
        raise ValueError("SVG contains raster images")
    if not list(root.iter(f"{{{SVG_NS}}}path")):
        raise ValueError("No vector paths in SVG")
    with Image.open(preview_path) as im:
        size = im.size
    actual, reference = _rgb(preview_path), _rgb(reference_path, size)
    mae = float(np.mean(np.abs(actual-reference)))
    a, b = _bbox(actual), _bbox(reference)
    drift = max(abs(x-y) for x, y in zip(a, b)) if a and b else 1.0
    warnings = []
    if not a or not b:
        warnings.append("Blank or nearly white artwork: inspect manually")
    if mae > cfg.MAX_VISUAL_MAE:
        warnings.append("Rendered colors/shapes differ substantially from the tracing input")
    if drift > cfg.MAX_BBOX_DRIFT:
        warnings.append("Artwork position or occupied area changed")
    if list(root.iter(f"{{{SVG_NS}}}text")):
        warnings.append("Live text found: inspect fonts/outlines")
    return {"passed": not warnings, "megapixels": round(mp, 4), "path_count": len(list(root.iter(f"{{{SVG_NS}}}path"))), "mae": round(mae, 6), "bbox_drift": round(drift, 6), "warnings": warnings}
