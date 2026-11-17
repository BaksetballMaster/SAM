"""concepts.py: one turn of the Concept helper, from the student's message to SAM's reply.

How a message travels. The chat page calls ask() through api.ask_sam:

    the student's message
      |
      |  guardrails.inspect()      What kind of message is this? A request for an
      |  guardrails.carry_over()   answer, a request to write the work, a concept
      |                            question, an everyday question ...
      |        "crisis" -> SAM shows guardrails.SAFETY_REPLY and stops. No model.
      |
      |  retrieval.retrieve()      Gather sources: the web, Wikipedia, SAM's library.
      |
      |  guardrails.rewrite()      A flagged message is wrapped in coaching
      |                            instructions before the model sees it.
      |
      |  sam_ai.complete()         Nemotron writes a reply from RULES + the sources.
      |
      |  guardrails.review()       Read the reply. If it gives an answer away it is
      |                            rejected: one retry, then guardrails.coach_reply().
      v
    a reply for the page: Markdown text, optional deep dives, numbered sources,
    and a note telling the student when SAM coached instead of answering.

Without NVIDIA_API_KEY the model steps are skipped. SAM still inspects the
message and gathers sources, then replies from _without_model(): guiding
questions, plus what the sources say. So the no-answers rule holds in demo mode too.
"""

import re

import sam_ai

from . import guardrails, retrieval

HISTORY_TURNS = 12

RULES = """You are SAM, the Student Assistant Machine: a study coach for middle and high school students.

Rules you never break:
1. Never give the final answer to a homework, quiz, test or assignment question, and never write a student's essay, paragraph, code or project for them. Coach instead: name the idea being tested, ask what they have tried, give one hint for the next step, and check their thinking. If they share their own answer, tell them whether it is right and why.
2. Explaining a concept is always fine. Use a fresh example with different numbers, never the student's exact problem.
3. Everyday questions (study habits, planning, careers, friends, money, clubs, sports, volunteering) get direct, practical answers.
4. Build on the sources below when they help, and cite them like [1] or [2]. Only cite sources you were given. Never make up links, places, dates or prices. If you don't know a detail, say so and suggest how to check.
5. Keep everything safe and age-appropriate. If a student mentions self-harm, abuse or being in danger, tell them to talk to a trusted adult right away, and that in the US they can call or text 988 any time.

SAM also has a Volunteer finder (/volunteer) and a Sports tracker (/sports) that show real places near the student. Point to them for anything local instead of guessing at places.

How to write: friendly and encouraging, at the student's level. Use Markdown: short paragraphs, **bold** for key terms, numbered lists for steps. Keep the main reply under 150 words and end it with one question that moves the student forward.
After the main reply you may add up to two optional sections for students who want more. Start each on its own line with "### Deep dive: <short title>" and keep each under 120 words."""

_DEEP_DIVE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*Deep dive[ \t]*:?[ \t]*(.*)$", re.I | re.M)


def ask(message, history, prefs):
    """Answer one chat message. history is the earlier chat: [{"role": "user" | "sam", "text"}]."""
    earlier = [m["text"] for m in history if m["role"] == "user"]
    verdict = guardrails.carry_over(guardrails.inspect(message), message, earlier)
    if verdict.kind == "crisis":
        return _reply(guardrails.SAFETY_REPLY, [], verdict, "safety")

    sources = retrieval.retrieve(message, verdict, prefs)
    if not sam_ai.chat_configured():
        return _reply(_without_model(verdict, sources, prefs), sources, verdict, "demo")
    try:
        text = _with_model(message, history, prefs, verdict, sources)
    except sam_ai.ModelError:
        reply = _reply("SAM couldn’t reach its AI model just now. Wait a moment and send your message again.", [], verdict, "error")
        reply.update(error=True, guard="")
        return reply
    return _reply(text, sources, verdict, "model")


def _with_model(message, history, prefs, verdict, sources):
    """Ask Nemotron, then check its reply against the guardrail before anyone sees it."""
    listed = "\n".join(f"[{n}] {s['title']} ({s['url']}): {s['text']}" for n, s in enumerate(sources, 1))
    system = f"{RULES}\n\n{_about(prefs)}\n\nSources:\n{listed or 'None. Answer from what you know, and do not cite sources.'}"
    turns = [{"role": "system", "content": system}]
    for earlier in history[-HISTORY_TURNS:]:
        turns.append({"role": "assistant" if earlier["role"] == "sam" else "user", "content": earlier["text"]})
    turns.append({"role": "user", "content": guardrails.rewrite(message, verdict)})

    text = sam_ai.complete(turns)
    problems = guardrails.review(text, verdict, message)
    if problems:
        print(f"[SAM] The guardrail rejected a reply because {'; '.join(problems)}. Asking again.")
        try:
            text = sam_ai.complete(turns + [{"role": "assistant", "content": text},
                                            {"role": "user", "content": guardrails.retry_note(problems)}])
        except sam_ai.ModelError:
            text = ""
        if not text or guardrails.review(text, verdict, message):
            text = guardrails.coach_reply(verdict)  # The last line of defence: no model involved
    return text


def _about(prefs):
    """What the model is told about the student. Only survey answers, never a name or email."""
    parts = []
    if prefs.get("age"):
        parts.append(f"age {prefs['age']}")
    if str(prefs.get("loc") or "").strip():
        parts.append(f"lives in or near {prefs['loc'].strip()}")
    sports = [s for s in prefs.get("sports", []) if s != "Other"] + ([prefs["sportOther"]] if prefs.get("sportOther") else [])
    if prefs.get("playsSports") == "yes" and sports:
        parts.append("interested in " + ", ".join(sports))
    volunteering = [v for v in prefs.get("vol", []) if v != "Other"] + ([prefs["volOther"]] if prefs.get("volOther") else [])
    if volunteering:
        parts.append("wants to volunteer with " + ", ".join(volunteering))
    return "About the student: " + ("; ".join(parts) if parts else "no details yet") + "."


def _without_model(verdict, sources, prefs):
    """SAM's reply when no AI model is connected: guiding questions, plus what the sources say."""
    if verdict.coach:
        text = guardrails.coach_reply(verdict)
        if sources:
            text += "\n\n### Deep dive: Where to read about this\n" + "\n".join(f"- {s['title']}: {s['text']} [{n}]" for n, s in enumerate(sources, 1))
        return text
    if verdict.kind == "near_me":
        where = str(prefs.get("loc") or "").strip() or "you"
        return (f"SAM's finders search real places near {where}:\n\n"
                "- [Volunteer finder](/volunteer): places to volunteer, with distance and opening hours\n"
                "- [Sports tracker](/sports): places to play and train, on a map\n\n"
                "What are you hoping to find?")
    if verdict.kind == "life":
        text = ("That's worth working on. Here's a way to start:\n\n"
                "1. **Name the real problem.** What exactly is getting in the way?\n"
                "2. **Pick one small step** you could do today in ten minutes or less.\n"
                "3. **Decide when** you'll do it, and tell someone your plan.\n\n"
                "What's the one thing that would make this week easier?")
    else:
        passage = next(((n, s) for n, s in enumerate(sources, 1) if s["source"] != "SAM's library"), None)
        if passage:
            n, source = passage
            text = (f"Here's a place to start, from {source['title']} [{n}]:\n\n> {source['text']}\n\n"
                    "Now make it yours:\n\n"
                    "1. **Say it in your own words.** What is the main idea, in one sentence?\n"
                    "2. **Find the fuzzy part.** Which word or step doesn't make sense yet?\n"
                    "3. **Test yourself.** How would you explain it to a friend?\n\n"
                    "Which part should we dig into first?")
        else:
            text = ("Let's work through it together. What subject is this, and which part feels confusing?\n\n"
                    "Tell me what you already understand, and I'll ask you a question to take the next step.")
    more = [(n, s) for n, s in enumerate(sources, 1) if s["source"] == "SAM's library"]
    if more:
        text += "\n\n### Deep dive: Places to learn more\n" + "\n".join(f"- {s['title']}: {s['text']} [{n}]" for n, s in more)
    return text


def split_deep_dives(text):
    """Split a reply into its main part and its "### Deep dive: title" sections."""
    marks = list(_DEEP_DIVE.finditer(text))
    if not marks:
        return text.strip(), []
    dives = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[mark.end():end].strip()
        if body:
            dives.append({"title": mark.group(1).strip(" *#:") or "More detail", "body": body})
    return text[:marks[0].start()].strip(), dives


def _reply(text, sources, verdict, mode):
    """Package a reply for the page. Sources keep their numbers so [2] in the text points at source 2."""
    main, dives = split_deep_dives(text)
    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", text) if 1 <= int(n) <= len(sources)})
    numbers = cited or list(range(1, min(3, len(sources)) + 1))
    return {
        "role": "sam",
        "text": text,
        "main": main,
        "deep_dives": dives,
        "sources": [{"n": n, "cited": bool(cited), **sources[n - 1]} for n in numbers],
        # Shown to the student, so they know SAM coached on purpose. Not repeated on follow-ups.
        "guard": verdict.reason if verdict.coach and not verdict.follow_up else "",
        "mode": mode,
        "error": False,
    }
