# preprocess/remove_text.py
import cv2
import numpy as np
import easyocr
from typing import List
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

# Initialize the EasyOCR reader globally within this module to avoid reloading
# the heavy PyTorch model for every single image.
try:
    log.debug(f"Initializing EasyOCR with languages: {cfg.OCR_LANGUAGES}")
    reader = easyocr.Reader(cfg.OCR_LANGUAGES, gpu=True) # Set gpu=True if CUDA is configured
except Exception as e:
    log.error(f"Failed to initialize EasyOCR: {e}")
    reader = None

@benchmark
def remove_text(img_array: np.ndarray) -> np.ndarray:
    """
    Detects text elements within the image using OCR and removes them seamlessly
    using Navier-Stokes based image inpainting.
    
    Args:
        img_array (np.ndarray): Input RGB image array.
        
    Returns:
        np.ndarray: Image array with text detected and inpainted.
    """
    if reader is None:
        log.warning("OCR Reader is not initialized. Skipping text removal.")
        return img_array

    log.debug("Scanning image for text/watermarks...")
    
    # EasyOCR expects BGR or grayscale for optimal detection, but handles RGB well.
    # We pass the raw numpy array directly.
    results = reader.readtext(img_array)
    
    if not results:
        log.debug("No text detected in the image.")
        return img_array
        
    log.info(f"Detected {len(results)} text region(s). Applying inpainting.")
    
    # Create an empty mask with the same dimensions as the image
    h, w = img_array.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    
   # Tambahkan filter confidence (misal: hanya hapus jika AI yakin > 0.8)
    for (bbox, text, prob) in results:
        if prob < 0.8:  # Abaikan deteksi yang tidak yakin
            continue
        
        pts = np.array(bbox, dtype=np.int32)
        cv2.fillPoly(mask, [pts], (255))
        log.debug(f"Masked text: '{text}' (Confidence: {prob:.2f})")
    
    # Dilate the mask slightly to ensure we capture the antialiased edges of the text
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated_mask = cv2.dilate(mask, kernel, iterations=1)
    
    # Apply Inpainting
    # INPAINT_NS uses Navier-Stokes fluid dynamics equations to fill the masked area smoothly
    inpainted_img = cv2.inpaint(img_array, dilated_mask, inpaintRadius=5, flags=cv2.INPAINT_NS)
    
    return inpainted_img