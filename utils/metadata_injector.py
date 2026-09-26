"""Metadata writers never insert executable raw XML into PostScript."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from lxml import etree
from utils.atomic_io import atomic_write
from utils.svg_tools import parse_svg, serialize_svg, SVG_NS
from utils.logger import log

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC = "http://purl.org/dc/elements/1.1/"

def inject_svg_metadata(svg_path, title, keywords):
    svg_path = Path(svg_path)
    tree = parse_svg(svg_path.read_bytes())
    root = tree.getroot()
    for old in list(root.findall(f"{{{SVG_NS}}}metadata")):
        root.remove(old)
    block = etree.SubElement(root, f"{{{SVG_NS}}}metadata")
    xmp = etree.SubElement(block, "{adobe:ns:meta/}xmpmeta", nsmap={"x": "adobe:ns:meta/", "rdf": RDF, "dc": DC})
    rdf = etree.SubElement(xmp, f"{{{RDF}}}RDF")
    desc = etree.SubElement(rdf, f"{{{RDF}}}Description", {f"{{{RDF}}}about": ""})
    for field in ("title", "description"):
        alt = etree.SubElement(etree.SubElement(desc, f"{{{DC}}}{field}"), f"{{{RDF}}}Alt")
        li = etree.SubElement(alt, f"{{{RDF}}}li", {"{http://www.w3.org/XML/1998/namespace}lang": "x-default"})
        li.text = title
    bag = etree.SubElement(etree.SubElement(desc, f"{{{DC}}}subject"), f"{{{RDF}}}Bag")
    for keyword in keywords:
        etree.SubElement(bag, f"{{{RDF}}}li").text = keyword
    atomic_write(svg_path, serialize_svg(tree))
    return True

def inject_eps_metadata(eps_path, title, keywords):
    eps_path = Path(eps_path)
    executable = shutil.which("exiftool")
    if not executable:
        log.warning("ExifTool unavailable; EPS keywords remain available in metadata.csv")
        return False
    from export.eps_export import validate_eps
    fd, name = tempfile.mkstemp(suffix=".eps", dir=eps_path.parent)
    os.close(fd)
    try:
        shutil.copy2(eps_path, name)
        command = [executable, "-overwrite_original", "-charset", "UTF8", f"-XMP-dc:Title={title}", f"-XMP-dc:Description={title}", "-XMP-dc:Subject="]
        command += [f"-XMP-dc:Subject+={word}" for word in keywords]
        result = subprocess.run(command + [name], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        validate_eps(name)
        os.replace(name, eps_path)
        return True
    finally:
        Path(name).unlink(missing_ok=True)
