"""db.py: a tiny JSON-file database so SAM remembers things between restarts.

It replaces the frontend's old `fakeDB` (which lived in the browser's localStorage).
Swap this for a real database (for example Postgres or SQLite) before launch.
"""

import json
import threading
from pathlib import Path

DB_PATH = Path(__file__).with_name("sam_data.json")
_lock = threading.Lock()


def _load():
    try:
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(DB_PATH)


def get(key):
    with _lock:
        return _load().get(key)


def put(key, value):
    with _lock:
        data = _load()
        data[key] = value
        _save(data)


def prepend(key, item):
    """Add an item to the front of a list (newest first)."""
    with _lock:
        data = _load()
        data[key] = [item] + data.get(key, [])
        _save(data)
