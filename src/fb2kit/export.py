"""Text export for RAG: one `TextBlock` per FB2 block, book metadata separately."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element

from fb2kit.model import iter_nodes
from fb2kit.model.bind import local_name, xlink_href
from fb2kit.model.inline import Link, Raw, Style, Text
from fb2kit.model.structure import (
    Annotation,
    Cite,
    Epigraph,
    Paragraph,
    Poem,
    Section,
    Stanza,
    Subtitle,
    Table,
    TextAuthor,
    Title,
    Verse,
)

if TYPE_CHECKING:
    from fb2kit.api import FictionBook


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A book text block for indexing.

    Attributes:
        text: Normalized text: whitespace collapsed, lines (verses, table rows,
            paragraphs of a composite block) separated by `\n`, table cells by ` | `.
        kind: Block kind: `paragraph`, `subtitle`, `title`, `poem-title`, `epigraph`,
            `annotation`, `cite`, `stanza`, `text-author`, `date`, `table`, `note`, `raw`.
        heading_path: Headings of the enclosing sections, outermost first; for a `title` block
            it includes its own heading, for `note` it does not.
        section_idx: Section numbers within the body, 1-based (`(1, 3, 2)`); `()` outside.
        section_id: `id` of the nearest enclosing section or `None`.
        node_id: `id` of the block itself (for `note` -- the footnote section id or `<p id>`), else
            `None`. A `note` section without an `id` gets a synthetic
            `notes{body_idx}-{section_idx joined by dots}`, for example `notes1-2.1`;
            it is stable for the same book.
        ordinal: Running block number in the book, 0-based.
        note_refs: `node_id` of the `note` blocks this block references, without repeats.
        body: `None` for the main text, otherwise the body name (`notes`).
        body_idx: Body number in `book.bodies`, 0-based.
    """

    text: str
    kind: str
    heading_path: tuple[str, ...] = ()
    section_idx: tuple[int, ...] = ()
    section_id: str | None = None
    node_id: str | None = None
    ordinal: int = 0
    note_refs: tuple[str, ...] = ()
    body: str | None = None
    body_idx: int = 0

    @property
    def depth(self) -> int:
        """Section nesting depth: `len(section_idx)`."""
        return len(self.section_idx)


_KIND: dict[type, str] = {
    Paragraph: "paragraph",
    Subtitle: "subtitle",
    TextAuthor: "text-author",
    Title: "title",
    Epigraph: "epigraph",
    Annotation: "annotation",
    Cite: "cite",
    Table: "table",
    Raw: "raw",
}


def _norm(s: str) -> str:
    return " ".join(s.split())


_LINE_BREAKERS = frozenset(
    {"p", "v", "subtitle", "text-author", "empty-line", "title", "epigraph", "annotation",
     "poem", "stanza", "cite", "table", "tr", "section"}
)  # fmt: skip


def _raw_text(raw: Raw) -> str:
    """Text of an unknown element; block children are set apart by a newline, cells by a space."""
    if raw.element is None:
        return raw.text or ""
    parts: list[str] = []

    def walk(e: Element) -> None:
        parts.append(e.text or "")
        for c in e:
            name = local_name(c)
            sep = "\n" if name in _LINE_BREAKERS else " " if name in ("td", "th") else ""
            parts.append(sep)
            walk(c)
            parts.append(sep + (c.tail or ""))

    walk(raw.element)
    return "".join(parts)


def _inline(children: Iterable[object]) -> str:
    out: list[str] = []
    for c in children:
        if isinstance(c, Text):
            out.append(c.value)
        elif isinstance(c, Style | Link):
            out.append(_inline(c.children))
        elif isinstance(c, Raw):
            out.append(_raw_text(c))
    return "".join(out)


def _lines(node: object) -> list[str]:
    """Non-empty normalised text lines of a node, in document order."""
    out: list[str]
    if isinstance(node, str):
        out = [node]
    elif isinstance(node, Paragraph | Subtitle | TextAuthor | Verse):
        out = [_inline(node.children)]
    elif isinstance(node, Raw):
        out = _raw_text(node).split("\n")
    elif isinstance(node, Text | Style | Link):
        out = [_inline((node,))]
    elif isinstance(node, Table):
        rows = ([_norm(_inline(c.children)) for c in r.cells] for r in node.rows)
        out = [" | ".join(filter(None, cells)) for cells in rows]
    elif isinstance(node, Stanza):
        out = [x for c in (node.title, *node.subtitles, *node.verses) for x in _lines(c)]
    elif isinstance(node, Title | Epigraph | Annotation | Cite | Section):
        out = [x for c in node.children for x in _lines(c)]
    elif isinstance(node, Poem):
        parts = (node.title, *node.epigraphs, *node.stanzas, *node.text_authors, node.date or "")
        out = [x for c in parts for x in _lines(c)]
    else:  # EmptyLine, Image, None
        out = []
    return [n for x in out if (n := _norm(x))]


_Item = tuple[str, object, tuple[str, ...], tuple[int, ...], str | None, str | None]


def _synthetic_id(body_idx: int, idx: tuple[int, ...]) -> str:
    return f"notes{body_idx}-{'.'.join(map(str, idx))}"


def _walk(
    children: Iterable[object],
    path: tuple[str, ...],
    idx: tuple[int, ...],
    sec: str | None,
    notes: int | None,
) -> Iterator[_Item]:
    n = 0
    for c in children:
        if isinstance(c, Section):
            n += 1
            title = " ".join(_lines(c.title))
            sub, sub_idx = (*path, title) if title else path, (*idx, n)
            if notes is not None and not c.sections:  # a leaf section is one note
                yield "note", c, path, sub_idx, c.id, c.id or _synthetic_id(notes, sub_idx)
            else:
                yield from _walk(c.children, sub, sub_idx, c.id, notes)
        elif isinstance(c, Poem):
            yield "poem-title", c.title, path, idx, sec, c.id
            for e in c.epigraphs:
                yield "epigraph", e, path, idx, sec, c.id
            for s in c.stanzas:
                yield "stanza", s, path, idx, sec, c.id
            for a in c.text_authors:
                yield "text-author", a, path, idx, sec, c.id
            yield "date", c.date or "", path, idx, sec, c.id
        elif notes is not None and isinstance(c, Paragraph) and c.id:
            yield "note", c, path, idx, sec, c.id
        else:
            yield _KIND.get(type(c), "raw"), c, path, idx, sec, getattr(c, "id", None)


def _ids(node: object) -> Iterator[str]:
    if i := getattr(node, "id", None):
        yield i
    if isinstance(node, Raw) and node.element is not None:
        yield from (i for e in node.element.iter() if (i := e.get("id")))


def _note_targets(
    children: Iterable[object], out: dict[str, str], body_idx: int, idx: tuple[int, ...] = ()
) -> str | None:
    """Fill id -> node_id of the note block holding it; return the first note block's id."""
    first = None
    n = 0
    for c in children:
        target: str | None
        if isinstance(c, Section):
            n += 1
            if c.sections:
                target = _note_targets(c.children, out, body_idx, (*idx, n))
            else:
                target = c.id or _synthetic_id(body_idx, (*idx, n))
                for i in (i for node in iter_nodes(c) for i in _ids(node)):
                    out.setdefault(i, target)
            if c.id and target:
                out.setdefault(c.id, target)
        elif isinstance(c, Paragraph) and (pid := c.id):
            target = pid
            out.setdefault(pid, pid)
        else:
            continue
        first = first or target
    return first


def _hrefs(node: object) -> Iterator[str]:
    for n in iter_nodes(node):
        if isinstance(n, Link):
            yield n.href
        elif isinstance(n, Raw) and n.element is not None:
            yield from (
                h for e in n.element.iter() if local_name(e) == "a" and (h := xlink_href(e))
            )


def iter_blocks(book: FictionBook) -> Iterator[TextBlock]:
    """Text blocks of all bodies in document order.

    Empty blocks and images are skipped. Block sizes are not equalized: merging into chunks is
    up to the consumer (merge consecutive blocks with the same `body_idx` and
    `section_idx`). `note_refs` contains only links to `note` blocks; links to other
    places in the book are not included, but the link text stays in `text`.

    Args:
        book: The parsed book.

    Yields:
        `TextBlock` blocks with increasing `ordinal`.
    """
    targets: dict[str, str] = {}
    for body_idx, b in enumerate(book.bodies):
        if b.is_notes:
            _note_targets(b.children, targets, body_idx)
    ordinal = 0
    for body_idx, body in enumerate(book.bodies):
        name = body.name if body.is_notes else None
        notes = body_idx if body.is_notes else None
        for kind, node, path, idx, sec, nid in _walk(body.children, (), (), None, notes):
            text = "\n".join(_lines(node))
            if not text:
                continue
            refs = (targets[h[1:]] for h in _hrefs(node) if h[1:] in targets)
            yield TextBlock(
                text, kind, path, idx, sec, nid, ordinal, tuple(dict.fromkeys(refs)), name, body_idx
            )
            ordinal += 1


def book_meta(book: FictionBook) -> dict[str, str | list[str]]:
    """Book card for the index.

    Args:
        book: The parsed book.

    Returns:
        A dict with keys `title`, `authors`, `genres`, `lang`, `sequence` (`"Name #N"`),
        `annotation` (paragraphs joined by `\n`); empty fields are omitted.
    """
    ti = book.description.title_info
    meta: dict[str, str | list[str]] = {
        "title": _norm(ti.title or ""),
        "authors": [a.full_name for a in ti.authors if a.full_name],
        "genres": list(ti.genres),
        "lang": ti.lang or "",
        "sequence": [
            f"{s.name} #{s.number}" if s.number is not None else s.name
            for s in ti.sequences
            if s.name
        ],
        "annotation": "\n".join(x for b in ti.annotation or () for x in _lines(b)),
    }
    return {k: v for k, v in meta.items() if v}
