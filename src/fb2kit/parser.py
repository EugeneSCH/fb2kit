"""Decoded text to a namespace-normalized element tree."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from fb2kit import report
from fb2kit.backends import Backend, lxml_etree, resolve_backend
from fb2kit.errors import Fb2ParseError
from fb2kit.report import Diagnostic, Mode, Severity
from fb2kit.source import check_safe_input

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_DEPTH = 200

_XML_DECL = re.compile(r"\A\ufeff?\s*<\?xml\s[^>]*\?>")
_ROOT_TAG = re.compile(r"<((?:[\w.-]+:)?FictionBook)\b")
_XLINK_PREFIXES = ("l", "xlink")


@dataclass(frozen=True, slots=True)
class ParsedTree:
    root: ET.Element = field(compare=False, repr=False)
    backend: str
    diagnostics: tuple[Diagnostic, ...]


def _fail(exc: Exception) -> Fb2ParseError:
    pos = getattr(exc, "position", None)
    line = pos[0] if pos else getattr(exc, "lineno", None)
    return Fb2ParseError(str(exc), line=line)


def _build(text: str, name: str, recover: bool) -> Any:
    try:
        if name == "lxml":
            etree = lxml_etree()
            parser = etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                huge_tree=True,
                remove_comments=True,
                remove_pis=True,
                recover=recover,
            )
            root = etree.fromstring(text, parser)
            if root is None:
                raise Fb2ParseError("document is empty")
            return root
        return ET.fromstring(text)
    except Fb2ParseError:
        raise
    except (ET.ParseError, ValueError) as exc:
        raise _fail(exc) from exc
    except Exception as exc:  # lxml.etree.XMLSyntaxError is not importable without the extra
        if type(exc).__name__ in {"XMLSyntaxError", "ParserError"}:
            raise _fail(exc) from exc
        raise


def _check_depth(root: Any) -> None:
    stack = [(root, 1)]
    while stack:
        el, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise Fb2ParseError(f"nesting depth exceeds {MAX_DEPTH}")
        stack.extend((child, depth + 1) for child in el)


def _normalize(root: Any) -> list[Diagnostic]:
    ns, _, local = root.tag[1:].partition("}") if root.tag.startswith("{") else ("", "", root.tag)
    if local != "FictionBook":
        raise Fb2ParseError(f"root element is {local!r}, not FictionBook")
    if ns == FB2_NS:
        return []
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        if ns == "" and not tag.startswith("{"):
            el.tag = f"{{{FB2_NS}}}{tag}"
        elif ns and tag.startswith(f"{{{ns}}}"):
            el.tag = f"{{{FB2_NS}}}{tag[len(ns) + 2 :]}"
    if ns:
        return [
            Diagnostic(report.NS_FOREIGN, f"foreign namespace {ns!r} replaced", Severity.WARNING)
        ]
    return [Diagnostic(report.NS_MISSING, "namespace is missing, FictionBook 2.0 assumed")]


def parse_tree(
    text: str, *, backend: Backend = Backend.AUTO, mode: Mode = Mode.STRICT
) -> ParsedTree:
    name = resolve_backend(backend)
    text = _XML_DECL.sub("", text, count=1)
    diags: list[Diagnostic] = []
    if mode is Mode.TOLERANT:
        from fb2kit.repair import repair_text

        repaired = repair_text(text)
        text, diags = repaired.text, list(repaired.diagnostics)
        check_safe_input(text)  # repair may have healed a hidden DTD marker
    try:
        root = _build(text, name, recover=False)
    except Fb2ParseError as exc:
        if mode is not Mode.TOLERANT:
            raise
        root = _heal(text, name, exc, diags)
    _check_depth(root)
    return ParsedTree(root, name, tuple(diags + _normalize(root)))


def _heal(text: str, name: str, first: Fb2ParseError, diags: list[Diagnostic]) -> Any:
    from fb2kit.repair import close_unterminated

    exc = first
    if re.search(r"unbound prefix|is not defined", str(exc)):
        used = [p for p in _XLINK_PREFIXES if re.search(rf"\s{p}:\w", text)]
        m = _ROOT_TAG.search(text)
        if used and m:
            decl = "".join(f' xmlns:{p}="{XLINK_NS}"' for p in used)
            text = text[: m.end()] + decl + text[m.end() :]
            diags.append(
                Diagnostic(report.NS_PREFIX_INJECTED, f"declared xlink prefix {', '.join(used)}")
            )
            try:
                return _build(text, name, recover=False)
            except Fb2ParseError as again:
                exc = again
    closed = close_unterminated(text)
    if closed.text != text:
        try:
            root = _build(closed.text, name, recover=False)
        except Fb2ParseError as again:
            exc = again
        else:
            diags.extend(closed.diagnostics)
            return root
    if name == "lxml":
        root = _build(text, name, recover=True)
        diags.append(Diagnostic(report.XML_LXML_RECOVER, f"lxml recovered from: {exc}"))
        return root
    raise exc
