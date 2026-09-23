# preprocess/quantization.py
import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def quantize_colors(img_array: np.ndarray, num_colors: int = 8, method: str = "kmeans") -> np.ndarray:
    """
    Reduces the number of colors in an image to create flat, solid regions.
    This is critical for clean vector tracing and reducing SVG node counts.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        num_colors (int): Target number of colors for the palette.
        method (str): Quantization algorithm ('kmeans' is currently supported).
        
    Returns:
        np.ndarray: Quantized RGB image array.
    """
    log.debug(f"Starting color quantization (Target: {num_colors} colors, Method: {method})")
    
    # Reshape the image to a 2D array of pixels (rows x columns, 3 color channels)
    h, w, c = img_array.shape
    pixel_data = img_array.reshape((-1, 3)).astype(np.float32)
    
    if method.lower() == "kmeans":
        # MiniBatchKMeans is significantly faster for large image arrays
        kmeans = MiniBatchKMeans(
            n_clusters=num_colors,
            random_state=42,
            batch_size=2048,
            n_init="auto",
            max_iter=100
        )
        
        # Perform clustering
        labels = kmeans.fit_predict(pixel_data)
        centers = kmeans.cluster_centers_.astype(np.uint8)
        
        # Map each pixel to its corresponding cluster center color
        quantized_pixels = centers[labels]
        quantized_img = quantized_pixels.reshape((h, w, c))
        
        log.debug("K-Means clustering completed successfully.")
        return quantized_img
        
    else:
        log.warning(f"Quantization method '{method}' is not implemented. Returning original image.")
        return img_array