# utils/metadata_ai.py
import os
import json
import base64
import hashlib
import time
from pathlib import Path
import requests

from config import cfg
from utils.logger import log
from utils.benchmark import benchmark

GEMINI_MODEL = "gemini-2.0-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

PROMPT = """You are a top-tier microstock metadata SEO expert with 10 years of experience
selling vectors on Adobe Stock. Analyze this image and produce metadata that maximizes
search visibility and buyer conversion.

Return ONLY valid JSON: {"title": "...", "keywords": ["...", ...]}

TITLE RULES:
- 6-12 words, English, natural descriptive phrase (NOT a keyword list).
- Structure: [main subject] + [description/action] + [style] + [type].
- Example: "Cute red fox sitting in autumn forest, flat style vector illustration"
- No brand names, no all-caps, no punctuation abuse.

KEYWORD RULES (buyer-oriented, SEO optimized):
- Exactly 35-49 keywords, lowercase, ordered by relevance (most important FIRST,
  because Adobe Stock ranks early keywords higher).
- Cover these 6 layers:
  1. Literal subject (what is visible): fox, animal, tail, fur
  2. Style & technique: vector, illustration, flat, cartoon, minimalist
  3. Concept & emotion (what buyers search): wildlife, freedom, autumn, curiosity
  4. Color & mood: orange, warm, vibrant, cozy
  5. Composition & format: isolated, background, banner, copy space, icon
  6. Use case: design, template, logo, print, web, decoration
- Max 3 words per keyword. No duplicates, no singular+plural of same word,
  no brand/trademark/celebrity names, no irrelevant spam.
- Think like a buyer: what would a designer type in the search box to find this?"""


@benchmark
def generate_metadata(image_path: Path, retries: int = 3) -> dict:
    """Generate title & keywords menggunakan Gemini Vision API."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY tidak diset! Gunakan metadata dummy.")
        return _dummy_metadata(image_path.stem)
    
    # Cache berbasis hash gambar
    cache_dir = cfg.CACHE_DIR / "metadata"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    img_hash = hashlib.md5(image_path.read_bytes()).hexdigest()
    cache_file = cache_dir / f"{img_hash}.json"
    
    if cache_file.exists():
        log.info(f"Metadata cache hit: {image_path.name}")
        return json.loads(cache_file.read_text())
    
    # Encode gambar ke base64
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    mime = {"png": "image/png", "jpg": "image/jpeg", 
            "jpeg": "image/jpeg", "webp": "image/webp"}.get(image_path.suffix.lower()[1:], "image/png")
    
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.4,
        },
    }
    
    for attempt in range(retries):
        try:
            resp = requests.post(API_URL, headers={"x-goog-api-key": api_key},
                                json=payload, timeout=90)
            
            if resp.status_code == 429:  # Rate limit
                wait = 10 * (attempt + 1)
                log.warning(f"Rate limit. Tunggu {wait}s...")
                time.sleep(wait)
                continue
            
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            meta = _clean_metadata(json.loads(raw))
            
            # Simpan ke cache
            cache_file.write_text(json.dumps(meta, indent=2))
            log.info(f"Metadata generated: {image_path.name} ({len(meta['keywords'])} keywords)")
            return meta
            
        except Exception as e:
            log.error(f"Metadata API error (attempt {attempt+1}): {e}")
            if attempt == retries - 1:
                log.warning("Menggunakan metadata dummy")
                return _dummy_metadata(image_path.stem)
    
    return _dummy_metadata(image_path.stem)


def _clean_metadata(meta: dict) -> dict:
    """Validasi dan bersihkan metadata dari AI."""
    title = " ".join(str(meta.get("title", "")).split())[:90]
    
    keywords, seen = [], set()
    for kw in meta.get("keywords", []):
        kw = " ".join(str(kw).lower().split())
        if not kw or kw in seen or len(kw.split()) > 3:
            continue
        seen.add(kw)
        keywords.append(kw)
        if len(keywords) == 49:
            break
    
    if len(keywords) < 5:
        raise ValueError("AI menghasilkan keyword < 5")
    
    return {"title": title, "keywords": keywords}


def _dummy_metadata(filename: str) -> dict:
    """Fallback metadata jika API gagal."""
    words = filename.replace("-", " ").replace("_", " ").split()
    title = " ".join(w.capitalize() for w in words) + " Vector Illustration"
    keywords = words + ["vector", "illustration", "design", "graphic", "art", 
                       "digital", "creative", "element", "decoration", "template"]
    return {"title": title, "keywords": keywords[:49]}