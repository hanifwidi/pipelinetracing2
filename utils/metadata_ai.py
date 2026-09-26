"""Bounded vision requests, relevant metadata, and versioned atomic caches."""
import base64
import hashlib
import functools
import io
import json
import os
import re
import threading
import time
from pathlib import Path
from email.utils import parsedate_to_datetime
import requests
from PIL import Image
from config import cfg
from utils.atomic_io import read_json, write_json
from utils.logger import log

PROMPT_VERSION = "2026-09-relevance-v2"
PROMPT = """Describe exactly what is visible in this vector artwork for Adobe Stock.
Return JSON only: {"title": "...", "keywords": ["...", ...]}.
Write a clear English title, ideally under 70 characters, maximum 90.
Use 5 to 49 distinct lowercase keywords, only as many as the image supports.
The first ten keywords must prioritize visible subjects and the specific niche.
Describe the actual style (line, flat, silhouette, etc.) only when visible.
Use relevant buyer concepts only when supported by this particular image.
Do not pad with generic uses like banner, template, marketing, mockup or trending.
Do not invent objects, brands, names, or unseen characteristics.
A keyword can have up to three words. Avoid duplicate singular/plural variants.
Do not describe every image as an icon set if it is not one."""
_rate_lock = threading.Lock()
_next_request = {}


def _compress_image(path, max_size=1024):
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _image_hash(path):
    # Legacy helper retained for old metadata caches and callers.
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _cache_path(path):
    content = Path(path).read_bytes()
    salt = PROMPT_VERSION + os.getenv("GEMINI_MODEL", "gemini-2.5-flash") + os.getenv("OPENROUTER_MODEL", "auto")
    digest = hashlib.sha256(content + salt.encode()).hexdigest()
    return cfg.CACHE_DIR / "metadata" / (digest + ".json")


def _clean_metadata(meta):
    if not isinstance(meta, dict) or not isinstance(meta.get("title"), str) or not isinstance(meta.get("keywords"), list):
        raise ValueError("Metadata must contain a title string and keyword list")
    title = " ".join(meta["title"].split())
    if not title or len(title) > 90:
        raise ValueError("Title must contain 1 to 90 characters")
    keywords, seen = [], set()
    for item in meta["keywords"]:
        if not isinstance(item, str):
            continue
        word = " ".join(item.lower().split())
        if word and word not in seen and len(word.split()) <= 3 and "," not in word:
            keywords.append(word); seen.add(word)
        if len(keywords) == 49:
            break
    if len(keywords) < 5:
        raise ValueError("At least five valid keywords are required")
    return {"title": title, "keywords": keywords}


def _parse_raw(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return _clean_metadata(json.loads(raw))


def _dummy_metadata(filename, reason="No configured vision provider"):
    title = re.sub(r"[_-]+", " ", re.sub(r"\d{8,}", "", filename)).strip()[:90] or "Untitled vector"
    # A draft only: never silently promote to upload metadata.
    return {"title": title, "keywords": [], "source": "dummy", "reason": reason}


def _pace(provider):
    interval = 60.0 / max(1, cfg.AI_REQUESTS_PER_MINUTE)
    with _rate_lock:
        now = time.monotonic()
        reserved = max(now, _next_request.get(provider, now))
        _next_request[provider] = reserved + interval
    if reserved > now:
        time.sleep(reserved - now)


def _retry_delay(response, attempt):
    value = response.headers.get("Retry-After", "") if response is not None else ""
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            seconds = 2 ** attempt
    return max(0, min(30, seconds))


def _post(provider, url, headers, payload, retries):
    for attempt in range(retries + 1):
        _pace(provider)
        response = None
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=cfg.AI_TIMEOUT)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(_retry_delay(response, attempt)); continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt >= retries or (response is not None and response.status_code not in {429} and response.status_code < 500):
                raise
            time.sleep(_retry_delay(response, attempt))
    raise RuntimeError("Vision request exhausted retries")


@functools.lru_cache(maxsize=1)
def _openrouter_models():
    explicit = os.getenv("OPENROUTER_MODEL")
    if explicit:
        return [explicit]
    response = requests.get("https://openrouter.ai/api/v1/models", timeout=cfg.AI_TIMEOUT)
    response.raise_for_status()
    return [m["id"] for m in response.json().get("data", [])
            if m.get("id", "").endswith(":free")
            and "image" in m.get("architecture", {}).get("input_modalities", [])][:2]


def generate_metadata(image_path, retries=None, force=False, filename=None):
    image_path = Path(image_path)
    cache = _cache_path(image_path)
    if cache.exists() and not force:
        try:
            saved = read_json(cache)
            if saved.get("source") != "ai" or saved.get("prompt_version") != PROMPT_VERSION:
                raise ValueError("Stale metadata cache")
            cleaned = _clean_metadata(saved)
            return {**saved, **cleaned}
        except (ValueError, OSError, TypeError):
            log.warning("Ignoring invalid metadata cache: %s", cache.name)
    retries = cfg.AI_RETRIES if retries is None else retries
    gemini, router = os.getenv("GEMINI_API_KEY"), os.getenv("OPENROUTER_API_KEY")
    if not gemini and not router:
        return _dummy_metadata(filename or image_path.stem)
    b64 = base64.b64encode(_compress_image(image_path)).decode("ascii")
    errors = []
    if gemini:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        try:
            body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}}, {"text": PROMPT}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048, "responseMimeType": "application/json"}}
            data = _post("gemini", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": gemini}, body, retries)
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought"))
            meta = {**_parse_raw(text), "source": "ai", "provider": f"gemini:{model}", "prompt_version": PROMPT_VERSION}
            write_json(cache, meta)
            return meta
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            errors.append("Gemini: " + type(exc).__name__)
    if router:
        try:
            for model in _openrouter_models():
                try:
                    body = {"model": model, "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}], "temperature": 0.2, "max_tokens": 2048}
                    data = _post("openrouter", "https://openrouter.ai/api/v1/chat/completions", {"Authorization": f"Bearer {router}"}, body, retries)
                    meta = {**_parse_raw(data["choices"][0]["message"]["content"]), "source": "ai", "provider": f"openrouter:{model}", "prompt_version": PROMPT_VERSION}
                    write_json(cache, meta)
                    return meta
                except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                    errors.append("OpenRouter: " + type(exc).__name__)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            errors.append("Model discovery: " + type(exc).__name__)
    reason = "; ".join(errors) or "No available vision model"
    log.warning("Metadata needs review: %s", reason)
    return _dummy_metadata(filename or image_path.stem, reason)
