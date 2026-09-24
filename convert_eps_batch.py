# convert_eps_batch.py
"""Convert SVG → EPS via Inkscape CLI. Metadata XMP tetap terpreserve."""
import subprocess
from pathlib import Path
import shutil
import sys

# Detect Inkscape path (macOS biasanya di /Applications)
INKSCAPE_PATHS = [
    "/Applications/Inkscape.app/Contents/MacOS/inkscape",
    shutil.which("inkscape"),
]

def find_inkscape():
    for p in INKSCAPE_PATHS:
        if p and Path(p).exists():
            return p
    print("❌ Inkscape tidak ditemukan. Pastikan /Applications/Inkscape.app ada.")
    sys.exit(1)

def get_inkscape_version(ink):
    try:
        out = subprocess.run([ink, "--version"], capture_output=True, text=True).stdout
        # contoh: "Inkscape 1.3 (0e150ed, 2023-07-21)"
        ver = out.split()[1] if len(out.split()) > 1 else "1.0"
        return float(ver.split(".")[0] + "." + ver.split(".")[1])
    except:
        return 1.0  # assume new

def convert(svg_path: Path, eps_path: Path, ink: str, version: float):
    if version >= 1.0:
        cmd = [ink, str(svg_path), "--export-filename", str(eps_path), "--export-type", "eps"]
    else:
        cmd = [ink, str(svg_path), f"--export-eps={eps_path}"]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return eps_path.exists(), result.returncode == 0

def main():
    ink = find_inkscape()
    ver = get_inkscape_version(ink)
    print(f"🎨 Inkscape: {ink} (v{ver})")
    
    svg_dir = Path("output_svg")
    eps_dir = Path("output_eps")
    eps_dir.mkdir(exist_ok=True)
    
    svgs = sorted(svg_dir.glob("*.svg"))
    print(f"📦 Converting {len(svgs)} files...")
    
    success, fail = 0, 0
    for svg in svgs:
        eps = eps_dir / f"{svg.stem}.eps"
        ok, status = convert(svg, eps, ink, ver)
        if ok:
            print(f"  ✅ {eps.name} ({eps.stat().st_size // 1024} KB)")
            success += 1
        else:
            print(f"  ❌ {svg.name}")
            fail += 1
    
    print(f"\n🎉 Done: {success} sukses, {fail} gagal")

if __name__ == "__main__":
    main()