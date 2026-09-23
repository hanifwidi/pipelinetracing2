# preprocess/morphology.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def apply_morphology(img_array: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """
    Executes Morphological Opening and Closing to clean up micro-artifacts.
    Opening removes small microscopic blobs (dust), and Closing fills in tiny 
    holes or gaps within solid color shapes.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        kernel_size (int): Size of the structuring element.
        
    Returns:
        np.ndarray: Cleaned RGB image array.
    """
    if not cfg.ENABLE_MORPHOLOGY:
        log.debug("Morphological operations are disabled in config. Skipping.")
        return img_array

    log.debug(f"Applying morphological filters (Kernel: {kernel_size}x{kernel_size})")
    
    try:
        # Create a rectangular structuring element
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        
        # Step 1: Morphological Opening (Erosion followed by Dilation)
        # Removes small objects from the foreground (assumes white background).
        # In a multi-color image, it disconnects weak bridges between shapes.
        opened_img = cv2.morphologyEx(img_array, cv2.MORPH_OPEN, kernel)
        
        # Step 2: Morphological Closing (Dilation followed by Erosion)
        # Fills small holes and closes gaps inside the color regions.
        closed_img = cv2.morphologyEx(opened_img, cv2.MORPH_CLOSE, kernel)
        
        log.debug("Morphological operations completed successfully.")
        return closed_img
        
    except Exception as e:
        log.error(f"Morphology operation failed: {str(e)}")
        return img_array