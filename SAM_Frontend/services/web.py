"""web.py: fetch JSON from another site.

Every request names SAM's client (the User-Agent), asks for JSON and gives up
after a few seconds, so a slow service can never freeze a page. Nothing about
the student is ever put in a header.

Set SAM_USER_AGENT in .env to name your own deployment, for example
"sam-yourschool/1.0 (https://your-site.example)".
"""

import json
import os
import urllib.parse
import urllib.request

USER_AGENT = os.environ.get("SAM_USER_AGENT", "").strip() or "student-resource-finder/1.0 (school project)"

# What can go wrong with a request: no connection, a timeout, an error status
# (all OSError), or a reply that isn't the JSON SAM expected.
FETCH_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError)


def get_json(url, params=None, timeout=12):
    """GET a URL and return its JSON. Raises one of FETCH_ERRORS if it can't."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "en",
    })
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.load(reply)
