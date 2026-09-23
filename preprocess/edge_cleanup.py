# preprocess/edge_cleanup.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def cleanup_edges(img_array: np.ndarray) -> np.ndarray:
    """
    Enhances and sharpens regional boundaries to prevent "fuzzy" vectors during 
    the tracing phase. Uses a custom unsharp masking technique tailored for flat geometry.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        
    Returns:
        np.ndarray: Edge-sharpened RGB image array.
    """
    log.debug("Enhancing edge boundaries for crisp vector tracing.")
    
    try:
        # Create a Gaussian blur of the image
        # A large kernel helps isolate the general structure vs the micro-edges
        blurred = cv2.GaussianBlur(img_array, (5, 5), 0)
        
        # Unsharp Mask Formula: sharpened = original + (original - blurred) * amount
        # We use addWeighted to blend them securely within 8-bit limits
        # weight 1 = 1.5, weight 2 = -0.5 creates a moderate sharpening effect
        sharpened = cv2.addWeighted(img_array, 1.5, blurred, -0.5, 0)
        
        # Apply a very light bilateral filter one last time to ensure the sharpening
        # didn't introduce new noise inside the solid color bodies.
        final_polished = cv2.bilateralFilter(sharpened, d=5, sigmaColor=50, sigmaSpace=50)
        
        return final_polished
        
    except Exception as e:
        log.error(f"Edge cleanup failed: {str(e)}")
        return img_array