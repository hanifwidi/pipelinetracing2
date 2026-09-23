from pathlib import Path
from lxml import etree
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def save_svg(svg_data, original_filename):
    # Tentukan direktori output. Pastikan direktori sudah dibuat.
    output_dir = Path("output") 
    output_dir.mkdir(exist_ok=True)
    
    # Ganti ekstensi file asli menjadi .svg
    filename = Path(original_filename).with_suffix('.svg').name
    output_path = output_dir / filename
    
    try:
        if isinstance(svg_data, str):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(svg_data)
        else:
            svg_data.write(str(output_path), encoding='utf-8', xml_declaration=True)
            
        return output_path
        
    except Exception as e:
        log.error(f"Failed to save SVG {output_path.name}: {str(e)}")
        raise