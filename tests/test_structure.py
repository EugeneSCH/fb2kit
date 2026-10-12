# tests/test_structure.py
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from fb2kit.builder import Builder
from fb2kit.model.bind import bind_body, bind_section
from fb2kit.model.inline import Text
from fb2kit.model.structure import (
    Cite,
    EmptyLine,
    Paragraph,
    Poem,
    Section,
    Subtitle,
    Table,
    TextAuthor,
    Title,
)
from fb2kit.parser import FB2_NS, XLINK_NS, parse_tree

FIXTURES = Path(__file__).parent / "fixtures"


def _ctx() -> Builder:
    return Builder(diagnostics=[], index={})


def _body():
    tree = parse_tree((FIXTURES / "structure-rich.fb2").read_text(encoding="utf-8"))
    return bind_body(next(el for el in tree.root if el.tag.endswith("}body")), _ctx())


def test_children_order_is_preserved() -> None:
    section = _body().children[0]
    kinds = [type(c).__name__ for c in section.children]
    assert kinds[:5] == ["Title", "Epigraph", "Image", "Annotation", "Paragraph"]
    assert "Section" in kinds and kinds[-1] == "Paragraph"


def test_convenience_properties_extract_without_reordering() -> None:
    section = _body().children[0]
    assert isinstance(section.title, Title)
    assert isinstance(section.sections[0], Section)
    assert section.sections[0].title is None
    assert all(not isinstance(b, Section) for b in section.blocks)


def test_poem_has_stanzas_and_verses() -> None:
    section = _body().children[0]
    poem = next(c for c in section.children if isinstance(c, Poem))
    assert len(poem.stanzas) == 2
    assert len(poem.stanzas[0].verses) == 2


def test_cite_keeps_text_author_in_place() -> None:
    section = _body().children[0]
    cite = next(c for c in section.children if isinstance(c, Cite))
    assert any(isinstance(c, TextAuthor) for c in cite.children)


def test_table_cell_spans() -> None:
    section = _body().children[0]
    table = next(c for c in section.children if isinstance(c, Table))
    assert table.rows[0].cells[1].colspan == 2
    assert table.rows[0].cells[0].rowspan == 1
    assert table.rows[0].cells[0].header is True and table.rows[0].cells[1].header is False


def test_subtitle_and_empty_line_are_distinct_nodes() -> None:
    section = _body().children[0]
    assert any(isinstance(c, Subtitle) for c in section.children)
    assert any(isinstance(c, EmptyLine) for c in section.children)


def test_unknown_block_is_raw_and_reported() -> None:
    ctx = _ctx()
    el = ET.fromstring(f'<section xmlns="{FB2_NS}" xmlns:l="{XLINK_NS}"><weird>x</weird></section>')
    section = bind_section(el, ctx)
    assert type(section.children[0]).__name__ == "Raw"
    assert ctx.diagnostics


def test_nested_sections_are_three_levels_deep() -> None:
    el = ET.fromstring(
        f'<section xmlns="{FB2_NS}"><section><section><p>x</p></section></section></section>'
    )
    section = bind_section(el, _ctx())
    assert section.sections[0].sections[0].blocks[0] == Paragraph(children=(Text("x"),))


def test_empty_section_binds_to_empty_node() -> None:
    assert bind_section(ET.fromstring(f'<section xmlns="{FB2_NS}"/>'), _ctx()) == Section()


def test_whitespace_between_blocks_is_dropped() -> None:
    el = ET.fromstring(f'<section xmlns="{FB2_NS}">\n  <p>a</p>\n  <p>b</p>\n</section>')
    assert [type(c).__name__ for c in bind_section(el, _ctx()).children] == [
        "Paragraph",
        "Paragraph",
    ]


def test_deep_sections_within_limit_bind_without_recursion_error() -> None:
    depth = 199
    el = ET.fromstring(
        f'<section xmlns="{FB2_NS}">' + "<section>" * depth + "</section>" * depth + "</section>"
    )
    node = bind_section(el, _ctx())
    for _ in range(depth):
        node = node.sections[0]
    assert node == Section()


def test_paragraph_attributes_are_read() -> None:
    el = ET.fromstring(f'<section xmlns="{FB2_NS}"><p id="p1" style="x">t</p></section>')
    assert bind_section(el, _ctx()).children[0] == Paragraph(
        children=(Text("t"),), style="x", id="p1"
    )


@pytest.mark.parametrize("value", ["x", "", "-1", "0"])
def test_invalid_span_falls_back_to_one(value: str) -> None:
    el = ET.fromstring(
        f'<section xmlns="{FB2_NS}"><table><tr><td colspan="{value}">x</td></tr></table></section>'
    )
    table = bind_section(el, _ctx()).children[0]
    assert isinstance(table, Table) and table.rows[0].cells[0].colspan == 1


def test_empty_table_and_row_do_not_fail() -> None:
    el = ET.fromstring(f'<section xmlns="{FB2_NS}"><table/><table><tr/></table></section>')
    tables = bind_section(el, _ctx()).children
    assert tables[0] == Table() and tables[1].rows[0].cells == ()


def test_body_keeps_title_and_epigraph_before_sections() -> None:
    el = ET.fromstring(
        f'<body xmlns="{FB2_NS}"><title><p>T</p></title><epigraph><p>E</p></epigraph>'
        "<section><p>x</p></section></body>"
    )
    body = bind_body(el, _ctx())
    assert [type(c).__name__ for c in body.children] == ["Title", "Epigraph", "Section"]
    assert isinstance(body.title, Title) and len(body.sections) == 1


def test_poem_epigraph_and_stanza_subtitle_are_bound() -> None:
    el = ET.fromstring(
        f'<section xmlns="{FB2_NS}"><poem><epigraph><p>e</p></epigraph>'
        "<stanza><subtitle>s</subtitle><v>a</v></stanza><text-author>A</text-author></poem></section>"
    )
    poem = bind_section(el, _ctx()).children[0]
    assert isinstance(poem, Poem) and len(poem.epigraphs) == 1
    assert len(poem.stanzas[0].subtitles) == 1 and len(poem.stanzas[0].verses) == 1
    assert len(poem.text_authors) == 1


def test_structure_nodes_are_hashable_and_comparable() -> None:
    a = bind_section(ET.fromstring(f'<section xmlns="{FB2_NS}"><p>x</p></section>'), _ctx())
    b = bind_section(ET.fromstring(f'<section xmlns="{FB2_NS}"><p>x</p></section>'), _ctx())
    assert a == b and hash(a) == hash(b)
