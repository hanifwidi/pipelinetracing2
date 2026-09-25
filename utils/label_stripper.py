# utils/label_stripper.py
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def strip_captions(img_rgb: np.ndarray, rows: int = 4, cols: int = 4,
                   bottom_frac: float = 0.24, max_h_frac: float = 0.18) -> np.ndarray:
    """
    Hapus teks caption di bawah ikon per sel grid.
    Kriteria caption: komponen connected kecil, tinggi < max_h_frac sel,
    dan seluruhnya berada di pita bawah sel (bottom_frac).
    """
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)

    out = img_rgb.copy()
    cell_h, cell_w = h // rows, w // cols
    removed = 0

    for r in range(rows):
        for c in range(cols):
            y0, y1 = r * cell_h, (r + 1) * cell_h
            x0, x1 = c * cell_w, (c + 1) * cell_w
            cell_bin = binary[y0:y1, x0:x1]

            n, labels, stats, _ = cv2.connectedComponentsWithStats(cell_bin, connectivity=8)
            band_top = int(cell_h * (1 - bottom_frac))
            for i in range(1, n):
                x, y, cw, ch, area = stats[i]
                if (ch < cell_h * max_h_frac) and (y > band_top) and (y + ch <= cell_h) and area > 20:
                    mask = (labels == i)
                    out[y0:y1, x0:x1][mask] = [255, 255, 255]
                    removed += 1

    log.info(f"Label stripper: {removed} caption components removed")
    return out