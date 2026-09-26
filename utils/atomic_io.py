"""Replace complete files atomically; callers coordinate read/modify/write."""
import csv
import io
import json
import os
import tempfile
from pathlib import Path

def atomic_write(path: Path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def write_json(path, data):
    atomic_write(Path(path), json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))

def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def write_csv(path, fields, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(Path(path), buf.getvalue())
