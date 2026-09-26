from pathlib import Path
from config import cfg
from utils.atomic_io import atomic_write
from utils.svg_tools import serialize_svg

def save_svg(svg_data, original_filename, output_path=None):
    target = Path(output_path) if output_path else cfg.OUTPUT_SVG_FOLDER / Path(original_filename).with_suffix(".svg").name
    atomic_write(target, serialize_svg(svg_data))
    return target
