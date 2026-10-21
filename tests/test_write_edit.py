"""Editing a book without touching it: the model is frozen, the edits are new books."""

from pathlib import Path

import fb2kit
from fb2kit.model.inline import Text
from fb2kit.model.metadata import Description, TitleInfo
from fb2kit.model.structure import Paragraph, Section

FIXTURES = Path(__file__).parent / "fixtures"


def _book():
    return fb2kit.parse(FIXTURES / "notes-and-links.fb2")


def test_edit_metadata_changes_title_only() -> None:
    """С27: edit_metadata changes the title and keeps the other fields."""
    book = _book()
    edited = fb2kit.edit_metadata(book, title="Новое название")
    assert edited.description.title_info.title == "Новое название"
    assert book.description.title_info.title != "Новое название"


def test_with_description_rebuilds_element_and_index() -> None:
    """С50: with_description rebuilds the element and the index."""
    book = _book()
    edited = fb2kit.with_description(book, Description(TitleInfo(title="X")))
    assert edited.description.title_info.title == "X"
    assert edited.by_id("n1") is not None
    assert b"X" in edited.to_bytes()


def test_replace_nested_section_keeps_order() -> None:
    """С28: replace_node keeps the order of the children."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="s1"><p>a</p><section id="s2"><p>b</p></section></section></body>'
        "</FictionBook>"
    )
    target = book.by_id("s2")
    assert isinstance(target, Section)
    replacement = Section("s2", (Paragraph((Text("NEW"),)),))
    edited = fb2kit.replace_node(book, target, replacement)
    assert b"NEW" in edited.to_bytes()
    assert edited.by_id("s2") is replacement


def test_replace_refreshes_element() -> None:
    """С50: replace_node refreshes the element."""
    book = _book()
    target = book.by_id("n1")
    edited = fb2kit.replace_node(book, target, Section("n1", (Paragraph((Text("NEW"),)),)))
    assert b"NEW" in fb2kit.write.serialize.serialize_bytes(edited.element)


def test_reindex_keeps_ids_inside_raw() -> None:
    """С35: reindex keeps the ids inside an unknown node."""
    # The parser registers the ids inside a Raw; reindex has to do the same.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section><p>a<foo id="fi">x</foo>b</p></section></body>'
        "</FictionBook>"
    )
    assert "fi" in book.index
    assert "fi" in fb2kit.reindex(book).index


def test_reindex_keeps_root_raw_ids() -> None:
    """С35: reindex keeps the ids of the root unknown nodes."""
    # The parser puts the ids of the root <stylesheet> / <output> into the index;
    # reindex has to do the same.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        '<stylesheet id="css1" type="text/css">p{}</stylesheet>'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        "<body><section><p>a</p></section></body></FictionBook>"
    )
    assert "css1" in book.index
    assert "css1" in fb2kit.reindex(book).index


def test_reindex_keeps_the_ids_of_the_description_extra() -> None:
    """С63: reindex keeps the ids of the extra of the description."""
    # <output id> lives inside the description; the parser registers it.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        "<body><section><p>a</p></section></body></FictionBook>"
    )
    assert "s1" not in book.index
    assert "css1" not in fb2kit.reindex(book).index


def test_with_cover_sets_coverpage_and_binary(tmp_path: Path) -> None:
    """С64: with_cover sets the coverpage and the binary."""
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    binary = fb2kit.Binary("img-1", "image/png", "QUJD")
    edited = fb2kit.with_cover(book, binary)
    assert edited.cover == binary
    assert edited.description.title_info.coverpage[0].href == "#img-1"
    out = tmp_path / "b.fb2"
    edited.write(out)
    assert fb2kit.parse(out).cover is not None


def test_with_cover_keeps_other_cover_images() -> None:
    """С65: with_cover keeps the other images of the coverpage."""
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    binary = fb2kit.Binary("img-1", "image/png", "QUJD")
    edited = fb2kit.with_cover(book, binary)
    assert len(edited.description.title_info.coverpage) == 1


def test_with_cover_replaces_only_the_first_cover_image() -> None:
    """С65: with_cover replaces only the first image of the coverpage."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
        ' xmlns:l="http://www.w3.org/1999/xlink">'
        "<description><title-info><book-title>T</book-title>"
        '<coverpage><image l:href="#old"/><image l:href="#other"/></coverpage>'
        "</title-info></description>"
        "<body><section><p>a</p></section></body></FictionBook>"
    )
    binary = fb2kit.Binary("img-1", "image/png", "QUJD")
    edited = fb2kit.with_cover(book, binary)
    coverpage = edited.description.title_info.coverpage
    assert coverpage[0].href == "#img-1"
    assert coverpage[1].href == "#other"


def test_with_binaries_does_not_touch_cover_when_none() -> None:
    """С66: with_binaries does not touch the cover when there is none."""
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    edited = fb2kit.with_binaries(book, ())
    assert edited.binaries == ()
    assert edited.cover is None


def test_reindex_first_id_wins() -> None:
    """С63: reindex keeps the first of the ids that are equal."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="d"><p>a</p></section><section id="d"><p>b</p></section></body>'
        "</FictionBook>"
    )
    assert isinstance(book.by_id("d"), Section)
    assert book.by_id("d").blocks[0].children[0].value == "a"  # type: ignore[union-attr]


def test_replace_node_finds_the_node_by_identity() -> None:
    """С69: replace_node finds the node by its identity."""
    # Two equal nodes are different nodes: only the one that is given is replaced.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="a"><p>x</p></section><section id="b"><p>x</p></section></body>'
        "</FictionBook>"
    )
    target = book.by_id("b")
    assert isinstance(target, Section)
    edited = fb2kit.replace_node(book, target, Section("b", (Paragraph((Text("Y"),)),)))
    assert b"Y" in edited.to_bytes()
    assert b"x</p>" in edited.to_bytes()


def test_edit_metadata_rejects_an_unknown_field() -> None:
    """С58: edit_metadata rejects an unknown field."""
    import pytest

    with pytest.raises(TypeError):
        fb2kit.edit_metadata(_book(), nonsense=1)


def test_edit_metadata_keeps_the_other_fields() -> None:
    """С59: edit_metadata keeps the fields it was not given."""
    book = _book()
    edited = fb2kit.edit_metadata(book, title="Другое")
    assert edited.description.title_info.genres == book.description.title_info.genres
    assert edited.description.title_info.authors == book.description.title_info.authors
