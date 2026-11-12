"""sam_ai.py: chatting with SAM, and SAM's web search.

Chat:    NVIDIA Nemotron through NVIDIA's API (get a key at build.nvidia.com).
         Set NVIDIA_API_KEY. NEMOTRON_MODEL picks the model.
Search:  Tavily (TAVILY_API_KEY) or Brave Search (BRAVE_API_KEY), whichever is set.

The keys are read on the server and never sent to the browser.
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
HISTORY_TURNS = 12

SYSTEM_PROMPT = """You are SAM, the Student Assistant Machine. You help middle and high school students learn, and find sports and volunteering opportunities near them.

How you help:
- Never give the final answer to a homework, test or assignment question, and never write essays, code or assignments for the student. Teach instead: explain the idea with a different example, give a hint, ask a guiding question, or point out where to look in their own work. If they ask for the answer, kindly say you can't hand it over, then help them take the next step.
- Answer everyday questions directly: study habits, planning, careers, clubs, sports and volunteering.
- Use the web results when they help, and cite them like [1] or [2]. Only cite results you were given. Never make up links, places, dates or prices. If you don't know a detail, say so and suggest how to check.
- For anything local, use the student's area.
- Keep it short: under 160 words, friendly and encouraging, at the student's age level. Write plain text in short paragraphs. Use a numbered list only for steps. No headings, tables or bold text.
- Keep everything safe and age-appropriate. If a student mentions self-harm, abuse or being in danger, tell them to talk to a trusted adult right away, and that in the US they can call or text 988 any time."""

LOCAL_WORDS = re.compile(r"\b(near|nearby|local|around|area|town|city|teams?|leagues?|clubs?|clinics?|camps?|tryouts?|volunteer\w*|program\w*|class(es)?|tutor\w*|events?|library|libraries)\b", re.I)
UNSAFE = re.compile(r"porn|xxx|nsfw|onlyfans|casino|gambl|betting|escort|hookup", re.I)

_search_cache = {}


def chat_configured():
    return bool(os.environ.get("NVIDIA_API_KEY", "").strip())


def search_configured():
    return bool(os.environ.get("TAVILY_API_KEY", "").strip() or os.environ.get("BRAVE_API_KEY", "").strip())


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
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as e:
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


# ---------- Chat ----------

def _profile(prefs):
    parts = []
    if prefs.get("age"):
        parts.append(f"age {prefs['age']}")
    if prefs.get("loc", "").strip():
        parts.append(f"lives in or near {prefs['loc'].strip()}")
    sports = [s for s in prefs.get("sports", []) if s != "Other"] + ([prefs["sportOther"]] if prefs.get("sportOther") else [])
    if prefs.get("playsSports") == "yes" and sports:
        parts.append("interested in " + ", ".join(sports))
        if prefs.get("gender") in ("female", "male"):
            parts.append(f"for sports programs, prefers {'girls' if prefs['gender'] == 'female' else 'boys'} or co-ed teams")
    vol = [v for v in prefs.get("vol", []) if v != "Other"] + ([prefs["volOther"]] if prefs.get("volOther") else [])
    if vol:
        parts.append("wants to volunteer with " + ", ".join(vol))
    return "About the student: " + ("; ".join(parts) if parts else "no details yet") + "."


def search_query(message, prefs):
    """What SAM searches for: the student's question, plus their area if it's about something local."""
    loc = prefs.get("loc", "").strip()
    return f"{message} near {loc}" if loc and LOCAL_WORDS.search(message) else message


def _clean(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)  # A reasoning block with no opening tag
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"^#{1,6}[ \t]*", "", text, flags=re.M)
    text = re.sub(r"^[ \t]*[-*][ \t]+", "• ", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def ask(message, history, prefs):
    """Ask Nemotron. history is the earlier chat: [{"role": "user"|"sam", "text"}].

    Returns {"text", "sources": [{"n", "title", "url"}]}. On failure, "error" is True.
    """
    results = web_search(search_query(message, prefs), 5)
    listed = "\n".join(f"[{i}] {r['title']} ({r['url']}): {r['text']}" for i, r in enumerate(results, 1))
    system = f"{SYSTEM_PROMPT}\n\n{_profile(prefs)}\n\nWeb results for this question:\n{listed or 'None. Answer from what you know, and do not cite sources.'}"
    messages = [{"role": "system", "content": system}]
    for m in history[-HISTORY_TURNS:]:
        messages.append({"role": "assistant" if m["role"] == "sam" else "user", "content": m["text"]})
    messages.append({"role": "user", "content": message})

    payload = {
        "model": os.environ.get("NEMOTRON_MODEL", "").strip() or DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 900,
        # Nemotron 3 models can "think" first. Turned off: faster replies for chat.
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
        text = _clean(data["choices"][0]["message"].get("content") or "")
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as e:
        detail = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
        print(f"[SAM] Nemotron request failed: {e} {detail}")
        return {"text": "SAM couldn’t reach its AI model just now. Wait a moment and send your message again.", "sources": [], "error": True}

    if not text:
        text = "Sorry, I lost my train of thought. Could you ask that again?"
    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", text) if 1 <= int(n) <= len(results)})
    shown = cited or list(range(1, min(3, len(results)) + 1))
    sources = [{"n": n if cited else None, "title": results[n - 1]["title"], "url": results[n - 1]["url"]} for n in shown]
    return {"text": text, "sources": sources}
