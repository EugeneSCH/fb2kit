"""The golden output of the writer: the bytes must not change.

The writer is a pure function of the model: the same model always gives the
same bytes. The hashes below pin the output of the eight strict fixtures and
of a synthetic book that holds every node type the writer knows. A refactoring
of the writer that changes a single byte of the output breaks these tests.
"""

import hashlib
from pathlib import Path

import pytest
from conftest import cases

import fb2kit
from fb2kit.model.inline import Text
from fb2kit.model.structure import Paragraph, Section

FIXTURES = Path(__file__).parent / "fixtures"

_GOLDEN = cases("write_golden")

# A book that holds every node type the writer knows: the metadata, the
# annotation, the coverpage, the dates, the translators and the series, and in
# the body a title, a paragraph with an inline link, an empty line, a subtitle,
# a poem, a cite, a table and an image.
_SYNTHETIC = (
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
    ' xmlns:l="http://www.w3.org/1999/xlink">'
    "<description><title-info><genre>sf</genre>"
    "<author><first-name>Ann</first-name><last-name>Example</last-name></author>"
    "<book-title>Golden</book-title>"
    "<annotation><p>Note</p></annotation>"
    "<keywords>a, b</keywords>"
    '<date value="2024-05-01">2024</date>'
    '<coverpage><image l:href="#cover.png"/></coverpage>'
    "<lang>en</lang><src-lang>fr</src-lang>"
    "<translator><nickname>tr</nickname></translator>"
    '<sequence name="Series" number="1"/>'
    "</title-info>"
    "<document-info><author><nickname>docs</nickname></author>"
    "<program-used>hand</program-used><id>gid</id><version>1.0</version>"
    "<history><p>v1</p></history><publisher>Pub</publisher></document-info>"
    "<publish-info><book-name>Print</book-name><publisher>Pub</publisher>"
    "<city>Town</city><year>2024</year><isbn>0</isbn></publish-info>"
    "</description>"
    '<body><section id="s1"><title><p>Chapter</p></title>'
    '<p>Text <emphasis>emph</emphasis> and <a l:href="#n1" type="note">[1]</a>.</p>'
    "<empty-line/><subtitle>Sub</subtitle>"
    "<poem><title><p>Poem</p></title><stanza><v>one</v><v>two</v></stanza></poem>"
    "<cite><p>Quote</p><text-author>Author</text-author></cite>"
    '<table><tr><th>H</th><td colspan="2" rowspan="3" align="left">C</td></tr></table>'
    '<image l:href="#map.png" alt="alt" title="title"/>'
    "</section></body>"
    "</FictionBook>"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("name", sorted(_GOLDEN["fixtures"]))
def test_the_compact_output_of_a_fixture_is_unchanged(name: str) -> None:
    """С70: the compact output of a fixture is pinned."""
    book = fb2kit.parse(FIXTURES / name)
    assert _sha(book.to_bytes()) == _GOLDEN["fixtures"][name]["compact"]


@pytest.mark.parametrize("name", sorted(_GOLDEN["fixtures"]))
def test_the_pretty_output_of_a_fixture_is_unchanged(name: str) -> None:
    """С70: the pretty output of a fixture is pinned."""
    book = fb2kit.parse(FIXTURES / name)
    assert _sha(book.to_bytes(pretty=True)) == _GOLDEN["fixtures"][name]["pretty"]


def test_the_compact_output_of_every_node_type_is_unchanged() -> None:
    """С70: the compact output of every node type is pinned."""
    book = fb2kit.parse_string(_SYNTHETIC)
    assert book.to_bytes().decode("utf-8") == _GOLDEN["synthetic"]["compact"]


def test_the_pretty_output_of_every_node_type_is_unchanged() -> None:
    """С70: the pretty output of every node type is pinned."""
    book = fb2kit.parse_string(_SYNTHETIC)
    assert book.to_bytes(pretty=True).decode("utf-8") == _GOLDEN["synthetic"]["pretty"]


def test_the_output_of_an_edited_book_is_unchanged() -> None:
    """С70: the output of an edited book is pinned."""
    # The edit path rebuilds the tree through the dataclass walk, so the bytes
    # of an edited book are pinned too.
    book = fb2kit.parse_string(_SYNTHETIC)
    target = book.by_id("s1")
    assert isinstance(target, Section)
    edited = fb2kit.replace_node(book, target, Section("s1", (Paragraph((Text("NEW"),)),)))
    assert edited.to_bytes().decode("utf-8") == _GOLDEN["edited"]
