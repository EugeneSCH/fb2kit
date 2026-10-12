"""Regressions found by the oracle on the real corpus (minimal fixtures from the failing books)."""

import pytest

import fb2kit
from fb2kit import report
from fb2kit.model.inline import Image, Raw, Style, Text
from fb2kit.model.structure import Paragraph

_NS = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink"'


def _book(body: str, binaries: str = "") -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?><FictionBook {_NS}><description><title-info>'
        "<genre>g</genre><author><first-name>a</first-name></author><book-title>t</book-title>"
        f"<lang>ru</lang></title-info></description><body>{body}</body>{binaries}</FictionBook>"
    )


def _par(book: fb2kit.FictionBook) -> Paragraph:
    return book.bodies[0].children[0].children[0]  # type: ignore[union-attr,return-value]


def _flat(nodes: tuple[object, ...]) -> str:
    out = ""
    for n in nodes:
        if isinstance(n, Text):
            out += n.value
        elif isinstance(n, Style):
            out += _flat(n.children)
    return out


@pytest.mark.parametrize("mode", ["strict", "tolerant"])
def test_p_inside_p_flattened_with_image(mode: str) -> None:
    xml = _book(
        '<section><p>a<p>b <strong>c</strong><image l:href="#i"/></p>d</p></section>',
        '<binary id="i" content-type="image/png">AAAA</binary>',
    )
    book = fb2kit.parse(xml.encode(), mode=mode)
    p = _par(book)
    assert _flat(p.children) == "a b c d"
    assert any(isinstance(n, Image) for n in p.children)
    assert not any(isinstance(n, Raw) for n in p.children)
    assert any(d.code == report.ELEMENT_UNKNOWN for d in book.report.diagnostics)


def test_p_inside_td_keeps_text() -> None:
    xml = _book("<section><table><tr><td><p><strong>and</strong></p></td></tr></table></section>")
    cell = fb2kit.parse(xml.encode()).bodies[0].children[0].children[0].rows[0].cells[0]  # type: ignore[union-attr]
    assert _flat(cell.children) == "and"


def test_subtitle_in_title_kept() -> None:
    xml = _book('<title><p>x</p><subtitle id="S">sub</subtitle></title><section/>')
    book = fb2kit.parse(xml.encode())
    texts = [_flat(p.children) for p in book.bodies[0].title.children]  # type: ignore[union-attr]
    assert texts == ["x", "sub"]
    assert "S" in book.index
    assert any(d.code == report.ELEMENT_UNKNOWN for d in book.report.diagnostics)


def test_raw_keeps_full_text_and_indexes_inner_ids() -> None:
    xml = _book(
        '<section><poem><stanza><v>a<cite id="c">q<b>w</b></cite></v></stanza></poem>'
        '<p><a l:href="#c">x</a></p></section>'
    )
    book = fb2kit.parse(xml.encode())
    assert "c" in book.index
    assert not any(d.code == report.LINK_UNRESOLVED for d in book.report.diagnostics)


def test_raw_text_is_full() -> None:
    book = fb2kit.parse(_book("<section><foo>a<b>b</b>c</foo></section>").encode())
    raw = book.bodies[0].children[0].children[0]
    assert isinstance(raw, Raw) and raw.text == "abc"


def test_link_to_binary_resolves() -> None:
    xml = _book(
        '<section><p><a l:href="#f.zip">x</a></p></section>',
        '<binary id="f.zip" content-type="application/zip">AAAA</binary>',
    )
    book = fb2kit.parse(xml.encode())
    assert book.by_id("f.zip") is book.binaries[0]
    assert not any(d.code == report.LINK_UNRESOLVED for d in book.report.diagnostics)


def test_verse_and_stanza_subtitle_ids_indexed() -> None:
    xml = _book(
        '<section><poem><stanza><subtitle id="s">h</subtitle><v id="v1">a</v></stanza></poem>'
        '<p><a l:href="#v1">x</a><a l:href="#s">y</a></p></section>'
    )
    book = fb2kit.parse(xml.encode())
    assert {"v1", "s"} <= set(book.index)
    assert not any(d.code == report.LINK_UNRESOLVED for d in book.report.diagnostics)


def test_stray_image_in_tr_kept() -> None:
    xml = _book(
        '<section><table><tr><td/><image l:href="#i"/><empty-line/></tr></table></section>',
        '<binary id="i" content-type="image/png">AAAA</binary>',
    )
    book = fb2kit.parse(xml.encode())
    row = book.bodies[0].children[0].children[0].rows[0]  # type: ignore[union-attr]
    images = [n for c in row.cells for n in c.children if isinstance(n, Image)]
    assert len(images) == 1
    assert any(d.code == report.ELEMENT_UNKNOWN for d in book.report.diagnostics)
