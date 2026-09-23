# utils/metadata_injector.py
import subprocess
import shutil
from pathlib import Path
from lxml import etree
from utils.logger import log
from utils.benchmark import benchmark

@benchmark
def inject_svg_metadata(svg_path: Path, title: str, keywords: list):
    """Inject XMP metadata ke file SVG."""
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(svg_path, parser)
        root = tree.getroot()
        
        # Namespace definitions
        nsmap = {
            'x': "adobe:ns:meta/",
            'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            'dc': "http://purl.org/dc/elements/1.1/"
        }
        
        # Cari atau buat elemen metadata
        metadata = root.find("{http://www.w3.org/2000/svg}metadata")
        if metadata is None:
            metadata = etree.SubElement(root, "{http://www.w3.org/2000/svg}metadata")
        
        # Hapus metadata lama
        for child in list(metadata):
            metadata.remove(child)
        
        # Buat struktur XMP
        xmpmeta = etree.SubElement(metadata, "{adobe:ns:meta/}xmpmeta")
        rdf = etree.SubElement(xmpmeta, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF")
        desc = etree.SubElement(rdf, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description")
        
        # Title
        dc_title = etree.SubElement(desc, "{http://purl.org/dc/elements/1.1/}title")
        alt = etree.SubElement(dc_title, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt")
        li = etree.SubElement(alt, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li")
        li.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
        li.text = title
        
        # Keywords (dc:subject as rdf:Bag)
        dc_subject = etree.SubElement(desc, "{http://purl.org/dc/elements/1.1/}subject")
        bag = etree.SubElement(dc_subject, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag")
        for kw in keywords:
            li = etree.SubElement(bag, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li")
            li.text = kw
        
        # Simpan
        tree.write(svg_path, xml_declaration=True, encoding='utf-8', pretty_print=True)
        log.info(f"Metadata injected to SVG: {svg_path.name}")
        
    except Exception as e:
        log.error(f"Failed to inject SVG metadata: {e}")


@benchmark
def inject_eps_metadata(eps_path: Path, title: str, keywords: list):
    """Inject metadata ke file EPS menggunakan ExifTool."""
    exiftool_path = shutil.which("exiftool")
    if not exiftool_path:
        log.warning("ExifTool tidak ditemukan! Install dengan: brew install exiftool")
        return
    
    try:
        # Build keyword arguments
        kw_args = []
        for kw in keywords:
            kw_args.extend(["-keywords=" + kw])
        
        command = [
            exiftool_path,
            "-overwrite_original",
            f"-Title={title}",
            f"-Description={title}",
            *kw_args,
            str(eps_path)
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            log.info(f"Metadata injected to EPS: {eps_path.name}")
        else:
            log.error(f"ExifTool failed: {result.stderr}")
            
    except Exception as e:
        log.error(f"Failed to inject EPS metadata: {e}")