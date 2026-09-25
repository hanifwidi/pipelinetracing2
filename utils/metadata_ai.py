# utils/metadata_ai.py
import os, json, base64, hashlib, time, io, re
from pathlib import Path
import requests
from PIL import Image
from config import cfg
from utils.logger import log
from utils.benchmark import benchmark

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_CHAIN = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.2-90b-vision-preview"]
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODELS = ["pixtral-12b-2409"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = ["qwen/qwen-2.5-vl-32b-instruct:free", "google/gemini-2.0-flash-exp:free",
                     "meta-llama/llama-3.2-11b-vision-instruct:free"]

PROMPT = """Analyze this vector icon sheet and produce Adobe Stock-ready metadata.
Return ONLY a single-line JSON object: {"title": "...", "keywords": ["...", ...]}

TITLE: 6-12 English words, natural descriptive phrase.
  Structure: [main niche] icon set featuring [3-4 representative icons].
  Example: "Cybersecurity and privacy icon set featuring shield lock, fingerprint, firewall and encryption"

KEYWORDS: exactly 40-49 lowercase terms, ordered by relevance (most important first).
  MUST include these 4 groups mixed into the order:
  1. Core subject (5-8): literal objects shown
  2. Style (3-5): "flat icon", "modern icon", "simple symbol", "clean design", "vector icon set"
  3. Buyer use-cases (10-12): banner, template, infographic, poster, flyer, social media post,
     marketing, advertising, presentation slide, corporate report, web design, mockup,
     business concept, digital, contemporary, trending
  4. Niche concepts (rest): industry-specific terms
  AVOID jargon: do NOT use "glyph", "solid icon", "silhouette", "pictogram".
  Max 3 words per keyword. No duplicates. No plurals of same word. No brand names.

Return JSON only. No markdown. No explanation."""


def _compress_image(path: Path, max_size: int = 1024) -> bytes:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_size:
        s = max_size / max(w, h)
        img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
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
        seen.add(kw); keywords.append(kw)
        if len(keywords) == 49: break
    if len(keywords) < 5:
        raise ValueError("keywords < 5")
    return {"title": title, "keywords": keywords}


def _dummy_metadata(filename: str) -> dict:
    clean = re.sub(r"\d{6,}", " ", filename)
    clean = re.sub(r"\b\d+\s*[kK]\b", " ", clean)
    words = [w for w in re.split(r"[-_ ]+", clean) if w and len(w) > 2]
    title = " ".join(w.capitalize() for w in words) + " Vector Icon Set"
    keywords, seen = [], set()
    for k in [w.lower() for w in words] + [
        "vector", "illustration", "icon set", "flat design", "simple symbol",
        "clean design", "design", "graphic", "element", "isolated", "template",
        "web design", "print", "sign", "collection", "modern", "business",
        "concept", "banner", "infographic", "poster", "marketing"]:
        if k not in seen:
            seen.add(k); keywords.append(k)
    return {"title": title, "keywords": keywords[:49], "source": "dummy"}


def _parse_raw(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return _clean_metadata(json.loads(raw))


def _gemini_attempt(api_key, b64):
    for model in GEMINI_CHAIN:
        url = f"{GEMINI_BASE}/{model}:generateContent"
        payload = {"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096}}
        for try_ in range(2):                      # retry 1x kalau JSON terpotong
            try:
                r = requests.post(url, headers={"x-goog-api-key": api_key},
                                  json=payload, timeout=60)
                if r.status_code != 200:
                    log.warning(f"Gemini {model} → HTTP {r.status_code}, next")
                    break
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return _parse_raw(raw), f"gemini:{model}"
            except requests.exceptions.RequestException as e:
                log.warning(f"Gemini {model} network: {e}")
                break
            except Exception as e:
                log.warning(f"Gemini {model} JSON terpotong → retry sekali")
    return None, None


def _openai_compat_attempt(url, key, models, b64, tag, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    payload = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        "temperature": 0.3}
    for model in models:
        payload["model"] = model
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code != 200:
                log.warning(f"{tag} {model} → HTTP {r.status_code}, next"); continue
            return _parse_raw(r.json()["choices"][0]["message"]["content"]), f"{tag}:{model}"
        except Exception as e:
            log.warning(f"{tag} {model} error: {e}")
    return None, None

import functools

@functools.lru_cache(maxsize=1)
def _discover_groq(key: str):
    """Tanya langsung ke Groq model vision apa yang HIDUP hari ini."""
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
        vision = [i for i in ids if any(k in i.lower()
                  for k in ("vision", "llama-4", "scout", "maverick", "pixtral"))]
        log.info(f"Groq vision models detected: {vision or ids[:3]}")
        return vision or ids[:3]
    except Exception as e:
        log.warning(f"Groq discovery gagal: {e}")
        return GROQ_MODELS

@functools.lru_cache(maxsize=1)

def _discover_openrouter():
    """Ambil model :free yang punya vision dari OpenRouter."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
        free_vision = [i for i in ids if i.endswith(":free")
                       and any(k in i.lower() for k in ("vl", "vision", "pixtral"))]
        log.info(f"OpenRouter free vision models: {free_vision[:3]}")
        return free_vision or OPENROUTER_MODELS
    except Exception as e:
        log.warning(f"OpenRouter discovery gagal: {e}")
        return OPENROUTER_MODELS

@benchmark
def generate_metadata(image_path: Path, retries: int = 1) -> dict:
    cache_dir = cfg.CACHE_DIR / "metadata"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{_image_hash(image_path)}.json"
    if cf.exists():
        log.info(f"Metadata cache hit: {image_path.name}")
        return json.loads(cf.read_text())

    gkey = os.getenv("GEMINI_API_KEY")
    groq = os.getenv("GROQ_API_KEY")
    mist = os.getenv("MISTRAL_API_KEY")
    orkey = os.getenv("OPENROUTER_API_KEY")
    if not any([gkey, groq, mist, orkey]):
        log.warning("Tidak ada API key → dummy metadata")
        return _dummy_metadata(image_path.stem)

    b64 = base64.b64encode(_compress_image(image_path)).decode()
    log.info(f"Payload size: {len(b64) * 3 // 4 // 1024} KB (compressed)")

    attempts = []
    if gkey:  attempts.append(("Gemini",     lambda: _gemini_attempt(gkey, b64)))
        # Groq disabled: free tier tidak punya model vision lagi (decommissioned 2026)
    if orkey: attempts.append(("OpenRouter", lambda: _openai_compat_attempt(
        OPENROUTER_URL, orkey, _discover_openrouter(), b64, "openrouter",
        extra_headers={"HTTP-Referer": "https://github.com/hanifwidi/pipelinetracing2",
                       "X-Title": "VectorFactoryV2"})))

    for name, fn in attempts:
        meta, via = fn()
        if meta:
            meta["source"] = "ai"
            meta["provider"] = via
            cf.write_text(json.dumps(meta, indent=2))
            log.info(f"Metadata via {via}: {image_path.name} ({len(meta['keywords'])} kw)")
            return meta
        log.warning(f"Provider {name} gagal → lompat ke provider berikutnya")

    log.warning("Semua provider gagal → metadata dummy")
    return _dummy_metadata(image_path.stem)