# tracing/svg_optimizer.py
from lxml import etree
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def optimize_svg_tree(svg_xml_string: str) -> etree._ElementTree:
    """
    Parses the raw SVG string into an lxml ElementTree and strips out 
    unnecessary metadata, empty groups, and overly verbose floating-point numbers.
    
    Args:
        svg_xml_string (str): The raw SVG string from VTracer.
        
    Returns:
        etree._ElementTree: The optimized XML tree object.
    """
    log.debug("Parsing and optimizing SVG XML structure.")
    
    # Parse the string into an lxml tree. Recover=True allows parsing slightly malformed XML.
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    try:
        root = etree.fromstring(svg_xml_string.encode('utf-8'), parser)
    except etree.XMLSyntaxError as e:
        log.error(f"XML Parsing failed: {e}")
        raise

    # Define standard SVG namespace for XPath queries
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    # 1. Remove comments and unused metadata blocks
    for element in root.xpath('//svg:metadata | //svg:defs[not(node())]', namespaces=ns):
        element.getparent().remove(element)
        
    # 2. Strip unnecessary root attributes (like generator tags)
    attribs_to_remove = ['{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}docname',
                         '{http://www.inkscape.org/namespaces/inkscape}version']
    for attr in attribs_to_remove:
        if attr in root.attrib:
            del root.attrib[attr]

    # 3. Clean up Paths (Round floats in 'd' attribute to reduce file size)
    # E.g., 'M 10.123456 20.987654' -> 'M 10.123 20.988'
    precision = cfg.SVG_PRECISION
    for path in root.xpath('//svg:path', namespaces=ns):
        d_attr = path.get('d')
        if d_attr:
            optimized_d = _optimize_path_string(d_attr, precision)
            path.set('d', optimized_d)

    log.debug("SVG tree metadata and precision optimization complete.")
    return etree.ElementTree(root)

def _optimize_path_string(d: str, precision: int) -> str:
    """Helper function to round floating point coordinates in an SVG path."""
    import re
    
    # Find all floating point numbers in the path string
    def round_match(match):
        val = float(match.group(0))
        # Round and remove trailing zeros (e.g., 5.0 -> 5)
        rounded = round(val, precision)
        if rounded == int(rounded):
            return str(int(rounded))
        return str(rounded)
        
    # Regex to match floating point numbers, handling negative signs and decimals
    number_pattern = re.compile(r'-?\d*\.\d+|-?\d+')
    optimized_d = number_pattern.sub(round_match, d)
    
    return optimized_d