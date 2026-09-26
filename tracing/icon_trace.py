"""Opt-in white-paper icons: trace each flat ink mask with real holes."""
import numpy as np
from lxml import etree
from tracing.vtracer_wrapper import trace_image_to_svg
from utils.svg_tools import SVG_NS, parse_svg, serialize_svg


class IconSourceNeedsReview(ValueError):
    pass


def trace_icon_source(image, analysis, params):
    if not analysis["white_background"]:
        raise IconSourceNeedsReview("Icon mode requires a plain white background and clear margins")
    if not analysis["flat_palette"]:
        raise IconSourceNeedsReview("Icon palette is not reliably flat; preserve the artwork for manual review")
    colors = [c for c in analysis["palette"] if not (min(c) >= 245 and max(c) - min(c) <= 10)]
    if not colors:
        raise IconSourceNeedsReview("No visible icon foreground")
    if any(min(c) >= 220 for c in colors):
        raise IconSourceNeedsReview("Near-white icon details are ambiguous; review intended white parts")
    palette = np.asarray([[255, 255, 255], *colors], dtype=np.float32)
    h, w = image.shape[:2]
    labels = np.zeros((h, w), dtype=np.uint8)
    for y in range(0, h, 128):
        tile = image[y:y + 128].astype(np.float32)
        distances = np.sum((tile[:, :, None, :] - palette) ** 2, axis=3)
        labels[y:y + 128] = np.argmin(distances, axis=2)
    expected_alpha = np.where(labels != 0, 255, 0).astype(np.uint8)
    root = etree.Element(f"{{{SVG_NS}}}svg", nsmap={None: SVG_NS},
                         width=str(w), height=str(h), viewBox=f"0 0 {w} {h}")
    binary_params = {**params, "colormode": "binary", "mode": "spline",
                     "filter_speckle": 2, "length_threshold": 2.0,
                     "corner_threshold": 60, "path_precision": 4}
    for idx, color in enumerate(colors, start=1):
        if not np.any(labels == idx):
            continue
        mask = np.repeat(np.where(labels == idx, 0, 255).astype(np.uint8)[:, :, None], 3, axis=2)
        traced = parse_svg(trace_image_to_svg(mask, binary_params)).getroot()
        fill = "#" + "".join(f"{v:02X}" for v in color)
        for path in traced.findall(f"{{{SVG_NS}}}path"):
            # Binary VTracer emits interior contours in the same path.
            path.set("fill", fill)
            path.set("fill-rule", "evenodd")
            root.append(path)
    if not len(root):
        raise IconSourceNeedsReview("No icon paths survived tracing")
    return serialize_svg(root).decode("utf-8"), expected_alpha
