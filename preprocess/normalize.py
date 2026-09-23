# preprocess/normalize.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def normalize_image(img_array: np.ndarray, clip_limit: float = 2.0, tile_grid_size: tuple = (8, 8)) -> np.ndarray:
    """
    Applies Contrast Limited Adaptive Histogram Equalization (CLAHE) to the LAB color space.
    This enhances edge definition and normalizes lighting without shifting core colors.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        clip_limit (float): Threshold for contrast limiting.
        tile_grid_size (tuple): Grid size for adaptive histogram equalization.
        
    Returns:
        np.ndarray: Contrast-normalized RGB image array.
    """
    try:
        # Convert RGB to LAB color space to isolate luminosity (L channel)
        lab_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab_img)
        
        # Apply CLAHE only to the Luminosity channel
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        cl = clahe.apply(l_channel)
        
        # Merge back and convert to RGB
        merged_lab = cv2.merge((cl, a_channel, b_channel))
        normalized_rgb = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2RGB)
        
        log.debug("Successfully applied CLAHE normalization.")
        return normalized_rgb
        
    except Exception as e:
        log.error(f"Failed to normalize image: {str(e)}")
        # In case of failure, return the original image to prevent pipeline crash
        return img_array