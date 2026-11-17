"""assistants: the thinking behind SAM's four assistants.

    volunteer.py        Volunteer finder: real places to volunteer near the student
    sports.py           Sports tracker: places to play and train, and clinic listings
    concepts.py         Concept helper: one chat turn, from question to coached reply
    guardrails.py         the rules that stop SAM handing over answers
    retrieval.py          the sources SAM reads before it replies
    code_translator.py  Code translator: what each line does, and pseudocode

Nothing in this folder knows about Flask or HTML. Each file takes plain values
(a message, a location, some code) and returns plain dicts and lists. The pages
call them through api.py, so they can be tested without a browser.
"""
