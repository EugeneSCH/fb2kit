"""A pretty printer for FB2 trees.

The printer builds a string and never touches the tree: the `tail` of an
element -- the text that follows it -- stays exactly where the parser put it.
An element that carries text is written on one line, the others are indented.

The knowledge about namespaces and escaping lives in
[`serialize`][fb2kit.write.serialize]: the pretty output and the compact one
must describe the same document.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from fb2kit.write.serialize import _escape_attr, _escape_text, _namespace_declarations

_INDENT = "  "


def render(root: ET.Element) -> str:
    """Render an element tree as indented XML.

    The tree is not modified: every `tail` is written as it is, so no text is
    lost and none is duplicated.

    Args:
        root: The root element.

    Returns:
        The XML text; it has no declaration and no trailing newline.
    """
    prefixes, declarations = _namespace_declarations(root)
    return "\n".join(_lines(root, 0, prefixes, declarations))


def _qname(name: str, prefixes: dict[str, str]) -> str:
    """The name of an element or of an attribute, with its prefix."""
    if not name.startswith("{"):
        return name
    uri, _, local = name[1:].partition("}")
    prefix = prefixes.get(uri, "")
    return f"{prefix}:{local}" if prefix else local


def _is_compact(el: ET.Element) -> bool:
    """`True` if the element carries text and has to stay on one line.

    An element with text or with a child that has a tail holds the text of
    the document; splitting it would put the text into the wrong place.
    """
    if el.text:
        return True
    return any(child.tail for child in el)


def _is_empty(el: ET.Element) -> bool:
    """`True` if the element has neither children nor text."""
    return not len(el) and el.text is None


def _attrs(el: ET.Element, prefixes: dict[str, str]) -> str:
    """The attributes of an element, as they go into the start tag.

    Every attribute is written with its prefix and its value escaped, exactly
    as the compact writer does it: the two writers must describe the same
    document.
    """
    parts: list[str] = []
    for name, value in el.attrib.items():
        parts.append(f' {_qname(name, prefixes)}="{_escape_attr(value)}"')
    return "".join(parts)


def _start(el: ET.Element, prefixes: dict[str, str], declarations: str) -> str:
    """The start tag of an element with its attributes."""
    parts = [f"<{_qname(el.tag, prefixes)}"]
    if declarations:
        parts.append(declarations)
    parts.append(_attrs(el, prefixes))
    parts.append(">")
    return "".join(parts)


def _end(el: ET.Element, prefixes: dict[str, str]) -> str:
    """The end tag of an element."""
    return f"</{_qname(el.tag, prefixes)}>"


def _inline(el: ET.Element, prefixes: dict[str, str]) -> str:
    """An element and everything under it on one line."""
    if _is_empty(el):
        return f"<{_qname(el.tag, prefixes)}{_attrs(el, prefixes)}/>"
    parts = [_start(el, prefixes, "")]
    if el.text:
        parts.append(_escape_text(el.text))
    for child in el:
        parts.append(_inline(child, prefixes))
        if child.tail:
            parts.append(_escape_text(child.tail))
    parts.append(_end(el, prefixes))
    return "".join(parts)


def _lines(el: ET.Element, depth: int, prefixes: dict[str, str], declarations: str) -> list[str]:
    """The lines of an element, without its tail.

    A compact element takes one line; the others put every child on a line of
    its own. A child of a non-compact element has no tail: a tail would have
    made the parent compact.
    """
    if _is_compact(el):
        return [_INDENT * depth + _inline(el, prefixes)]
    if _is_empty(el):
        return [_INDENT * depth + f"<{_qname(el.tag, prefixes)}{_attrs(el, prefixes)}/>"]
    out = [_INDENT * depth + _start(el, prefixes, declarations)]
    for child in el:
        out.extend(_lines(child, depth + 1, prefixes, ""))
    out.append(_INDENT * depth + _end(el, prefixes))
    return out
