# contour/shape_cleanup.py
import cv2
import numpy as np
from typing import List
from utils.logger import log

def cleanup_invalid_shapes(contours: List[np.ndarray], min_points: int = 3) -> List[np.ndarray]:
    """
    Filters out invalid or collapsed geometries that would crash the SVG parser 
    or VTracer engine.
    
    Args:
        contours (List[np.ndarray]): List of simplified contours.
        min_points (int): Minimum vertices required to form a valid polygon.
        
    Returns:
        List[np.ndarray]: Validated contours.
    """
    valid_contours = []
    
    for contour in contours:
        # A valid polygon must have at least 'min_points' vertices
        if len(contour) >= min_points:
            # Additionally, ensure the contour has a non-zero area
            area = cv2.contourArea(contour)
            if area > 1.0:
                valid_contours.append(contour)
                
    return valid_contours