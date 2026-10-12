"""Book metadata: title-info, document-info, publish-info."""

from __future__ import annotations

from dataclasses import dataclass

from fb2kit.model.inline import Image, Raw
from fb2kit.model.structure import Block


@dataclass(frozen=True, slots=True)
class Author:
    """Author, translator or document author.

    Attributes:
        first_name: First name.
        middle_name: Middle name.
        last_name: Last name.
        nickname: Nickname.
        emails: `<email>` addresses.
        home_pages: `<home-page>` addresses.
    """

    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    emails: tuple[str, ...] = ()
    home_pages: tuple[str, ...] = ()

    @property
    def full_name(self) -> str:
        """First Middle Last from the non-empty parts, else the nickname, else `""`."""
        parts = (self.first_name, self.middle_name, self.last_name)
        return " ".join(p for p in parts if p) or self.nickname or ""


@dataclass(frozen=True, slots=True)
class Sequence:
    """Series.

    Attributes:
        name: Series name.
        number: Number in the series; `None` if not set or not an integer.
    """

    name: str | None = None
    number: int | None = None


@dataclass(frozen=True, slots=True)
class Date:
    """Date `<date>`.

    Attributes:
        value: Date text as written.
        lang: `xml:lang`, if set.
        iso: The `value` attribute (usually an ISO date `YYYY-MM-DD`).
    """

    value: str
    lang: str | None = None
    iso: str | None = None


@dataclass(frozen=True, slots=True)
class TitleInfo:
    """`<title-info>`: information about the book.

    Attributes:
        genres: Genres (`<genre>`), FB2 codes as is.
        authors: Authors.
        title: Title (`<book-title>`).
        annotation: Annotation blocks or `None` if there is none.
        keywords: Keywords as a single string.
        dates: Dates.
        coverpage: `<coverpage>` images; the first is the cover (`FictionBook.cover`).
        lang: Book language.
        src_lang: Original language.
        translators: Translators.
        sequences: Series.
    """

    genres: tuple[str, ...] = ()
    authors: tuple[Author, ...] = ()
    title: str | None = None
    annotation: tuple[Block, ...] | None = None
    keywords: str | None = None
    dates: tuple[Date, ...] = ()
    coverpage: tuple[Image, ...] = ()
    lang: str | None = None
    src_lang: str | None = None
    translators: tuple[Author, ...] = ()
    sequences: tuple[Sequence, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """`<document-info>`: information about the FB2 file.

    Attributes:
        authors: File authors.
        program_used: Program that produced the file.
        dates: Dates.
        source_url: The first `<src-url>`.
        source_ocr: OCR author.
        ids: `<id>` values.
        version: File version.
        history: `<history>` paragraphs as text.
        publisher: File publisher.
    """

    authors: tuple[Author, ...] = ()
    program_used: str | None = None
    dates: tuple[Date, ...] = ()
    source_url: str | None = None
    source_ocr: str | None = None
    ids: tuple[str, ...] = ()
    version: str | None = None
    history: tuple[str, ...] = ()
    publisher: str | None = None


@dataclass(frozen=True, slots=True)
class PublishInfo:
    """`<publish-info>`: information about the paper edition.

    Attributes:
        book_name: Edition title.
        publisher: Publisher.
        city: City.
        year: Year, as a string as in the file.
        isbn: ISBN.
        sequences: Publisher series.
    """

    book_name: str | None = None
    publisher: str | None = None
    city: str | None = None
    year: str | None = None
    isbn: str | None = None
    sequences: tuple[Sequence, ...] = ()


@dataclass(frozen=True, slots=True)
class CustomInfo:
    """`<custom-info>`.

    Attributes:
        info_type: The `info-type` attribute.
        text: Element text.
    """

    info_type: str | None = None
    text: str = ""


@dataclass(frozen=True, slots=True)
class Description:
    """`<description>`: all book metadata.

    Attributes:
        title_info: Book information (an empty `TitleInfo()` if the element is missing).
        document_info: File information or `None`.
        publish_info: Edition information or `None`.
        custom_info: `<custom-info>` elements.
        extra: Other `<description>` elements as `Raw` (for example `<src-title-info>`).
    """

    title_info: TitleInfo
    document_info: DocumentInfo | None = None
    publish_info: PublishInfo | None = None
    custom_info: tuple[CustomInfo, ...] = ()
    extra: tuple[Raw, ...] = ()
