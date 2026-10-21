"""The edges of the writer: the branches the happy path does not reach."""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

import fb2kit
from fb2kit.model.binary import Binary
from fb2kit.model.inline import Image, Text
from fb2kit.model.structure import Body, Paragraph, Section
from fb2kit.write.build import IdGenerator
from fb2kit.write.edit import reindex
from fb2kit.write.pretty import render
from fb2kit.write.validate import WRITE_INVALID_CHAR, WRITE_INVALID_ID, validate

FIXTURES = Path(__file__).parent / "fixtures"


def _book(**changes):
    base = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        "<body><section><p>x</p></section></body></FictionBook>"
    )
    return base.replace(**changes) if changes else base


def test_replace_rejects_an_unknown_field() -> None:
    """С58: replace rejects an unknown field."""
    with pytest.raises(TypeError):
        _book().replace(nonsense=1)


def test_replace_rejects_a_tuple_of_the_wrong_kind() -> None:
    """С58: replace rejects a list of bodies."""
    with pytest.raises(TypeError):
        _book().replace(bodies=[])


def test_replace_rejects_a_cover_of_the_wrong_kind() -> None:
    """С58: replace rejects a cover that is not a binary."""
    with pytest.raises(TypeError):
        _book().replace(cover="not a binary")


def test_replace_rejects_a_description_of_the_wrong_kind() -> None:
    """С58: replace rejects a description of the wrong type."""
    with pytest.raises(TypeError):
        _book().replace(description="not a description")


def test_a_temporary_file_with_a_taken_name_is_skipped(tmp_path: Path, monkeypatch) -> None:
    """С60: a taken name of the temporary file is skipped."""
    # The name of the temporary file must be free; the writer tries the next one.
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    real_open = __import__("os").open
    calls: list[str] = []

    def fake_open(path, flags, mode=0o777, **kwargs):
        calls.append(str(path))
        if len(calls) == 1:
            raise FileExistsError(path)
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr("os.open", fake_open)
    out = tmp_path / "book.fb2"
    book.write(out)
    assert out.exists()
    assert len(calls) == 2


def test_the_writer_gives_up_after_a_hundred_taken_names(tmp_path: Path, monkeypatch) -> None:
    """С60: the writer gives up after a hundred taken names."""
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    monkeypatch.setattr("os.open", lambda *a, **_kw: (_ for _ in ()).throw(FileExistsError("busy")))
    with pytest.raises(OSError):
        book.write(tmp_path / "book.fb2")
    assert list(tmp_path.iterdir()) == []


def test_an_id_inside_a_raw_is_checked() -> None:
    """С61: the id inside an unknown node is checked."""
    # The ids of an unknown element are attributes too: they have to be valid.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section><p>a<foo id="bad id">x</foo></p></section></body>'
        "</FictionBook>"
    )
    codes = [p.code for p in validate(book).problems]
    assert WRITE_INVALID_ID in codes


def test_a_bad_character_in_an_attribute_of_a_raw_is_an_error() -> None:
    """С61: a bad character in an attribute of a raw is an error."""
    # A Raw built by hand may hold a character XML does not allow: the writer
    # has to see it.
    element = ET.Element("foo")
    element.set("bar", "x\x0cy")
    raw = fb2kit.Raw(tag="foo", text="z", element=element)
    body = Body(children=(Section(children=(Paragraph((raw,)),)),))
    book = _book(bodies=(body,))
    codes = [p.code for p in validate(book).problems]
    assert WRITE_INVALID_CHAR in codes


def test_a_raw_without_an_element_is_not_checked() -> None:
    """С61: a raw without an element is not checked."""
    # A Raw made by hand has no element: there is nothing to check in it.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        "<body><section><p>a</p></section></body></FictionBook>"
    )
    raw = fb2kit.Raw(tag="foo", text="bar")
    body = Body(children=(Section(children=(Paragraph((raw,)),)),))
    edited = book.replace(bodies=(body,))
    assert validate(edited).ok is True


def test_lost_id_is_skipped_when_the_tree_does_not_match_the_model() -> None:
    """С89: the lost id is skipped when the tree is not the model."""
    # The tree of the book belongs to another book: the comparison of the ids
    # would be meaningless, so the rule does not fire.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="s1"><title id="t1"><p>x</p></title></section></body>'
        "</FictionBook>"
    )
    other = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        '<body><section id="zz"><p>x</p></section></body>'
        "</FictionBook>"
    )
    mixed = book.replace(bodies=other.bodies)
    codes = [p.code for p in validate(mixed).problems]
    assert "write.lost-id" not in codes


def test_a_book_without_an_element_has_no_lost_ids() -> None:
    """С89: a book without an original tree has no lost ids."""
    book = _book()
    assert validate(book).problems == ()


def test_the_id_generator_skips_the_taken_names() -> None:
    """С62: the generator of the ids skips the taken names."""
    generator = IdGenerator(["note-1", "note-2"])
    assert generator.next("note") == "note-3"
    assert generator.next("note") == "note-4"
    assert generator.next("other") == "other-1"


def test_the_id_generator_uses_its_own_count() -> None:
    """С62: the generator of the ids counts every prefix apart."""
    generator = IdGenerator()
    assert generator.next("note") == "note-1"
    assert generator.next("note") == "note-2"


def test_a_nested_section_is_built() -> None:
    """С55: the builder creates a nested section."""
    builder = fb2kit.new_book(title="T")
    outer = builder.add_section("Внешняя")
    inner = outer.add_section("Внутренняя")
    inner.add_paragraph("Текст")
    book = builder.build()
    outer_section = book.bodies[0].sections[0]
    nested = outer_section.sections[0]
    assert nested.title is not None
    paragraph = next(b for b in nested.blocks if isinstance(b, Paragraph))
    assert paragraph.children[0] == Text("Текст")


def test_reindex_of_a_book_without_binaries() -> None:
    """С63: reindex keeps a book without binaries."""
    book = _book()
    assert reindex(book).binaries == ()


def test_a_binary_without_a_cover_is_not_the_cover() -> None:
    """С63: a binary without a cover is not the cover."""
    book = _book(binaries=(Binary("b1", "image/png", "QUJD"),))
    assert book.cover is None
    assert reindex(book).by_id("b1") is not None


def test_the_zip_of_a_book_with_a_cover_holds_the_book(tmp_path: Path) -> None:
    """С64: the archive of a book with a cover holds the book."""
    builder = fb2kit.new_book(title="T")
    builder.add_binary(b"\x89PNG\r\n\x1a\n", "image/png")
    builder.add_section("Глава")
    book = builder.build()
    out = tmp_path / "book.fbz"
    book.write(out)
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["book.fb2"]
        assert b"binary" in zf.read("book.fb2")


def test_a_book_with_a_cover_has_the_coverpage() -> None:
    """С64: a book with a cover has a coverpage."""
    builder = fb2kit.new_book(title="T")
    binary = builder.add_binary(b"\x89PNG\r\n\x1a\n", "image/png")
    builder.set_cover(binary)
    builder.add_section("Глава")
    book = builder.build()
    assert book.description.title_info.coverpage[0].href == f"#{binary.id}"


def test_an_image_with_no_href_is_written_without_one() -> None:
    """С68: an image without a href is written without one."""
    body = Body(
        children=(
            Section(
                children=(Image(alt="a"),),
            ),
        )
    )
    book = _book(bodies=(body,))
    assert b'alt="a"' in book.to_bytes(strict=False)


def test_replace_node_of_a_node_that_is_not_in_the_book() -> None:
    """С69: replacing a node that is not in the book changes nothing."""
    # Nothing to replace: the book comes back, only with a fresh tree.
    book = _book()
    edited = fb2kit.replace_node(book, object(), object())
    assert edited.bodies == book.bodies


def test_with_cover_drops_the_cover_when_the_binary_is_none() -> None:
    """С65: with_cover drops the cover when the binary is None."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
        ' xmlns:l="http://www.w3.org/1999/xlink">'
        "<description><title-info><book-title>T</book-title>"
        '<coverpage><image l:href="#old"/></coverpage>'
        "</title-info></description>"
        "<body><section><p>a</p></section></body></FictionBook>"
    )
    edited = fb2kit.with_cover(book, None)
    assert edited.cover is None
    assert edited.description.title_info.coverpage == ()


def test_with_cover_keeps_a_binary_that_is_already_there() -> None:
    """С65: with_cover keeps a binary that is already there."""
    book = _book(binaries=(Binary("img-1", "image/png", "QUJD"),))
    binary = Binary("img-1", "image/png", "QUJD")
    edited = fb2kit.with_cover(book, binary)
    assert len(edited.binaries) == 1


def test_edit_metadata_rejects_a_tuple_of_the_wrong_kind() -> None:
    """С58: edit_metadata rejects a list of authors."""
    with pytest.raises(TypeError):
        fb2kit.edit_metadata(_book(), authors=[])


def test_edit_metadata_rejects_a_string_of_the_wrong_kind() -> None:
    """С58: edit_metadata rejects a number as a title."""
    with pytest.raises(TypeError):
        fb2kit.edit_metadata(_book(), title=42)


def test_edit_metadata_accepts_none_for_a_string() -> None:
    """С59: edit_metadata accepts None for a string."""
    book = _book()
    edited = fb2kit.edit_metadata(book, title=None)
    assert edited.description.title_info.title is None


def test_the_builder_adds_an_author_a_genre_and_keywords() -> None:
    """С67: the builder adds an author, a genre and keywords."""
    builder = fb2kit.new_book(title="T")
    builder.add_author(fb2kit.Author(last_name="Петров"))
    builder.add_genre("sf")
    builder.set_keywords("книга, тест")
    builder.add_section("Глава")
    book = builder.build()
    assert book.description.title_info.authors[0].last_name == "Петров"
    assert book.description.title_info.genres == ("sf",)
    assert book.description.title_info.keywords == "книга, тест"


def test_the_builder_sets_a_cover_that_is_not_attached_yet() -> None:
    """С67: the builder sets a cover that is not attached yet."""
    builder = fb2kit.new_book(title="T")
    binary = Binary("img-1", "image/png", "QUJD")
    builder.set_cover(binary)
    builder.add_section("Глава")
    book = builder.build()
    assert book.binaries == (binary,)
    assert book.cover == binary


def test_the_pretty_printer_writes_an_empty_element_on_one_line() -> None:
    """С75: the pretty printer writes an empty element on one line."""
    root = ET.fromstring("<r><a/></r>")
    assert "<a/>" in render(root)
