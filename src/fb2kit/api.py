"""Entry points: `parse()`, `parse_string()` and the `FictionBook` book class."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias, TypeVar, cast
from xml.etree.ElementTree import Element

from fb2kit import report
from fb2kit.backends import Backend
from fb2kit.builder import Builder
from fb2kit.errors import Fb2ParseError
from fb2kit.model import iter_nodes
from fb2kit.model.binary import Binary
from fb2kit.model.bind import (
    _full_raw,
    _raw,
    bind_binaries,
    bind_body,
    bind_description,
    local_name,
    resolve_cover,
)
from fb2kit.model.inline import Link, Raw
from fb2kit.model.links import check_links
from fb2kit.model.metadata import Description, TitleInfo
from fb2kit.model.structure import Body, Node, Section
from fb2kit.parser import parse_tree
from fb2kit.report import Diagnostic, Mode, ParseReport
from fb2kit.source import (
    DEFAULT_MAX_SIZE,
    SourceLike,
    check_safe_input,
    decode_source,
    open_container,
    too_big,
)

_EMPTY_REPORT = ParseReport()

Indexed: TypeAlias = Node | Binary
"""Anything in the `id` map: a model node or a `Binary` attachment."""


@dataclass(frozen=True, slots=True)
class FictionBook:
    """A parsed FB2 book: an immutable model tree and the parse report.

    Created only via [`parse`][fb2kit.parse] and [`parse_string`][fb2kit.parse_string].

    Attributes:
        description: Metadata from `<description>`; empty in tolerant mode if it is missing.
            `Description(TitleInfo())`.
        bodies: All `<body>` elements in document order; the main text is usually first, notes are
            the body with a `name` (see `notes_body`).
        binaries: Attached `<binary>` elements (images); bytes are decoded lazily.
        element: Root `xml.etree.ElementTree.Element` after namespace normalization --
            an escape hatch to the raw XML; not used when comparing books.
        cover: Cover -- the `Binary` that the first `<coverpage><image>` points to, or `None`.
        report: Parse report: encoding, container, backend and all diagnostics.
        extra: Unknown child elements of `<FictionBook>` (for example `<stylesheet>`) as `Raw`.
        index: Read-only map `id` -> node (and `Binary`); the first one wins on duplicates.
    """

    description: Description
    bodies: tuple[Body, ...]
    binaries: tuple[Binary, ...]
    element: Element = field(compare=False, repr=False)
    cover: Binary | None = None
    report: ParseReport = _EMPTY_REPORT
    extra: tuple[Raw, ...] = ()
    index: Mapping[str, Indexed] = field(default_factory=dict, compare=False, repr=False)

    @property
    def notes_body(self) -> Body | None:
        """First body with notes (its `name` is set and not `main`) or `None`."""
        return next((b for b in self.bodies if b.is_notes), None)

    def by_id(self, id_: str) -> Indexed | None:
        """Node by its `id` attribute.

        Args:
            id_: The `id` value without a leading `#`.

        Returns:
            The model node or `Binary` with this `id`; `None` if there is none.
        """
        return self.index.get(id_)

    def resolve(self, link: Link) -> Indexed | None:
        """Target of an internal link.

        Args:
            link: A link from the text (`Link`), for example a `type="note"` footnote.

        Returns:
            The node or `Binary` that `#id` points to; `None` for external links and
            missing ids.
        """
        return self.by_id(link.href[1:]) if link.href.startswith("#") else None

    def iter_sections(self) -> Iterator[Section]:
        """All sections of all bodies depth-first, in document order (children follow parents).

        Yields:
            `Section` elements, including sections of notes bodies.
        """
        return (n for n in iter_nodes(self.bodies) if isinstance(n, Section))


def _build(
    text: str,
    *,
    mode: Mode,
    backend: Backend,
    pre: tuple[Diagnostic, ...] = (),
    encoding: str = "utf-8",
    declared: str | None = None,
    container: str | None = None,
) -> FictionBook:
    check_safe_input(text)
    tree = parse_tree(text, backend=backend, mode=mode)
    root = tree.root
    ctx = Builder([], {})
    kids = [(local_name(c), c) for c in root]
    desc_els = [c for n, c in kids if n == "description"]
    if desc_els:
        description = bind_description(desc_els[0], ctx)
    elif mode is Mode.STRICT:
        raise Fb2ParseError("missing description", path="FictionBook")
    else:
        ctx.warn(report.ELEMENT_MISSING, "FictionBook has no <description>")
        description = Description(TitleInfo())
    bodies = tuple(bind_body(c, ctx) for n, c in kids if n == "body")
    if not bodies:
        ctx.warn(report.ELEMENT_MISSING, "FictionBook has no <body>")
    binaries = bind_binaries(root, ctx)
    cover = resolve_cover(description, binaries, ctx)
    check_links(bodies, ctx)
    extra = tuple(
        _full_raw(c, ctx) if n == "stylesheet" else _raw(c, ctx)
        for n, c in kids
        if n not in {"description", "body", "binary"}
    )
    rep = ParseReport(
        (*pre, *tree.diagnostics, *ctx.diagnostics), encoding, declared, container, tree.backend
    )
    return FictionBook(
        description,
        bodies,
        binaries,
        root,
        cover,
        rep,
        extra,
        cast(Mapping[str, Indexed], MappingProxyType(ctx.index)),
    )


_E = TypeVar("_E", bound=StrEnum)


def _coerce(cls: type[_E], value: object) -> _E:
    try:
        return cls(value)  # type: ignore[arg-type]
    except ValueError:
        raise TypeError(f"{cls.__name__} expected, got {value!r}") from None


def parse(
    source: SourceLike,
    *,
    encoding: str | None = None,
    mode: Mode | str = Mode.STRICT,
    backend: Backend | str = Backend.AUTO,
    max_size: int = DEFAULT_MAX_SIZE,
) -> FictionBook:
    """Parse an FB2 book from a file, bytes, a file object or a `.fbz`/`.fb2.zip`.

    Args:
        source: A path (`str` or `os.PathLike`; a string is always a path, not XML),
            `bytes`/`bytearray` or a binary file object. A zip archive is detected by signature,
            not by extension.
        encoding: Overrides the BOM and the prolog; `None` -- detect automatically.
        mode: `Mode.STRICT` -- any XML or encoding error raises an exception;
            `Mode.TOLERANT` -- repair what can be repaired and record every repair in `report`.
        backend: XML backend: `AUTO` (lxml if installed), `STDLIB` or `LXML`.
        max_size: Input size limit in bytes; for an archive, of the unpacked book
            (256 MB by default).

    Returns:
        The parsed book.

    Raises:
        Fb2SourceError: The file is unreadable, empty, larger than `max_size`, a broken archive,
            or the archive contains no book.
        Fb2UnsafeInputError: The input contains `<!DOCTYPE` or `<!ENTITY` (in both modes).
        Fb2EncodingError: The encoding cannot be detected or the bytes contradict it.
        Fb2ParseError: The XML does not parse, the root is not `FictionBook`, `<description>` is
            missing (strict) or nesting is deeper than 200.
        Fb2Error: `Backend.LXML` was requested but lxml is not installed.
        TypeError: Unsupported type of `source`, `mode` or `backend`.
    """
    mode, backend = _coerce(Mode, mode), _coerce(Backend, backend)
    opened = open_container(source, max_size=max_size)
    decoded = decode_source(opened.raw, encoding=encoding, mode=mode)
    return _build(
        decoded.text,
        mode=mode,
        backend=backend,
        pre=(*opened.diagnostics, *decoded.diagnostics),
        encoding=decoded.encoding,
        declared=decoded.declared_encoding,
        container=opened.container,
    )


def parse_string(
    text: str,
    *,
    mode: Mode | str = Mode.STRICT,
    backend: Backend | str = Backend.AUTO,
    max_size: int = DEFAULT_MAX_SIZE,
) -> FictionBook:
    """Parse a book from an already decoded XML string.

    There is no encoding detection or archive unpacking here; the `<?xml ...?>` prolog is ignored.
    `report.source_encoding` is always `"utf-8"`.

    Args:
        text: The book's XML text.
        mode: Parse mode, as in [`parse`][fb2kit.parse].
        backend: XML backend, as in [`parse`][fb2kit.parse].
        max_size: Text size limit in UTF-8 bytes (256 MB by default).

    Returns:
        The parsed book.

    Raises:
        Fb2SourceError: The text is larger than `max_size`.
        Fb2UnsafeInputError: The text contains `<!DOCTYPE` or `<!ENTITY`.
        Fb2ParseError: The XML does not parse or it is not a FictionBook.
        Fb2Error: `Backend.LXML` was requested but lxml is not installed.
        TypeError: Unsupported `mode` or `backend`.
    """
    mode, backend = _coerce(Mode, mode), _coerce(Backend, backend)
    if len(text.encode(errors="surrogatepass")) > max_size:
        raise too_big(max_size)
    return _build(text, mode=mode, backend=backend)
