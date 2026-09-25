# archive_old_inputs.py
"""Pindahkan semua file lama di input/ ke input_processed/ (sekali jalan)."""
import shutil, time
from pathlib import Path
from config import cfg
from utils.filesystem import setup_directories

setup_directories()
moved = 0
for f in sorted(cfg.INPUT_FOLDER.iterdir()):
    if not f.is_file() or f.name.startswith("."):
        continue
    dest = cfg.INPUT_PROCESSED_FOLDER / f.name
    if dest.exists():
        dest = cfg.INPUT_PROCESSED_FOLDER / f"{f.stem}_{int(time.time())}{f.suffix}"
    shutil.move(str(f), str(dest))
    moved += 1
print(f"✅ {moved} files archived → {cfg.INPUT_PROCESSED_FOLDER}/")