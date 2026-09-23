# preprocess/resize.py
import cv2
import numpy as np
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def resize_image(image_path: Path, max_dimension: int = 2048) -> np.ndarray:
    """
    Loads an image safely bypassing Windows Unicode issues and resizes it.
    """
    # BYPASS WINDOWS ENCODING BUG
    try:
        img_array = np.fromfile(str(image_path), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        log.error(f"Failed to read file via numpy storage: {str(e)}")
        img = None
    
    if img is None:
        log.error(f"OpenCV failed to decode image: {image_path}")
        raise FileNotFoundError(f"Corrupt or unreadable image: {image_path}")
    
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    height, width = img_rgb.shape[:2]
    
    if width > max_dimension or height > max_dimension:
        if width > height:
            new_width = max_dimension
            new_height = int(max_dimension * (height / width))
        else:
            new_height = max_dimension
            new_width = int(max_dimension * (width / height))
            
        log.debug(f"Resizing {image_path.name} from {width}x{height} to {new_width}x{new_height}")
        img_rgb = cv2.resize(img_rgb, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    else:
        log.debug(f"Image {image_path.name} ({width}x{height}) is within limits. Skipping resize.")
        
    return img_rgb