from pathlib import Path
import cv2
import numpy as np
from utils.benchmark import benchmark

@benchmark
def resize_image(image_path: Path, max_dimension=2048):
    if max_dimension < 1:
        raise ValueError("max_dimension must be positive")
    data = np.fromfile(str(image_path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Unreadable image: {image_path}")
    if img.dtype != np.uint8:
        img = (img.astype(np.float64) * 255 / np.iinfo(img.dtype).max).astype(np.uint8)
    if img.ndim == 2:
        rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        rgb = np.rint(img[:, :, :3][:, :, ::-1] * alpha + 255 * (1-alpha)).astype(np.uint8)
    else:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    scale = min(1, max_dimension / max(h, w))
    if scale < 1:
        rgb = cv2.resize(rgb, (max(1, round(w*scale)), max(1, round(h*scale))), interpolation=cv2.INTER_AREA)
    return rgb
