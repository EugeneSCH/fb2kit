"""Creating a book from scratch.

The builder collects the parts of a book and turns them into a model. The
writer does the rest: the builder never forms XML itself, so a book built
here and a book parsed from a file are written the same way.
"""

from __future__ import annotations

import base64
import datetime
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from fb2kit.model.binary import Binary
from fb2kit.model.inline import Image, Inline, Text
from fb2kit.model.metadata import (
    Author,
    Date,
    Description,
    DocumentInfo,
    TitleInfo,
)
from fb2kit.model.metadata import (
    Sequence as Series,
)
from fb2kit.model.structure import (
    Block,
    Body,
    EmptyLine,
    Paragraph,
    Poem,
    Section,
    Stanza,
    Subtitle,
    TextAuthor,
    Title,
    Verse,
)

if TYPE_CHECKING:
    from fb2kit.api import FictionBook

_NOTES_BODY_NAME = "notes"


class IdGenerator:
    """Names for the nodes that need one.

    The names are built from a prefix and a number: `note-1`, `note-2`. The
    names that are already taken are skipped, so two calls never give the
    same name.

    Attributes:
        taken: The names that are in use.
    """

    def __init__(self, existing: Iterable[str] = ()) -> None:
        self.taken: set[str] = set(existing)
        self._counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        """A free name with the given prefix.

        Args:
            prefix: The prefix of the name, for example `note`.

        Returns:
            The name, for example `note-1`.
        """
        number = self._counters.get(prefix, 0) + 1
        while f"{prefix}-{number}" in self.taken:
            number += 1
        self._counters[prefix] = number
        name = f"{prefix}-{number}"
        self.taken.add(name)
        return name


def _inline(parts: Sequence[str | Inline]) -> tuple[Inline, ...]:
    """Turn the parts of a paragraph into inline nodes.

    Args:
        parts: The parts: plain strings and inline nodes.

    Returns:
        The inline nodes, in order.
    """
    out: list[Inline] = []
    for part in parts:
        if isinstance(part, str):
            out.append(Text(part))
        else:
            out.append(part)
    return tuple(out)


class SectionBuilder:
    """The content of a section.

    A section holds blocks and nested sections. The builder keeps them in the
    order they were added: the order of the document is the order of the
    calls.

    Attributes:
        id: The `id` of the section.
        title: The title of the section.
    """

    def __init__(
        self, title: str | None = None, id: str | None = None, ids: IdGenerator | None = None
    ) -> None:
        self.id = id
        self.title = title
        self._ids = ids
        if ids is not None and id is not None:
            ids.taken.add(id)
        self._children: list[Block | Section | SectionBuilder] = []

    @property
    def section(self) -> Section:
        """The section the builder has collected so far."""
        children: list[Block | Section] = []
        if self.title is not None:
            children.append(Title((Paragraph((Text(self.title),)),)))
        for child in self._children:
            children.append(child.section if isinstance(child, SectionBuilder) else child)
        return Section(self.id, tuple(children))

    def add_paragraph(self, *parts: str | Inline, style: str | None = None) -> SectionBuilder:
        """Add a paragraph.

        Args:
            parts: The parts of the paragraph: plain strings and inline nodes.
            style: The `style` attribute of the paragraph.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self._children.append(Paragraph(_inline(parts), style))
        return self

    def add_subtitle(self, text: str) -> SectionBuilder:
        """Add a subtitle.

        Args:
            text: The text of the subtitle.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self._children.append(Subtitle((Text(text),)))
        return self

    def add_empty_line(self) -> SectionBuilder:
        """Add an empty line.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self._children.append(EmptyLine())
        return self

    def add_poem(
        self,
        title: str | None,
        stanzas: Sequence[Sequence[str]],
        *,
        author: str | None = None,
    ) -> SectionBuilder:
        """Add a poem.

        Args:
            title: The title of the poem.
            stanzas: The stanzas; every stanza is a list of lines.
            author: The author of the poem.

        Returns:
            The builder itself, so the calls can be chained.
        """
        poem_title = Title((Paragraph((Text(title),)),)) if title is not None else None
        built = tuple(
            Stanza(verses=tuple(Verse((Text(line),)) for line in stanza)) for stanza in stanzas
        )
        text_authors = (TextAuthor((Text(author),)),) if author is not None else ()
        self._children.append(Poem(poem_title, (), built, text_authors))
        return self

    def add_image(self, binary: Binary, *, alt: str | None = None) -> SectionBuilder:
        """Add an image that points to a binary.

        Args:
            binary: The binary the image points to.
            alt: The `alt` attribute of the image.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self._children.append(Image(href=f"#{binary.id}", alt=alt))
        return self

    def add_section(self, title: str | None = None, *, id: str | None = None) -> SectionBuilder:
        """Add a nested section.

        Args:
            title: The title of the section.
            id: The `id` of the section.

        Returns:
            The builder of the nested section.
        """
        nested = SectionBuilder(title, id, self._ids)
        self._children.append(nested)
        return nested


class BookBuilder:
    """A book that is being written.

    The builder is mutable; the book it makes is not: every call of `build`
    returns a new, frozen book.

    Attributes:
        title: The title of the book.
        lang: The language of the book.
    """

    def __init__(
        self,
        *,
        title: str,
        lang: str = "ru",
        authors: Iterable[Author] = (),
        document_date: str | None = None,
    ) -> None:
        self.title = title
        self.lang = lang
        self.authors: list[Author] = list(authors)
        self.document_date = document_date or datetime.date.today().isoformat()
        self.genres: list[str] = []
        self.keywords: str | None = None
        self.sequences: list[Series] = []
        self.annotation: tuple[Block, ...] | None = None
        self.binaries: list[Binary] = []
        self.cover: Binary | None = None
        self.ids = IdGenerator()
        self._sections: list[SectionBuilder] = []
        self._notes: list[Section] = []

    def add_author(self, author: Author) -> BookBuilder:
        """Add an author.

        Args:
            author: The author.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self.authors.append(author)
        return self

    def add_genre(self, code: str) -> BookBuilder:
        """Add a genre.

        Args:
            code: The code of the genre, for example `sf`.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self.genres.append(code)
        return self

    def set_sequence(self, name: str, number: int | None = None) -> BookBuilder:
        """Set the series the book belongs to.

        Args:
            name: The name of the series.
            number: The number of the book in the series.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self.sequences = [Series(name, number)]
        return self

    def set_keywords(self, keywords: str) -> BookBuilder:
        """Set the keywords of the book.

        Args:
            keywords: The keywords, as a single string.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self.keywords = keywords
        return self

    def set_annotation(self, *blocks: Block) -> BookBuilder:
        """Set the annotation of the book.

        Args:
            blocks: The blocks of the annotation.

        Returns:
            The builder itself, so the calls can be chained.
        """
        self.annotation = blocks
        return self

    def add_section(self, title: str | None = None, *, id: str | None = None) -> SectionBuilder:
        """Add a section to the main text.

        Args:
            title: The title of the section.
            id: The `id` of the section.

        Returns:
            The builder of the section.
        """
        section = SectionBuilder(title, id, self.ids)
        self._sections.append(section)
        return section

    def add_binary(
        self,
        data: bytes,
        content_type: str = "image/png",
        *,
        id: str | None = None,
    ) -> Binary:
        """Attach a file to the book.

        Args:
            data: The bytes of the file.
            content_type: The MIME type of the file.
            id: The `id` of the binary; a free name is taken when it is not given.

        Returns:
            The binary.
        """
        name = id if id is not None else self.ids.next("bin")
        self.ids.taken.add(name)
        binary = Binary(name, content_type, base64.b64encode(data).decode("ascii"))
        self.binaries.append(binary)
        return binary

    def set_cover(self, binary: Binary) -> BookBuilder:
        """Set the cover of the book.

        Args:
            binary: The binary the cover points to.

        Returns:
            The builder itself, so the calls can be chained.
        """
        if binary not in self.binaries:
            self.binaries.append(binary)
        self.cover = binary
        return self

    def add_note(self, text: str, *, title: str | None = None) -> str:
        """Add a footnote.

        The footnote goes to the body of the notes; the body is created when it
        is not there yet.

        Args:
            text: The text of the footnote.
            title: The title of the footnote; the number of the note by default.

        Returns:
            The `id` of the footnote, to be used in a link.
        """
        note_id = self.ids.next("note")
        heading = title if title is not None else str(len(self._notes) + 1)
        self._notes.append(
            Section(
                note_id,
                (
                    Title((Paragraph((Text(heading),)),)),
                    Paragraph((Text(text),)),
                ),
            )
        )
        return note_id

    def build(self) -> FictionBook:
        """The book the builder has collected.

        Returns:
            The new book.

        Raises:
            Fb2WriteError: The book has a blocking problem: no title or no body.
        """
        from fb2kit.api import FictionBook
        from fb2kit.errors import Fb2WriteError
        from fb2kit.write.edit import reindex
        from fb2kit.write.validate import validate

        bodies: list[Body] = []
        if self._sections or self.binaries or self.cover is not None:
            # A book with a cover and no text still has a body: the format wants
            # one, and the cover has nowhere to live without it.
            bodies.append(Body(children=tuple(s.section for s in self._sections)))
        if self._notes:
            bodies.append(Body(name=_NOTES_BODY_NAME, children=tuple(self._notes)))
        title_info = TitleInfo(
            genres=tuple(self.genres),
            authors=tuple(self.authors),
            title=self.title,
            annotation=self.annotation,
            keywords=self.keywords,
            coverpage=(Image(href=f"#{self.cover.id}"),) if self.cover is not None else (),
            lang=self.lang,
            sequences=tuple(self.sequences),
        )
        document_authors = tuple(self.authors) or (Author(nickname="fb2kit"),)
        document_info = DocumentInfo(
            authors=document_authors,
            program_used="fb2kit",
            dates=(Date(self.document_date),),
            ids=(self.ids.next("doc"),),
            version="1.0",
        )
        book = FictionBook(
            description=Description(title_info, document_info=document_info),
            bodies=tuple(bodies),
            binaries=tuple(self.binaries),
            element=ET.Element("FictionBook"),
            cover=self.cover,
        )
        report = validate(book)
        if report.errors:
            raise Fb2WriteError(report.errors)
        return reindex(book)


def new_book(
    *,
    title: str,
    lang: str = "ru",
    authors: Iterable[Author] = (),
    document_date: str | None = None,
) -> BookBuilder:
    """Start a new book.

    Args:
        title: The title of the book.
        lang: The language of the book.
        authors: The authors of the book.
        document_date: The date of the document for `<document-info>`; today by
            default. Pass it explicitly to get the same output on another day.

    Returns:
        The builder of the book.
    """
    return BookBuilder(title=title, lang=lang, authors=authors, document_date=document_date)


__all__ = [
    "BookBuilder",
    "IdGenerator",
    "SectionBuilder",
    "new_book",
]
