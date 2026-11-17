"""sam_ai.py: SAM's AI model and SAM's web search.

Model:   NVIDIA Nemotron through NVIDIA's API (get a free key at build.nvidia.com).
         Set NVIDIA_API_KEY. NEMOTRON_MODEL picks the model.
         To use a model running on your own computer instead, point NVIDIA_BASE_URL
         at any server that speaks the same chat API, and set NEMOTRON_MODEL to match.
Search:  Tavily (TAVILY_API_KEY) or Brave Search (BRAVE_API_KEY), whichever is set.

The keys are read on the server and never sent to the browser.

This file only sends messages and returns text. What SAM says, and the rules it
follows, are decided in assistants/concepts.py and assistants/code_translator.py.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
SEARCH_CACHE_SECONDS = 6 * 60 * 60

UNSAFE = re.compile(r"porn|xxx|nsfw|onlyfans|casino|gambl|betting|escort|hookup", re.I)

# What can go wrong with a request: no connection, a timeout, an error status
# (all OSError), or a reply that isn't shaped the way SAM expected.
_REQUEST_ERRORS = (OSError, ValueError, KeyError, IndexError, TypeError)

_search_cache = {}


class ModelError(Exception):
    """The AI model couldn't be reached, or sent back something unusable."""


def chat_configured():
    return bool(os.environ.get("NVIDIA_API_KEY", "").strip())


def search_configured():
    return bool(os.environ.get("TAVILY_API_KEY", "").strip() or os.environ.get("BRAVE_API_KEY", "").strip())


def model_name():
    return os.environ.get("NEMOTRON_MODEL", "").strip() or DEFAULT_MODEL


def _http_json(url, payload=None, headers=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    all_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        all_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=all_headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def _clip(text, limit=300):
    text = re.sub(r"<[^>]+>", "", " ".join(str(text or "").split()))
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


# ---------- The model ----------

def complete(messages, max_tokens=900, temperature=0.6):
    """Send a conversation to the model and return its reply as text.

    messages is a list like [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}].
    Raises ModelError if the model can't be reached or replies with nothing.
    """
    payload = {
        "model": model_name(),
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        # Nemotron 3 models can "think" first. Turned off: faster replies.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    url = (os.environ.get("NVIDIA_BASE_URL", "").strip() or NVIDIA_URL).rstrip("/") + "/chat/completions"
    auth = {"Authorization": f"Bearer {os.environ.get('NVIDIA_API_KEY', '').strip()}"}
    try:
        try:
            data = _http_json(url, payload, auth, timeout=90)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise
            payload.pop("chat_template_kwargs")  # This model doesn't take that setting; ask again without it.
            data = _http_json(url, payload, auth, timeout=90)
        text = without_thinking(data["choices"][0]["message"].get("content") or "")
    except _REQUEST_ERRORS as e:
        detail = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
        print(f"[SAM] The AI model request failed: {e} {detail}")
        raise ModelError(str(e)) from e
    if not text:
        raise ModelError("The model sent back an empty reply.")
    return text


def without_thinking(text):
    """Drop a model's private reasoning, which some models wrap in <think> tags."""
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)  # A reasoning block with no opening tag
    return text.strip()


# ---------- Web search ----------

def web_search(query, count=5):
    """Search the web. Returns [{"title", "url", "text"}], or [] if search isn't set up or fails."""
    query = " ".join(str(query).split())[:300]
    if not query or not search_configured():
        return []
    hit = _search_cache.get((query, count))
    if hit and time.time() - hit[0] < SEARCH_CACHE_SECONDS:
        return hit[1]
    try:
        found = _tavily(query, count) if os.environ.get("TAVILY_API_KEY", "").strip() else _brave(query, count)
    except _REQUEST_ERRORS as e:
        print(f"[SAM] Web search failed for {query!r}: {e}")
        return []
    results = [
        r for r in found
        if r["url"].startswith(("https://", "http://")) and not UNSAFE.search(r["url"] + " " + r["title"])
    ][:count]
    _search_cache[(query, count)] = (time.time(), results)
    return results


def web_search_many(queries, count=3):
    """Run several searches at once (much faster than one after another)."""
    if not queries:
        return []
    with ThreadPoolExecutor(max_workers=min(6, len(queries))) as pool:
        return list(pool.map(lambda q: web_search(q, count), queries))


def _tavily(query, count):
    key = os.environ["TAVILY_API_KEY"].strip()
    data = _http_json("https://api.tavily.com/search", {"query": query, "max_results": count, "search_depth": "basic"},
                      {"Authorization": f"Bearer {key}"}, timeout=20)
    return [{"title": _clip(r.get("title") or r["url"], 120), "url": r["url"], "text": _clip(r.get("content"))}
            for r in data.get("results", [])]


def _brave(query, count):
    key = os.environ["BRAVE_API_KEY"].strip()
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": count, "safesearch": "strict"})
    data = _http_json(url, headers={"X-Subscription-Token": key}, timeout=20)
    return [{"title": _clip(r.get("title") or r["url"], 120), "url": r["url"], "text": _clip(r.get("description"))}
            for r in data.get("web", {}).get("results", [])]
