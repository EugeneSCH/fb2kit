"""Binding of XML elements to model nodes."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from xml.etree.ElementTree import Element

from fb2kit import report
from fb2kit.builder import Builder
from fb2kit.model.binary import Binary
from fb2kit.model.inline import Image, Inline, Link, Raw, Style, Text
from fb2kit.model.metadata import (
    Author,
    CustomInfo,
    Date,
    Description,
    DocumentInfo,
    PublishInfo,
    Sequence,
    TitleInfo,
)
from fb2kit.model.structure import (
    Annotation,
    Block,
    Body,
    Cell,
    Cite,
    EmptyLine,
    Epigraph,
    Paragraph,
    Poem,
    Row,
    Section,
    Stanza,
    Subtitle,
    Table,
    TextAuthor,
    Title,
    Verse,
)
from fb2kit.parser import XLINK_NS
from fb2kit.report import Severity

# Block elements that may show up where only inline content is allowed.
_BLOCKISH = frozenset(
    {
        "p", "v", "subtitle", "text-author", "empty-line", "title", "epigraph", "annotation",
        "poem", "stanza", "cite", "table", "tr", "td", "th", "section",
    }
)  # fmt: skip
_STYLES = frozenset({"strong", "emphasis", "strikethrough", "sub", "sup", "code", "style"})


def local_name(el: Element) -> str:
    return str(el.tag).rpartition("}")[2]


def xlink_href(el: Element) -> str | None:
    return el.get(f"{{{XLINK_NS}}}href", el.get("href"))


def _full_raw(el: Element, ctx: Builder) -> Raw:
    """Raw keeps all text and indexes the ids of every element inside it."""
    raw = Raw(tag=local_name(el), text="".join(el.itertext()), element=el)
    for e in el.iter():
        if (i := e.get("id")) is not None:
            ctx.register_id(i, raw)
    return raw


def _raw(el: Element, ctx: Builder) -> Raw:
    ctx.warn(report.ELEMENT_UNKNOWN, f"unexpected element <{local_name(el)}>")
    return _full_raw(el, ctx)


_T = TypeVar("_T")
_N = TypeVar("_N")


def _reg(node: _T, ctx: Builder) -> _T:
    ctx.register(node)
    return node


def _bind_one(el: Element, ctx: Builder) -> Inline:
    return _reg(_bind_inline_node(el, ctx), ctx)


def _bind_inline_node(el: Element, ctx: Builder) -> Inline:
    name = local_name(el)
    if name in _STYLES:
        return Style(name, bind_inline(el, ctx), el.get("name") if name == "style" else None)
    href = xlink_href(el)
    if name == "a" and href is not None:
        return Link(href, el.get("type"), bind_inline(el, ctx), el.get("id"))
    if name == "image":
        return Image(href, el.get("alt"), el.get("title"), el.get("id"))
    return _raw(el, ctx)


def bind_inline(el: Element, ctx: Builder) -> tuple[Inline, ...]:
    out: list[Inline] = []
    if el.text:
        out.append(Text(el.text))
    for i, child in enumerate(el):
        name = local_name(child)
        if name in _BLOCKISH:
            ctx.warn(report.ELEMENT_UNKNOWN, f"block <{name}> inside inline content flattened")
            if (nid := child.get("id")) is not None:
                ctx.register_id(nid, Raw(name, "".join(child.itertext()), child))
            if out:  # keep words of neighbouring blocks apart
                out.append(Text(" "))
            out.extend(bind_inline(child, ctx))
            if child.tail or i + 1 < len(el):
                out.append(Text(" "))
        else:
            out.append(_bind_one(child, ctx))
        if child.tail:
            out.append(Text(child.tail))
    return tuple(out)


def _span(el: Element, name: str) -> int:
    try:
        return max(int(el.get(name, "1")), 1)
    except ValueError:
        return 1


def _cell(el: Element, ctx: Builder) -> Cell:
    return _reg(
        Cell(
            bind_inline(el, ctx),
            local_name(el) == "th",
            _span(el, "colspan"),
            _span(el, "rowspan"),
            el.get("align"),
            el.get("id"),
        ),
        ctx,
    )


def _row_cell(c: Element, ctx: Builder) -> Cell:
    if local_name(c) in {"td", "th"}:
        return _cell(c, ctx)
    ctx.warn(report.ELEMENT_UNKNOWN, f"unexpected <{local_name(c)}> in <tr> kept as a cell")
    return Cell((_bind_one(c, ctx),))


def _row(el: Element, ctx: Builder) -> Row:
    return Row(tuple(_row_cell(c, ctx) for c in el if local_name(c) != "empty-line"))


def _table(el: Element, ctx: Builder) -> Table:
    return Table(tuple(_row(c, ctx) for c in el if local_name(c) == "tr"), el.get("id"))


def _title_part(c: Element, ctx: Builder) -> Paragraph | EmptyLine | Raw:
    name = local_name(c)
    if name == "subtitle":
        ctx.warn(report.ELEMENT_UNKNOWN, "<subtitle> inside <title> kept as a paragraph")
        return _reg(Paragraph(bind_inline(c, ctx), None, c.get("id")), ctx)
    if name in {"p", "empty-line"}:
        n = _block(c, ctx)
        if isinstance(n, Paragraph | EmptyLine):
            return n
    return _raw(c, ctx)


def _stray(text: str | None, ctx: Builder) -> list[Paragraph]:
    """Free text between the children of a container becomes a paragraph, not a loss."""
    if not text or not text.strip():
        return []
    ctx.warn(report.ELEMENT_UNKNOWN, "text outside <p> kept as a paragraph")
    return [_reg(Paragraph((Text(text),)), ctx)]


def _with_stray(
    el: Element, ctx: Builder, bind: Callable[[Element], _N]
) -> tuple[_N | Paragraph, ...]:
    out: list[_N | Paragraph] = list(_stray(el.text, ctx))
    for c in el:
        out.append(bind(c))
        out.extend(_stray(c.tail, ctx))
    return tuple(out)


def _title(el: Element, ctx: Builder) -> Title:
    return Title(_with_stray(el, ctx, lambda c: _title_part(c, ctx)))


def _poem(el: Element, ctx: Builder) -> Poem:
    parts: dict[str, list[Element]] = {}
    for c in el:
        parts.setdefault(local_name(c), []).append(c)
    title = parts.get("title")
    date = parts.get("date")
    return Poem(
        _title(title[0], ctx) if title else None,
        tuple(Epigraph(bind_blocks(e, ctx)) for e in parts.get("epigraph", [])),
        tuple(_stanza(s, ctx) for s in parts.get("stanza", [])),
        tuple(
            _reg(TextAuthor(bind_inline(t, ctx), t.get("id")), ctx)
            for t in parts.get("text-author", [])
        ),
        "".join(date[0].itertext()).strip() if date else None,
        el.get("id"),
    )


def _named(el: Element, name: str) -> list[Element]:
    return [c for c in el if local_name(c) == name]


def _stanza(el: Element, ctx: Builder) -> Stanza:
    title = next((c for c in el if local_name(c) == "title"), None)
    return Stanza(
        _title(title, ctx) if title is not None else None,
        tuple(
            _reg(Subtitle(bind_inline(c, ctx), c.get("id")), ctx)
            for c in el
            if local_name(c) == "subtitle"
        ),
        tuple(
            _reg(Verse(bind_inline(c, ctx), c.get("id")), ctx) for c in el if local_name(c) == "v"
        ),
    )


def _block(el: Element, ctx: Builder) -> Block:
    return _reg(_block_node(el, ctx), ctx)


def _block_node(el: Element, ctx: Builder) -> Block:
    name = local_name(el)
    if name == "p":
        return Paragraph(bind_inline(el, ctx), el.get("style"), el.get("id"))
    if name == "subtitle":
        return Subtitle(bind_inline(el, ctx), el.get("id"))
    if name == "empty-line":
        return EmptyLine()
    if name == "title":
        return _title(el, ctx)
    if name == "epigraph":
        return Epigraph(bind_blocks(el, ctx))
    if name == "annotation":
        return Annotation(bind_blocks(el, ctx))
    if name == "poem":
        return _poem(el, ctx)
    if name == "cite":
        return Cite(bind_blocks(el, ctx), el.get("id"))
    if name == "text-author":
        return TextAuthor(bind_inline(el, ctx), el.get("id"))
    if name == "table":
        return _table(el, ctx)
    if name == "image":
        return Image(xlink_href(el), el.get("alt"), el.get("title"), el.get("id"))
    return _raw(el, ctx)


def bind_blocks(el: Element, ctx: Builder) -> tuple[Block, ...]:
    return _with_stray(el, ctx, lambda c: _block(c, ctx))


def _children(el: Element, ctx: Builder) -> tuple[Block | Section, ...]:
    return _with_stray(
        el, ctx, lambda c: bind_section(c, ctx) if local_name(c) == "section" else _block(c, ctx)
    )


def bind_section(el: Element, ctx: Builder) -> Section:
    return _reg(Section(el.get("id"), _children(el, ctx)), ctx)


def bind_body(el: Element, ctx: Builder) -> Body:
    body = _reg(Body(el.get("name"), _children(el, ctx), el.get("id")), ctx)
    if body.is_notes and body.name not in _NOTES_NAMES:
        ctx.warn(
            report.NOTES_BODY_NAME,
            f"non-standard notes body name {body.name!r}",
            severity=Severity.INFO,
        )
    return body


_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_NOTES_NAMES = frozenset({"notes", "footnotes", "comments"})
_SILENT_EXTRA = frozenset({"output", "src-title-info"})


def _text(el: Element) -> str:
    return "".join(el.itertext()).strip()


def _first(el: Element, name: str) -> str | None:
    found = _named(el, name)
    return _text(found[0]) if found else None


def _texts(el: Element, name: str) -> tuple[str, ...]:
    return tuple(_text(c) for c in _named(el, name))


def _author(el: Element) -> Author:
    return Author(
        _first(el, "first-name"),
        _first(el, "middle-name"),
        _first(el, "last-name"),
        _first(el, "nickname"),
        _texts(el, "email"),
        _texts(el, "home-page"),
    )


def _authors(el: Element, name: str) -> tuple[Author, ...]:
    return tuple(_author(c) for c in _named(el, name))


def _sequence(el: Element) -> Sequence:
    try:
        number: int | None = int(el.get("number", "").strip())
    except ValueError:
        number = None
    return Sequence(el.get("name"), number)


def _dates(el: Element) -> tuple[Date, ...]:
    return tuple(Date(_text(c), c.get(_XML_LANG), c.get("value")) for c in _named(el, "date"))


def _title_info(el: Element, ctx: Builder) -> TitleInfo:
    annotation = _named(el, "annotation")
    cover = _named(el, "coverpage")
    return TitleInfo(
        _texts(el, "genre"),
        _authors(el, "author"),
        _first(el, "book-title"),
        bind_blocks(annotation[0], ctx) if annotation else None,
        _first(el, "keywords"),
        _dates(el),
        tuple(
            Image(xlink_href(i), i.get("alt"), i.get("title"), i.get("id"))
            for c in cover
            for i in _named(c, "image")
        ),
        _first(el, "lang"),
        _first(el, "src-lang"),
        _authors(el, "translator"),
        tuple(_sequence(c) for c in _named(el, "sequence")),
    )


def _document_info(el: Element) -> DocumentInfo:
    history = _named(el, "history")
    return DocumentInfo(
        _authors(el, "author"),
        _first(el, "program-used"),
        _dates(el),
        _first(el, "src-url"),
        _first(el, "src-ocr"),
        _texts(el, "id"),
        _first(el, "version"),
        tuple(_text(p) for h in history for p in _named(h, "p")),
        _first(el, "publisher"),
    )


def _publish_info(el: Element) -> PublishInfo:
    return PublishInfo(
        _first(el, "book-name"),
        _first(el, "publisher"),
        _first(el, "city"),
        _first(el, "year"),
        _first(el, "isbn"),
        tuple(_sequence(c) for c in _named(el, "sequence")),
    )


def bind_description(el: Element, ctx: Builder) -> Description:
    title = _named(el, "title-info")
    doc = _named(el, "document-info")
    pub = _named(el, "publish-info")
    if not title:
        ctx.warn(report.ELEMENT_MISSING, "description has no <title-info>")
    extra = tuple(
        _full_raw(c, ctx) if local_name(c) in _SILENT_EXTRA else _raw(c, ctx)
        for c in el
        if local_name(c) not in {"title-info", "document-info", "publish-info", "custom-info"}
    )
    return Description(
        _title_info(title[0], ctx) if title else TitleInfo(),
        _document_info(doc[0]) if doc else None,
        _publish_info(pub[0]) if pub else None,
        tuple(CustomInfo(c.get("info-type"), _text(c)) for c in _named(el, "custom-info")),
        extra,
    )


def bind_binaries(root: Element, ctx: Builder) -> tuple[Binary, ...]:
    out: list[Binary] = []
    seen: set[str] = set()
    for el in _named(root, "binary"):
        bin_id = el.get("id")
        if not bin_id:
            ctx.warn(report.ELEMENT_MISSING, "<binary> without id skipped")
            continue
        if bin_id in seen:
            ctx.warn(report.DUPLICATE_ID, f"duplicate binary id {bin_id!r}")
        seen.add(bin_id)
        binary = Binary(bin_id, el.get("content-type") or "application/octet-stream", el.text or "")
        ctx.index.setdefault(bin_id, binary)
        out.append(binary)
    return tuple(out)


def resolve_cover(
    description: Description, binaries: tuple[Binary, ...], ctx: Builder
) -> Binary | None:
    covers = description.title_info.coverpage
    if not covers:
        return None
    href = covers[0].href or ""
    cover = next((b for b in binaries if href.startswith("#") and b.id == href[1:]), None)
    if cover is None:
        ctx.warn(report.COVER_MISSING, f"cover image {href!r} not found among binaries")
    return cover
