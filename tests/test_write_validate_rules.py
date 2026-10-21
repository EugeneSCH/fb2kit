"""Every rule of the writer's validation: what blocks a write and what only warns."""

import dataclasses
from pathlib import Path

import fb2kit
from fb2kit.model.binary import Binary
from fb2kit.model.inline import Image, Link, Text
from fb2kit.model.metadata import DocumentInfo
from fb2kit.model.structure import Body, Paragraph, Section
from fb2kit.write.validate import (
    WRITE_DANGLING_LINK,
    WRITE_DUPLICATE_ID,
    WRITE_EMPTY_BODY,
    WRITE_INCOMPLETE_AUTHOR,
    WRITE_INVALID_CHAR,
    WRITE_INVALID_ID,
    WRITE_INVALID_TAG,
    WRITE_MISSING_BINARY,
    WRITE_NO_AUTHOR,
    WRITE_NO_BODY,
    WRITE_NO_GENRE,
    WRITE_NO_TITLE,
    WriteSeverity,
    validate,
)

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


def _codes(report):
    return [p.code for p in report.problems]


def test_valid_book_has_no_problems() -> None:
    """С88: a valid book has no problems."""
    assert validate(_book()).problems == ()


def test_missing_title_and_body_are_errors() -> None:
    """С12: a book without a title and without a body has two errors."""
    book = _book()
    broken = book.replace(
        description=dataclasses.replace(
            book.description,
            title_info=dataclasses.replace(book.description.title_info, title=None),
        ),
        bodies=(),
    )
    rep = validate(broken)
    assert {WRITE_NO_TITLE, WRITE_NO_BODY} <= set(_codes(rep))
    assert all(p.severity is WriteSeverity.ERROR for p in rep.errors)


def test_a_blank_title_is_an_error() -> None:
    """С12: a blank title is an error."""
    book = _book()
    broken = book.replace(
        description=dataclasses.replace(
            book.description,
            title_info=dataclasses.replace(book.description.title_info, title="   "),
        ),
    )
    assert WRITE_NO_TITLE in _codes(validate(broken))


def test_duplicate_id_is_an_error() -> None:
    """С13: two nodes with the same id are an error."""
    body = Body(
        children=(
            Section("dup", (Paragraph((Text("a"),)),)),
            Section("dup", (Paragraph((Text("b"),)),)),
        )
    )
    rep = validate(_book(bodies=(body,)))
    assert WRITE_DUPLICATE_ID in _codes(rep)


def test_invalid_id_is_an_error() -> None:
    """С14: an invalid id is an error."""
    body = Body(children=(Section("bad id", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,)))
    assert WRITE_INVALID_ID in _codes(rep)


def test_an_id_that_starts_with_a_digit_is_invalid() -> None:
    """С14: an id that starts with a digit is invalid."""
    body = Body(children=(Section("1bad", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,)))
    assert WRITE_INVALID_ID in _codes(rep)


def test_a_valid_ascii_id_is_accepted() -> None:
    """С14: a valid ASCII id is accepted."""
    body = Body(children=(Section("a.b-c_1", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,)))
    assert WRITE_INVALID_ID not in _codes(rep)


def test_invalid_xml_char_is_an_error() -> None:
    """С15: a character that XML does not allow is an error."""
    body = Body(children=(Section(children=(Paragraph((Text("a\x0cb"),)),)),))
    rep = validate(_book(bodies=(body,)))
    assert WRITE_INVALID_CHAR in _codes(rep)


def test_missing_binary_is_only_a_warning() -> None:
    """С16: a missing binary is only a warning."""
    # Real books regularly refer to a missing binary: the write must not fail.
    body = Body(
        children=(
            Section(
                children=(Image(href="#missing"),),
            ),
        )
    )
    rep = validate(_book(bodies=(body,)))
    assert WRITE_MISSING_BINARY in _codes(rep)
    assert rep.ok is True


def test_dangling_link_is_only_a_warning() -> None:
    """С17: a broken link is only a warning."""
    body = Body(
        children=(Section(children=(Paragraph((Link("#missing", children=(Text("x"),)),)),)),)
    )
    rep = validate(_book(bodies=(body,)))
    assert WRITE_DANGLING_LINK in _codes(rep)
    assert rep.ok is True


def test_empty_body_is_a_warning() -> None:
    """С18: an empty body is a warning."""
    rep = validate(_book(bodies=(Body(),)))
    assert WRITE_EMPTY_BODY in _codes(rep)
    assert rep.ok is True


def test_existing_binary_and_resolved_link_are_silent() -> None:
    """С17: an existing binary and a resolved link are silent."""
    body = Body(
        children=(
            Section(
                "s1",
                (
                    Paragraph(
                        (Link("#b1", children=(Text("x"),)),),
                    ),
                    Image(href="#b1"),
                ),
            ),
        )
    )
    rep = validate(_book(bodies=(body,), binaries=(Binary("b1", "image/png", "QUJD"),)))
    assert rep.problems == ()


def test_document_info_uuid_id_is_not_treated_as_an_attribute_id() -> None:
    """С34: the id of the document info is not an attribute id."""
    # <document-info><id> is an element with free text (xs:token in the XSD); it holds
    # UUIDs that start with a digit. Checking the attribute on them would block the
    # write of 6 of the 10 books of the corpus.
    book = _book()
    broken = book.replace(
        description=dataclasses.replace(
            book.description,
            document_info=DocumentInfo(ids=("38322674-e7e5-455e-9ba7-699d2e567551",)),
        ),
    )
    rep = validate(broken)
    assert WRITE_INVALID_ID not in _codes(rep)
    assert rep.ok is True


def test_real_fixtures_with_missing_binaries_are_writable() -> None:
    """С16: the real books with missing binaries are writable."""
    # structure-rich.fb2 refers to #pic, metadata-full.fb2 to #cover; neither has them.
    for name in ("structure-rich.fb2", "metadata-full.fb2"):
        book = fb2kit.parse(FIXTURES / name)
        rep = validate(book)
        assert rep.ok is True, (name, _codes(rep))


def test_lost_id_is_a_warning() -> None:
    """С89: a lost id is a warning."""
    # The model does not keep the id of a <title>: the writer says so instead of
    # losing it silently.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        '<body><section id="s1"><title id="t1"><p>x</p></title></section></body>'
        "</FictionBook>"
    )
    rep = validate(book)
    assert "write.lost-id" in _codes(rep)
    assert rep.ok is True


def test_lost_id_is_not_reported_for_a_fresh_book() -> None:
    """С89: a lost id is not reported for a fresh book."""
    # A book that was never parsed has no original XML: nothing can be lost.
    book = _book()
    assert "write.lost-id" not in _codes(validate(book))


def test_the_id_of_a_body_is_reported_as_lost() -> None:
    """С89: the id of a body is reported as lost."""
    # The format has no place for the id of a <body>: the writer does not
    # write it, so it says so instead of losing it silently.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        '<body id="b1"><section><p>x</p></section></body>'
        "</FictionBook>"
    )
    rep = validate(book)
    assert "write.lost-id" in _codes(rep)
    assert rep.ok is True
    assert any("b1" in p.message for p in rep.warnings)


def test_a_body_without_an_id_is_not_reported_as_lost() -> None:
    """С89: a body without an id is not reported as lost."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        "<body><section><p>x</p></section></body>"
        "</FictionBook>"
    )
    assert "write.lost-id" not in _codes(validate(book))


def test_the_lost_id_of_a_body_is_reported_after_an_edit() -> None:
    """С89: the lost id of a body is reported after an edit."""
    # The warning does not depend on the original tree: it stays after the
    # book is edited, because the id is still lost on the way out.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        '<body id="b1"><section><p>x</p></section></body>'
        "</FictionBook>"
    )
    edited = fb2kit.edit_metadata(book, title="New")
    assert "write.lost-id" in _codes(validate(edited))


def test_the_id_of_a_body_is_still_in_the_index() -> None:
    """С89: the id of a body is still in the index."""
    # The model keeps the id of a body: a link to it still resolves, even
    # though the format has no place for it.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre>"
        "<author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        '<body id="b1"><section><p>x</p></section></body>'
        "</FictionBook>"
    )
    assert book.by_id("b1") is not None


def test_a_description_extra_with_an_id_is_not_a_duplicate() -> None:
    """С13: an extra with an id is not a duplicate."""
    # <src-title-info id="sti1"> is an ordinary construct: the id belongs to the
    # element once, so it is not a duplicate and the book stays writable.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info>"
        '<src-title-info id="sti1"><book-title>S</book-title></src-title-info>'
        "</description>"
        "<body><section><p>x</p></section></body></FictionBook>"
    )
    rep = validate(book)
    assert WRITE_DUPLICATE_ID not in _codes(rep)
    assert rep.ok is True
    book.to_bytes()


def test_two_different_extras_with_the_same_id_are_a_duplicate() -> None:
    """С13: two extras with the same id are a duplicate."""
    # The rule still works: two different elements with the same id are a duplicate.
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><book-title>T</book-title></title-info>"
        '<src-title-info id="dup"><book-title>S</book-title></src-title-info>'
        '<output id="dup" mode="free"/>'
        "</description>"
        "<body><section><p>x</p></section></body></FictionBook>"
    )
    assert WRITE_DUPLICATE_ID in _codes(validate(book))


def test_a_duplicate_binary_id_is_an_error() -> None:
    """С90: two binaries with the same id are an error."""
    # The id of a <binary> is an xs:ID attribute: two binaries with the same id
    # make a file the schema rejects.
    body = Body(children=(Section("s1", (Paragraph((Text("a"),)),)),))
    rep = validate(
        _book(
            bodies=(body,),
            binaries=(Binary("dup", "image/png", "QUJD"), Binary("dup", "image/png", "QUJD")),
        )
    )
    assert WRITE_DUPLICATE_ID in _codes(rep)


def test_a_binary_id_that_duplicates_a_node_id_is_an_error() -> None:
    """С90: the id of a binary that repeats a node id is an error."""
    body = Body(children=(Section("s1", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,), binaries=(Binary("s1", "image/png", "QUJD"),)))
    assert WRITE_DUPLICATE_ID in _codes(rep)


def test_an_invalid_binary_id_is_an_error() -> None:
    """С90: an invalid id of a binary is an error."""
    # The id is written as an attribute of type xs:ID: it has to be an ASCII
    # identifier, like the id of any other element.
    body = Body(children=(Section("s1", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,), binaries=(Binary("b 1", "image/png", "QUJD"),)))
    assert WRITE_INVALID_ID in _codes(rep)


def test_a_valid_binary_id_is_accepted() -> None:
    """С90: a valid id of a binary is accepted."""
    body = Body(children=(Section("s1", (Paragraph((Text("a"),)),)),))
    rep = validate(_book(bodies=(body,), binaries=(Binary("cover.png", "image/png", "QUJD"),)))
    assert WRITE_INVALID_ID not in _codes(rep)
    assert WRITE_DUPLICATE_ID not in _codes(rep)


def test_an_invalid_character_in_the_text_of_a_root_extra_is_an_error() -> None:
    """С93: a root-level Raw with an invalid character is not written silently."""
    from fb2kit.model.inline import Raw

    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    broken = book.replace(extra=(Raw("stylesheet", "css\x0cbody{}"),))
    rep = validate(broken)
    assert WRITE_INVALID_CHAR in _codes(rep)
    assert rep.ok is False


def test_a_tag_with_an_unbound_prefix_is_an_error() -> None:
    """С94: a tag like <a:b> cannot be written without inventing a namespace."""
    book = fb2kit.parse_string(
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info><genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>T</book-title><lang>ru</lang></title-info></description>"
        "<body><section><p>a<o:p>x</o:p>c</p></section></body></FictionBook>",
        mode=fb2kit.Mode.TOLERANT,
        backend=fb2kit.Backend.LXML,
    )
    rep = validate(book)
    assert WRITE_INVALID_TAG in _codes(rep)
    assert rep.ok is False


def test_an_attribute_with_an_unbound_prefix_is_an_error() -> None:
    """С94: an attribute like o:style cannot be written without a namespace."""
    import xml.etree.ElementTree as ET

    from fb2kit.model.inline import Raw

    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    element = ET.fromstring("<unknown/>")
    element.set("o:style", "x")
    broken = book.replace(extra=(Raw("unknown", "", element),))
    rep = validate(broken)
    assert WRITE_INVALID_TAG in _codes(rep)


def test_missing_genre_and_author_are_warnings() -> None:
    """С95: the schema needs a genre and an author; the writer warns, not blocks."""
    book = _book()
    broken = book.replace(
        description=dataclasses.replace(
            book.description,
            title_info=dataclasses.replace(book.description.title_info, genres=(), authors=()),
        ),
    )
    rep = validate(broken)
    assert {WRITE_NO_GENRE, WRITE_NO_AUTHOR} <= set(_codes(rep))
    assert rep.ok is True


def test_an_author_without_a_first_name_and_a_nickname_is_a_warning() -> None:
    """С95: an author needs first+last or a nickname, as the schema says."""
    from fb2kit.model.metadata import Author

    book = _book()
    broken = book.replace(
        description=dataclasses.replace(
            book.description,
            title_info=dataclasses.replace(
                book.description.title_info, authors=(Author(last_name="Only"),)
            ),
        ),
    )
    rep = validate(broken)
    assert WRITE_INCOMPLETE_AUTHOR in _codes(rep)
    assert rep.ok is True
