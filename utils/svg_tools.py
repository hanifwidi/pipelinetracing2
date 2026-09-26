"""Strict SVG serialization and aspect-preserving artboard sizing."""
import math
import re
from lxml import etree
from config import cfg

SVG_NS = "http://www.w3.org/2000/svg"
ICON_TYPES = ("icon", "icon-sheet")
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
TOKEN = re.compile(rf"[AaCcHhLlMmQqSsTtVvZz]|{NUMBER}")

def parse_svg(value):
    if isinstance(value, etree._ElementTree):
        return value
    if isinstance(value, etree._Element):
        return etree.ElementTree(value)
    data = value.encode("utf-8") if isinstance(value, str) else value
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser)
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("Document root must be an SVG element")
    return etree.ElementTree(root)

def serialize_svg(value):
    return etree.tostring(parse_svg(value), xml_declaration=True, encoding="utf-8")

def pixel_length(value):
    match = re.fullmatch(rf"\s*({NUMBER})\s*(px|pt|pc|in|cm|mm)?\s*", value or "")
    if not match:
        raise ValueError(f"Unsupported SVG dimension: {value!r}")
    factor = {None: 1, "px": 1, "pt": 96/72, "pc": 16, "in": 96, "cm": 96/2.54, "mm": 96/25.4}
    number = float(match[1]) * factor[match[2]]
    if not math.isfinite(number) or number <= 0:
        raise ValueError("SVG dimensions must be finite and positive")
    return number

def harden_for_adobe(value, target_mp=None, asset_type=None):
    tree = parse_svg(value)
    root = tree.getroot()
    target = cfg.TARGET_MEGAPIXELS if target_mp is None else target_mp
    asset_type = asset_type or cfg.ASSET_TYPE
    if not math.isfinite(target) or target <= 0:
        raise ValueError("Target artboard area must be positive and finite")
    if asset_type in ICON_TYPES:
        if target > cfg.ICON_MAX_SIZE ** 2 / 1_000_000:
            raise ValueError("Icon artboard target must not exceed 16 MP")
    elif not cfg.MIN_MEGAPIXELS <= target <= cfg.MAX_MEGAPIXELS:
        raise ValueError("Target artboard must be between 15 and 65 megapixels")
    if root.get("viewBox"):
        bounds = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox").strip())]
        if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds) or min(bounds[2:]) <= 0:
            raise ValueError("Invalid SVG viewBox")
    else:
        bounds = [0, 0, pixel_length(root.get("width")), pixel_length(root.get("height"))]
    width, height = bounds[2:]
    if max(width, height) / min(width, height) > 1000:
        raise ValueError("Extreme SVG aspect ratio requires manual review")
    scale = math.sqrt(target * 1_000_000 / (width * height))
    if asset_type in ICON_TYPES:
        scale = min(scale, cfg.ICON_MAX_SIZE / max(width, height))
    out_w, out_h = max(1, round(width * scale)), max(1, round(height * scale))
    if asset_type in ICON_TYPES:
        minimum = cfg.ICON_SHEET_MIN_SIZE if asset_type == "icon-sheet" else cfg.ICON_MIN_SIZE
        if min(out_w, out_h) < minimum:
            raise ValueError(f"{asset_type} artboard sides must be {minimum}-4000px; review aspect ratio/target")
    else:
        # Rounding at the exact 15/65 MP boundary must not violate the bounds.
        while out_w * out_h < cfg.MIN_MEGAPIXELS * 1_000_000:
            out_w += 1
        while out_w * out_h > cfg.MAX_MEGAPIXELS * 1_000_000:
            out_w -= 1
    root.set("viewBox", " ".join(format(v, ".12g") for v in bounds))
    root.set("width", str(out_w))
    root.set("height", str(out_h))
    root.set("preserveAspectRatio", "xMidYMid meet")
    root.set("shape-rendering", "geometricPrecision")
    return serialize_svg(tree).decode("utf-8")

def path_tokens(path):
    tokens = TOKEN.findall(path)
    if re.sub(r"[\s,]+", "", TOKEN.sub("", path)):
        raise ValueError("Invalid SVG path token")
    return tokens
