# contour/contour_merge.py
import numpy as np
from typing import List
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.errors import TopologicalError
from utils.logger import log

def merge_overlapping_contours(contours: List[np.ndarray]) -> List[np.ndarray]:
    """
    Converts OpenCV contours to Shapely Polygons, computes their Boolean Union 
    to merge overlaps, and converts them back to OpenCV format.
    
    Args:
        contours (List[np.ndarray]): Validated contours.
        
    Returns:
        List[np.ndarray]: Merged, non-overlapping contours.
    """
    polygons = []
    
    # Convert cv2 contours to Shapely Polygons
    for contour in contours:
        if len(contour) >= 3:
            # Flatten cv2 format (N, 1, 2) to (N, 2)
            pts = contour.reshape(-1, 2)
            try:
                poly = Polygon(pts)
                if poly.is_valid:
                    polygons.append(poly)
                else:
                    # Attempt to fix invalid self-intersecting polygons
                    poly = poly.buffer(0)
                    if poly.is_valid:
                        polygons.append(poly)
            except Exception as e:
                pass # Ignore completely broken geometries

    if not polygons:
        return []

    try:
        # Perform Boolean Union to fuse all overlapping/touching polygons
        merged = unary_union(polygons)
    except TopologicalError as e:
        log.warning(f"Topological error during polygon merge: {e}")
        return contours # Fallback to original if shapely fails

    # Extract coordinates back to cv2 contour format
    merged_contours = []
    
    # unary_union can return a single Polygon or a MultiPolygon
    geometries = [merged] if merged.geom_type == 'Polygon' else merged.geoms
    
    for geom in geometries:
        # Extract the exterior shell coordinates
        coords = np.array(geom.exterior.coords, dtype=np.int32)
        # Reshape to cv2 contour expected shape (N, 1, 2)
        cv_contour = coords.reshape((-1, 1, 2))
        merged_contours.append(cv_contour)
        
    return merged_contours