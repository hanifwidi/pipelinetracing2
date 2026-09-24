# utils/metadata_ai.py
import os, json, base64, hashlib, time, io, re
from pathlib import Path
import requests
from PIL import Image
from config import cfg
from utils.logger import log
from utils.benchmark import benchmark

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Model prioritas berdasarkan hasil TES 1
MODEL_CHAIN = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash"]
_WORKING_MODEL = None

PROMPT = """Analyze this vector icon sheet and produce Adobe Stock-ready metadata.
Return ONLY a single-line JSON object: {"title": "...", "keywords": ["...", ...]}

TITLE: 6-12 English words, natural descriptive phrase.
  Structure: [main niche] icon set featuring [3-4 representative icons].
  Example: "Cybersecurity and privacy icon set featuring shield lock, fingerprint, firewall and encryption"

KEYWORDS: exactly 40-49 lowercase terms, ordered by relevance (most important first).
  MUST include these 4 mandatory groups (mix them into the order):
  1. Core subject (5-8 keywords): literal objects shown
  2. Style (3-5 keywords): "flat icon", "modern icon", "simple symbol", "clean design", "vector icon set"
  3. Buyer use-cases (MANDATORY, 10-12 keywords): 
     "banner, template, infographic, poster, flyer, social media post, marketing, 
      advertising, presentation slide, corporate report, web design, mockup, 
      business concept, digital, 2026, contemporary, trending"
  4. Niche concepts (rest): industry-specific terms
  
  AVOID internal pipeline jargon: do NOT use "glyph", "solid icon", "silhouette", "pictogram".
  Max 3 words per keyword. No duplicates. No plurals of same word.

Return JSON only. No markdown. No explanation."""


def _compress_image(path: Path, max_size: int = 1024) -> bytes:
    """Resize + kompres JPEG supaya payload base64 kecil (< 200KB)."""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > max_size or h > max_size:
        scale = max_size / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def _image_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _clean_metadata(meta: dict) -> dict:
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
    """Fallback bersih kalau API mati total."""
    clean = re.sub(r"\d{6,}", " ", filename)
    clean = re.sub(r"\b\d+\s*[kK]\b", " ", clean)
    clean = re.sub(r"_", " ", clean)
    words = [w for w in re.split(r"\s+", clean) if w and len(w) > 2]
    title = " ".join(w.capitalize() for w in words) + " Vector Icon Set"
    keywords, seen = [], set()
    for k in [w.lower() for w in words] + [
        "vector", "illustration", "icon set", "flat design", "glyph", "symbol",
        "design", "graphic", "element", "isolated", "silhouette", "template",
        "web design", "print", "sign", "pictogram", "collection", "modern",
        "minimal", "business", "concept", "set", "black", "white",
    ]:
        if k not in seen:
            seen.add(k); keywords.append(k)
    return {"title": title, "keywords": keywords[:49]}


@benchmark
def generate_metadata(image_path: Path, retries: int = 3) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY tidak diset → dummy metadata")
        return _dummy_metadata(image_path.stem)

    # Cache MD5
    cache_dir = cfg.CACHE_DIR / "metadata"
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_hash = _image_hash(image_path)
    cache_file = cache_dir / f"{img_hash}.json"
    if cache_file.exists():
        log.info(f"Metadata cache hit: {image_path.name}")
        return json.loads(cache_file.read_text())

    # Kompresi gambar (10x lebih kecil dari PNG/JPEG asli)
    compressed_bytes = _compress_image(image_path, max_size=1024)
    b64 = base64.b64encode(compressed_bytes).decode()
    log.info(f"Payload size: {len(compressed_bytes) // 1024} KB (compressed)")

    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0.3},
    }

    global _WORKING_MODEL
    base_chain = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
    chain = ([_WORKING_MODEL] + base_chain) if _WORKING_MODEL else base_chain

    for attempt in range(retries):
        for model in chain:
            url = f"{API_BASE}/{model}:generateContent"
            try:
                resp = requests.post(url, headers={"x-goog-api-key": api_key},
                                     json=payload, timeout=45)
                if resp.status_code == 429:
                    time.sleep(8); continue
                if resp.status_code in (404, 500, 502, 503):
                    log.warning(f"{model} → HTTP {resp.status_code}, coba model lain")
                    continue
                resp.raise_for_status()
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
                meta = _clean_metadata(json.loads(raw))
                meta["source"] = "ai"
                _WORKING_MODEL = model
                cache_file.write_text(json.dumps(meta, indent=2))
                log.info(f"Metadata via {model}: {image_path.name} ({len(meta['keywords'])} kw)")
                return meta
            except requests.exceptions.Timeout:
                log.warning(f"{model} timeout 45s → next"); continue
            except requests.exceptions.RequestException as e:
                log.warning(f"{model} network error → next"); continue
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                log.warning(f"{model} parse error → next"); continue
        wait = 15 * (attempt + 1)
        log.warning(f"Semua model sibuk → backoff {wait}s (pass {attempt+1}/{retries})")
        time.sleep(wait)

    log.warning("Semua model gagal → metadata dummy")
    dummy = _dummy_metadata(image_path.stem)
    dummy["source"] = "dummy"
    return dummy