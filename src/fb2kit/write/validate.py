"""Validation of a book before it is written.

The writer refuses to produce a file that no reader can open. Problems are
collected instead of raised one by one, so a caller sees every reason at once.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from xml.etree.ElementTree import Element

from fb2kit.api import FictionBook
from fb2kit.model import iter_nodes
from fb2kit.model.inline import Image, Link, Raw

WRITE_NO_TITLE: Final = "write.no-title"
WRITE_NO_BODY: Final = "write.no-body"
WRITE_DUPLICATE_ID: Final = "write.duplicate-id"
WRITE_INVALID_ID: Final = "write.invalid-id"
WRITE_INVALID_CHAR: Final = "write.invalid-char"
WRITE_MISSING_BINARY: Final = "write.missing-binary"
WRITE_DANGLING_LINK: Final = "write.dangling-link"
WRITE_EMPTY_BODY: Final = "write.empty-body"
WRITE_LOST_ID: Final = "write.lost-id"
WRITE_INVALID_TAG: Final = "write.invalid-tag"
WRITE_NO_GENRE: Final = "write.no-genre"
WRITE_NO_AUTHOR: Final = "write.no-author"
WRITE_INCOMPLETE_AUTHOR: Final = "write.incomplete-author"

_ID_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")
"""An ASCII identifier: the name says it, `:` is not allowed here.

XML would accept a colon in the value of an attribute, but the format uses the
`id` as a name of its own, and a colon would break the references to it.
"""

_BAD_CHARS: Final = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
"""The characters XML 1.0 does not allow anywhere in a document."""

_XML_NAME: Final = re.compile(r"^[A-Za-z_\u00c0-\uffff][A-Za-z0-9._\-\u00b7\u00c0-\uffff]*$")
"""An XML name without a prefix: a colon is not allowed here.

A name with a colon but without a namespace URI is an unbound prefix: lxml in
the tolerant mode keeps such a tag as a plain string, and writing it out
without a declaration would produce a file no parser can read.
"""


class WriteSeverity(StrEnum):
    """Severity of a write problem: `ERROR` blocks the write, `WARNING` does not."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Problem:
    """A single reason why a book cannot be written (or was written with a loss).

    Attributes:
        code: Machine code, for example `write.no-title`.
        message: Human-readable explanation (in English).
        severity: Severity.
        path: Location in the document, if known.
    """

    code: str
    message: str
    severity: WriteSeverity = WriteSeverity.WARNING
    path: str | None = None


@dataclass(frozen=True, slots=True)
class WriteReport:
    """The result of [`validate`][fb2kit.write.validate.validate].

    Attributes:
        problems: All problems in the order they were found.
    """

    problems: tuple[Problem, ...] = ()

    @property
    def errors(self) -> tuple[Problem, ...]:
        """Problems with `WriteSeverity.ERROR`."""
        return tuple(p for p in self.problems if p.severity is WriteSeverity.ERROR)

    @property
    def warnings(self) -> tuple[Problem, ...]:
        """Problems with `WriteSeverity.WARNING`."""
        return tuple(p for p in self.problems if p.severity is WriteSeverity.WARNING)

    @property
    def ok(self) -> bool:
        """`True` if there is no blocking error."""
        return not self.errors


def _bad_chars(text: str | None) -> bool:
    """`True` if the text holds a character XML 1.0 does not allow."""
    return text is not None and _BAD_CHARS.search(text) is not None


def _node_texts(node: object) -> list[str]:
    """Every string a model node holds.

    The fields are read by their names, so a new field of the model is checked
    as soon as it is a string.

    Args:
        node: The node to read.

    Returns:
        The strings of the node.
    """
    out: list[str] = []
    for f in dataclasses.fields(node):  # type: ignore[arg-type]  # node: dataclass, не object
        if not f.compare:
            continue
        value = getattr(node, f.name)
        if isinstance(value, str):
            out.append(value)
    return out


def _model_texts(book: FictionBook) -> list[str]:
    """Every text the model holds, including the unknown elements of the root."""
    out: list[str] = []
    for node in iter_nodes((book.description, book.bodies, book.extra, book.binaries)):
        out.extend(_node_texts(node))
    return out


def _xml_name_ok(name: str) -> bool:
    """`True` if the name can be written without inventing a namespace."""
    return name.startswith("{") or _XML_NAME.match(name) is not None


def _bad_name(name: str, what: str, problems: list[Problem]) -> None:
    """Report a name no parser accepts.

    Args:
        name: The element or attribute name.
        what: "element" or "attribute", for the message.
        problems: The problems found so far; a new one is appended.
    """
    if not _xml_name_ok(name):
        problems.append(
            Problem(
                WRITE_INVALID_TAG,
                f"{name!r} is not a valid {what} name",
                WriteSeverity.ERROR,
            )
        )


def _check_names(book: FictionBook, problems: list[Problem]) -> None:
    """The rule about the names of the unknown elements and their attributes.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    for raw in _raw_nodes(book):
        if raw.element is None:
            _bad_name(raw.tag, "element", problems)
            continue
        for el in raw.element.iter():
            if isinstance(el.tag, str):
                _bad_name(el.tag, "element", problems)
            for name in el.attrib:
                _bad_name(name, "attribute", problems)


def _raw_nodes(book: FictionBook) -> list[Raw]:
    """Every unknown element of the book.

    The `Raw` nodes of the root come first, then the ones that are inside the
    text. The `Raw` nodes of the description are found by the walk: counting
    them twice would make every id of a `<src-title-info>` a duplicate.

    Args:
        book: The book to read.

    Returns:
        The unknown elements.
    """
    out: list[Raw] = [*book.extra]
    out.extend(
        node for node in iter_nodes((book.description, book.bodies)) if isinstance(node, Raw)
    )
    return out


def _raw_attr_texts(raw: Raw) -> list[str]:
    """The texts of the attributes of an unknown element and of its children."""
    out: list[str] = []
    if raw.element is not None:
        for el in raw.element.iter():
            out.extend(el.attrib.values())
    return out


def _element_ids(root: Element) -> set[str]:
    """The `id` attributes of the tree."""
    return {id_ for el in root.iter() if (id_ := el.get("id")) is not None}


def _model_ids(book: FictionBook) -> set[str]:
    """The `id` attributes the model keeps."""
    out: set[str] = set()
    for node in iter_nodes((book.description, book.bodies)):
        node_id = getattr(node, "id", None)
        if node_id is not None:
            out.add(node_id)
    out.update(binary.id for binary in book.binaries)
    for raw in _raw_nodes(book):
        if raw.element is not None:
            out.update(_element_ids(raw.element))
    return out


def _check_one_id(node_id: str, seen: set[str], problems: list[Problem]) -> None:
    """Check one `id` attribute and remember it.

    Args:
        node_id: The value of the attribute.
        seen: The ids that are already taken; the new one is added to it.
        problems: The problems found so far; new ones are appended.
    """
    if node_id in seen:
        problems.append(
            Problem(
                WRITE_DUPLICATE_ID,
                f"duplicate id {node_id!r}",
                WriteSeverity.ERROR,
            )
        )
    seen.add(node_id)
    if not _ID_RE.match(node_id):
        problems.append(
            Problem(
                WRITE_INVALID_ID,
                f"id {node_id!r} is not an ASCII identifier",
                WriteSeverity.ERROR,
            )
        )


def _check_ids(book: FictionBook, problems: list[Problem]) -> None:
    """The rules about the `id` attributes.

    The id of a `<binary>` is an `xs:ID` attribute too, so it is checked like
    the id of any other element: a duplicate of it makes a file the schema
    rejects.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    seen: set[str] = set()
    for node in iter_nodes((book.description, book.bodies)):
        node_id = getattr(node, "id", None)
        if node_id is None:
            continue
        _check_one_id(node_id, seen, problems)
    for binary in book.binaries:
        _check_one_id(binary.id, seen, problems)
    for raw in _raw_nodes(book):
        if raw.element is None:
            continue
        for el in raw.element.iter():
            node_id = el.get("id")
            if node_id is None:
                continue
            _check_one_id(node_id, seen, problems)


def _check_chars(book: FictionBook, problems: list[Problem]) -> None:
    """The rule about the characters XML does not allow.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    for text in _model_texts(book):
        if _bad_chars(text):
            problems.append(
                Problem(
                    WRITE_INVALID_CHAR,
                    "the text holds a character XML 1.0 does not allow",
                    WriteSeverity.ERROR,
                )
            )
    for raw in _raw_nodes(book):
        for text in _raw_attr_texts(raw):
            if _bad_chars(text):
                problems.append(
                    Problem(
                        WRITE_INVALID_CHAR,
                        "an attribute holds a character XML 1.0 does not allow",
                        WriteSeverity.ERROR,
                    )
                )


def _check_references(book: FictionBook, problems: list[Problem]) -> None:
    """The rules about the links to the binaries and to the other nodes.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    binary_ids = {binary.id for binary in book.binaries}
    known: set[str] = _model_ids(book)
    for node in iter_nodes((book.description, book.bodies)):
        if isinstance(node, Image):
            href = node.href or ""
            if href.startswith("#") and href[1:] not in binary_ids:
                problems.append(
                    Problem(
                        WRITE_MISSING_BINARY,
                        f"image refers to the missing binary {href!r}",
                        WriteSeverity.WARNING,
                    )
                )
        elif isinstance(node, Link):
            href = node.href
            if href.startswith("#") and href[1:] not in known:
                problems.append(
                    Problem(
                        WRITE_DANGLING_LINK,
                        f"link refers to the missing target {href!r}",
                        WriteSeverity.WARNING,
                    )
                )


def _check_title_info(book: FictionBook, problems: list[Problem]) -> None:
    """The rules about the required metadata of a book.

    The schema requires at least one genre and one author, and every author is
    either a first name with a last name or a nickname. The rules are warnings:
    a parsed book from the real world may miss them, and refusing to write such
    a book would be worse than writing it with a warning.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    info = book.description.title_info
    if not info.genres:
        problems.append(Problem(WRITE_NO_GENRE, "the book has no <genre>", WriteSeverity.WARNING))
    if not info.authors:
        problems.append(Problem(WRITE_NO_AUTHOR, "the book has no <author>", WriteSeverity.WARNING))
    for author in info.authors:
        if not (author.nickname or (author.first_name and author.last_name)):
            problems.append(
                Problem(
                    WRITE_INCOMPLETE_AUTHOR,
                    (
                        "an author needs a first name and a last name, or a nickname: "
                        f"{author.full_name or '<empty>'!r}"
                    ),
                    WriteSeverity.WARNING,
                )
            )


def _check_bodies(book: FictionBook, problems: list[Problem]) -> None:
    """The rule about an empty body.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    for number, body in enumerate(book.bodies):
        if not body.children:
            problems.append(
                Problem(
                    WRITE_EMPTY_BODY,
                    f"body[{number}] is empty",
                    WriteSeverity.WARNING,
                    f"body[{number}]",
                )
            )


def _check_lost_body_ids(book: FictionBook, problems: list[Problem]) -> None:
    """The rule about the id of a body.

    The format has no place for the id of a `<body>`: the schema allows only
    `xml:lang` and `name` there, so an id would make the file invalid. The
    writer does not write it and says so instead of losing it silently.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    for number, body in enumerate(book.bodies):
        if body.id is not None:
            problems.append(
                Problem(
                    WRITE_LOST_ID,
                    f"the id {body.id!r} of the body is not allowed by the format and will be lost",
                    WriteSeverity.WARNING,
                    f"body[{number}]",
                )
            )


def _check_lost_ids(book: FictionBook, problems: list[Problem]) -> None:
    """The rule about the ids the model does not keep.

    The model has no place for the `id` of a `<title>`, a `<tr>`, a `<stanza>`
    and a few others: such an id is lost on the way out. The writer says so
    instead of losing it silently.

    The rule needs the original tree: a book that was never parsed has no
    original XML, and a book whose `element` belongs to another book would
    report ids that are not lost at all.

    Args:
        book: The book to check.
        problems: The problems found so far; new ones are appended.
    """
    if book.element is None:
        return
    original = _element_ids(book.element)
    if not original:
        return
    kept = _model_ids(book)
    if not kept <= original:
        # The tree does not match the model: the comparison of the ids would be
        # meaningless.
        return
    for id_ in sorted(original - kept):
        problems.append(
            Problem(
                WRITE_LOST_ID,
                f"the id {id_!r} is not kept by the model and will be lost",
                WriteSeverity.WARNING,
            )
        )


def validate(book: FictionBook) -> WriteReport:
    """Check that the book can be written.

    Args:
        book: The book to check.

    Returns:
        The report: blocking errors make `ok` `False`.
    """
    problems: list[Problem] = []
    title = book.description.title_info.title
    if title is None or not title.strip():
        problems.append(
            Problem(
                WRITE_NO_TITLE,
                "the book has no <book-title>",
                WriteSeverity.ERROR,
                "description/title-info/book-title",
            )
        )
    if not book.bodies:
        problems.append(Problem(WRITE_NO_BODY, "the book has no <body>", WriteSeverity.ERROR))
    _check_ids(book, problems)
    _check_names(book, problems)
    _check_chars(book, problems)
    _check_references(book, problems)
    _check_title_info(book, problems)
    _check_bodies(book, problems)
    _check_lost_body_ids(book, problems)
    _check_lost_ids(book, problems)
    return WriteReport(tuple(problems))
