"""The output of the writer against the schema of the format.

The schema is the one of `gribuser/fb2` (FictionBook 2.0, BSD-2-Clause); it is
shipped with the package, so the test needs nothing but the package itself.
`lxml` is an optional extra: without it the test is skipped.
"""

from pathlib import Path

import pytest

import fb2kit

pytest.importorskip("lxml")

from lxml import etree

SCHEMA_DIR = Path(fb2kit.__file__).parent / "write" / "_schema"


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    """The schema of the format, built from the files of the package."""
    return etree.XMLSchema(etree.parse(str(SCHEMA_DIR / "FictionBook.xsd")))


@pytest.mark.corpus
def test_writer_output_is_xsd_valid(schema: etree.XMLSchema) -> None:
    """С31: the output of the writer is valid by the schema."""
    from conftest import corpus_files

    for path in corpus_files():
        book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
        out = book.to_bytes(strict=False)
        doc = etree.fromstring(out)
        assert schema.validate(doc), f"{path.name}: {schema.error_log}"


def test_writer_output_order_follows_the_schema(schema: etree.XMLSchema) -> None:
    """С32: the order of the output follows the schema."""
    # A document built by hand according to the rules of the schema: home-page
    # before email, genre/author/book-title/lang.
    xml = (
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" '
        'xmlns:l="http://www.w3.org/1999/xlink">'
        "<description><title-info>"
        "<genre>sf</genre>"
        "<author><first-name>Иван</first-name><last-name>Петров</last-name>"
        "<home-page>https://example.com</home-page><email>i@example.com</email></author>"
        "<book-title>Книга</book-title>"
        "<lang>ru</lang>"
        "</title-info>"
        "<document-info><author><nickname>d</nickname></author>"
        "<date>2020</date><id>fb2-test</id><version>1.0</version></document-info>"
        "</description>"
        "<body><section><p>текст</p></section></body></FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    out = book.to_bytes(strict=False)
    doc = etree.fromstring(out)
    assert schema.validate(doc), str(schema.error_log)


def test_src_title_info_stays_right_after_title_info(schema: etree.XMLSchema) -> None:
    """С33: src-title-info stays right after title-info."""
    # src-title-info goes right after title-info in the schema; output -- to the
    # end of the description.
    xml = (
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info>"
        "<genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>Книга</book-title><lang>ru</lang>"
        "</title-info>"
        "<src-title-info><genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>Исходное</book-title><lang>ru</lang></src-title-info>"
        "<document-info><author><nickname>d</nickname></author>"
        "<date>2020</date><id>fb2-test</id><version>1.0</version></document-info>"
        "</description>"
        "<body><section><p>текст</p></section></body></FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    out = book.to_bytes(strict=False)
    doc = etree.fromstring(out)
    assert schema.validate(doc), str(schema.error_log)
    # The element is not only valid: it is there, and it is where the schema
    # wants it.
    assert (
        doc.find(
            "{http://www.gribuser.ru/xml/fictionbook/2.0}description/"
            "{http://www.gribuser.ru/xml/fictionbook/2.0}src-title-info"
        )
        is not None
    )
    description = doc[0]
    assert description[1].tag.endswith("src-title-info")


def test_the_output_of_the_root_moves_into_the_description(schema: etree.XMLSchema) -> None:
    """С51: the output of the root moves into the description by the schema."""
    # The schema does not allow <output> at the root of the document: it lives
    # inside the <description>, at the end of it.
    xml = (
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info>"
        "<genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>Книга</book-title><lang>ru</lang>"
        "</title-info>"
        "<document-info><author><nickname>d</nickname></author>"
        "<date>2020</date><id>fb2-test</id><version>1.0</version></document-info>"
        "</description>"
        '<output mode="free" include-all="allow"/>'
        "<body><section><p>текст</p></section></body></FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    out = book.to_bytes(strict=False)
    doc = etree.fromstring(out)
    assert schema.validate(doc), str(schema.error_log)
    ns = "{http://www.gribuser.ru/xml/fictionbook/2.0}"
    assert doc.find(f"{ns}output") is None
    assert doc.find(f"{ns}description/{ns}output") is not None


def test_the_id_of_a_body_is_not_written(schema: etree.XMLSchema) -> None:
    """С91: the id of a body is not written."""
    # The schema of the format does not allow an id on <body>: writing it
    # makes a file that no reader of the schema accepts.
    xml = (
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info>"
        "<genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>Книга</book-title><lang>ru</lang>"
        "</title-info>"
        "<document-info><author><nickname>d</nickname></author>"
        "<date>2020</date><id>fb2-test</id><version>1.0</version></document-info>"
        "</description>"
        '<body id="b1"><section><p>текст</p></section></body>'
        "</FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    out = book.to_bytes(strict=False)
    assert b'<body id="b1"' not in out
    doc = etree.fromstring(out)
    assert schema.validate(doc), str(schema.error_log)


def test_a_duplicate_binary_id_is_rejected_by_the_schema(schema: etree.XMLSchema) -> None:
    """С90: the schema rejects two binaries with one id."""
    # Two <binary> with the same id: the schema declares the id as xs:ID, so
    # the file is invalid. The writer refuses such a book (write.duplicate-id).
    xml = (
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        "<description><title-info>"
        "<genre>sf</genre><author><nickname>a</nickname></author>"
        "<book-title>Книга</book-title><lang>ru</lang>"
        "</title-info>"
        "</description>"
        "<body><section><p>текст</p></section></body>"
        '<binary id="dup" content-type="image/png">QUJD</binary>'
        '<binary id="dup" content-type="image/png">QUJD</binary>'
        "</FictionBook>"
    )
    book = fb2kit.parse_string(xml)
    doc = etree.fromstring(book.to_bytes(strict=False))
    assert not schema.validate(doc), "the schema must reject two binaries with one id"


def test_the_schema_of_the_package_is_complete(schema: etree.XMLSchema) -> None:
    """С92: the schema of the format is shipped with the package."""
    assert SCHEMA_DIR.is_dir()
    for name in (
        "FictionBook.xsd",
        "FictionBookGenres.xsd",
        "FictionBookLang.xsd",
        "FictionBookLinks.xsd",
    ):
        assert (SCHEMA_DIR / name).is_file(), name
    assert schema is not None
