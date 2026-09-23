# contour/contour_extract.py
import cv2
import numpy as np
from typing import Dict, List, Tuple
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def extract_contours_by_color(img_array: np.ndarray) -> Dict[Tuple[int, int, int], List[np.ndarray]]:
    """
    Isolates each unique color in the image and extracts its topological contours.
    
    Args:
        img_array (np.ndarray): Preprocessed RGB image array.
        
    Returns:
        Dict: A mapping of RGB color tuples to a list of their respective OpenCV contours.
    """
    log.debug("Extracting topological contours per color region.")
    
    contours_dict = {}
    
    # Flatten the image to find unique RGB colors
    pixels = img_array.reshape(-1, 3)
    unique_colors = np.unique(pixels, axis=0)
    
    for color in unique_colors:
        color_tuple = tuple(int(c) for c in color)
        
        # Create a binary mask for the exact color
        mask = cv2.inRange(img_array, color, color)
        
        # RETR_EXTERNAL fetches only the outer boundaries, ignoring inner noise holes.
        # CHAIN_APPROX_SIMPLE compresses horizontal, vertical, and diagonal segments.
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            contours_dict[color_tuple] = list(contours)
            
    log.debug(f"Extracted contours for {len(contours_dict)} distinct colors.")
    return contours_dict