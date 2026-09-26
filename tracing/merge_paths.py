"""Merge only adjacent, identically styled, provably disjoint simple paths.

Other paths are deliberately retained. Bounding boxes include Bezier control
points, giving conservative bounds; relative commands and arcs are not merged.
"""
from config import cfg
from utils.svg_tools import SVG_NS, parse_svg, path_tokens

def _bounds(d):
    tokens = path_tokens(d)
    if not tokens or tokens[0] != "M":
        return None
    points = []
    i = 0
    counts = {"M": 2, "L": 2, "C": 6, "Q": 4, "Z": 0}
    while i < len(tokens):
        cmd = tokens[i]
        if cmd not in counts:
            return None
        i += 1
        coords = []
        while i < len(tokens) and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
            coords.append(float(tokens[i])); i += 1
        size = counts[cmd]
        if (size and (not coords or len(coords) % size)) or (not size and coords):
            return None
        points.extend(zip(coords[::2], coords[1::2]))
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)

def merge_same_color_paths(tree):
    tree = parse_svg(tree)
    if not cfg.MERGE_ADJACENT_PATHS:
        return tree
    allowed = {"fill", "fill-rule", "stroke", "transform", "d"}
    for parent in list(tree.getroot().iter()):
        if parent.tag not in {f"{{{SVG_NS}}}svg", f"{{{SVG_NS}}}g"}:
            continue
        previous = None
        for current in list(parent):
            if current.tag != f"{{{SVG_NS}}}path" or set(current.attrib) - allowed or current.get("stroke", "none") != "none":
                previous = None; continue
            attrs = {k: v for k, v in current.attrib.items() if k != "d"}
            bounds = _bounds(current.get("d", ""))
            if previous is not None and bounds:
                old, old_attrs, old_bounds = previous
                if attrs == old_attrs and old_bounds:
                    a, b = old_bounds, bounds
                    disjoint = a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
                    if disjoint:
                        old.set("d", old.get("d") + " " + current.get("d"))
                        parent.remove(current)
                        previous = (old, attrs, (min(a[0],b[0]), min(a[1],b[1]), max(a[2],b[2]), max(a[3],b[3])))
                        continue
            previous = (current, attrs, bounds)
    return tree
