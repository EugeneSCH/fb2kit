"""Creating a book from scratch with the builder."""

from pathlib import Path

import pytest

import fb2kit
from fb2kit.errors import Fb2WriteError
from fb2kit.model.inline import Link, Text


def test_build_minimal_book_and_reparse(tmp_path: Path) -> None:
    """С24: a book built from scratch is written and read back."""
    builder = fb2kit.new_book(
        title="Моя книга", lang="ru", authors=(fb2kit.Author(last_name="Иванов"),)
    ).add_genre("sf")
    section = builder.add_section("Глава 1")
    section.add_paragraph("Текст ", fb2kit.Style("emphasis", (Text("курсивом"),)))
    section.add_subtitle("Подзаголовок").add_empty_line()
    book = builder.build()

    out = tmp_path / "book.fb2"
    book.write(out)
    parsed = fb2kit.parse(out)
    assert parsed.description.title_info.title == "Моя книга"
    assert parsed.description.title_info.authors[0].full_name == "Иванов"
    assert parsed.bodies[0].sections[0].title is not None
    assert "курсивом" in parsed.to_xml()


def test_notes_are_created_and_resolve(tmp_path: Path) -> None:
    """С25: the notes of the builder are created and resolve."""
    builder = fb2kit.new_book(title="T")
    section = builder.add_section("Глава")
    note_id = builder.add_note("Текст сноски")
    section.add_paragraph("Слово", Link(f"#{note_id}", "note", (Text("1"),)))
    book = builder.build()

    out = tmp_path / "book.fb2"
    book.write(out)
    parsed = fb2kit.parse(out)
    assert parsed.notes_body is not None
    assert parsed.by_id(note_id) is not None


def test_ids_do_not_collide() -> None:
    """С25: the notes of the builder get different ids."""
    builder = fb2kit.new_book(title="T")
    first = builder.add_note("a")
    second = builder.add_note("b")
    assert first != second


def test_binary_and_cover(tmp_path: Path) -> None:
    """С26: the builder sets a binary and a cover."""
    builder = fb2kit.new_book(title="T")
    cover = builder.add_binary(b"\x89PNG\r\n\x1a\n", "image/png")
    builder.set_cover(cover)
    book = builder.build()

    out = tmp_path / "book.fb2"
    book.write(out)
    parsed = fb2kit.parse(out)
    assert parsed.cover is not None and parsed.cover.id == cover.id
    assert parsed.cover.content_type == "image/png"


def test_build_without_title_is_a_write_error() -> None:
    """С29: a book built without a title is a write error."""
    with pytest.raises(Fb2WriteError):
        fb2kit.new_book(title="").build()


def test_build_without_body_is_a_write_error() -> None:
    """С29: a book built without a body is a write error."""
    with pytest.raises(Fb2WriteError):
        fb2kit.new_book(title="T").build()


def test_section_ids_can_be_set_explicitly() -> None:
    """С55: the id of a section can be set explicitly."""
    builder = fb2kit.new_book(title="T")
    builder.add_section("S", id="my-id")
    builder.add_section("T2")
    book = builder.build()
    assert book.bodies[0].sections[0].id == "my-id"


def test_a_poem_is_built(tmp_path: Path) -> None:
    """С56: the builder creates a poem."""
    builder = fb2kit.new_book(title="T")
    section = builder.add_section("Стихи")
    section.add_poem("Стих", [["one", "two"], ["three"]], author="Поэт")
    book = builder.build()

    out = tmp_path / "book.fb2"
    book.write(out)
    parsed = fb2kit.parse(out)
    poem = next(c for c in parsed.bodies[0].sections[0].children if isinstance(c, fb2kit.Poem))
    assert poem.stanzas[0].verses[0].children[0] == Text("one")
    assert poem.text_authors[0].children[0] == Text("Поэт")


def test_an_image_is_added_to_a_section(tmp_path: Path) -> None:
    """С56: the builder adds an image to a section."""
    builder = fb2kit.new_book(title="T")
    binary = builder.add_binary(b"\x89PNG\r\n\x1a\n", "image/png")
    section = builder.add_section("Глава")
    section.add_image(binary, alt="Обложка")
    book = builder.build()

    out = tmp_path / "book.fb2"
    book.write(out)
    parsed = fb2kit.parse(out)
    image = parsed.bodies[0].sections[0].image
    assert image is not None
    assert image.href == f"#{binary.id}"
    assert image.alt == "Обложка"


def test_the_builder_does_not_mutate_the_book_after_build() -> None:
    """С57: the builder does not change the book it has built."""
    builder = fb2kit.new_book(title="T")
    builder.add_section("Глава")
    first = builder.build()
    builder.add_section("Ещё")
    second = builder.build()
    assert len(first.bodies[0].sections) == 1
    assert len(second.bodies[0].sections) == 2


def test_a_sequence_and_keywords_are_set() -> None:
    """С56: the builder sets the series, the keywords and the annotation."""
    builder = fb2kit.new_book(title="T")
    builder.set_sequence("Хроники", 3)
    builder.set_annotation(fb2kit.Paragraph((Text("Аннотация"),)))
    builder.add_section("Глава")
    book = builder.build()
    assert book.description.title_info.sequences[0].name == "Хроники"
    assert book.description.title_info.sequences[0].number == 3
    assert book.description.title_info.annotation is not None


def test_a_built_book_has_a_document_info() -> None:
    """С96: the schema requires a document-info; the builder always writes one."""
    builder = fb2kit.new_book(
        title="T", lang="ru", authors=(fb2kit.Author(first_name="A", last_name="B"),)
    )
    builder.add_genre("sf")
    builder.add_section("S").add_paragraph("x")
    book = builder.build()
    info = book.description.document_info
    assert info is not None
    assert info.ids and info.version == "1.0" and info.dates


def test_a_built_book_is_valid_against_the_schema() -> None:
    """С96: a book built with a genre and an author passes the bundled schema."""
    pytest.importorskip("lxml")
    from lxml import etree

    schema = etree.XMLSchema(
        etree.parse(str(Path(fb2kit.__file__).parent / "write" / "_schema" / "FictionBook.xsd"))
    )
    builder = fb2kit.new_book(
        title="T",
        lang="ru",
        authors=(fb2kit.Author(first_name="A", last_name="B"),),
        document_date="2024-01-01",
    )
    builder.add_genre("sf")
    builder.add_section("S").add_paragraph("x")
    out = builder.build().to_bytes()
    assert schema.validate(etree.fromstring(out)), str(schema.error_log)


def test_an_explicit_section_id_reserves_the_name() -> None:
    """С97: an explicit id keeps the IdGenerator from handing it out again."""
    builder = fb2kit.new_book(title="T")
    builder.add_section("S", id="note-1")
    note_id = builder.add_note("text")
    assert note_id != "note-1"
    builder.build()
