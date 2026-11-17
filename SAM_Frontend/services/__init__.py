"""services: the code that talks to outside services, and a few shared tools.

    web.py        fetch JSON from another site, politely (named client, timeouts)
    cache.py      remember answers in memory and on disk, so SAM asks each thing once
    geo.py        "Town or ZIP code" -> a point on the map, and distances in miles
    places.py     real places near a point, from OpenStreetMap, with opening hours
    wikipedia.py  short article introductions, used as sources by the Concept helper
    richtext.py   turn the AI's Markdown into safe HTML

None of these files know about Flask or the pages. The assistants/ folder uses
them to build each assistant's answers.
"""
