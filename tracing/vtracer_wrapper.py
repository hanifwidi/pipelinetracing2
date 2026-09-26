# tracing/vtracer_wrapper.py
import os
import tempfile
import cv2
import numpy as np
import vtracer
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

# tracing/vtracer_wrapper.py (TAMBAHKAN INI)

@benchmark
def trace_image_to_svg(img_array: np.ndarray, custom_params: dict = None) -> str:
    """
    MODIFIED: Sekarang menerima custom_params dari adaptive tuner.
    """
    log.info("Initiating VTracer vectorization engine...")

    temp_dir = cfg.CACHE_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)

    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".png", delete=False) as temp_in:
        input_path = temp_in.name

    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".svg", delete=False) as temp_out:
        output_path = temp_out.name

    try:
        ok, encoded_img = cv2.imencode('.png', img_bgr)
        if not ok:
            raise ValueError('Could not encode tracing input')
        encoded_img.tofile(input_path)


        # GUNAKAN custom_params jika ada, otherwise pakai default
        params = custom_params or {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 60,
            "length_threshold": 4.5,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3
        }

        vtracer.convert_image_to_svg_py(
            input_path,
            output_path,
            **params  # Spread parameters
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        return svg_content

    finally:
        # Cleanup temp files
        for path in [input_path, output_path]:
            try:
                os.unlink(path)
            except:
                pass
