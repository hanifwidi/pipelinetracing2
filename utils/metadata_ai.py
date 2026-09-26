"""Bounded vision requests, relevant metadata, and versioned atomic caches."""
import base64
import hashlib
import functools
import io
import json
import math
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
_cooldowns = {}
_disabled = {}
_provider_locks = {}


class ProviderUnavailable(requests.RequestException):
    """Safe diagnostic, without request URLs, credentials, or response echoes."""


def _gemini_models():
    primary = os.getenv("GEMINI_MODEL", cfg.GEMINI_MODEL)
    fallback = os.getenv("GEMINI_FALLBACK_MODELS")
    models = fallback.split(",") if fallback is not None else cfg.GEMINI_FALLBACK_MODELS
    return list(dict.fromkeys(m.strip().removeprefix("models/")
                             for m in [primary, *models] if m.strip()))


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
    salt = PROMPT_VERSION + ",".join(_gemini_models()) + os.getenv("OPENROUTER_MODEL", "auto")
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
    while True:
        with _rate_lock:
            now = time.monotonic()
            delay = _next_request.get(provider, now) - now
            if delay <= 0:
                _next_request[provider] = now + interval
                return
        _sleep(delay)


def _sleep(seconds):
    # Interruptible waits, even when the server requests more than a minute.
    while seconds > 0:
        chunk = min(seconds, 30.0)
        time.sleep(chunk)
        seconds -= chunk


def _error(response):
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return error if isinstance(error, dict) else {}
    except (ValueError, TypeError):
        return {}


def _violations(response):
    details = _error(response).get("details", [])
    return [v for d in details if isinstance(d, dict)
            for v in d.get("violations", []) if isinstance(v, dict)] if isinstance(details, list) else []


def _long_quota(response):
    for v in _violations(response):
        label = (str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))).lower()
        if "perday" in label or "per_day" in label:
            return "daily quota exhausted"
        if str(v.get("quotaValue", "")) == "0":
            return "quota is zero"
    if re.search(r"\b(?:per day|daily quota)\b", str(_error(response).get("message", "")), re.I):
        return "daily quota exhausted"
    return None


def _quota_scope(provider, model_key, response):
    # A quota without model dimensions may be shared across all models.
    violations = _violations(response)
    if violations and all(isinstance(v.get("quotaDimensions"), dict)
                          and v["quotaDimensions"].get("model") for v in violations):
        return model_key
    return provider


def _retry_delay(response, attempt):
    delays = []
    def add(value):
        try:
            number = float(value)
            if math.isfinite(number):
                delays.append(max(0.0, number))
        except (ValueError, TypeError):
            pass
    if response is not None:
        value = response.headers.get("Retry-After", "")
        add(value)
        if value and not delays:
            try:
                add(parsedate_to_datetime(value).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
        error = _error(response)
        details = error.get("details", [])
        for detail in details if isinstance(details, list) else []:
            if not isinstance(detail, dict):
                continue
            duration = detail.get("retryDelay", "")
            if isinstance(duration, str) and duration.endswith("s"):
                add(duration[:-1])
            elif isinstance(duration, dict):
                try:
                    add(float(duration.get("seconds", 0)) + float(duration.get("nanos", 0)) / 1e9)
                except (ValueError, TypeError):
                    pass
        match = re.search(r"retry\s+(?:in|after)\s+([\d.]+)\s*s", str(error.get("message", "")), re.I)
        if match:
            add(match[1])
    # Never truncate the server's requested wait (the old 30-second cap did).
    return max(delays) if delays else min(60.0, 2.0 ** min(attempt, 6))


def _post(provider, url, headers, payload, retries):
    model = payload.get("model") or url.rsplit("/", 1)[-1].split(":", 1)[0]
    key = (provider, model)
    with _rate_lock:
        lock = _provider_locks.setdefault(provider, threading.Lock())
    # Serialize each provider, including retries: queued workers cannot bypass
    # a cooldown learned by another request. Different providers stay independent.
    with lock:
        for scope in (provider, key):
            if scope in _disabled:
                raise ProviderUnavailable(_disabled[scope])
            remaining = _cooldowns.get(scope, 0) - time.monotonic()
            if remaining > 0:
                raise ProviderUnavailable(f"cooldown active for {remaining:.1f}s")
        waited = 0.0
        for attempt in range(max(0, retries) + 1):
            _pace(provider)
            response = None
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=cfg.AI_TIMEOUT)
            except requests.RequestException as exc:
                reason = type(exc).__name__
                delay = _retry_delay(None, attempt)
            else:
                status = response.status_code
                if 200 <= status < 300:
                    return response.json()
                reason = f"HTTP {status}"
                if status in (401, 403):
                    _disabled[provider] = reason + " (check credentials/access)"
                    raise ProviderUnavailable(_disabled[provider])
                if status == 404:
                    _disabled[key] = reason + " (model unavailable)"
                    raise ProviderUnavailable(_disabled[key])
                if status != 429 and not 500 <= status < 600:
                    raise ProviderUnavailable(reason)
                quota = _long_quota(response) if status == 429 else None
                scope = _quota_scope(provider, key, response) if status == 429 else key
                if quota:
                    _disabled[scope] = reason + " (" + quota + "; skipped for this run)"
                    raise ProviderUnavailable(_disabled[scope])
                delay = _retry_delay(response, attempt)
                _cooldowns[scope] = max(_cooldowns.get(scope, 0), time.monotonic() + delay)
            if attempt >= retries or waited + delay > cfg.AI_MAX_RETRY_WAIT:
                # Avoid retry storms across the rest of a failing batch.
                scope = _quota_scope(provider, key, response) if response is not None and response.status_code == 429 else key
                _cooldowns[scope] = max(_cooldowns.get(scope, 0), time.monotonic() + max(delay, 30.0))
                raise ProviderUnavailable(reason + " (retry budget exhausted; fallback next)")
            log.warning("%s/%s: %s; retry %d/%d in %.2fs", provider, model, reason, attempt + 1, retries, delay)
            _sleep(delay)
            waited += delay


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


def _diagnostic(exc):
    if isinstance(exc, ProviderUnavailable):
        return str(exc)
    response = getattr(exc, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


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
        for model in _gemini_models():
            try:
                body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}}, {"text": PROMPT}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048, "responseMimeType": "application/json"}}
                data = _post("gemini", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": gemini}, body, retries)
                text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought"))
                meta = {**_parse_raw(text), "source": "ai", "provider": f"gemini:{model}", "prompt_version": PROMPT_VERSION}
                write_json(cache, meta)
                return meta
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                diagnostic = f"Gemini/{model}: {_diagnostic(exc)}"
                errors.append(diagnostic)
                log.warning("%s", diagnostic)
                if "gemini" in _disabled or _cooldowns.get("gemini", 0) > time.monotonic():
                    break
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
                    errors.append(f"OpenRouter/{model}: {_diagnostic(exc)}")
                    if "openrouter" in _disabled or _cooldowns.get("openrouter", 0) > time.monotonic():
                        break
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            errors.append("Model discovery: " + _diagnostic(exc))
    reason = "; ".join(errors) or "No available vision model"
    log.warning("Metadata pending: %s", reason)
    return _dummy_metadata(filename or image_path.stem, reason)
