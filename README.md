# Vector Factory V2 🚀
*Automatic Image-to-Clean-Vector Pipeline Optimized for Adobe Stock*

Vector Factory V2 is a production-grade, multiprocessed software pipeline designed to convert raster images (PNG, JPEG, WEBP) into highly optimized, commercial-quality SVG and EPS files. It utilizes advanced Computer Vision, Computational Geometry, and XML DOM manipulation to ensure minimal anchor points, smooth curves, and perfect editing compatibility in Adobe Illustrator.

## 🏗️ Pipeline Architecture

1. **Preprocess:** Resize ➔ CLAHE Normalization ➔ OCR Text Removal ➔ Color Quantization (K-Means) ➔ Noise Reduction ➔ Morphological Cleanup ➔ Edge Enhancement.
2. **Contour:** Topological Extraction ➔ RDP Mathematical Simplification ➔ Boolean Geometry Union.
3. **Tracing:** VTracer Rust Engine (Auto-tuned) ➔ LXML DOM Parsing ➔ Compound Path Merging ➔ Duplicate Node Purging.
4. **Export:** Minified SVG Serialization ➔ (Optional) Inkscape CLI EPS Generation.

## 📦 Installation

```bash
# 1. Clone or download the repository
# 2. Create a virtual environment
python -m venv venv

# 3. Activate the environment
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt