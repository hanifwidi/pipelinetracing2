"""Conservative precision cleanup without changing path order or transforms."""
from decimal import Decimal
from config import cfg
from utils.svg_tools import parse_svg, path_tokens, SVG_NS

def optimize_svg_tree(svg_xml_string):
    tree = parse_svg(svg_xml_string)
    for path in tree.getroot().iter(f"{{{SVG_NS}}}path"):
        if path.get("d"):
            path.set("d", _optimize_path_string(path.get("d"), cfg.SVG_PRECISION))
    return tree

def _optimize_path_string(d, precision):
    result = []
    for token in path_tokens(d):
        if len(token) == 1 and token.isalpha():
            result.append(token)
        else:
            value = round(Decimal(token), precision)
            result.append("0" if value == 0 else format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f"))
    return " ".join(result)
