"""cache.py: remember answers from outside services.

Looking up a town or the places around it takes a second or more, and the free
services SAM uses ask apps not to send the same question twice. So every answer
is kept in memory and in data/cache/ (one small JSON file each).

If a service is down, an old answer is used instead of failing. That also means
a search that worked once keeps working without internet, which is handy for a
demo on shaky Wi-Fi.
"""

import hashlib
import json
import os
import threading
import time

import database

CACHE_DIR = database.DATA_DIR / "cache"
MAX_IN_MEMORY = 500

HOUR = 60 * 60
DAY = 24 * HOUR

_memory = {}  # key -> (time saved, value)
_lock = threading.Lock()


def _file(key):
    return CACHE_DIR / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")


def get(key):
    """(value, age in seconds) for a remembered answer, or (None, None)."""
    with _lock:
        hit = _memory.get(key)
    if hit is None:
        try:
            saved = json.loads(_file(key).read_text(encoding="utf-8"))
            hit = (float(saved["at"]), saved["value"])
        except (OSError, ValueError, KeyError, TypeError):
            return None, None
        _keep(key, hit)
    return hit[1], time.time() - hit[0]


def put(key, value):
    hit = (time.time(), value)
    _keep(key, hit)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _file(key).with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": hit[0], "value": value}), encoding="utf-8")
        os.replace(tmp, _file(key))
    except OSError:
        pass  # The disk copy is a bonus. SAM still works from memory.


def _keep(key, hit):
    with _lock:
        if len(_memory) >= MAX_IN_MEMORY:
            for old in sorted(_memory, key=lambda k: _memory[k][0])[: MAX_IN_MEMORY // 5]:
                del _memory[old]
        _memory[key] = hit


def remember(key, max_age, fetch):
    """The remembered answer if it's newer than max_age seconds, otherwise fetch() (and remember that).

    If fetch() fails and there is an older answer, the older answer is returned.
    If there isn't one, the error is raised for the caller to handle.
    """
    value, age = get(key)
    if value is not None and age <= max_age:
        return value
    try:
        fresh = fetch()
    except Exception:
        if value is not None:
            return value
        raise
    put(key, fresh)
    return fresh
