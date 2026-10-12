"""Text-level repairs for tolerant mode."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fb2kit import report
from fb2kit.report import Diagnostic

_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_OPENERS = (("<!--", "-->"), ("<![CDATA[", "]]>"))
# Possessive groups: a tag without '>' fails in one pass, so the scan stays linear.
_TOKEN = re.compile(
    r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<![^>]*>"
    r"|<(?P<close>/?)(?P<name>[^\s/>]++)(?:[^>\"']++|\"[^\"]*+\"|'[^']*+')*+>",
    re.S,
)


@dataclass(frozen=True, slots=True)
class RepairResult:
    text: str
    diagnostics: tuple[Diagnostic, ...] = ()


def _split_verbatim(text: str) -> list[str]:
    """Like re.split on comments/CDATA, but one forward pass: an unclosed opener ends the scan."""
    parts: list[str] = []
    pos = 0
    while True:
        found = [(i, o, c) for o, c in _OPENERS if (i := text.find(o, pos)) >= 0]
        if not found:
            break
        i, opener, closer = min(found)
        end = text.find(closer, i + len(opener))
        if end < 0:  # unclosed: the rest is plain text, no rescanning
            break
        end += len(closer)
        parts += [text[pos:i], text[i:end]]
        pos = end
    parts.append(text[pos:])
    return parts


def repair_text(text: str) -> RepairResult:
    diags: list[Diagnostic] = []
    # Order matters: stripping control chars first could glue "&\x00amp;" into an entity.
    parts = _split_verbatim(text)  # odd items are CDATA/comments: left as is
    n = 0
    for i in range(0, len(parts), 2):
        parts[i], k = _BARE_AMP.subn("&amp;", parts[i])
        n += k
    text = "".join(parts)
    if n:
        diags.append(Diagnostic(report.XML_BARE_AMP, f"escaped {n} bare ampersand(s)"))
    text, n = _INVALID.subn("", text)
    if n:
        diags.append(Diagnostic(report.XML_CONTROL_CHARS, f"removed {n} invalid XML character(s)"))
    return RepairResult(text, tuple(diags))


def close_unterminated(text: str) -> RepairResult:
    stack: list[str] = []
    pos = 0
    while (start := text.find("<", pos)) >= 0:
        m = _TOKEN.match(text, start)
        if m is None:
            nxt = text[start + 1 : start + 2]
            if nxt.isspace() or nxt.isdigit() or not nxt:
                pos = start + 1  # bare '<' in text is not a tag
                continue
            break  # unterminated construct swallows the rest of the text
        pos = m.end()
        name = m["name"]
        if name is None or text[pos - 2] == "/":
            continue
        if not m["close"]:
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
        else:
            return RepairResult(text)
    if not stack:
        return RepairResult(text)
    tail = "".join(f"</{n}>" for n in reversed(stack))
    return RepairResult(
        text + tail, (Diagnostic(report.XML_AUTO_CLOSED, f"closed {len(stack)} open element(s)"),)
    )
