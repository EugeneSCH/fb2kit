"""Blocks and document structure."""

from __future__ import annotations

from dataclasses import dataclass

from fb2kit.model.inline import Image, Inline, Raw


@dataclass(frozen=True, slots=True)
class Paragraph:
    """Paragraph `<p>`.

    Attributes:
        children: Content.
        style: The `style` attribute.
        id: The paragraph's `id`.
    """

    children: tuple[Inline, ...] = ()
    style: str | None = None
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Subtitle:
    """Subtitle `<subtitle>`.

    Attributes:
        children: Content.
        id: `id`.
    """

    children: tuple[Inline, ...] = ()
    id: str | None = None


@dataclass(frozen=True, slots=True)
class EmptyLine:
    """Empty line `<empty-line/>`."""


@dataclass(frozen=True, slots=True)
class Title:
    """Title `<title>` of a section, body or poem.

    Attributes:
        children: Paragraphs and empty lines (text outside `<p>` is kept as a paragraph).
    """

    children: tuple[Inline | Paragraph | EmptyLine, ...] = ()


@dataclass(frozen=True, slots=True)
class Epigraph:
    """Epigraph `<epigraph>`.

    Attributes:
        children: Blocks, including `TextAuthor`.
    """

    children: tuple[Block, ...] = ()


@dataclass(frozen=True, slots=True)
class Annotation:
    """Annotation `<annotation>` of a section.

    Attributes:
        children: Blocks.
    """

    children: tuple[Block, ...] = ()


@dataclass(frozen=True, slots=True)
class TextAuthor:
    """Author of a quote or epigraph `<text-author>`.

    Attributes:
        children: Content.
        id: `id`.
    """

    children: tuple[Inline, ...] = ()
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Verse:
    """Verse line `<v>`.

    Attributes:
        children: Content.
        id: `id`.
    """

    children: tuple[Inline, ...] = ()
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Stanza:
    """Stanza `<stanza>`.

    Attributes:
        title: Stanza title or `None`.
        subtitles: Subtitles.
        verses: Lines.
    """

    title: Title | None = None
    subtitles: tuple[Subtitle, ...] = ()
    verses: tuple[Verse, ...] = ()


@dataclass(frozen=True, slots=True)
class Poem:
    """Poem `<poem>`.

    Attributes:
        title: Title or `None`.
        epigraphs: Epigraphs.
        stanzas: Stanzas.
        text_authors: Authors.
        date: Date as text.
        id: `id`.
    """

    title: Title | None = None
    epigraphs: tuple[Epigraph, ...] = ()
    stanzas: tuple[Stanza, ...] = ()
    text_authors: tuple[TextAuthor, ...] = ()
    date: str | None = None
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Cite:
    """Quote `<cite>`.

    Attributes:
        children: Blocks and `TextAuthor`.
        id: `id`.
    """

    children: tuple[Block | TextAuthor, ...] = ()
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    """Table cell `<td>` or `<th>`.

    Attributes:
        children: Content.
        header: `True` for `<th>`.
        colspan: The `colspan` attribute (1 if absent or not a number).
        rowspan: The `rowspan` attribute.
        align: The `align` attribute.
        id: `id`.
    """

    children: tuple[Inline, ...] = ()
    header: bool = False
    colspan: int = 1
    rowspan: int = 1
    align: str | None = None
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Row:
    """Table row `<tr>`.

    Attributes:
        cells: Cells.
    """

    cells: tuple[Cell, ...] = ()


@dataclass(frozen=True, slots=True)
class Table:
    """Table `<table>`.

    Attributes:
        rows: Rows.
        id: `id`.
    """

    rows: tuple[Row, ...] = ()
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Section:
    """Section `<section>` -- a chapter or part.

    Attributes:
        id: The section's `id`.
        children: Blocks and nested sections in document order (a mix is allowed: this
            happens in real books).
    """

    id: str | None = None
    children: tuple[Block | Section, ...] = ()

    @property
    def title(self) -> Title | None:
        """First `Title` among `children` or `None`."""
        return next((c for c in self.children if isinstance(c, Title)), None)

    @property
    def epigraph(self) -> tuple[Epigraph, ...]:
        """All epigraphs of the section."""
        return tuple(c for c in self.children if isinstance(c, Epigraph))

    @property
    def image(self) -> Image | None:
        """First image of the section or `None`."""
        return next((c for c in self.children if isinstance(c, Image)), None)

    @property
    def annotation(self) -> Annotation | None:
        """Annotation of the section or `None`."""
        return next((c for c in self.children if isinstance(c, Annotation)), None)

    @property
    def sections(self) -> tuple[Section, ...]:
        """Nested sections."""
        return tuple(c for c in self.children if isinstance(c, Section))

    @property
    def blocks(self) -> tuple[Block, ...]:
        """All children except nested sections."""
        return tuple(c for c in self.children if not isinstance(c, Section))


@dataclass(frozen=True, slots=True)
class Body:
    """`<body>`: main text or notes.

    Attributes:
        name: The `name` attribute (`notes` for notes), usually `None` for the main text.
        children: Title, epigraphs, image, sections and blocks in document order.
        id: `id`.
    """

    name: str | None = None
    children: tuple[Block | Section, ...] = ()
    id: str | None = None

    @property
    def is_notes(self) -> bool:
        """`True` if `name` is set and not `main`."""
        return bool(self.name) and self.name != "main"

    @property
    def title(self) -> Title | None:
        """Title of the body or `None`."""
        return next((c for c in self.children if isinstance(c, Title)), None)

    @property
    def epigraph(self) -> tuple[Epigraph, ...]:
        """Epigraphs of the body."""
        return tuple(c for c in self.children if isinstance(c, Epigraph))

    @property
    def image(self) -> Image | None:
        """Image of the body or `None`."""
        return next((c for c in self.children if isinstance(c, Image)), None)

    @property
    def sections(self) -> tuple[Section, ...]:
        """Top-level sections."""
        return tuple(c for c in self.children if isinstance(c, Section))


Block = (
    Paragraph
    | Subtitle
    | EmptyLine
    | Title
    | Epigraph
    | Annotation
    | Poem
    | Cite
    | TextAuthor
    | Table
    | Image
    | Raw
)
Node = Inline | Block | Section | Body | Stanza | Verse | Row | Cell
