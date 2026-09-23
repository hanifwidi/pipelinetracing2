# utils/adaptive_tuner.py
import cv2
import numpy as np
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def analyze_image_complexity(img_array: np.ndarray) -> dict:
    """
    Analisis kompleksitas gambar untuk menentukan parameter VTracer yang optimal.
    Returns: {color_count, edge_density, complexity_score}
    """
    h, w = img_array.shape[:2]
    
    # 1. Hitung jumlah warna unik
    pixels = img_array.reshape(-1, 3)
    unique_colors = len(np.unique(pixels, axis=0))
    
    # 2. Hitung edge density (kepadatan garis)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / (h * w)
    
    # 3. Hitung variance warna (indikator gradient)
    color_variance = np.std(pixels, axis=0).mean()
    
    # 4. Skor kompleksitas (0-100)
    # Warna banyak + edge padat + variance tinggi = kompleks
    complexity = min(100, (unique_colors * 0.3) + (edge_density * 500) + (color_variance * 0.5))
    
    result = {
        "color_count": unique_colors,
        "edge_density": edge_density,
        "color_variance": color_variance,
        "complexity_score": complexity
    }
    
    log.info(f"Image analysis: {unique_colors} colors, edge density: {edge_density:.3f}, complexity: {complexity:.1f}/100")
    return result


def get_adaptive_vtracer_params(complexity_data: dict) -> dict:
    """
    Generate parameter VTracer berdasarkan analisis kompleksitas gambar.
    """
    complexity = complexity_data["complexity_score"]
    color_count = complexity_data["color_count"]
    
    # Default parameters
    params = {
        "color_mode": "color",
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
    
    # ADAPTIVE TUNING LOGIC
    
    # Gambar simpel (logo, flat design, < 20 warna)
    if complexity < 30 or color_count < 20:
        params["filter_speckle"] = 2          # Kurangi filtering
        params["corner_threshold"] = 60       # Pertahankan sudut tajam
        params["length_threshold"] = 2.0      # Lebih detail
        params["color_precision"] = 8         # Lebih presisi
        log.info("Adaptive: Simple image detected (logo/flat design)")
    
    # Gambar medium (ilustrasi standar, 20-100 warna)
    elif complexity < 70:
        params["filter_speckle"] = 4
        params["corner_threshold"] = 60
        params["length_threshold"] = 4.5
        params["color_precision"] = 6
        log.info("Adaptive: Medium complexity illustration")
    
    # Gambar kompleks (foto, cat air, > 100 warna, banyak gradient)
    else:
        params["filter_speckle"] = 8          # Lebih agresif filter noise
        params["corner_threshold"] = 50       # Lebih smooth curves
        params["length_threshold"] = 6.0      # Kurangi detail kecil
        params["color_precision"] = 4         # Toleransi warna lebih besar
        params["layer_difference"] = 32       # Merge layer yang mirip
        log.info("Adaptive: Complex image (photo/watercolor) - aggressive smoothing")
    
    return params