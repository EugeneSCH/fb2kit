from typing import Any

import pytest
from conftest import case, cases, fixture_text

import fb2kit
from fb2kit.export import TextBlock, book_meta, iter_blocks

_NS = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink"'
_DESC = fixture_text("export-desc.xml")


def _chunks(body: str, extra: str = "") -> list[TextBlock]:
    xml = f'<?xml version="1.0" encoding="utf-8"?><FictionBook {_NS}>{_DESC}<body>{body}</body>{extra}</FictionBook>'
    return list(iter_blocks(fb2kit.parse_string(xml, mode=fb2kit.Mode.TOLERANT)))


def _case_chunks(c: dict[str, Any]) -> list[TextBlock]:
    return _chunks(c["body"], c.get("extra", ""))


def _row(block: TextBlock, fields: list[str]) -> list[Any]:
    return [list(v) if isinstance(v, tuple) else v for v in (getattr(block, f) for f in fields)]


@pytest.mark.parametrize("c", [c for c in cases("export") if "fields" in c], ids=lambda c: c["id"])
def test_block_table(c: dict[str, Any]) -> None:
    assert [_row(b, c["fields"]) for b in _case_chunks(c)] == c["expected"]


def test_empty_book() -> None:
    assert _chunks("<section><empty-line/><p> </p></section>") == []


def test_section_without_title() -> None:
    cs = _chunks("<section><title><p>A</p></title><section><p>x</p></section></section>")
    assert cs[-1].heading_path == ("A",)
    assert cs[-1].section_id is None
    assert cs[-1].section_idx == (1, 1)


def test_raw_keeps_text() -> None:
    cs = _chunks(
        "<section><epigraph><emphasis><p>a</p><p>b</p></emphasis></epigraph>"
        "<strong><p>c</p><p>d</p></strong><p>x<foo>y</foo></p></section>"
    )
    assert [(c.kind, c.text) for c in cs] == [
        ("epigraph", "a\nb"),
        ("raw", "c\nd"),
        ("paragraph", "xy"),
    ]


def test_table() -> None:
    cs = _chunks(
        '<section><table id="t"><tr><th>a</th><td> b </td></tr><tr><td/></tr>'
        '<tr><td>c</td><td>d<image l:href="#i"/></td></tr></table><image l:href="#i"/></section>'
    )
    assert [(c.kind, c.text, c.node_id) for c in cs] == [("table", "a | b\nc | d", "t")]


def test_reexport() -> None:
    assert fb2kit.iter_blocks is iter_blocks and fb2kit.book_meta is book_meta


def test_note_refs_inside_raw() -> None:
    cs = _chunks(
        '<section><p>w<foo><a l:href="#n1" type="note">1</a></foo></p></section>',
        '<body name="notes"><section id="n1"><p>x</p></section></body>',
    )
    assert cs[0].note_refs == ("n1",)


def test_two_unnamed_bodies_have_distinct_keys() -> None:
    cs = _chunks("<section><p>a</p></section></body><body><section><p>b</p></section>")
    assert [(c.body_idx, c.section_idx) for c in cs] == [(0, (1,)), (1, (1,))]


def test_table_empty_first_cell() -> None:
    cs = _chunks("<section><table><tr><td/><td>b</td></tr></table></section>")
    assert cs[0].text == "b"


def test_nested_sections_heading_path() -> None:
    c = case("export", "nested_sections")
    cs = _case_chunks(c)
    p = cs[-1]
    assert list(p.heading_path) == c["heading_path"]
    assert (p.section_id, p.node_id, p.body) == ("s2", "p1", None)
    assert [x.ordinal for x in cs] == [0, 1, 2]
    assert list(cs[0].heading_path) == c["first_heading_path"]
    assert (cs[0].section_idx, p.section_idx, p.depth) == ((1,), (1, 1), 2)


def test_notes() -> None:
    c = case("export", "notes")
    cs = _case_chunks(c)
    p = cs[0]
    assert p.text == c["text"]
    assert p.note_refs == ("n1", "n2")
    notes = [x for x in cs if x.kind == "note"]
    assert [[x.node_id, x.text, list(x.heading_path)] for x in notes] == c["notes"]
    assert [x.section_idx for x in notes] == [(1,), (2, 1)]
    assert {x.body for x in cs[1:]} == {"notes"}
    assert cs[1].kind == "title" and cs[1].text == c["notes_title"]


def test_note_refs_resolve_to_note_blocks() -> None:
    cs = _case_chunks(case("export", "note_refs_resolve_to_note_blocks"))
    assert cs[0].note_refs == ("n2", "n1", "q")
    notes = {x.node_id for x in cs if x.kind == "note"}
    assert set(cs[0].note_refs) <= notes
    assert "free" in [x.text for x in cs if x.kind == "note"]


def test_stray_text_in_containers_is_kept() -> None:
    c = case("export", "stray_text_in_containers_is_kept")
    assert "\n".join(x.text for x in _case_chunks(c)).split() == c["words"]


def test_book_meta() -> None:
    c = case("export", "book_meta")
    xml = f'<?xml version="1.0" encoding="utf-8"?><FictionBook {_NS}>{_DESC}<body><section><p>x</p></section></body></FictionBook>'
    assert book_meta(fb2kit.parse_string(xml)) == c["expected"]


def test_book_meta_sparse() -> None:
    c = case("export", "book_meta_sparse")
    xml = f'<?xml version="1.0" encoding="utf-8"?><FictionBook {_NS}>{c["head"]}<body><p>x</p></body></FictionBook>'
    assert book_meta(fb2kit.parse_string(xml, mode=fb2kit.Mode.TOLERANT)) == c["expected"]
