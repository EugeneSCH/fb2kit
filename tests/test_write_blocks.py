import xml.etree.ElementTree as ET

from fb2kit.model.inline import Text
from fb2kit.model.structure import (
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
    Table,
    TextAuthor,
    Title,
    Verse,
)
from fb2kit.write.serialize import _block_el, _body_el, _section_el, _stanza_el


def _names(el: ET.Element) -> list[str]:
    return [c.tag.rpartition("}")[2] for c in el]


def test_section_preserves_child_order() -> None:
    """С7: a section keeps the order of its children."""
    sec = Section(
        "s1",
        (
            Title((Paragraph((Text("Глава"),)),)),
            Epigraph((Paragraph((Text("эпи"),)),)),
            Paragraph((Text("текст"),), id="p1"),
            Section("s2", (Paragraph((Text("вложенная"),)),)),
            Paragraph((Text("после"),)),
        ),
    )
    names = [c.tag.rpartition("}")[2] for c in _section_el(sec)]
    assert names == ["title", "epigraph", "p", "section", "p"]
    assert _section_el(sec).get("id") == "s1"


def test_title_mixes_paragraphs_and_inline_text() -> None:
    """С52: a title mixes inline text and blocks."""
    el = _block_el(Title((Text("a"), Paragraph((Text("b"),)), EmptyLine())))
    names = [c.tag.rpartition("}")[2] for c in el]
    assert el.text == "a"
    assert names == ["p", "empty-line"]


def test_poem_fixed_child_order() -> None:
    """С52: a poem keeps the order of the schema."""
    poem = Poem(
        title=Title((Paragraph((Text("T"),)),)),
        epigraphs=(Epigraph((Paragraph((Text("E"),)),)),),
        stanzas=(Stanza(verses=(Verse((Text("v1"),)), Verse((Text("v2"),)))),),
        text_authors=(TextAuthor((Text("A"),)),),
        date="1900",
        id="poem1",
    )
    names = [c.tag.rpartition("}")[2] for c in _block_el(poem)]
    assert names == ["title", "epigraph", "stanza", "text-author", "date"]


def test_stanza_verses_are_separate_elements() -> None:
    """С52: the verses of a stanza are separate elements."""
    el = _stanza_el(Stanza(verses=(Verse((Text("a"),)), Verse((Text("b"),)))))
    assert [c.tag.rpartition("}")[2] for c in el] == ["v", "v"]


def test_cite_keeps_text_author_position() -> None:
    """С52: a cite keeps the text author after the paragraph."""
    cite = Cite((Paragraph((Text("q"),)), TextAuthor((Text("author"),))), id="c1")
    names = [c.tag.rpartition("}")[2] for c in _block_el(cite)]
    assert names == ["p", "text-author"]


def test_table_header_cells_use_th() -> None:
    """С53: a header cell of a table is written as th."""
    table = Table((Row((Cell((Text("h"),), header=True), Cell((Text("d"),)))),))
    row = _block_el(table)[0]
    assert [c.tag.rpartition("}")[2] for c in row] == ["th", "td"]


def test_cell_spans_and_align_are_emitted() -> None:
    """С53: the spans and the align of a cell are written."""
    cell = Cell((Text("x"),), colspan=2, rowspan=3, align="center", id="c1")
    el = _block_el(Table((Row((cell,)),)))
    td = el[0][0]
    assert (td.get("colspan"), td.get("rowspan"), td.get("align"), td.get("id")) == (
        "2",
        "3",
        "center",
        "c1",
    )


def test_body_keeps_name_and_children_order() -> None:
    """С52: a body keeps its name and the order of its children."""
    body = Body(
        "notes", (Title((Paragraph((Text("1"),)),)), Section("n1", (Paragraph((Text("x"),)),)))
    )
    el = _body_el(body)
    assert el.get("name") == "notes"
    assert [c.tag.rpartition("}")[2] for c in el] == ["title", "section"]


def test_empty_section_serializes_to_empty_element() -> None:
    """С54: an empty section is written as an empty element."""
    el = _section_el(Section())
    assert ET.tostring(el, encoding="unicode").endswith("/>")
