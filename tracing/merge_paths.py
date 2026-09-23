# tracing/merge_paths.py
from lxml import etree
from collections import defaultdict
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def merge_same_color_paths(tree: etree._ElementTree) -> etree._ElementTree:
    """
    Scans the SVG document for paths sharing the exact same fill color and 
    concatenates their geometry data ('d' attributes) into a single compound path.
    This drastically reduces DOM size and improves editability in Adobe Illustrator.
    
    Args:
        tree (etree._ElementTree): The parsed SVG XML tree.
        
    Returns:
        etree._ElementTree: The optimized tree with merged paths.
    """
    if not cfg.MERGE_ADJACENT_PATHS:
        return tree

    log.debug("Executing compound path merging by color signature.")
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    # Dictionary to hold the combined path data for each color
    # Key: fill_color string, Value: list of 'd' string segments
    color_paths = defaultdict(list)
    
    # Find all path elements
    paths = root.xpath('.//svg:path', namespaces=ns)
    
    if not paths:
        return tree
        
    # Extract data and remove the original individual paths from the DOM
    for path in paths:
        fill_color = path.get('fill')
        d_attr = path.get('d')
        
        if fill_color and d_attr:
            color_paths[fill_color].append(d_attr.strip())
        
        # Remove the node from its parent
        parent = path.getparent()
        if parent is not None:
            parent.remove(path)
            
    # Create new combined paths and append them back to the root (or main group)
    # Finding the first group <g> to append to, or root if no group exists
    target_container = root.xpath('.//svg:g', namespaces=ns)
    container = target_container[0] if target_container else root
    
    merged_count = 0
    for color, d_segments in color_paths.items():
        # Concatenate path strings with a space
        combined_d = " ".join(d_segments)
        
        # Create a new compound <path> element
        new_path = etree.Element(f"{{{ns['svg']}}}path")
        new_path.set('fill', color)
        new_path.set('d', combined_d)
        
        # Set stroke to none to ensure clean compound shapes
        new_path.set('stroke', 'none')
        
        container.append(new_path)
        merged_count += 1
        
    log.info(f"Merged {len(paths)} individual paths into {merged_count} compound paths.")
    
    return tree