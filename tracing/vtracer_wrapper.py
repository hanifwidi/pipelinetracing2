# tracing/vtracer_wrapper.py
import os
import tempfile
import cv2
import numpy as np
import vtracer
from pathlib import Path
from utils.logger import log
from utils.benchmark import benchmark
from config import cfg

@benchmark
def trace_image_to_svg(img_array: np.ndarray) -> str:
    log.info("Initiating VTracer vectorization engine...")
    
    temp_dir = cfg.CACHE_DIR
    temp_dir.mkdir(exist_ok=True)
    
    # img_array sekarang datang sebagai RGB bersih dari geometry.py.
    # Di sini kita konversi ke BGR agar siap ditulis oleh file saver.
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".png", delete=False) as temp_in:
        input_path = temp_in.name
        
    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=".svg", delete=False) as temp_out:
        output_path = temp_out.name

    try:
        # BYPASS WINDOWS WRITE BUG
        _, encoded_img = cv2.imencode('.png', img_bgr)
        encoded_img.tofile(input_path)
        
        import time
        time.sleep(0.1) # Tweak minor untuk IO lock window
        
       # Execute VTracer with production-grade parameters.
        vtracer.convert_image_to_svg_py(
            input_path,
            output_path,
            colormode="color",
            hierarchical="stacked",
            mode="spline",                  # Ganti kembali ke 'spline' untuk gambar organik
            filter_speckle=4,               # Naikkan sedikit agar tidak melacak noise kecil
            color_precision=6,              
            layer_difference=16,
            corner_threshold=60,            # Naikkan agar ujung daun membulat alami
            length_threshold=4.0,                 
            max_iterations=10,
            splice_threshold=45,
            path_precision=3                
        )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
            
        log.debug(f"Raw SVG tracing successful. Length: {len(svg_content)} chars.")
        return svg_content
        
    except Exception as e:
        log.error(f"VTracer engine failed: {str(e)}")
        raise
        
    finally:
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except OSError as cleanup_error:
            log.warning(f"Failed to cleanup temp files: {cleanup_error}")