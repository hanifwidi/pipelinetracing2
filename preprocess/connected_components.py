# preprocess/connected_components.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def remove_tiny_objects(img_array: np.ndarray, min_area: int = None) -> np.ndarray:
    """
    Identifies and removes microscopic blobs (dust/noise) that are isolated from 
    main color bodies. Uses Connected Components analysis and seamless inpainting.
    
    Args:
        img_array (np.ndarray): Input RGB image array (usually quantized).
        min_area (int, optional): Minimum pixel area to keep. Defaults to config.
        
    Returns:
        np.ndarray: Cleaned RGB image array.
    """
    area_threshold = min_area if min_area is not None else cfg.MIN_COMPONENT_AREA
    
    if not cfg.REMOVE_TINY_OBJECTS:
        log.debug("Tiny object removal is disabled in config. Skipping.")
        return img_array

    log.debug(f"Scanning for microscopic dust and blobs (Area < {area_threshold}px)")
    
    try:
        # Create a unified mask to collect all "dust" pixels across all colors
        h, w = img_array.shape[:2]
        global_dust_mask = np.zeros((h, w), dtype=np.uint8)
        
        # Get unique colors in the quantized image
        # Using reshape to process as a list of RGB pixels
        pixels = img_array.reshape(-1, 3)
        unique_colors = np.unique(pixels, axis=0)
        
        for color in unique_colors:
            # Create a binary mask for the current color
            color_mask = cv2.inRange(img_array, color, color)
            
            # Run Connected Components analysis
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(color_mask, connectivity=8)
            
            # Start from 1 to skip the background (label 0)
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area < area_threshold:
                    # Add this tiny blob to our global dust mask
                    global_dust_mask[labels == i] = 255
                    
        # If no dust was found, return early
        if cv2.countNonZero(global_dust_mask) == 0:
            log.debug("No microscopic blobs found.")
            return img_array
            
        # Dilate the dust mask slightly to ensure clean inpainting
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated_mask = cv2.dilate(global_dust_mask, kernel, iterations=1)
        
        # Inpaint the dust using the surrounding colors (Telea algorithm is faster for small blobs)
        cleaned_img = cv2.inpaint(img_array, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        
        log.debug("Successfully scrubbed microscopic artifacts.")
        return cleaned_img
        
    except Exception as e:
        log.error(f"Failed to remove tiny objects: {str(e)}")
        return img_array