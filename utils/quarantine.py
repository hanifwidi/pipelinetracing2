# utils/quarantine.py
import shutil
from pathlib import Path
from datetime import datetime
from utils.logger import log

def move_to_quarantine(file_path: Path, error_msg: str = "Unknown error"):
    """
    Pindahkan file yang gagal diproses ke folder quarantine dengan log error.
    """
    quarantine_dir = file_path.parent.parent / "quarantine"
    quarantine_dir.mkdir(exist_ok=True)
    
    # Tambahkan timestamp agar tidak overwrite
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{timestamp}_{file_path.name}"
    dest_path = quarantine_dir / new_name
    
    # Copy file (jangan move, biar bisa debug)
    shutil.copy2(file_path, dest_path)
    
    # Tulis log error
    log_file = quarantine_dir / f"{timestamp}_{file_path.stem}_error.log"
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"File: {file_path}\n")
        f.write(f"Error: {error_msg}\n")
        f.write(f"Timestamp: {timestamp}\n")
    
    log.error(f"File moved to quarantine: {file_path.name} | Error: {error_msg}")
    return dest_path