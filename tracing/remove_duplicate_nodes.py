from config import cfg
from utils.svg_tools import parse_svg, path_tokens, SVG_NS

def clean_duplicate_nodes(tree):
    tree = parse_svg(tree)
    if not cfg.REMOVE_DUPLICATE_NODES:
        return tree
    for path in tree.getroot().iter(f"{{{SVG_NS}}}path"):
        tokens = path_tokens(path.get("d", ""))
        chunks = []
        for token in tokens:
            if len(token) == 1 and token.isalpha():
                chunks.append([token])
            elif chunks:
                chunks[-1].append(token)
        cleaned = []
        for chunk in chunks:
            if chunk[0] == "L" and len(chunk) == 3 and cleaned and chunk == cleaned[-1]:
                continue
            cleaned.append(chunk)
        path.set("d", " ".join(t for chunk in cleaned for t in chunk))
    return tree
