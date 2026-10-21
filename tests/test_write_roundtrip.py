"""Round-trip of the writer: the model must survive a write and a re-read.

The writer and the parser meet here: every character the writer emits has to
come back the way the model stored it. XML normalizes whitespace on the way
in, so the writer has to escape the characters the parser would change.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import fb2kit
from fb2kit import parse_string
from fb2kit.api import FictionBook
from fb2kit.model.inline import Image, Link, Text
from fb2kit.parser import FB2_NS
from fb2kit.write.serialize import _el, serialize_book, serialize_bytes

FIXTURES = Path(__file__).parent / "fixtures"

_BOOK = (
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
    ' xmlns:l="http://www.w3.org/1999/xlink">'
    "<description><title-info><book-title>T</book-title></title-info></description>"
    "<body><section><p>{text}</p></section></body></FictionBook>"
)


def _book_with(text: str) -> str:
    return _BOOK.format(text=text)


def _paragraph_text(book: FictionBook) -> str:
    """The text of the first paragraph of the first section of the first body."""
    body = book.bodies[0]
    section = body.children[0]
    paragraph = section.children[0]
    return "".join(child.value for child in paragraph.children)


def test_carriage_return_in_text_survives_the_round_trip() -> None:
    """С79: a carriage return in the text survives the round trip."""
    # A raw CR in the output is normalized into LF by every XML parser, so the writer
    # has to write it as a character reference.
    book = parse_string(_book_with("a&#13;b"))
    data = serialize_book(book)
    assert b"&#13;" in data
    again = parse_string(data.decode())
    assert _paragraph_text(again) == "a\rb"


def test_carriage_return_in_text_is_escaped_in_the_output() -> None:
    """С79: a carriage return is written as a character reference."""
    root = _el("p", text="a\rb")
    data = serialize_bytes(root)
    assert b"a&#13;b" in data
    assert b"\r" not in data


def test_line_feed_in_text_is_left_as_it_is() -> None:
    """С79: a line feed in the text is left as it is."""
    # A LF is normalized into a LF, so it needs no escaping.
    root = _el("p", text="a\nb")
    data = serialize_bytes(root)
    assert b"a\nb" in data


def test_tab_in_an_attribute_value_survives_the_round_trip() -> None:
    """С79: a tab in an attribute survives the round trip."""
    # XML 1.0 3.3.3: a horizontal tab in an attribute value is normalized into a space.
    book = parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="sec&#9;1"><p>text</p></section></body></FictionBook>'
    )
    assert book.bodies[0].children[0].id == "sec\t1"
    data = serialize_book(book)
    assert b"&#9;" in data
    again = parse_string(data.decode())
    assert again.bodies[0].children[0].id == "sec\t1"


def test_tab_in_an_attribute_value_is_escaped_in_the_output() -> None:
    """С79: a tab in an attribute is written as a character reference."""
    root = _el("p", (("id", "a\tb"),))
    data = serialize_bytes(root)
    assert b'id="a&#9;b"' in data
    assert b"\t" not in data


def test_the_whitespace_of_an_attribute_value_survives_the_round_trip() -> None:
    """С79: every whitespace of an attribute survives the round trip."""
    # XML 1.0 3.3.3: every whitespace character of an attribute value is normalized
    # into a space, so all of them have to be written as character references.
    for value in ("a\tb", "a\rb", "a\nb", "a\r\nb"):
        root = _el("p", (("id", value),))
        again = ET.fromstring(serialize_bytes(root))
        assert again.get("id") == value


def test_an_empty_link_href_survives_the_round_trip() -> None:
    """С80: an empty href of a link survives the round trip."""
    # l:href is required by the schema, and an empty one is still an href: without it the
    # <a> is read back as an unknown element and the model changes its type.
    book = parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
        ' xmlns:l="http://www.w3.org/1999/xlink">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section><p><a l:href="">t</a></p></section></body></FictionBook>'
    )
    link = book.bodies[0].children[0].children[0].children[0]
    assert link == Link(href="", children=(Text("t"),))
    data = serialize_book(book)
    assert b'l:href=""' in data
    again = parse_string(data.decode())
    assert again.bodies[0].children[0].children[0].children[0] == link


def test_an_empty_image_href_survives_the_round_trip() -> None:
    """С80: an empty href of an image survives the round trip."""
    book = parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
        ' xmlns:l="http://www.w3.org/1999/xlink">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section><p><image l:href="" alt="a"/></p></section></body></FictionBook>'
    )
    image = book.bodies[0].children[0].children[0].children[0]
    assert image == Image(href="", alt="a")
    data = serialize_book(book)
    assert b'l:href=""' in data
    again = parse_string(data.decode())
    assert again.bodies[0].children[0].children[0].children[0] == image


STRICT_FIXTURES = [
    "minimal.fb2",
    "metadata-full.fb2",
    "notes-and-links.fb2",
    "structure-rich.fb2",
    "binary-cover.fb2",
    "sample.fb2",
    "utf8-bom.fb2",
    "koi8r-prolog.fb2",
]


def test_serialize_book_honours_pretty() -> None:
    """С47: the lowest entry point of the writer honours pretty."""
    # The parameter of the lowest entry point of the writer is not dead.
    book = parse_string(_book_with("text"))
    data = serialize_book(book, pretty=True)
    assert b"\n  <" in data
    assert data != serialize_book(book)
    parse_string(data.decode())


def _content(book: FictionBook) -> tuple[object, ...]:
    """The model content without the report and without the spelling of the base64."""
    return (
        book.description,
        book.bodies,
        book.extra,
        tuple((b.id, b.content_type, b.data) for b in book.binaries),
    )


def _text_of(root: ET.Element) -> str:
    """The meaningful text: all the whitespace is removed, so the line breaks of
    the base64 do not count."""
    return "".join("".join(root.itertext()).split())


@pytest.mark.parametrize("name", STRICT_FIXTURES)
def test_output_is_a_byte_fixpoint(name: str) -> None:
    """С2: the output of a book is a byte fixpoint."""
    first = fb2kit.parse(FIXTURES / name)
    once = first.to_bytes()
    twice = fb2kit.parse(once).to_bytes()
    assert once == twice


@pytest.mark.parametrize("name", STRICT_FIXTURES)
def test_output_reparses_in_strict_mode(name: str) -> None:
    """С1: the output is re-read in strict mode."""
    book = fb2kit.parse(FIXTURES / name)
    again = fb2kit.parse(book.to_bytes(), mode=fb2kit.Mode.STRICT)
    assert _content(again) == _content(book)


@pytest.mark.parametrize("name", STRICT_FIXTURES)
def test_no_text_is_lost(name: str) -> None:
    """С3: no text is lost on the way out."""
    book = fb2kit.parse(FIXTURES / name)
    assert _text_of(book.element) == _text_of(fb2kit.parse(book.to_bytes()).element)


def test_cp1251_book_becomes_utf8_and_keeps_text() -> None:
    """С5: a book in a single byte encoding becomes UTF-8 and keeps its text."""
    book = fb2kit.parse(FIXTURES / "cp1251-no-prolog.fb2", mode=fb2kit.Mode.TOLERANT)
    out = book.to_bytes()
    out.decode("utf-8")  # fails if the output is not UTF-8
    again = fb2kit.parse(out, mode=fb2kit.Mode.STRICT)
    assert again.description.title_info.title == book.description.title_info.title


def test_unknown_subtree_survives_roundtrip() -> None:
    """С4: an unknown subtree survives the round trip."""
    raw = '<foo><bar a="1">x</bar><baz>y</baz></foo>'
    xml = (
        f'<FictionBook xmlns="{FB2_NS}"><description><title-info>'
        "<book-title>T</book-title></title-info></description>"
        f"<body><section><p>a{raw}b</p></section></body></FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    out = book.to_xml()
    assert "<bar" in out and "<baz>" in out


@pytest.mark.corpus
def test_corpus_roundtrip_tolerant() -> None:
    """С30: the books of the corpus survive the round trip."""
    from conftest import corpus_files

    for path in corpus_files():
        book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
        again = fb2kit.parse(book.to_bytes(strict=False), mode=fb2kit.Mode.TOLERANT)
        assert _content(again) == _content(book), path.name
        assert _text_of(book.element) == _text_of(again.element), path.name
