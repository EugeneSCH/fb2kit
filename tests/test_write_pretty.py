"""The pretty printer: it formats the tree without touching the text it carries."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import fb2kit
from fb2kit.write.pretty import render

FIXTURES = Path(__file__).parent / "fixtures"


def test_pretty_indents_simple_elements() -> None:
    """С74: the pretty printer indents the elements."""
    root = ET.fromstring("<r><a><b>x</b></a></r>")
    out = render(root)
    assert out.splitlines() == ["<r>", "  <a>", "    <b>x</b>", "  </a>", "</r>"]


def test_pretty_keeps_text_bearing_elements_on_one_line() -> None:
    """С74: an element with a text stays on one line."""
    root = ET.fromstring("<r><p>текст <b>жирный</b> хвост</p></r>")
    out = render(root)
    assert "<p>текст <b>жирный</b> хвост</p>" in out
    assert out.count("\n") <= 2


def test_pretty_does_not_mutate_the_tree() -> None:
    """С74: the pretty printer does not change the tree."""
    root = ET.fromstring("<r><a><b>x</b></a></r>")
    before = ET.tostring(root, encoding="unicode")
    render(root)
    assert ET.tostring(root, encoding="unicode") == before


def test_pretty_keeps_tail_inline() -> None:
    """С74: the pretty printer keeps the tail of an element."""
    root = ET.fromstring("<r><a>x</a>tail</r>")
    out = render(root)
    assert "tail" in out
    assert "<a>x</a>tail" in out.replace("\n", "").replace("  ", "")


def test_pretty_escapes_the_special_characters() -> None:
    """С6: the pretty printer escapes the special characters."""
    root = ET.fromstring("<r><a>x &amp; y &lt; z</a></r>")
    out = render(root)
    assert "x &amp; y &lt; z" in out
    assert "&amp;amp;" not in out


def test_pretty_escapes_quotes_in_an_attribute() -> None:
    """С6: the pretty printer escapes the quotes of an attribute."""
    root = ET.fromstring('<r><a id="a&quot;b">x</a></r>')
    out = render(root)
    assert 'id="a&quot;b"' in out


def test_pretty_writes_an_empty_element_as_a_self_closing_tag() -> None:
    """С75: an empty element is written as a self closing tag."""
    root = ET.fromstring("<r><a/></r>")
    out = render(root)
    assert out.splitlines() == ["<r>", "  <a/>", "</r>"]


def test_pretty_keeps_a_nested_text_element_on_one_line() -> None:
    """С74: an element with a text keeps its child on one line."""
    # An element with text is written in one line, but its children may still be nested.
    root = ET.fromstring("<r><p>text<b>bold</b></p></r>")
    out = render(root)
    assert "<p>text<b>bold</b></p>" in out


def test_pretty_keeps_the_attributes_of_an_empty_element() -> None:
    """С75: an empty element keeps its attributes."""
    # An empty element has no text to lose, but its attributes are data too:
    # <image l:href="#pic"/> must not become <image/>.
    root = ET.fromstring(
        '<r xmlns:l="http://www.w3.org/1999/xlink">'
        '<image l:href="#pic" alt="a" title="t" id="i1"/></r>'
    )
    out = render(root)
    assert '<image l:href="#pic" alt="a" title="t" id="i1"/>' in out


def test_pretty_keeps_the_attributes_of_an_empty_element_on_its_own_line() -> None:
    """С75: an empty element on its own line keeps its attributes."""
    # The same element, but not in a compact line: the attributes must be there too.
    root = ET.fromstring(
        '<r xmlns:l="http://www.w3.org/1999/xlink"><a><image l:href="#pic"/></a></r>'
    )
    out = render(root)
    assert out.splitlines() == [
        '<r xmlns:l="http://www.w3.org/1999/xlink">',
        "  <a>",
        '    <image l:href="#pic"/>',
        "  </a>",
        "</r>",
    ]


def test_pretty_keeps_the_attributes_of_an_empty_element_with_a_foreign_namespace() -> None:
    """С75: an empty element keeps the namespace of its attributes."""
    # A namespace of an attribute must not be lost either: the prefix may be
    # ours, but the namespace has to stay.
    root = ET.fromstring('<r><image xmlns:z="http://example.com/ns" z:attr="v"/></r>')
    out = render(root)
    assert "http://example.com/ns" in out
    assert 'attr="v"' in out


@pytest.mark.parametrize("name", ["structure-rich.fb2", "metadata-full.fb2", "notes-and-links.fb2"])
def test_pretty_output_has_the_same_attributes_as_the_compact_one(name: str) -> None:
    """С76: the pretty and the compact output have the same attributes."""
    # The two writers must describe the same document: the pretty output may
    # differ in the layout, but not in the attributes of the elements.
    book = fb2kit.parse(FIXTURES / name)
    compact = fb2kit.parse_string(book.to_xml()).element
    pretty = fb2kit.parse_string(book.to_xml(pretty=True)).element
    assert _attributes(pretty) == _attributes(compact)


def _attributes(root: ET.Element) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """The tag and the attributes of every element of the tree, in document order."""
    return [(el.tag, tuple(sorted(el.attrib.items()))) for el in root.iter()]


@pytest.mark.corpus
def test_the_pretty_output_of_the_corpus_keeps_the_attributes() -> None:
    """С76: the pretty output of the corpus keeps the attributes."""
    from conftest import corpus_files

    for path in corpus_files():
        book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
        compact = fb2kit.parse_string(book.to_xml()).element
        pretty = fb2kit.parse_string(book.to_xml(pretty=True)).element
        assert _attributes(pretty) == _attributes(compact), path.name
        # The text survives the pretty output too: only the whitespace of the
        # indentation is new, so the model is not equal but the words are.
        assert _text(pretty) == _text(compact), path.name


def _text(root: ET.Element) -> str:
    """The text of the tree without the whitespace."""
    return "".join("".join(root.itertext()).split())


def test_the_pretty_output_is_read_by_both_backends() -> None:
    """С77: the pretty output is read by both backends."""
    # The pretty output must be a well-formed XML document: both backends have
    # to be able to read it.
    lxml_etree = pytest.importorskip("lxml.etree")
    book = fb2kit.parse(FIXTURES / "structure-rich.fb2")
    xml = book.to_xml(pretty=True)
    ET.fromstring(xml)
    lxml_etree.fromstring(xml)


def test_the_pretty_output_does_not_give_the_same_model() -> None:
    """С78: the pretty output does not give the same model."""
    # A documented limitation: the guarantee "one model -> the same bytes ->
    # the same model" holds for the compact output only. A paragraph with an
    # element inside is written on several lines, and the whitespace of the
    # indentation becomes the text of the paragraph, so the model read back
    # from the pretty output is not the model that was written. The attributes
    # and the words are the same -- only the whitespace of the indentation is
    # new.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        "<body><section><p><strong>text</strong></p></section></body></FictionBook>"
    )
    again = fb2kit.parse_string(book.to_xml(pretty=True))
    assert again.bodies != book.bodies
    compact = fb2kit.parse_string(book.to_xml())
    assert _attributes(again.element) == _attributes(compact.element)
    assert _text(again.element) == _text(compact.element)
