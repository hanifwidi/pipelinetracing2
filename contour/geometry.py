import cv2
import numpy as np
from utils.logger import log
from contour.contour_extract import extract_contours_by_color

def optimize_geometry_for_tracing(img_array: np.ndarray) -> np.ndarray:
    log.info("Running diagnostic geometry bypass...")
    h, w = img_array.shape[:2]
    
    pristine_canvas = np.ones((h, w, 3), dtype=np.uint8) * 255
    contours_dict = extract_contours_by_color(img_array)
    
    sorted_colors = sorted(contours_dict.keys(), key=lambda c: sum(cv2.contourArea(cnt) for cnt in contours_dict[c]), reverse=True)
    
    for color in sorted_colors:
        raw_contours = contours_dict[color]
        if raw_contours:
            # Bypass simplify, shape_cleanup, dan merge untuk membuktikan letak bug spasial.
            cv2.drawContours(pristine_canvas, raw_contours, -1, color, thickness=cv2.FILLED)
            
    # Ekspor langsung ke disk sebelum masuk VTracer.
    cv2.imwrite("diagnostic_canvas.png", cv2.cvtColor(pristine_canvas, cv2.COLOR_RGB2BGR))
    
    return pristine_canvas