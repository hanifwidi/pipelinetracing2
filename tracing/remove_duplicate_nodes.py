# tracing/remove_duplicate_nodes.py
import re
from lxml import etree
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def clean_duplicate_nodes(tree: etree._ElementTree) -> etree._ElementTree:
    """
    Parses compound path data and removes sequential duplicate coordinate commands 
    to further minimize file size and prevent node clustering in Adobe Illustrator.
    
    Args:
        tree (etree._ElementTree): The merged SVG XML tree.
        
    Returns:
        etree._ElementTree: The cleaned XML tree.
    """
    if not cfg.REMOVE_DUPLICATE_NODES:
        return tree

    log.debug("Scanning path data for redundant overlapping nodes.")
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    paths = root.xpath('.//svg:path', namespaces=ns)
    
    # Regex to find commands like L, M, C followed by coordinates
    # For a production pipeline, we do a safe string replacement for exact sequential matches
    nodes_removed = 0
    
    for path in paths:
        d_attr = path.get('d')
        if not d_attr:
            continue
            
        # Split the path string by commands (M, L, C, Z, etc.)
        # This is a basic optimization for straight lines and moves
        commands = re.findall(r'([a-zA-Z][^a-zA-Z]*)', d_attr)
        
        cleaned_commands = []
        prev_cmd_data = None
        
        for cmd in commands:
            cmd = cmd.strip()
            # If this command is exactly the same as the last one (e.g., redundant Line-to)
            # and it's not a relative curve that accumulates, we can often skip it.
            # To be 100% mathematically safe for SVG, we strictly remove duplicate absolute LineTo (L)
            if cmd.startswith('L') and cmd == prev_cmd_data:
                nodes_removed += 1
                continue
                
            cleaned_commands.append(cmd)
            prev_cmd_data = cmd
            
        optimized_d = " ".join(cleaned_commands)
        path.set('d', optimized_d)
        
    if nodes_removed > 0:
        log.info(f"Purged {nodes_removed} redundant anchor points from geometries.")
        
    return tree