"""Estimate palette complexity from interiors, not JPEG/antialias edge colors."""
import cv2
import numpy as np
from utils.logger import log
from utils.benchmark import benchmark

PALETTE_DISTANCE = 12.0
MAX_FLAT_COLORS = 9  # Includes the source background.


def _palette(pixels):
    """Deterministic weighted color clustering on at most 32768 RGB buckets."""
    buckets, inverse, counts = np.unique(pixels // 8, axis=0,
                                        return_inverse=True, return_counts=True)
    means = np.column_stack([np.bincount(inverse, weights=pixels[:, c]) / counts
                             for c in range(3)])
    centers, weights = [], []
    for idx in np.argsort(-counts, kind="stable"):
        color, count = means[idx], int(counts[idx])
        if centers:
            distances = np.sum((np.asarray(centers) - color) ** 2, axis=1)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= PALETTE_DISTANCE ** 2:
                weight = weights[nearest]
                centers[nearest] = (centers[nearest] * weight + color * count) / (weight + count)
                weights[nearest] += count
                continue
        if len(centers) < 128:
            centers.append(color)
            weights.append(count)
    order = np.argsort(-np.asarray(weights), kind="stable")
    return np.asarray(centers)[order], np.asarray(weights)[order], len(buckets)


def _distances(pixels, palette):
    best = np.full(len(pixels), np.inf, dtype=np.float32)
    for color in palette:
        best = np.minimum(best, np.sum((pixels.astype(np.float32) - color) ** 2, axis=1))
    return np.sqrt(best)


@benchmark
def analyze_image_complexity(img_array: np.ndarray) -> dict:
    h, w = img_array.shape[:2]
    scale = min(1, 512 / max(h, w))
    sample = cv2.resize(img_array, (max(1, round(w * scale)), max(1, round(h * scale))),
                        interpolation=cv2.INTER_AREA) if scale < 1 else img_array
    gray = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    edge_density = float(np.count_nonzero(edges) / gray.size)
    interior = cv2.dilate(edges, np.ones((3, 3), np.uint8)) == 0
    pixels = sample[interior]
    if len(pixels) < 16:
        pixels = sample.reshape(-1, 3)
    centers, counts, raw_count = _palette(pixels)
    significant = counts >= max(3, len(pixels) * 0.00002)
    if not np.any(significant):
        significant[0] = True
    count = int(np.count_nonzero(significant))
    palette = centers[significant][:MAX_FLAT_COLORS]
    coverage = float(counts[significant][:MAX_FLAT_COLORS].sum() / len(pixels))
    residual = _distances(pixels, palette)
    border = np.concatenate((sample[0], sample[-1], sample[:, 0], sample[:, -1]))
    white_border = (np.min(border, axis=1) >= 245) & (np.ptp(border, axis=1) <= 10)
    white_background = bool(np.mean(white_border) >= 0.98)
    # A tiny photo on mostly white paper still has a complex foreground.
    foreground = np.linalg.norm(pixels.astype(np.float32) - 255, axis=1) > 30
    detail_residual = residual[foreground] if np.any(foreground) else residual
    foreground_coverage = float(np.mean(detail_residual <= PALETTE_DISTANCE))
    residual_p95 = float(np.percentile(detail_residual, 95))
    flat = bool(count <= MAX_FLAT_COLORS and coverage >= 0.995
                and foreground_coverage >= 0.98 and residual_p95 <= PALETTE_DISTANCE
                and edge_density < 0.12)
    # Contrast between two intentional colors is not photographic complexity.
    score = min(100.0, count * 4.0 + edge_density * 250
                + (1 - foreground_coverage) * 80)
    result = {
        "color_count": count, "raw_bucket_count": raw_count,
        "edge_density": edge_density, "complexity_score": score,
        "flat_palette": flat, "palette_coverage": coverage,
        "foreground_coverage": foreground_coverage,
        "residual_p95": residual_p95, "white_background": white_background,
        "palette": np.clip(np.rint(palette), 0, 255).astype(np.uint8).tolist(),
    }
    log.info("Image analysis: %d palette colors, edge density %.3f, complexity %.1f/100; flat=%s",
             count, edge_density, score, flat)
    return result


def get_adaptive_vtracer_params(complexity_data: dict) -> dict:
    score = complexity_data["complexity_score"]
    params = {
        "colormode": "color", "hierarchical": "stacked", "mode": "spline",
        "filter_speckle": 4, "color_precision": 6, "layer_difference": 16,
        "corner_threshold": 60, "length_threshold": 4.5, "max_iterations": 10,
        "splice_threshold": 45, "path_precision": 3,
    }
    if complexity_data.get("flat_palette") or score < 35:
        params.update(filter_speckle=2, length_threshold=2.0, color_precision=6)
        log.info("Adaptive: Simple artwork (limited flat palette)")
    elif score < 70:
        log.info("Adaptive: Medium complexity illustration")
    else:
        params.update(filter_speckle=8, corner_threshold=50, length_threshold=6.0,
                      color_precision=4, layer_difference=32)
        log.info("Adaptive: Complex or textured artwork")
    return params
