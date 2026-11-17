"""guardrails.py: how SAM avoids doing a student's work for them.

SAM's promise is to help students learn "without explicitly providing answers
for tasks and assignments". The AI model is told that rule, but being told is
not enough: models slip. So every chat message also passes through the three
checks in this file, which are plain Python and behave the same every time.

    1. inspect(message)   BEFORE the model sees anything, decide what kind of
                          message this is. "Just give me the answer to #4" and
                          "write my essay" are flagged as requests to do the work.

    2. rewrite(message)   A flagged message is not passed on as it was typed. It
                          is wrapped in coaching instructions, so what the model
                          receives is "coach this student through it", not
                          "answer this".

    3. review(reply)      AFTER the model replies, read the reply. If it states
                          an answer, gives a value for the student's unknown,
                          contains a finished essay or finished code, or forgets
                          to ask the student a question, it is thrown away.

concepts.py runs these in order. When review() rejects a reply, the model gets
one more try with a sharper warning. If that fails too, the student sees
coach_reply(): guiding questions written here, with no model involved.

These checks look for patterns in the text, so they can't catch every possible
leak. They are a second and third line of defence behind the model's own rules.

Two more things live here because they must not depend on the model either:
SAFETY_REPLY, shown when a message suggests a student may be in danger, and
SUBJECTS, used to pick sources and to count which subjects students ask about.
"""

import re
from dataclasses import dataclass

# Subject names and the words that signal them. The first match wins.
SUBJECTS = [
    ("Math", r"\b(math\w*|algebra|equations?|geometry|calculus|fractions?|trig\w*|statistics?|percent\w*|quadratic\w*|derivatives?|integrals?|slope|polynomials?|decimals?|graph\w*)\b"),
    ("Science", r"photosynth|biolog|\bcells?\b|science|chemi|physics|\batoms?\b|ecosystem|molecul|gravity|evolution|\bdna\b"),
    ("Coding", r"\b(code|coding|program\w*|python|javascript|java|html|css|loops?|algorithms?|debug\w*)\b"),
    ("Writing and essays", r"\b(essays?|thesis|paragraphs?|writing|grammar|poems?|citations?)\b"),
    ("Test prep", r"\b(sat|psat|act|ap|exams?|finals|test prep|midterms?)\b"),
    ("History and civics", r"\b(history|civics|government|elections?|wars?|revolution|constitution)\b"),
    ("Languages", r"\b(spanish|french|hindi|mandarin|chinese|german|latin|japanese|korean|language)\b"),
]


def subject_of(message):
    """"Math", "Science", ... or "" if the message doesn't name a school subject."""
    return next((name for name, pattern in SUBJECTS if re.search(pattern, message, re.I)), "")


@dataclass
class Verdict:
    """What inspect() decided about one message."""
    kind: str           # "crisis", "answer", "write_it", "near_me", "life", "concept" or "other"
    reason: str = ""    # Why it was flagged, in words the student can read
    subject: str = ""   # From subject_of()
    variable: str = ""  # The unknown in the student's equation, for example "x"
    hint: str = ""      # Which hint coach_reply() should give
    follow_up: bool = False  # True when this message continues a flagged one (see carry_over)

    @property
    def coach(self):
        """True when SAM must coach instead of answering."""
        return self.kind in ("answer", "write_it")


# ---------- 1. Inspect: what is the student asking for? ----------

_CRISIS = re.compile(
    r"\b(kill(ing)? myself|suicid\w*|end(ing)? my (own )?life|want(ed)? to die|wish i (was|were) dead"
    r"|don'?t want to (be alive|live)|hurt(ing)? myself|self[- ]?harm\w*|cut(ting)? myself"
    r"|(hits|beats|abuses|molests|touches) me|being abused|not safe at home|afraid to go home)\b", re.I)

# Asking outright for an answer.
_ASKS_FOR_ANSWER = re.compile(
    r"\b(give|tell|show|get|send)\s+me\s+(the\s+|an?\s+|all\s+the\s+)?(final\s+|correct\s+|right\s+)?(answers?|solutions?)\b"
    r"|\bwhat(?:'s|s| is| are| would be)\s+the\s+(final\s+|correct\s+|right\s+)?(answers?|solutions?)\b"
    r"|\b(answers?|solutions?)\s+(to|for)\s+(my|the|this|these|those|number|question|problem|#|\d)"
    r"|\b(need|want)\s+(the\s+|all\s+the\s+)?(answers?|solutions?)\b"
    r"|\banswer\s+key\b"
    r"|\b(which|what)\s+(one|option|choice|letter)\s+is\s+(correct|right|the answer)\b", re.I)

# Asking SAM to produce the assignment itself.
_WRITE_IT = [
    (re.compile(r"\b(write|do|finish|complete|make|type)\s+(up\s+)?(me\s+)?(my|the|an?|this|that)\s+(\w+\s+){0,3}"
                r"(essays?|paragraphs?|homework|assignments?|reports?|papers?|projects?|speech|poem|story|worksheet"
                r"|thesis|conclusion|introduction|summary|lab)\b", re.I), "you asked SAM to write it for you"),
    (re.compile(r"\bwrite\s+(me\s+)?(a\s+|an\s+)?(\d+|one|two|three|four|five)[- ]?(word|page|paragraph|sentence)", re.I),
     "you asked SAM to write it for you"),
    (re.compile(r"\b(do|finish|write|solve|answer)\s+(it|this|these|them|that)\s+for\s+me\b", re.I),
     "you asked SAM to do it for you"),
    (re.compile(r"\b(write|give me|make|create|code)\s+(me\s+)?(the\s+|some\s+|a\s+|an\s+)?(\w+\s+){0,2}"
                r"(code|program|function|script|class|method|algorithm)\b", re.I), "you asked SAM to write the code for you"),
    (re.compile(r"\b(summar(y|ies|i[sz]e)|analy[sz]e|analysis of)\b.{0,60}\b(chapters?|act|scene|book|novel|poem|article|passage|story)\b",
                re.I | re.S), "you asked SAM to do the reading for you"),
]
# "How do I write a thesis statement?" asks how, so it is a question about a skill, not a request to write.
_ASKS_HOW = re.compile(r"\b(how (do|can|should|would|to)|what makes|tips|advice|steps (to|for)|what(?:'s| is| are))\b", re.I)

# A specific problem to work out.
_SOLVE_WORDS = re.compile(
    r"\b(solve|simplify|factor(i[sz]e)?|evaluate|calculate|compute|differentiate|integrate|expand|balance"
    r"|find\s+(the\s+)?(value|slope|area|perimeter|volume|derivative|integral|roots?|zeros?|solutions?|mean|median|mode|gcf|lcm|x|y)"
    r"|what(?:'s| is)\s+the\s+(value|slope|area|perimeter|volume|derivative|integral|sum|product|difference|quotient))\b", re.I)
_HAS_NUMBERS = re.compile(r"\d|[=^√]")
_ARITHMETIC = re.compile(
    r"\bwhat(?:'s|s| is)\s+\(?-?\d[\d.,]*\s*(%|percent)?\s*"
    r"(of|plus|minus|times|divided by|multiplied by|to the power of|over|mod|\+|-|–|\*|x|×|/|÷|\^)\s*\(?-?\d", re.I)
_EQUALS = re.compile(r"(?<![=!<>])=(?![=>])")
_CHOICE_LINE = re.compile(r"^\s*\(?[a-dA-D][).:]\s+\S", re.M)
_CHOICES_INLINE = re.compile(r"\ba[).]\s.+\bb[).]\s.+\bc[).]\s", re.I | re.S)

_NEAR_ME = re.compile(r"\b(near me|nearby|close to me|around here|in my (area|town|city|neighbou?rhood)"
                      r"|volunteer\w*|tryouts?|leagues?|clinics?|camps?|community service|service hours)\b", re.I)
_LIFE = re.compile(r"\b(stress\w*|anxious|anxiety|sleep\w*|friends?|parents?|motivat\w*|procrastinat\w*|time management"
                   r"|manage my time|organi[sz]ed?|part[- ]time job|resume|interview|college|scholarships?|careers?"
                   r"|money|budget\w*|bank account|saving|bully\w*|bullied|confiden\w*|habits?|nervous)\b", re.I)
_EXPLAIN = re.compile(r"\b(explain|understand|what (is|are|was|were|does|do|did|year|caused|happened)|how (does|do|did|is|are)"
                      r"|why (is|are|was|were|does|do|did)|who (is|was|were|invented|discovered|wrote)|when (is|was|were|did)"
                      r"|where (is|are|was|were|did)|difference between|meaning of|define|learn)\b", re.I)
# Code has "=" signs too, but "x = 5" in a program is not an equation to solve.
_LOOKS_LIKE_CODE = re.compile(r"\b(code|program|script|def|print|console|function|import|return|var|let|const)\b|[{};]|==|\+=|:=", re.I)


def _unknown(message):
    """The letter standing for the unknown in an equation, like "x" in "2x + 6 = 14". "" if there isn't one."""
    if not (_EQUALS.search(message) and re.search(r"\d", message)) or _LOOKS_LIKE_CODE.search(message):
        return ""
    with_number = re.search(r"(?<![a-z])\d+(?:\.\d+)?\s*([a-z])(?![a-z])", message, re.I)  # 2x, 3a
    if with_number:
        return with_number.group(1).lower()
    for match in re.finditer(r"(?<![a-z'])([b-hj-z])(?![a-z'])", message, re.I):  # a lone x, y, n (not "a" or "I")
        nearest_equals = min(abs(match.start() - e.start()) for e in _EQUALS.finditer(message))
        if nearest_equals <= 14:
            return match.group(1).lower()
    return ""


def inspect(message):
    """Decide what kind of message this is. Runs before the model sees anything."""
    message = str(message or "")
    subject = subject_of(message)

    if _CRISIS.search(message):
        return Verdict("crisis")
    if _ASKS_FOR_ANSWER.search(message):
        return Verdict("answer", "you asked for the answer", subject, _unknown(message), _hint_for(message, subject))

    asks_how = _ASKS_HOW.search(message) and not re.search(r"\bfor me\b", message, re.I)
    if not asks_how:
        for pattern, reason in _WRITE_IT:
            if pattern.search(message):
                hint = "code" if "code" in reason or subject == "Coding" else "writing"
                return Verdict("write_it", reason, subject, hint=hint)

    variable = _unknown(message)
    reason = ""
    if _ARITHMETIC.search(message):
        reason = "this is a calculation to work out"
    elif variable:
        reason = "this is an equation to solve"
    elif _SOLVE_WORDS.search(message) and _HAS_NUMBERS.search(message):
        reason = "this is a problem to work out"
    elif len(_CHOICE_LINE.findall(message)) >= 3 or _CHOICES_INLINE.search(message):
        reason = "this is a multiple-choice question"
    if reason:
        return Verdict("answer", reason, subject or "Math", variable, _hint_for(message, subject or "Math"))

    if _NEAR_ME.search(message):
        return Verdict("near_me", subject=subject)
    if _LIFE.search(message):
        return Verdict("life", subject=subject)
    if subject or _EXPLAIN.search(message):
        return Verdict("concept", subject=subject)
    return Verdict("other", subject=subject)


def carry_over(verdict, message, earlier_messages):
    """Keep coaching through short follow-ups.

    After "Solve 2x + 6 = 14" is flagged, a student may simply ask "so what is x?".
    On its own that looks harmless, but it is the same request. If one of the last
    two student messages was flagged, and this one is short and not about a new
    subject, the flag carries over.
    """
    if verdict.coach or verdict.kind == "crisis" or not earlier_messages or len(str(message).split()) > 12:
        return verdict
    for earlier in reversed(earlier_messages[-2:]):
        before = inspect(earlier)
        same_topic = not verdict.subject or verdict.subject == before.subject  # A new subject is a new question
        if before.coach and same_topic:
            return Verdict(before.kind, before.reason, before.subject or verdict.subject, before.variable, before.hint, follow_up=True)
    return verdict


def _hint_for(message, subject):
    if _unknown(message):
        return "equation"
    if re.search(r"%|percent", message, re.I):
        return "percent"
    if len(_CHOICE_LINE.findall(message)) >= 3 or _CHOICES_INLINE.search(message):
        return "choices"
    if _ARITHMETIC.search(message):
        return "arithmetic"
    return "notes" if subject and subject != "Math" else "keywords"


# ---------- 2. Rewrite: what the model is actually sent ----------

_COACH_AN_ANSWER = """Coach them instead:
1. In one sentence, name the idea or skill this task is testing.
2. Ask what they have tried so far, or what they already know about it.
3. Give one hint for the first step only. Do not carry out the step for them.
4. End with a question that gets them to take that step.
Never state the final result, not even to check it. If you show an example, use different numbers and a different variable letter from the student's."""

_COACH_WRITING = """Coach them instead:
1. Say in one friendly sentence that you won't write it, because the work has to be theirs.
2. Ask what the assignment is asking for, and what their main idea is.
3. Offer a simple structure they can fill in themselves (for an essay: claim, evidence, explanation; for code: inputs, steps, output). Give headings or questions only, never finished sentences and never working code.
4. End by asking them to send their own first attempt at one small piece."""


_COACH_FOLLOW_UP = """Keep coaching:
- If they share their own answer or attempt, tell them whether it is right, and why. If it is wrong, point to the step to re-check without correcting it for them.
- Otherwise give one hint for the next step only, and end with a question.
Never state the final result yourself, and never write the work for them."""


def rewrite(message, verdict):
    """The text sent to the model in place of the student's message.

    Ordinary messages pass through untouched. A flagged message is quoted inside
    instructions to coach, so the model is never simply asked to answer it.
    """
    if not verdict.coach:
        return message
    if verdict.follow_up:
        return (f'The student replied:\n"""\n{message}\n"""\n\n'
                f"They are still working on the task SAM's guardrail flagged earlier. {_COACH_FOLLOW_UP}")
    banned = "write it for them" if verdict.kind == "write_it" else "give them the answer"
    steps = _COACH_WRITING if verdict.kind == "write_it" else _COACH_AN_ANSWER
    return (f'The student wrote:\n"""\n{message}\n"""\n\n'
            f"SAM's guardrail flagged this message because {verdict.reason}. Do not {banned}. {steps}")


def retry_note(problems):
    """Added to the instructions when review() rejected the model's first reply."""
    return ("Your last draft broke SAM's first rule: " + "; ".join(problems) + ". Write a new reply. "
            "Do not state any final answer, value or finished text. Ask the student a question that moves them one step forward.")


# ---------- 3. Review: read the reply before the student does ----------

_STATES_ANSWER = re.compile(
    r"\b(the|your)\s+(final\s+|correct\s+|right\s+)?(answer|solution|result)\s+(is|=|would be|comes out to|equals|should be)\s+"
    r"(?!correct|right|wrong|incorrect|not\b|close|almost|on\b|off\b|missing|what|something|up to)"
    r"|\b(answer|solution)\s*[:=]\s*\S"
    r"|\bcorrect\s+(option|choice|answer|letter)\s+is\b"
    r"|\bhere(?:'s| is| are)\s+(the|your|a|an)\s+(finished\s+|complete\s+|full\s+|short\s+|sample\s+)?"
    r"(essay|paragraph|code|program|function|answers?|solution|summary|poem|story)\b", re.I)
# "I can't tell you what the answer is" talks about the answer without giving it.
_TALKS_ABOUT_ANSWER = re.compile(r"\b(what|whether|if|how|why|check|sure)\s+(the|your)\s+(final\s+)?(answer|solution|result)\s+(is|would be|should be)\b", re.I)


def review(reply, verdict, student_message=""):
    """Problems found in a reply to a flagged message. An empty list means it may be shown.

    student_message is what the student just wrote. A value they worked out and
    typed themselves ("is it 4?") may be repeated back to confirm it.
    """
    if not verdict.coach:
        return []
    reply = str(reply or "")
    problems = []
    if "?" not in reply and not verdict.follow_up:
        problems.append("it doesn't ask the student a question")
    if _STATES_ANSWER.search(_TALKS_ABOUT_ANSWER.sub("", reply)):
        problems.append("it states an answer")
    if verdict.variable:
        their_numbers = set(re.findall(r"-?\d+(?:\.\d+)?", str(student_message))) if verdict.follow_up else set()
        given = re.findall(rf"(?<![A-Za-z0-9]){re.escape(verdict.variable)}\s*=\s*(-?\d+(?:\.\d+)?)", reply, re.I)
        if any(value not in their_numbers for value in given):
            problems.append(f"it gives a value for {verdict.variable}")
    if verdict.kind == "write_it":
        code_blocks = re.findall(r"```.*?```", reply, re.S)
        if any(block.count("\n") > 7 for block in code_blocks):
            problems.append("it contains finished code")
        prose = re.sub(r"```.*?```", "", reply, flags=re.S)
        if any(len(re.findall(r"\w+", part)) > 90 for part in re.split(r"\n\s*\n", prose)):
            problems.append("it contains a finished paragraph")
    return problems


# ---------- Replies that never depend on the model ----------

_HINTS = {
    "equation": "**A hint:** an equation stays balanced when you do the same thing to both sides. What could you undo first to get `{variable}` by itself?",
    "percent": "**A hint:** percent means “out of 100”. How would you write this percent as a decimal or a fraction?",
    "arithmetic": "**A hint:** break the numbers into easier pieces, then put the pieces back together. Which piece would you start with?",
    "choices": "**A hint:** answer in your own words before you look at the choices, then cross out the ones that can't be right. Which choice can you rule out first?",
    "notes": "**A hint:** find the part of your notes or textbook this comes from. Which idea from that section is the question testing?",
    "keywords": "**A hint:** underline the key words in the question. What is it really asking you to do?",
}

_COACH_ANSWER = """I won't hand you the answer, but I'll help you get there yourself.

1. **What is the question asking you to find?** Say it in your own words.
2. **What do you already know** that could help: a rule, a formula, or an example from class?
3. **Try the first step** and send it to me. I'll tell you if you're on track.

{hint}"""

_COACH_ESSAY = """I won't write it for you, because then it wouldn't be yours. I can help you build it one piece at a time.

1. **What is the assignment asking for?** Tell me the prompt in your own words.
2. **What is your main idea?** One sentence is enough to start.
3. **Which two or three points back it up?** Rough notes are fine.

What's your main idea so far?"""

_COACH_CODE = """I won't write the code for you, but I'll help you write it yourself.

1. **What goes in, and what should come out?** Give me one example.
2. **What are the steps, in plain words?** Don't worry about code yet.
3. **Which step can you code first?** Try it and send me what you have.

What should the program do with your example?"""

SAFETY_REPLY = """I'm really glad you told me. What you're feeling matters, and you deserve support from a real person right now.

- **Talk to an adult you trust today:** a parent, a teacher, a school counselor or a coach.
- **In the US, call or text 988** (the Suicide & Crisis Lifeline) any time, day or night. It's free and private.
- **If you are in danger right now, call 911.**

If I misunderstood and you only need help with schoolwork, tell me what you're working on."""


def coach_reply(verdict):
    """Guiding questions for a flagged message, written here so they are safe to show without a model."""
    if verdict.kind == "write_it":
        return _COACH_CODE if verdict.hint == "code" else _COACH_ESSAY
    hint = _HINTS.get(verdict.hint, _HINTS["keywords"]).format(variable=verdict.variable or "the unknown")
    return _COACH_ANSWER.format(hint=hint)
