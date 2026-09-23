# preprocess/remove_noise.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def reduce_noise(img_array: np.ndarray, kernel_size: int = None) -> np.ndarray:
    """
    Applies edge-preserving noise reduction. It combines Median Filtering to remove
    salt-and-pepper speckles and Bilateral Filtering to smooth flat color regions
    without blurring the sharp geometric boundaries.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        kernel_size (int, optional): Size of the filter kernel. Defaults to config.
        
    Returns:
        np.ndarray: Smoothed RGB image array.
    """
    # Use configuration default if not explicitly provided
    k_size = kernel_size if kernel_size else cfg.DENOISE_KERNEL_SIZE
    
    # Kernel size must be an odd number for OpenCV filters
    if k_size % 2 == 0:
        k_size += 1
        
    log.debug(f"Applying noise reduction (Kernel: {k_size}x{k_size})")
    
    try:
        # Step 1: Median Filter
        # Excellent for removing random isolated noisy pixels (salt and pepper noise)
        # that often occur after aggressive color quantization.
        median_filtered = cv2.medianBlur(img_array, k_size)
        
        # Step 2: Bilateral Filter
        # Highly effective at smoothing regions while keeping edges razor-sharp.
        # d=9, sigmaColor=75, sigmaSpace=75 are standard production values for vector prep.
        bilateral_filtered = cv2.bilateralFilter(
            median_filtered, 
            d=9, 
            sigmaColor=75, 
            sigmaSpace=75
        )
        
        log.debug("Noise reduction completed successfully.")
        return bilateral_filtered
        
    except Exception as e:
        log.error(f"Noise reduction failed: {str(e)}")
        # Return original image to prevent pipeline termination
        return img_array