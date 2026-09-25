# repair_metadata.py
import csv, json
from config import cfg
from utils.logger import log
from utils.filesystem import setup_directories, get_image_files
from utils.metadata_ai import generate_metadata, _image_hash
from utils.metadata_injector import inject_svg_metadata

setup_directories()
images = get_image_files(cfg.INPUT_FOLDER) + get_image_files(cfg.INPUT_PROCESSED_FOLDER)
log.info(f"REPAIR MODE: {len(images)} images (cache hit = instan, tanpa API)")

for img in images:
    meta = generate_metadata(img)
    svg = cfg.OUTPUT_SVG_FOLDER / f"{img.stem}.svg"
    if meta.get("source", "ai") == "ai":   # cache lama tanpa field source = tetap AI (dummy tidak pernah di-cache)
        if svg.exists():
            inject_svg_metadata(svg, meta["title"], meta["keywords"])
        log.info(f"✅ {img.name} → metadata AI")
    else:
        log.warning(f"⏳ {img.name} → masih dummy (API sibuk), jalankan ulang nanti")

# Rebuild metadata.csv dari cache (anti baris duplikat)
rows = []
for img in images:
    cf = cfg.CACHE_DIR / "metadata" / f"{_image_hash(img)}.json"
    if cf.exists():
        m = json.loads(cf.read_text())
        rows.append([f"{img.stem}.svg", m["title"], ", ".join(m["keywords"]), ""])
csv_path = cfg.OUTPUT_SVG_FOLDER / "metadata.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Filename", "Title", "Keywords", "Category"])
    w.writerows(rows)
log.info(f"metadata.csv rebuilt: {len(rows)} baris metadata AI")
