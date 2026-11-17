"""richtext.py: turn Markdown (what the AI model writes) into safe HTML.

The model's words are never trusted. Everything is HTML-escaped first, and then
only these pieces are turned back into tags:

    **bold**   *italic*   `code`   ```code blocks```   # headings
    - bullet lists   1. numbered lists   > quotes
    [links](https://...)   and source numbers like [1]

Links must start with http://, https:// or a single / (a page inside SAM), so a
reply can never smuggle in a script or a "javascript:" link.
"""

import html
import re

from markupsafe import Markup

_BULLET = re.compile(r"^\s*(?:[-*•]|(\d{1,3})[.)])\s+(.*)$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_LINK = re.compile(r"\[([^\]\n]{1,160})\]\(((?:https?://|/(?!/))[^\s()]{1,500})\)")
_BOLD = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*|__(?!\s)(.+?)(?<!\s)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])|(?<!\w)_(?![\s_])(.+?)(?<![\s_])_(?!\w)")
_CITATION = re.compile(r"\[(\d{1,2})\]")


def render(text, cite=None):
    """Markdown -> safe HTML, as Markup that templates can print directly.

    cite is an optional function: cite(3) returns the HTML for source number 3,
    or None if there is no such source (then "[3]" is left as plain text).
    """
    lines = str(text or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, paragraph, items = [], [], []
    numbered = [False, 1]  # Is the open list numbered, and what number does it start at?

    def close_paragraph():
        if paragraph:
            out.append("<p>" + "<br>".join(inline(line, cite) for line in paragraph) + "</p>")
            paragraph.clear()

    def close_list():
        if items:
            tag = "ol" if numbered[0] else "ul"
            start = f' start="{numbered[1]}"' if numbered[0] and numbered[1] != 1 else ""
            out.append(f"<{tag}{start}>" + "".join(f"<li>{inline(item, cite)}</li>" for item in items) + f"</{tag}>")
            items.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            close_paragraph()
            close_list()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
        elif not stripped:
            close_paragraph()
            # A blank line between two list items doesn't end the list.
            upcoming = next((later for later in lines[i + 1:] if later.strip()), "")
            if not _BULLET.match(upcoming):
                close_list()
        elif _HEADING.match(line):
            close_paragraph()
            close_list()
            out.append("<h4>" + inline(_HEADING.match(line).group(1), cite) + "</h4>")
        elif _BULLET.match(line):
            close_paragraph()
            number, item = _BULLET.match(line).groups()
            if items and (number is not None) != numbered[0]:
                close_list()
            if not items:
                numbered[:] = [number is not None, int(number or 1)]
            items.append(item)
        elif stripped.startswith(">"):
            close_paragraph()
            close_list()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(q, cite) for q in quote if q) + "</blockquote>")
            continue
        else:
            close_list()
            paragraph.append(stripped)
        i += 1
    close_paragraph()
    close_list()
    return Markup("".join(out))


def inline(text, cite=None):
    """One line of Markdown -> safe HTML (bold, italic, code, links, source numbers)."""
    text = html.escape(str(text).replace("\x00", ""), quote=True)
    code_spans = []

    def hold_code(match):
        code_spans.append(match.group(1))
        return f"\x00{len(code_spans) - 1}\x00"

    def link(match):
        label, url = match.groups()
        new_tab = "" if url.startswith("/") else ' target="_blank" rel="noopener noreferrer"'
        return f'<a href="{url}"{new_tab}>{label}</a>'

    text = re.sub(r"`([^`\n]+)`", hold_code, text)  # Set code aside so nothing inside it is restyled
    text = _LINK.sub(link, text)
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    text = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    if cite:
        text = _CITATION.sub(lambda m: cite(int(m.group(1))) or m.group(0), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{code_spans[int(m.group(1))]}</code>", text)
