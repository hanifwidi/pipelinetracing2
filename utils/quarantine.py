import hashlib
import shutil
from pathlib import Path
from config import cfg
from utils.atomic_io import write_json
from utils.logger import log

def move_to_quarantine(file_path, error_msg="Unknown error"):
    """Compatibility name: retain the original and copy a failed input for inspection."""
    file_path = Path(file_path)
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()[:12]
    folder = cfg.QUARANTINE_FOLDER / digest
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / file_path.name
    if not destination.exists():
        shutil.copy2(file_path, destination)
    write_json(folder / "error.json", {"source": str(file_path), "error": error_msg})
    log.error("Copied to quarantine: %s", file_path.name)
    return destination
