# utils/adaptive_tuner.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def analyze_image_complexity(img_array: np.ndarray) -> dict:
    """
    FIX: quantize dulu ke 8 warna sebelum hitung, supaya JPEG compression
    noise tidak dianggap "foto watercolor".
    """
    h, w = img_array.shape[:2]
    if max(h, w) > 512:
        scale = 512 / max(h, w)
        img_array = cv2.resize(img_array, (max(1, round(w*scale)), max(1, round(h*scale))), interpolation=cv2.INTER_AREA)
        h, w = img_array.shape[:2]

    # --- STEP 1: Hilangkan noise warna JPEG dengan quantize cepat ---
    # Reshape + kuantisasi ke 16 level per channel (4096 bucket) cukup
    # untuk membedakan warna solid dari noise kompresi.
    quant = (img_array // 16) * 16
    pixels_q = quant.reshape(-1, 3)
    unique_colors = len(np.unique(pixels_q, axis=0))

    # --- STEP 2: Edge density (tetap di gambar asli, tapi pakai threshold tinggi) ---
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 100, 200)  # threshold tinggi = abaikan noise
    edge_density = np.count_nonzero(edges) / (h * w)

    # --- STEP 3: Color variance di gambar yang sudah di-quantize ---
    color_variance = np.std(pixels_q, axis=0).mean()

    # --- STEP 4: Skor kompleksitas baru ---
    # Icon set solid: < 30 warna quantized, edge density rendah → SIMPLE
    # Ilustrasi organik: > 60 warna, edge density tinggi → COMPLEX
    complexity = min(100, (unique_colors * 1.5) + (edge_density * 800) + (color_variance * 0.3))

    result = {
        "color_count": unique_colors,
        "edge_density": edge_density,
        "color_variance": color_variance,
        "complexity_score": complexity,
    }
    log.info(f"Image analysis: {unique_colors} distinct colors (quantized), "
             f"edge density: {edge_density:.3f}, complexity: {complexity:.1f}/100")
    return result


def get_adaptive_vtracer_params(complexity_data: dict) -> dict:
    complexity = complexity_data["complexity_score"]
    color_count = complexity_data["color_count"]

    params = {
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
        "path_precision": 3,
    }

    # Icon set solid (quantized < 30 colors, complexity < 35)
    if complexity < 35 and color_count < 30:
        params["filter_speckle"] = 2
        params["corner_threshold"] = 60
        params["length_threshold"] = 2.0
        params["color_precision"] = 8
        log.info("Adaptive: Simple image (solid icon set)")

    elif complexity < 70:
        log.info("Adaptive: Medium complexity illustration")

    else:
        params["filter_speckle"] = 8
        params["corner_threshold"] = 50
        params["length_threshold"] = 6.0
        params["color_precision"] = 4
        params["layer_difference"] = 32
        log.info("Adaptive: Complex image (photo/watercolor)")

    return params
