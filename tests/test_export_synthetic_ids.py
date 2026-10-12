from conftest import case

import fb2kit
from fb2kit.export import iter_blocks

_NS = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
_DESC = "<description><title-info><book-title>T</book-title></title-info></description>"


def _book(body: str, notes: str = "") -> fb2kit.FictionBook:
    xml = f"<FictionBook {_NS}>{_DESC}<body>{body}</body>{notes}</FictionBook>"
    return fb2kit.parse_string(xml)


def test_notes_without_id_get_stable_synthetic_ids() -> None:
    c = case("export_synthetic_ids", "synthetic_ids")
    book = _book("<section><p>a</p></section>", c["notes"])
    got = [(b.node_id, b.text) for b in iter_blocks(book) if b.kind == "note"]
    assert got == [tuple(row) for row in c["expected"]]
    assert got == [(b.node_id, b.text) for b in iter_blocks(book) if b.kind == "note"]


def test_note_refs_reach_synthetic_note_via_inner_id() -> None:
    notes = case("export_synthetic_ids", "inner_id")["notes"]
    xml_body = '<section><p>w<a href="#x" type="note">1</a></p></section>'
    blocks = list(iter_blocks(_book(xml_body, notes)))
    assert blocks[0].note_refs == ("notes1-1",)
