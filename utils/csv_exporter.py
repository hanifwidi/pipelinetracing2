"""Idempotent CSV metadata writes; the pipeline calls these in its parent process."""
import csv
from pathlib import Path
from filelock import FileLock
from utils.atomic_io import write_csv

FIELDS = ["Filename", "Title", "Keywords", "Category"]

def append_metadata_csv(csv_path: Path, filename: str, title: str, keywords: list, category=""):
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(csv_path) + ".lock", timeout=30):
        rows = {}
        if csv_path.exists():
            with csv_path.open(newline="", encoding="utf-8-sig") as stream:
                rows = {r["Filename"]: {k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(stream)}
        rows[filename] = dict(Filename=filename, Title=title, Keywords=", ".join(keywords), Category=category or rows.get(filename, {}).get("Category", ""))
        write_csv(csv_path, FIELDS, [rows[k] for k in sorted(rows)])

def remove_metadata_row(csv_path, filename):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return
    with FileLock(str(csv_path) + ".lock", timeout=30):
        with csv_path.open(newline="", encoding="utf-8-sig") as stream:
            rows = [{k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(stream) if r["Filename"] != filename]
        write_csv(csv_path, FIELDS, rows)
