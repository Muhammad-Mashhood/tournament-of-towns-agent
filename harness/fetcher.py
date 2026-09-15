"""
fetcher.py — HTTP fetch with disk caching and retry.

Cache key = SHA-256 of URL → stored in cache/<hex>.{json,bin}
The API key is never passed here; only public archive URLs are fetched.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Tuple

import requests

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "TournamentOfTownsArchiveAgent/1.0 "
        "(academic research; contact: see README)"
    )
})

MAX_RETRIES = 4
RETRY_BACKOFF = [2, 5, 15, 30]  # seconds


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _cache_path(url: str, ext: str = "bin") -> Path:
    return CACHE_DIR / f"{_cache_key(url)}.{ext}"


def _save_cache(url: str, content: bytes, content_type: str) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(url, "bin").write_bytes(content)
    _cache_path(url, "meta.json").write_text(
        json.dumps({"url": url, "content_type": content_type}), encoding="utf-8"
    )


def _load_cache(url: str) -> Tuple[bytes, str, bool]:
    """Returns (content, content_type, from_cache=True) or raises FileNotFoundError."""
    meta_path = _cache_path(url, "meta.json")
    bin_path = _cache_path(url, "bin")
    if meta_path.exists() and bin_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return bin_path.read_bytes(), meta.get("content_type", ""), True
    raise FileNotFoundError(f"No cache for {url}")


def fetch(url: str, force_refresh: bool = False) -> Tuple[bytes, str, bool]:
    """
    Fetch a URL with caching and retry.

    Returns:
        (content_bytes, content_type, from_cache)
    Raises:
        requests.HTTPError on non-retryable failure
    """
    if not force_refresh:
        try:
            return _load_cache(url)
        except FileNotFoundError:
            pass

    last_exc = None
    for attempt, wait in enumerate(RETRY_BACKOFF, 1):
        try:
            resp = SESSION.get(url, timeout=30)
            if resp.status_code == 404:
                raise requests.HTTPError(f"404 Not Found: {url}", response=resp)
            if resp.status_code in (429, 503, 502):
                print(f"  [fetcher] HTTP {resp.status_code}, waiting {wait}s (attempt {attempt})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.content
            content_type = resp.headers.get("Content-Type", "")
            _save_cache(url, content, content_type)
            return content, content_type, False
        except requests.HTTPError:
            raise
        except requests.RequestException as e:
            last_exc = e
            print(f"  [fetcher] Request error: {e}, waiting {wait}s (attempt {attempt})")
            time.sleep(wait)

    raise last_exc or RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts")


def fetch_text(url: str, encoding: str = "utf-8", **kwargs) -> str:
    """Convenience wrapper that returns decoded text."""
    content, _, _ = fetch(url, **kwargs)
    return content.decode(encoding, errors="replace")
