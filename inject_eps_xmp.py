# inject_eps_xmp.py
"""Inject XMP metadata directly into EPS files (no ExifTool needed).
EPS = PostScript text format, so we insert XMP packet after %%EndComments."""
import json
from pathlib import Path
from lxml import etree
from config import cfg
from utils.logger import log
from utils.filesystem import setup_directories, get_image_files
from utils.metadata_ai import _image_hash

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
X_NS = "adobe:ns:meta/"
IPTS_NS = "http://ns.adobe.com/iX/1.0/"
PHOTOSHOP_NS = "http://ns.adobe.com/photoshop/1.0/"


def build_xmp(title: str, keywords: list) -> str:
    """Bangun XMP packet (XML + wrapper standar Adobe)."""
    root = etree.Element(f"{{{X_NS}}}xmpmeta")
    rdf = etree.SubElement(root, f"{{{RDF_NS}}}RDF")
    desc = etree.SubElement(rdf, f"{{{RDF_NS}}}Description",
                            attrib={f"{{{RDF_NS}}}about": ""})

    # dc:title (localized)
    title_el = etree.SubElement(desc, f"{{{DC_NS}}}title")
    bag_t = etree.SubElement(title_el, f"{{{RDF_NS}}}Alt")
    li_t = etree.SubElement(bag_t, f"{{{RDF_NS}}}li",
                            attrib={"{http://www.w3.org/XML/1998/namespace}lang": "x-default"})
    li_t.text = title

    # dc:description
    desc_el = etree.SubElement(desc, f"{{{DC_NS}}}description")
    bag_d = etree.SubElement(desc_el, f"{{{RDF_NS}}}Alt")
    li_d = etree.SubElement(bag_d, f"{{{RDF_NS}}}li",
                            attrib={"{http://www.w3.org/XML/1998/namespace}lang": "x-default"})
    li_d.text = title

    # dc:subject (keywords)
    subj_el = etree.SubElement(desc, f"{{{DC_NS}}}subject")
    bag_s = etree.SubElement(subj_el, f"{{{RDF_NS}}}Bag")
    for kw in keywords:
        li_s = etree.SubElement(bag_s, f"{{{RDF_NS}}}li")
        li_s.text = kw

    xml_bytes = etree.tostring(root, pretty_print=True, encoding="utf-8")
    xmp_str = xml_bytes.decode("utf-8")

    # Adobe XMP packet wrapper (standar ISO 16684-1)
    padding = " " * 2000  # padding untuk editability di Adobe apps
    header = (
        '<?xpacket begin="\xef\xbb\xbf" id="W5M0"?>\n'
        f'{xmp_str}\n'
        f'{padding}\n'
        '<?xpacket end="w"?>\n'
    )
    return header


def inject_to_eps(eps_path: Path, title: str, keywords: list) -> bool:
    """Suntik XMP packet ke EPS file (setelah header PostScript)."""
    try:
        content = eps_path.read_text(encoding="latin-1", errors="replace")
    except Exception as e:
        log.error(f"Cannot read {eps_path.name}: {e}")
        return False

    # Cari posisi sisip: setelah %%EndComments atau %%BeginProlog
    lines = content.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("%%EndComments"):
            insert_idx = i + 1
            break
        if line.startswith("%%BeginProlog"):
            insert_idx = i
            break
    if insert_idx == 0:
        insert_idx = min(5, len(lines))  # fallback: setelah header dasar

    xmp_packet = build_xmp(title, keywords)

    # Sisipkan XMP packet dengan PS comment markers
    xmp_block = [
        "%XMP_BEGIN_METADATA",
        *[line for line in xmp_packet.split("\n")],
        "%XMP_END_METADATA",
    ]
    new_lines = lines[:insert_idx] + xmp_block + lines[insert_idx:]

    eps_path.write_text("\n".join(new_lines), encoding="latin-1")
    return True


def main():
    setup_directories()
    images = get_image_files(cfg.INPUT_FOLDER)
    log.info(f"XMP injector: {len(images)} images")

    ok = 0
    for img in images:
        eps = cfg.OUTPUT_EPS_FOLDER / f"{img.stem}.eps"
        cache = cfg.CACHE_DIR / "metadata" / f"{_image_hash(img)}.json"
        if not eps.exists() or not cache.exists():
            log.warning(f"Skip: {img.name}")
            continue
        meta = json.loads(cache.read_text())
        if inject_to_eps(eps, meta["title"], meta["keywords"]):
            log.info(f"✅ XMP injected: {eps.name} ({len(meta['keywords'])} kw)")
            ok += 1

    log.info(f"Selesai: {ok}/{len(images)} EPS ber-XMP")


if __name__ == "__main__":
    main()