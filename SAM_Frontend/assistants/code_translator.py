"""code_translator.py: "Google Translate, but for code".

A student pastes code and picks its language. explain() returns, for every line,
a plain-English sentence saying what that line does, plus the whole program
rewritten as pseudocode. The code is only ever read as text. SAM never runs it.

How a request travels. The Code translator page calls explain() through api.explain_code:

    code + language
      |
      |  a made-up language?  to_python() swaps the student's own keywords back
      |                       to Python's, so the rest of SAM can read the code
      |
      |  explain_basic()      SAM's built-in explainer: patterns that recognise
      |                       loops, ifs, functions, assignments, prints ...
      |                       It always runs, needs no key, and works offline.
      |
      |  _ask_model()         If NVIDIA_API_KEY is set, Nemotron (a pre-trained
      |                       model) explains each line as well. Its sentences
      |                       replace the built-in ones wherever it answered.
      v
    {"lines": [{"n", "code", "text"}], "pseudocode", "summary", "engine", ...}

The built-in explainer knows Python and the curly-brace languages (JavaScript,
Java, C, C++, C#, Go, Rust, Swift, Kotlin, PHP). Other languages get a simpler
reading unless the model is connected.

"Make your own language": a student picks their own words for Python's
keywords (say "shout" for print). clean_language() checks the words,
to_python() and from_python() translate code between the two.
"""

import json
import re
from collections import Counter

import sam_ai

MAX_LINES = 150
MAX_CHARS = 8000

# (id, name the student sees, family for the built-in explainer, CodeMirror mode for the editor)
LANGUAGES = [
    ("python", "Python", "python", "python"),
    ("javascript", "JavaScript", "braces", "javascript"),
    ("typescript", "TypeScript", "braces", "text/typescript"),
    ("java", "Java", "braces", "text/x-java"),
    ("c", "C", "braces", "text/x-csrc"),
    ("cpp", "C++", "braces", "text/x-c++src"),
    ("csharp", "C#", "braces", "text/x-csharp"),
    ("go", "Go", "braces", "go"),
    ("rust", "Rust", "braces", "rust"),
    ("swift", "Swift", "braces", "swift"),
    ("kotlin", "Kotlin", "braces", "text/x-kotlin"),
    ("php", "PHP", "braces", "text/x-php"),
    ("ruby", "Ruby", "other", "ruby"),
    ("sql", "SQL", "other", "text/x-sql"),
    ("html", "HTML", "other", "htmlmixed"),
    ("css", "CSS", "other", "css"),
    ("bash", "Bash", "other", "shell"),
]

# The Python words a student can rename in their own language, and what each one means.
KEYWORDS = [
    ("print", "show something on the screen"),
    ("input", "ask the user to type something"),
    ("if", "do this only when something is true"),
    ("elif", "otherwise, check something else"),
    ("else", "otherwise"),
    ("for", "repeat for each item"),
    ("in", "inside (goes with the repeat word)"),
    ("while", "keep repeating while something is true"),
    ("def", "make a new command (a function)"),
    ("return", "send a result back"),
    ("and", "both must be true"),
    ("or", "at least one must be true"),
    ("not", "the opposite"),
    ("True", "yes"),
    ("False", "no"),
]

EXAMPLES = {
    "python": 'scores = [88, 92, 79]\ntotal = 0\nfor score in scores:\n    total += score\naverage = total / len(scores)\nif average >= 85:\n    print("Great work!")\nelse:\n    print("Keep practising")\n',
    "javascript": 'const scores = [88, 92, 79];\nlet total = 0;\nfor (const score of scores) {\n  total += score;\n}\nconst average = total / scores.length;\nif (average >= 85) {\n  console.log("Great work!");\n} else {\n  console.log("Keep practising");\n}\n',
    "java": 'public class Average {\n    public static void main(String[] args) {\n        int[] scores = {88, 92, 79};\n        int total = 0;\n        for (int score : scores) {\n            total += score;\n        }\n        double average = total / 3.0;\n        if (average >= 85) {\n            System.out.println("Great work!");\n        }\n    }\n}\n',
    "cpp": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int total = 0;\n    for (int i = 1; i <= 10; i++) {\n        total += i;\n    }\n    cout << "Total: " << total << endl;\n    return 0;\n}\n',
}


def language(language_id):
    """(id, name, family, mode) for a language id, or None."""
    return next((entry for entry in LANGUAGES if entry[0] == language_id), None)


# ---------- The entry point ----------

def explain(code, language_id, custom=None, mirror_into=None):
    """Explain code line by line.

    custom       the student's own language {"name", "words"}, when the code is written in it
    mirror_into  one of the student's languages; Python code is also shown rewritten in it
    Returns {"ok": True, ...} or {"ok": False, "error": message for the student}.
    """
    code = str(code or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").strip("\n")
    if not code.strip():
        return {"ok": False, "error": "Paste or type some code first."}
    if len(code) > MAX_CHARS or code.count("\n") >= MAX_LINES:
        return {"ok": False, "error": f"That's a lot of code. Paste up to {MAX_LINES} lines at a time."}

    mirror = None
    if custom:
        name, family = custom["name"], "python"
        readable = to_python(code, custom)
        mirror = {"title": "The same code in Python", "code": readable}
    else:
        entry = language(language_id)
        if not entry:
            return {"ok": False, "error": "Choose a language from the list."}
        _, name, family, _ = entry
        readable = code
        if language_id == "python" and mirror_into:
            mirror = {"title": f"The same code in {mirror_into['name']}", "code": from_python(code, mirror_into)}

    rows = explain_basic(readable, family)
    shown = code.split("\n")
    for row in rows:
        row["code"] = shown[row["n"] - 1].rstrip()  # Show the line as the student typed it
    pseudocode = "\n".join("    " * row["depth"] + row["pseudo"] for row in rows if row["pseudo"])
    result = {
        "ok": True, "language": name, "engine": "basic", "summary": _summary(rows, name),
        "lines": rows, "pseudocode": pseudocode, "mirror": mirror, "note": "",
    }
    if sam_ai.chat_configured():
        _ask_model(result, readable, name, custom)
    elif family == "other":
        result["note"] = (f"SAM's built-in explainer reads Python and curly-brace languages best. "
                          f"Connect the AI model (see README) for a fuller reading of {name}.")
    return result


# ---------- The model ----------

_MODEL_RULES = """You explain code to middle and high school students who are learning to program.
For every numbered line, write one short, plain-English sentence (25 words at most) saying what that line does. Say what it does, not how to improve it. Never fix, extend or rewrite the code.
Then write the whole program as pseudocode: plain capitalised keywords such as SET, IF, ELSE, FOR EACH, WHILE, DEFINE, RETURN and DISPLAY, indented with four spaces.
Reply with JSON only, in exactly this shape:
{"summary": "<one sentence on what the whole program does>", "lines": [{"n": <line number>, "text": "<what the line does>"}], "pseudocode": "<pseudocode, lines separated by \\n>"}"""


def _ask_model(result, code, name, custom):
    """Replace the built-in sentences with Nemotron's, wherever it gave a usable one."""
    numbered = "\n".join(f"{row['n']}| {code.split(chr(10))[row['n'] - 1]}" for row in result["lines"])
    made_up = f" (a made-up language called {custom['name']}, shown here with Python keywords)" if custom else ""
    try:
        reply = sam_ai.complete(
            [{"role": "system", "content": _MODEL_RULES},
             {"role": "user", "content": f"Language: {name}{made_up}\n\nCode:\n{numbered}"}],
            max_tokens=min(4000, 500 + 70 * len(result["lines"])), temperature=0.2)
        data = json.loads(reply[reply.index("{"): reply.rindex("}") + 1])
        sentences = {int(item["n"]): " ".join(str(item["text"]).split()) for item in data["lines"]
                     if isinstance(item, dict) and str(item.get("text") or "").strip()}
    except (sam_ai.ModelError, ValueError, KeyError, TypeError) as problem:
        print(f"[SAM] The model's code explanation couldn't be used ({problem}). Showing the built-in one.")
        result["note"] = "The AI model didn't answer, so this is SAM's built-in explanation."
        return
    if not sentences:
        return
    for row in result["lines"]:
        if row["n"] in sentences:
            row["text"] = sentences[row["n"]][:400]
    if isinstance(data.get("pseudocode"), str) and data["pseudocode"].strip():
        result["pseudocode"] = data["pseudocode"].strip("\n")[:6000]
    if isinstance(data.get("summary"), str) and data["summary"].strip():
        result["summary"] = " ".join(data["summary"].split())[:300]
    result["engine"] = "model"


# ---------- Make your own language ----------

_WORD = re.compile(r"[^\W\d]\w{0,19}")
_TOKEN = re.compile(r"""
      (?P<comment>\#[^\n]*)
    | (?P<string>[rbfuRBFU]{0,2}(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"))
    | (?P<word>[^\W\d]\w*)
""", re.X)


def clean_language(name, words):
    """Check a student's language. Returns ({"name", "words"}, "") or (None, what to fix)."""
    name = " ".join(str(name or "").split())[:24]
    if len(name) < 2 or not re.fullmatch(r"[\w][\w .+#-]*", name):
        return None, "Give your language a name (2 to 24 letters or numbers)."
    if any(name.lower() == entry[1].lower() for entry in LANGUAGES):
        return None, f"{name} is already a language. Pick a new name."
    python_words = [key for key, _ in KEYWORDS]
    chosen = {}
    for key in python_words:
        word = str((words or {}).get(key) or "").strip()
        if not word or word == key:
            continue
        if not _WORD.fullmatch(word):
            return None, f"“{word}” can't be a keyword. Use one word made of letters, with no spaces."
        if word in python_words:
            return None, f"“{word}” already means something else in Python. Pick a different word for {key}."
        if word in chosen.values():
            return None, f"You used “{word}” twice. Each keyword needs its own word."
        chosen[key] = word
    if len(chosen) < 3:
        return None, "Rename at least three keywords to make it your own language."
    return {"name": name, "words": chosen}, ""


def _swap_words(code, mapping):
    """Replace whole words in code, leaving text inside quotes and comments alone."""
    return _TOKEN.sub(lambda m: mapping.get(m.group(), m.group()) if m.lastgroup == "word" else m.group(), code)


def to_python(code, custom):
    """Code in the student's language -> the same code with Python's keywords."""
    return _swap_words(code, {theirs: python for python, theirs in custom["words"].items()})


def from_python(code, custom):
    """Python code -> the same code with the student's keywords."""
    return _swap_words(code, custom["words"])


# ---------- The built-in explainer ----------

def explain_basic(code, family):
    """[{"n", "code", "text", "pseudo", "depth", "kind"}] for each line that isn't blank."""
    lines = code.split("\n")
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    step = min((i for i in indents if i), default=4)  # How many spaces one level of indent is
    rows, depth = [], 0
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if family == "python":
            kind, text, pseudo = _python_line(line)
            level = (len(raw) - len(raw.lstrip())) // step
        elif family == "braces":
            kind, text, pseudo = _braces_line(line)
            level = max(depth - 1, 0) if line.startswith("}") else depth
            bare = _STRING.sub('""', _drop_comment(line, "//"))
            depth = max(depth + bare.count("{") - bare.count("}"), 0)
        else:
            kind, text, pseudo = _other_line(line)
            level = (len(raw) - len(raw.lstrip())) // step
        rows.append({"n": n, "code": raw.rstrip(), "text": text, "pseudo": pseudo, "depth": level, "kind": kind})
    return rows


_STRING = re.compile(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`""")
_KEYWORDS_NOT_NAMES = {"if", "else", "elif", "for", "while", "switch", "return", "catch", "do", "try", "case", "new", "throw",
                       "sizeof", "typeof", "await", "yield", "delete", "function", "except", "with", "and", "or", "not", "go", "defer"}


def _t(code, limit=70):
    """A piece of code, quoted so it shows as code inside a sentence."""
    code = " ".join(str(code).split()).replace("`", "'")
    if len(code) > limit:
        code = code[: limit - 1] + "…"
    return f"`{code}`" if code else ""


def _drop_comment(line, marker):
    """The line without a trailing comment, taking care not to cut inside a string."""
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif line.startswith(marker, i):
            return line[:i].rstrip()
        i += 1
    return line.rstrip()


def _split(text, separator=","):
    """Split on a separator, but not inside brackets or quotes: "a, f(b, c)" -> ["a", "f(b, c)"]."""
    parts, depth, quote, start = [], 0, "", 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(separator, i):
            parts.append(text[start:i].strip())
            start = i + len(separator)
            i += len(separator) - 1
        i += 1
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def _assignment(code):
    """Split a line at the "=" that stores a value: "total += n" -> ("total", "+=", "n").

    Skips "=" inside brackets or quotes, and the ones that compare ("==", "<=", "=>").
    Returns None when the line doesn't store anything.
    """
    depth, quote, i = 0, "", 0
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and depth == 0:
            if code[i + 1:i + 2] in ("=", ">"):
                i += 2
                continue
            if code[i - 1:i] not in ("=", "!", "<", ">"):
                before = code[:i]
                for op in ("**", "//", "+", "-", "*", "/", "%", ":"):
                    if before.endswith(op):
                        return before[:-len(op)].strip(), op + "=", code[i + 1:].strip()
                return before.strip(), "=", code[i + 1:].strip()
        i += 1
    return None


def _declared_name(target):
    """The variable's name in the left side of an assignment: "const double avg" -> "avg"."""
    unpacked = re.fullmatch(r"(?:(?:const|let|var|val|auto)\s+)?([\[{(].*[\]})])", target)
    if unpacked:
        return unpacked.group(1)
    if len(_split(target)) > 1:  # a, b = b, a
        return ", ".join(_split(target))
    if "[" not in target and "(" not in target:
        target = re.sub(r"(?<!:):(?!:).*$", "", target).strip()  # Drop a type written after the name: "total: Int"
    words = target.split()
    if len(words) < 2:
        return target.lstrip("*&")
    return re.sub(r"\[\w*\]$", "", words[-1].lstrip("*&"))


def _unwrap(text):
    """Remove one pair of brackets that wraps the whole text: "(x > 3)" -> "x > 3"."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        depth = 0
        for i, ch in enumerate(text):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(text) - 1:
                return text
        return text[1:-1].strip()
    return text


def _things(args):
    """A list of values for a sentence: `a`, `b` and `c`."""
    parts = [_t(a) for a in _split(args)]
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


_COMPARE = [
    (r"\s*(?:!==|!=)\s*", "is not equal to"), (r"\s*>=\s*", "is at least"), (r"\s*<=\s*", "is at most"),
    (r"\s*(?:===|==)\s*", "equals"), (r"\s*>\s*", "is greater than"), (r"\s*<\s*", "is less than"),
    (r"\s+is\s+not\s+", "is not"), (r"\s+is\s+", "is"), (r"\s+not\s+in\s+", "is not in"), (r"\s+in\s+", "is in"),
]


def _condition(expr):
    """A test in words: "x % 2 == 0" -> "`x` is even"."""
    expr = _unwrap(expr)
    if not _STRING.search(expr) and not re.search(r"[(\[{]", expr):
        for pattern, word in ((r"\s+and\s+|\s*&&\s*", "and"), (r"\s+or\s+|\s*\|\|\s*", "or")):
            parts = re.split(pattern, expr)
            if len(parts) > 1:
                return f" {word} ".join(_condition(part) for part in parts)
    negated = re.match(r"^(?:not\s+|!(?!=)\s*)(.+)$", expr)
    if negated:
        return f"{_t(negated.group(1))} is not true"
    remainder = re.match(r"^(.+?)\s*%\s*(\w+)\s*(===?|!==?)\s*(\d+)$", expr)
    if remainder:
        left, by, op, value = remainder.groups()
        even = op.startswith("=") == (value == "0")
        if by == "2":
            return f"{_t(left)} is {'even' if even else 'odd'}"
        if value == "0":
            return f"{_t(left)} {'divides' if even else 'does not divide'} evenly by {_t(by)}"
    for pattern, word in _COMPARE:
        sides = re.split(pattern, expr, maxsplit=1)
        if len(sides) == 2 and sides[0].strip() and sides[1].strip():
            return f"{_t(sides[0])} {word} {_t(sides[1])}"
    return f"{_t(expr)} is true"


def _pseudo_test(expr):
    """A test for pseudocode: "x >= 3 && !done" -> "x ≥ 3 AND NOT done"."""
    pieces = re.split(f"({_STRING.pattern})", _unwrap(expr))
    for i in range(0, len(pieces), 2):  # Only the parts outside quotes
        p = pieces[i]
        p = re.sub(r"===?", "=", p)
        p = re.sub(r"!==?", "≠", p)
        p = p.replace(">=", "≥").replace("<=", "≤")
        p = re.sub(r"\s*&&\s*|\s+and\s+", " AND ", p)
        p = re.sub(r"\s*\|\|\s*|\s+or\s+", " OR ", p)
        p = re.sub(r"!\s*(?=[\w(])|\bnot\s+", "NOT ", p)
        pieces[i] = re.sub(r"\s*%\s*", " MOD ", p)
    return "".join(pieces).strip()


def _value(expr):
    """Describe a value being stored: "[1, 2, 3]" -> "a list of 3 items"."""
    expr = expr.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", expr):
        return f"the number {_t(expr)}"
    if re.fullmatch(r"[fF]('.*'|\".*\")", expr) or (expr.startswith("`") and "${" in expr):
        return f"text built from the values inside {_t(expr)}"
    if _STRING.fullmatch(expr):
        return f"the text {_t(expr)}"
    if expr in ("True", "true"):
        return "the value true (yes)"
    if expr in ("False", "false"):
        return "the value false (no)"
    if expr in ("None", "null", "nil", "undefined", "nullptr", "NULL"):
        return f"nothing yet ({_t(expr)})"
    if expr in ("[]", "list()", "new ArrayList<>()"):
        return "an empty list"
    typed_list = re.fullmatch(r"\[\d*\][\w.*]+\{(.*)\}|vec!\[(.*)\]|(?:listOf|arrayOf|mutableListOf)\((.*)\)", expr)
    if typed_list:
        count = len(_split(next(g for g in typed_list.groups() if g is not None)))
        return f"a list of {count} item{'s' if count != 1 else ''}"
    if expr in ("{}", "dict()"):
        return "an empty collection"
    if expr.startswith("[") and expr.endswith("]"):
        count = len(_split(expr[1:-1]))
        return f"a list of {count} item{'s' if count != 1 else ''}"
    if expr.startswith("{") and expr.endswith("}"):
        inner = _split(expr[1:-1])
        if inner and all(":" in item for item in inner):
            return f"a collection of {len(inner)} named value{'s' if len(inner) != 1 else ''}"
        return f"a list of {len(inner)} item{'s' if len(inner) != 1 else ''}"
    known = re.fullmatch(r"(len|int|float|str|sum|max|min|sorted|abs|round)\((.*)\)", expr)
    if known:
        what = {"len": "the number of items in {}", "int": "{} turned into a whole number", "float": "{} turned into a decimal number",
                "str": "{} turned into text", "sum": "the total of {}", "max": "the largest value in {}", "min": "the smallest value in {}",
                "sorted": "a sorted copy of {}", "abs": "the size of {} without its sign", "round": "{} rounded"}[known.group(1)]
        return what.format(_t(known.group(2)))
    if re.fullmatch(r"(new\s+)?[\w.:<>]+\(.*\)", expr):
        return f"the result of {_t(expr)}"
    if re.search(r"[-+*/%]|\*\*", _STRING.sub("", expr)):
        return f"the result of working out {_t(expr)}"
    return f"the value of {_t(expr)}"


def _store(name, expr):
    """The sentence and pseudocode for "name = expr"."""
    small = re.fullmatch(r"lambda\s*(.*?)\s*:\s*(.+)", expr)
    if small:
        takes = f"takes {_things(small.group(1))} and" if small.group(1).strip() else "takes no inputs and"
        return ("function", f"Makes a small function named {_t(name)} that {takes} gives back {_t(small.group(2))}.",
                f"DEFINE {name}({small.group(1)}): RETURN {small.group(2)}")
    choice = re.fullmatch(r"(.+?)\s+if\s+(.+?)\s+else\s+(.+)", expr)
    if choice:
        yes, test, no = choice.groups()
    else:
        asks = _split(expr, "?")
        either = _split(asks[1], ":") if len(asks) == 2 and not asks[1].startswith((".", "?")) else []
        choice = len(either) == 2
        test, yes, no = (asks[0], either[0], either[1]) if choice else ("", "", "")
    if choice:
        return ("assign", f"If {_condition(test)}, stores {_t(yes)} in {_t(name)}. Otherwise stores {_t(no)}.",
                f"IF {_pseudo_test(test)} THEN SET {name} TO {yes} ELSE SET {name} TO {no}")
    grow = re.fullmatch(rf"{re.escape(name)}\s*([-+*/])\s*(.+)", expr)
    if grow and re.fullmatch(r"[\w.\[\]]+", name):
        return _change(name, grow.group(1) + "=", grow.group(2))
    if name.startswith(("[", "{", "(")):
        return "assign", f"Takes {_things(name[1:-1])} out of {_t(expr)} and makes each one a variable.", f"SET {name} FROM {expr}"
    if "," in name:
        return "assign", f"Sets {_t(name)} to {_t(expr)}, all in one step.", f"SET {name} TO {expr}"
    where = _t(name) if re.search(r"[.\[>]", name) else f"a variable named {_t(name)}"
    return "assign", f"Stores {_value(expr)} in {where}.", f"SET {name} TO {expr}"


def _change(name, op, amount):
    """The sentence and pseudocode for "name += amount" and friends."""
    sentence, pseudo = {
        "+=": ("Adds {a} to {n}.", "INCREASE {n} BY {a}"), "-=": ("Subtracts {a} from {n}.", "DECREASE {n} BY {a}"),
        "*=": ("Multiplies {n} by {a}.", "MULTIPLY {n} BY {a}"), "/=": ("Divides {n} by {a}.", "DIVIDE {n} BY {a}"),
        "//=": ("Divides {n} by {a} and drops the remainder.", "DIVIDE {n} BY {a} (whole number)"),
        "%=": ("Sets {n} to the remainder of dividing it by {a}.", "SET {n} TO {n} MOD {a}"),
        "**=": ("Raises {n} to the power of {a}.", "RAISE {n} TO THE POWER {a}"),
    }[op]
    return "assign", sentence.format(n=_t(name), a=_t(amount)), pseudo.format(n=name, a=amount)


_METHODS = {
    "append": "Adds {a} to the end of the list {o}.", "push": "Adds {a} to the end of the list {o}.", "push_back": "Adds {a} to the end of the list {o}.",
    "add": "Adds {a} to {o}.", "pop": "Removes the last item from {o}.", "remove": "Removes {a} from {o}.", "sort": "Sorts {o} into order.",
    "reverse": "Reverses the order of {o}.", "clear": "Empties {o}.", "insert": "Inserts {a} into {o}.", "extend": "Adds every item of {a} to {o}.",
    "close": "Closes {o}.", "write": "Writes {a} to {o}.", "update": "Updates {o} with {a}.",
}


def _call(code):
    """Sentence and pseudocode for a line that only runs a function, or None if it isn't one."""
    each = re.fullmatch(r"([\w.\[\]]+)\.(forEach|map|filter|each)\s*\(\s*(?:\(?\s*(\w+)[^)]*\)?\s*=>|function\s*\(\s*(\w+)[^)]*\))\s*\{?\)?", code) \
        or re.fullmatch(r"(.+?)\.(each)\s+do\s*\|(\w+)[^|]*\|()", code)
    if each:
        items, how, name = each.group(1), each.group(2), each.group(3) or each.group(4)
        does = {"map": "makes a new list from what the block below gives back for each one",
                "filter": "keeps the items the block below says yes to"}.get(how, "runs the block below for each one")
        return "loop", f"Goes through {_t(items)} one item at a time, calls each one {_t(name)}, and {does}.", f"FOR EACH {name} IN {items}"
    method = re.fullmatch(r"([\w.\[\]]+)\.(\w+)\((.*)\)", code)
    if method:
        owner, name, args = method.groups()
        if name in _METHODS:
            return "call", _METHODS[name].format(o=_t(owner), a=_things(args) or "it"), f"CALL {owner}.{name}({args})"
        with_args = f" with {_things(args)}" if args.strip() else ""
        return "call", f"Tells {_t(owner)} to run its {_t(name)} action{with_args}.", f"CALL {owner}.{name}({args})"
    call = re.fullmatch(r"([A-Za-z_]\w*)\((.*)\)", code)
    if call and call.group(1) not in _KEYWORDS_NOT_NAMES:
        name, args = call.groups()
        with_args = f" with {_things(args)}" if args.strip() else ""
        return "call", f"Runs the function {_t(name)}{with_args}.", f"CALL {name}({args})"
    return None


def _counting(variable, start, end, inclusive=False):
    upto = f"up to {_t(end)}" if inclusive else f"up to, but not including, {_t(end)}"
    return ("loop", f"Repeats the lines below, counting {_t(variable)} from {_t(start)} {upto}.",
            f"FOR {variable} FROM {start} TO {end}" + ("" if inclusive else " - 1"))


def _python_line(line):
    """(kind, sentence, pseudocode) for one line of Python."""
    code = _drop_comment(line, "#")
    if not code:
        note = line.lstrip("#").strip()
        return "comment", "A comment: a note for people reading the code. Python skips it.", f"NOTE: {note}" if note else None
    if code.startswith(('"""', "'''")) or (_STRING.fullmatch(code)):
        return "comment", "A text note describing the code. Python doesn't act on it.", None
    block = code[:-1].rstrip() if code.endswith(":") else None  # The line opens an indented block

    m = re.fullmatch(r"(?:from\s+([\w.]+)\s+)?import\s+(.+)", code)
    if m:
        source, names = m.groups()
        if source:
            return "import", f"Brings in {_things(names)} from the {_t(source)} module so this code can use {'them' if ',' in names else 'it'}.", f"USE {names} FROM {source}"
        return "import", f"Loads the {_things(names)} module so this code can use its tools.", f"USE {names}"
    if code.startswith("@"):
        return "other", f"A decorator: it changes how the function below behaves ({_t(code)}).", None
    if block is not None:
        m = re.fullmatch(r"(?:async\s+)?def\s+(\w+)\s*\((.*)\)\s*(?:->\s*.+)?", block)
        if m:
            name, args = m.groups()
            takes = f"that takes {_things(args)}" if args.strip() else "that takes no inputs"
            return "function", f"Starts a function named {_t(name)} {takes}. The indented lines below are what it does.", f"DEFINE {name}({args})"
        m = re.fullmatch(r"class\s+(\w+)\s*(?:\((.*)\))?", block)
        if m:
            based = f", based on {_t(m.group(2))}" if m.group(2) else ""
            return "class", f"Starts a class named {_t(m.group(1))}{based}: a blueprint for making objects.", f"DEFINE CLASS {m.group(1)}"
        m = re.fullmatch(r"(if|elif|while)\s+(.+)", block)
        if m:
            word, test = m.groups()
            if word == "if":
                return "decision", f"Checks whether {_condition(test)}. If so, the indented lines below run.", f"IF {_pseudo_test(test)} THEN"
            if word == "elif":
                return "decision", f"Otherwise, checks whether {_condition(test)}. If so, the indented lines below run.", f"ELSE IF {_pseudo_test(test)} THEN"
            if test in ("True", "1"):
                return "loop", "Repeats the indented lines forever, until a `break` stops it.", "REPEAT FOREVER"
            return "loop", f"Keeps repeating the indented lines as long as {_condition(test)}.", f"WHILE {_pseudo_test(test)}"
        if block == "else":
            return "decision", "Otherwise (when the checks above were not true), the indented lines below run.", "ELSE"
        m = re.fullmatch(r"for\s+(.+?)\s+in\s+(.+)", block)
        if m:
            target, items = m.groups()
            counted = re.fullmatch(r"range\((.*)\)", items)
            if counted:
                args = _split(counted.group(1))
                if len(args) == 1:
                    return ("loop", f"Repeats the indented lines {_t(args[0])} times. {_t(target)} counts up from 0.",
                            f"REPEAT {args[0]} TIMES ({target} counts from 0)")
                if len(args) == 2:
                    return _counting(target, args[0], args[1])
                return "loop", f"Repeats the indented lines, moving {_t(target)} from {_t(args[0])} towards {_t(args[1])} in steps of {_t(args[2])}.", f"FOR {target} FROM {args[0]} TO {args[1]} STEP {args[2]}"
            numbered = re.fullmatch(r"enumerate\((.*)\)", items)
            if numbered:
                return "loop", f"Goes through {_t(numbered.group(1))} one item at a time, keeping count as it goes ({_t(target)}).", f"FOR EACH {target} IN {numbered.group(1)} (WITH A COUNT)"
            return "loop", f"Goes through {_t(items)} one item at a time, calling each one {_t(target)}.", f"FOR EACH {target} IN {items}"
        if block == "try":
            return "other", "Tries the indented lines below, ready to catch an error if one happens.", "TRY"
        m = re.fullmatch(r"except\s*(.*)", block)
        if m:
            error = re.sub(r"\s+as\s+\w+$", "", m.group(1))
            which = f"a {_t(error)} error" if error else "an error"
            return "other", f"If {which} happened above, the indented lines below run instead of crashing.", "IF THAT FAILS"
        if block == "finally":
            return "other", "The indented lines below run at the end, whether or not there was an error.", "FINALLY"
        m = re.fullmatch(r"with\s+(.+?)(?:\s+as\s+(\w+))?", block)
        if m:
            named = f", calling it {_t(m.group(2))}," if m.group(2) else ""
            opened = re.fullmatch(r"open\((.*)\)", m.group(1))
            what = f"the file {_t(_split(opened.group(1))[0])}" if opened and opened.group(1).strip() else _t(m.group(1))
            return "other", f"Opens {what}{named} for the indented lines below, then closes it automatically.", f"WITH {m.group(1)}"

    m = re.fullmatch(r"(if|elif|while)\s+(.+?):\s+(.+)", code)
    if m:
        return "decision", f"Checks whether {_condition(m.group(2))}. If so, runs {_t(m.group(3))}.", f"IF {_pseudo_test(m.group(2))} THEN {m.group(3)}"
    m = re.fullmatch(r"return\b\s*(.*)", code)
    if m:
        if m.group(1):
            return "return", f"Ends the function and sends back {_t(m.group(1))}.", f"RETURN {m.group(1)}"
        return "return", "Ends the function here.", "RETURN"
    simple = {"break": ("Stops the loop right away.", "LEAVE THE LOOP"), "continue": ("Skips to the next turn of the loop.", "SKIP TO THE NEXT TURN"),
              "pass": ("Does nothing. It's a placeholder.", "DO NOTHING")}
    if code in simple:
        return ("other",) + simple[code]
    m = re.fullmatch(r"(raise|assert|del|global|nonlocal|yield)\b\s*(.*)", code)
    if m:
        what = {"raise": "Stops with an error: {}.", "assert": "Checks that {} is true, and stops with an error if it isn't.", "del": "Deletes {}.",
                "global": "Says that {} is a variable shared by the whole program.", "nonlocal": "Says that {} belongs to the function outside this one.",
                "yield": "Hands back {} and pauses here until the next value is asked for."}[m.group(1)]
        return "other", what.format(_t(m.group(2)) or "it"), f"{m.group(1).upper()} {m.group(2)}".strip()
    m = re.fullmatch(r"print\((.*)\)", code)
    if m:
        shown = [a for a in _split(m.group(1)) if not re.match(r"(end|sep|file|flush)\s*=", a)]
        if not shown:
            return "output", "Shows an empty line on the screen.", "DISPLAY a blank line"
        return "output", f"Shows {_things(', '.join(shown))} on the screen.", f"DISPLAY {', '.join(shown)}"
    stores = _assignment(code)
    if stores and stores[0] and stores[2]:
        target, op, value = stores
        name = _declared_name(target)
        asked = re.fullmatch(r"(int|float|str)?\(?\s*input\((.*?)\)\s*\)?", value)
        if op == "=" and asked:
            cast, prompt = asked.groups()
            as_what = {"int": " as a whole number", "float": " as a decimal number", None: "", "str": ""}[cast]
            asks = f"Shows {_t(prompt)} and waits" if prompt.strip() else "Waits"
            return "input", f"{asks} for the user to type something, then stores it{as_what} in {_t(name)}.", f"SET {name} TO USER INPUT"
        return _store(name, value) if op in ("=", ":=") else _change(name, op, value)
    return _call(code) or ("other", f"Python runs {_t(code)}. SAM's built-in explainer doesn't have a simpler way to say this one yet.", code)


_PRINTS = [
    r"console\.(?:log|info|warn|error)\((.*)\)", r"System\.(?:out|err)\.print(?:ln|f)?\((.*)\)", r"(?:std::)?printf\((.*)\)",
    r"fmt\.Print(?:ln|f)?\((.*)\)", r"print(?:ln)?!?\((.*)\)", r"Console\.Write(?:Line)?\((.*)\)", r"document\.write\((.*)\)", r"echo\s+(.*)",
]
_MODIFIERS = r"(?:(?:public|private|protected|internal|static|final|virtual|inline|constexpr|const|unsigned|signed|override|abstract|async|extern|synchronized|export|default|open|suspend)\s+)*"


def _braces_line(line):
    """(kind, sentence, pseudocode) for one line of a curly-brace language."""
    if line.startswith("//"):
        note = line.lstrip("/").strip()
        return "comment", "A comment: a note for people reading the code. The computer skips it.", f"NOTE: {note}" if note else None
    if line.startswith(("/*", "*/")) or re.match(r"\*(\s|$)", line):
        return "comment", "Part of a comment: a note for people reading the code. The computer skips it.", None
    code = _drop_comment(line, "//")
    ended = code.endswith(";")
    code = code.rstrip(";").rstrip()
    opens = code.endswith("{")
    if opens:
        code = code[:-1].rstrip()
    one_line = re.fullmatch(r"((?:if|else|for|while|do|try|catch|finally|switch)\b[^{]*)\{(.*)\}", code)
    if one_line:  # A whole block on one line: while (n > 0) { n -= 1; }
        kind, text, pseudo = _braces_line(one_line.group(1).strip() + " {")
        body = one_line.group(2).strip().rstrip(";")
        return kind, text.replace("the block below runs", f"it runs {_t(body)}").replace("the block", f"{_t(body)}", 1) if body else text, f"{pseudo} {body}".strip()
    if code.startswith("}"):
        code = code.lstrip("}").strip()
        if re.fullmatch(r"[)\];,]*", code):
            return "end", "Ends the block that started above.", None
        again = re.fullmatch(r"while\b\s*(.+)", code)
        if again:  # The end of a do ... while loop
            test = _unwrap(again.group(1))
            return "loop", f"Goes back and repeats the block above as long as {_condition(test)}.", f"REPEAT WHILE {_pseudo_test(test)}"
    if not code:
        return "other", "Starts a block of code.", None

    m = re.fullmatch(r"else\s+if\b\s*(.*)", code)
    if m:
        return "decision", f"Otherwise, checks whether {_condition(m.group(1))}. If so, the block below runs.", f"ELSE IF {_pseudo_test(m.group(1))} THEN"
    if code == "else":
        return "decision", "Otherwise (when the checks above were not true), the block below runs.", "ELSE"
    m = re.fullmatch(r"if\b\s*(.+)", code)
    if m:
        test, after = _test_and_rest(m.group(1))
        if after:
            return "decision", f"Checks whether {_condition(test)}. If so, runs {_t(after)}.", f"IF {_pseudo_test(test)} THEN {after}"
        return "decision", f"Checks whether {_condition(test)}. If so, the block below runs.", f"IF {_pseudo_test(test)} THEN"
    m = re.fullmatch(r"for\b\s*(.*)", code)
    if m:
        return _braces_for(_unwrap(m.group(1)))
    m = re.fullmatch(r"while\b\s*(.+)", code)
    if m:
        test = _unwrap(m.group(1))
        if test in ("true", "1"):
            return "loop", "Repeats the block below forever, until a `break` stops it.", "REPEAT FOREVER"
        return "loop", f"Keeps repeating the block as long as {_condition(test)}.", f"WHILE {_pseudo_test(test)}"
    if code == "do":
        return "loop", "Starts a block that runs once, then repeats while the test at its end is true.", "REPEAT"
    if code == "loop":
        return "loop", "Repeats the block below forever, until a `break` stops it.", "REPEAT FOREVER"
    m = re.fullmatch(r"switch\b\s*(.+)", code)
    if m:
        return "decision", f"Looks at {_t(_unwrap(m.group(1)))} and jumps to the matching case below.", f"CHOOSE BY {_unwrap(m.group(1))}"
    m = re.fullmatch(r"case\s+(.+?):?", code)
    if m:
        return "decision", f"If the value is {_t(m.group(1))}, the lines below run.", f"WHEN {m.group(1)}"
    if code in ("default:", "default"):
        return "decision", "If no case matched, the lines below run.", "OTHERWISE"
    m = re.fullmatch(r"return\b\s*(.*)", code)
    if m:
        if m.group(1):
            return "return", f"Ends the function and sends back {_t(m.group(1))}.", f"RETURN {m.group(1)}"
        return "return", "Ends the function here.", "RETURN"
    simple = {"break": ("Stops the loop (or case) right away.", "LEAVE THE LOOP OR CASE"), "continue": ("Skips to the next turn of the loop.", "SKIP TO THE NEXT TURN"),
              "try": ("Tries the block below, ready to catch an error if one happens.", "TRY"),
              "finally": ("The block below runs at the end, whether or not there was an error.", "FINALLY")}
    if code in simple:
        return ("other",) + simple[code]
    m = re.fullmatch(r"catch\b\s*(.*)", code)
    if m:
        return "other", "If an error happened in the block above, this block runs instead of crashing.", "IF THAT FAILS"
    m = re.fullmatch(r"throw\s+(.+)", code)
    if m:
        return "other", f"Stops with an error: {_t(m.group(1))}.", f"RAISE {m.group(1)}"

    m = re.fullmatch(r"#\s*include\s*[<\"](.+)[>\"]", code)
    if m:
        return "import", f"Loads the {_t(m.group(1))} library so this code can use its tools.", f"USE {m.group(1)}"
    m = re.fullmatch(r"(?:const|let|var)\s+(\{.*\}|\w+)\s*=\s*require\((.+)\)", code)
    if m:
        return "import", f"Loads the {_t(m.group(2))} module and calls it {_t(m.group(1))}.", f"USE {m.group(2)}"
    m = re.fullmatch(r"import\s+(.+?)\s+from\s+['\"](.+)['\"]", code)
    if m:
        names = m.group(1).strip()
        what = _things(names[1:-1]) if names.startswith("{") and names.endswith("}") else _t(names)
        return "import", f"Brings in {what} from the {_t(m.group(2))} module so this code can use {'them' if ',' in names else 'it'}.", f"USE {names} FROM {m.group(2)}"
    m = re.fullmatch(r"using\s+namespace\s+(\w+)", code)
    if m:
        return "import", f"Lets the code use names from {_t(m.group(1))} without writing {_t(m.group(1) + '::')} in front each time.", None
    m = re.fullmatch(r"(import|using|package|use|namespace)\s+(.+)", code)
    if m:
        word, what = m.groups()
        if word in ("package", "namespace"):
            return "import", f"Says this file belongs to the group of code named {_t(what)}.", None
        return "import", f"Brings in {_t(what)} so this code can use it.", f"USE {what}"

    m = re.fullmatch(_MODIFIERS + r"(?:data\s+|sealed\s+)?(class|struct|interface|enum|trait|impl|object)\s+([\w<>]+)(.*)", code)
    if m:
        kind_word, name, rest = m.groups()
        based = re.search(r"(?:extends|implements|:)\s*([\w<>, .]+)", rest)
        extra = f", based on {_t(based.group(1))}" if based else ""
        meaning = {"class": "a blueprint for making objects", "struct": "a bundle of related values", "interface": "a list of actions other code must provide",
                   "enum": "a fixed list of named choices", "trait": "a set of shared abilities", "impl": "the actions that belong to it", "object": "a single ready-made object"}[kind_word]
        return "class", f"Starts a {kind_word} named {_t(name)}{extra}: {meaning}.", f"DEFINE {kind_word.upper()} {name}"

    function = _function_start(code, ended, opens)
    if function:
        return function

    for pattern in _PRINTS:
        m = re.fullmatch(pattern, code)
        if m:
            if not m.group(1).strip():
                return "output", "Shows an empty line on the screen.", "DISPLAY a blank line"
            return "output", f"Shows {_things(m.group(1))} on the screen.", f"DISPLAY {m.group(1)}"
    m = re.fullmatch(r"(?:std::)?cout\s*<<\s*(.+)", code)
    if m:
        parts = [p for p in _split(m.group(1), "<<") if p not in ("endl", "std::endl", '"\\n"')]
        return "output", f"Shows {_things(', '.join(parts))} on the screen.", f"DISPLAY {', '.join(parts)}"
    m = re.fullmatch(r"(?:std::)?cin\s*>>\s*(.+)", code)
    if m:
        names = ", ".join(_split(m.group(1), ">>"))
        return "input", f"Waits for the user to type something and stores it in {_things(names)}.", f"SET {names} TO USER INPUT"

    m = re.fullmatch(r"([\w.\[\]]+)\s*(\+\+|--)|(\+\+|--)\s*([\w.\[\]]+)", code)
    if m:
        name, op = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return _change(name, "+=" if op == "++" else "-=", "1")
    stores = _assignment(code)
    if stores and stores[0] and stores[2] and stores[0].split()[0] not in _KEYWORDS_NOT_NAMES:
        target, op, value = stores
        name = _declared_name(target)
        return _store(name, value) if op in ("=", ":=") else _change(name, op, value)
    m = re.fullmatch(_MODIFIERS + r"(?:let|var|val|mut|auto)\s+(?:mut\s+)?([A-Za-z_$][\w$]*)(?:\s*:\s*.+)?", code)
    if m:
        return "assign", f"Creates a variable named {_t(m.group(1))} with no value yet.", f"CREATE {m.group(1)}"
    m = re.fullmatch(_MODIFIERS + r"([A-Za-z_][\w<>\[\],.:*&?]*)\s+[*&]*([A-Za-z_]\w*)(\[\w*\])?", code)
    if m and ended and m.group(3) and m.group(1) not in _KEYWORDS_NOT_NAMES:
        room = f" with room for {_t(m.group(3)[1:-1])} items" if m.group(3) != "[]" else ""
        return "assign", f"Creates a list named {_t(m.group(2))}{room} (type {_t(m.group(1))}).", f"CREATE LIST {m.group(2)}"
    if m and ended and m.group(1) not in _KEYWORDS_NOT_NAMES:
        return "assign", f"Creates a variable named {_t(m.group(2))} (type {_t(m.group(1))}) with no value yet.", f"CREATE {m.group(2)}"
    return _call(code) or ("other", f"Runs {_t(code)}. SAM's built-in explainer doesn't have a simpler way to say this one yet.", code)


def _test_and_rest(text):
    """Split "(x > 0) return x" into the test "x > 0" and what follows it."""
    text = text.strip()
    if text.startswith("("):
        depth = 0
        for i, ch in enumerate(text):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                return text[1:i].strip(), text[i + 1:].strip()
    return text, ""


def _braces_for(inside):
    """The many spellings of "for" in curly-brace languages."""
    parts = _split(inside, ";")
    if len(parts) == 3:
        start, test, step = parts
        counter = re.fullmatch(r"(?:[\w<>]+\s+)?(\w+)\s*(?::=|=)\s*(.+)", start)
        if counter:
            name, first = counter.groups()
            limit = re.fullmatch(rf"{re.escape(name)}\s*(<=|<)\s*(.+)", test)
            if limit and re.fullmatch(rf"{re.escape(name)}\+\+|\+\+{re.escape(name)}|{re.escape(name)}\s*\+=\s*1", step):
                return _counting(name, first, limit.group(2), inclusive=limit.group(1) == "<=")
        return ("loop", f"A counting loop: starts with {_t(start)}, keeps going while {_condition(test)}, and does {_t(step)} after each turn.",
                f"FOR ({start}; {_pseudo_test(test)}; {step})")
    m = re.fullmatch(r"(?:\w+\s*,\s*)?(\w+)\s*:=\s*range\s+(.+)", inside)  # Go
    if m:
        return "loop", f"Goes through {_t(m.group(2))} one item at a time, calling each one {_t(m.group(1))}.", f"FOR EACH {m.group(1)} IN {m.group(2)}"
    m = re.fullmatch(r"(?:(?:const|let|var|final|auto|val)\s+)?(?:[\w<>\[\]&*]+\s+)?[&*]?(\w+)\s*(?::\s*[\w<>]+\s*)?\s+(of|in)\s+(.+)|(?:(?:const|final|auto)\s+)?(?:[\w<>\[\]&*]+\s+)?[&*]?(\w+)\s*:\s*(.+)", inside)
    if m:
        name, word, items = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), "of", m.group(5))
        span = re.fullmatch(r"(.+?)\s*(\.\.\.|\.\.=|\.\.<|\.\.|until)\s*(.+)", items)  # Rust, Swift, Kotlin ranges
        if span:
            return _counting(name, span.group(1), span.group(3), inclusive=span.group(2) in ("...", "..="))
        if word == "in" and not re.search(r"[.(\[]", items) and re.match(r"(const|let|var)\b", inside):
            return "loop", f"Goes through each key of {_t(items)}, calling it {_t(name)}.", f"FOR EACH KEY {name} IN {items}"
        return "loop", f"Goes through {_t(items)} one item at a time, calling each one {_t(name)}.", f"FOR EACH {name} IN {items}"
    if not inside:
        return "loop", "Repeats the block below forever, until a `break` stops it.", "REPEAT FOREVER"
    return "loop", f"Keeps repeating the block as long as {_condition(inside)}.", f"WHILE {_pseudo_test(inside)}"


def _function_start(code, ended, opens):
    """Recognise the start of a function in any curly-brace language."""
    name = args = None
    arrow = re.fullmatch(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\((.*?)\)|(\w+))\s*=>\s*([^{\s].*)", code)
    if arrow:  # A one-line function: const double = (n) => n * 2
        inputs = (arrow.group(2) if arrow.group(2) is not None else arrow.group(3)) or ""
        takes = f"takes {_things(inputs)} and" if inputs.strip() else "takes no inputs and"
        return ("function", f"Makes a function named {_t(arrow.group(1))} that {takes} gives back {_t(arrow.group(4))}.",
                f"DEFINE {arrow.group(1)}({inputs}): RETURN {arrow.group(4)}")
    m = (re.fullmatch(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w*)\s*\((.*)\).*", code)
         or re.fullmatch(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\((.*?)\)|(\w+))\s*(?::\s*[\w<>\[\]]+\s*)?=>.*", code)
         or re.fullmatch(_MODIFIERS + r"(?:pub\s+)?(?:fn|func|fun)\s+(?:\([^)]*\)\s*)?(\w+)\s*(?:<[^>]*>)?\s*\((.*?)\).*", code))
    if m:
        name = m.group(1) or "(no name)"
        args = m.group(2) if m.group(2) is not None else (m.group(3) if m.lastindex and m.lastindex >= 3 else "")
    elif not ended:
        m = re.fullmatch(_MODIFIERS + r"([\w<>\[\],.:*&?\s]+?)[\s*&]+(\w+)\s*\((.*)\)\s*(?:const)?\s*(?:noexcept)?\s*(?:throws\s+[\w.,\s]+)?", code)
        if m and m.group(2) not in _KEYWORDS_NOT_NAMES and m.group(1).split()[0] not in _KEYWORDS_NOT_NAMES:
            name, args = m.group(2), m.group(3)
        elif opens:  # A method inside a class: speak() {
            m = re.fullmatch(_MODIFIERS + r"(?:get\s+|set\s+)?(\w+)\s*\((.*)\)", code)
            if m and m.group(1) not in _KEYWORDS_NOT_NAMES:
                name, args = m.group(1), m.group(2)
    if name is None:
        return None
    args = (args or "").strip()
    takes = f"that takes {_things(args)}" if args and args != "void" else "that takes no inputs"
    if name == "constructor":
        return "function", f"Starts the constructor, the setup that runs when a new object is made. It takes {_things(args) or 'no inputs'}.", f"DEFINE constructor({args})"
    if name == "main":
        return "function", f"Starts {_t('main')}, the function where the program begins running.", "DEFINE main (the program starts here)"
    return "function", f"Starts a function named {_t(name)} {takes}. The block below is what it does.", f"DEFINE {name}({args})"


def _other_line(line):
    """A simple reading for languages the built-in explainer doesn't know well."""
    if line.startswith(("#", "//", "--", "<!--", "/*", "*")):
        return "comment", "A comment: a note for people reading the code. The computer skips it.", None
    code = line.rstrip(";")
    m = re.fullmatch(r"(?:puts|print|echo)\s+(.+)", code)
    if m:
        return "output", f"Shows {_things(m.group(1))} on the screen.", f"DISPLAY {m.group(1)}"
    stores = _assignment(code)
    if stores and re.fullmatch(r"[\w.\[\]@$]+", stores[0]) and stores[2]:
        return _store(stores[0], stores[2]) if stores[1] == "=" else _change(*stores)
    if code in ("end", "fi", "done", "}"):
        return "end", "Ends the block that started above.", None
    return _call(code) or ("other", f"Runs {_t(code)}.", code)


def _summary(rows, name):
    """One sentence on what the whole program does, from the kinds of lines in it."""
    count = Counter(row["kind"] for row in rows)
    parts = []
    if count["function"]:
        parts.append(f"defines {count['function']} function{'s' if count['function'] != 1 else ''}")
    if count["input"]:
        parts.append("asks the user for input")
    if count["assign"]:
        parts.append("stores values in variables")
    if count["loop"]:
        parts.append("repeats steps with a loop" if count["loop"] == 1 else f"repeats steps with {count['loop']} loops")
    if count["decision"]:
        parts.append("makes a decision with if")
    if count["output"]:
        parts.append("shows results on the screen")
    if not parts:
        return f"This {name} code has {len(rows)} line{'s' if len(rows) != 1 else ''} to read through."
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"This {name} code {joined}."
