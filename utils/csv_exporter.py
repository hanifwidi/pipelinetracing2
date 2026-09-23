# utils/csv_exporter.py
import csv
from pathlib import Path
from utils.logger import log

def append_metadata_csv(csv_path: Path, filename: str, title: str, keywords: list):
    """Append metadata ke file CSV sebagai backup."""
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write header jika file belum ada
        if not csv_path.exists():
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Filename", "Title", "Keywords", "Category"])
        
        # Append baris baru
        keywords_str = ", ".join(keywords)
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([filename, title, keywords_str, ""])
        
        log.debug(f"Metadata appended to CSV: {csv_path.name}")
        
    except Exception as e:
        log.error(f"Failed to write CSV: {e}")