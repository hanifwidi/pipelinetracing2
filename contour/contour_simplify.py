# contour/contour_simplify.py
import cv2
import numpy as np
from typing import List
from config import cfg
from utils.logger import log

def simplify_contours(contours: List[np.ndarray], epsilon_factor: float = None) -> List[np.ndarray]:
    """
    Applies the Ramer-Douglas-Peucker algorithm to reduce the number of vertices 
    in a contour while preserving its core geometric shape.
    
    Args:
        contours (List[np.ndarray]): List of OpenCV contours.
        epsilon_factor (float): Precision parameter. Defaults to config.
        
    Returns:
        List[np.ndarray]: Simplified contours.
    """
    eps_factor = epsilon_factor if epsilon_factor is not None else cfg.EPSILON_FACTOR
    simplified = []
    
    for contour in contours:
        # Calculate the perimeter of the contour
        perimeter = cv2.arcLength(contour, closed=True)
        
        # Epsilon is the maximum distance from contour to approximated contour
        epsilon = eps_factor * perimeter
        
        # Approximate the polygon
        approx = cv2.approxPolyDP(contour, epsilon, closed=True)
        simplified.append(approx)
        
    return simplified