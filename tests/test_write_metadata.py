import xml.etree.ElementTree as ET

from fb2kit.model.inline import Image, Text
from fb2kit.model.metadata import (
    Author,
    CustomInfo,
    Date,
    Description,
    DocumentInfo,
    PublishInfo,
    Sequence,
    TitleInfo,
)
from fb2kit.model.structure import Paragraph
from fb2kit.parser import FB2_NS
from fb2kit.write.serialize import _description_el


def _names(el: ET.Element) -> list[str]:
    return [c.tag.rpartition("}")[2] for c in el]


def test_description_child_order() -> None:
    """С71: the children of the description keep the order of the schema."""
    desc = Description(
        title_info=TitleInfo(title="T"),
        document_info=DocumentInfo(ids=("id1",)),
        publish_info=PublishInfo(isbn="978"),
        custom_info=(CustomInfo("x", "y"),),
    )
    assert _names(_description_el(desc)) == [
        "title-info",
        "document-info",
        "publish-info",
        "custom-info",
    ]


def test_title_info_child_order() -> None:
    """С9: the children of the title info keep the order of the schema."""
    ti = TitleInfo(
        genres=("sf",),
        authors=(Author(last_name="A"),),
        title="T",
        annotation=(Paragraph((Text("ann"),)),),
        keywords="k",
        dates=(Date("1900", "ru", "1900-01-01"),),
        coverpage=(Image(href="#cover"),),
        lang="ru",
        src_lang="en",
        translators=(Author(last_name="TR"),),
        sequences=(Sequence("S", 2),),
    )
    desc = _description_el(Description(ti))
    assert _names(desc[0]) == [
        "genre",
        "author",
        "book-title",
        "annotation",
        "keywords",
        "date",
        "coverpage",
        "lang",
        "src-lang",
        "translator",
        "sequence",
    ]


def test_author_fields_and_full_name_parts() -> None:
    """С32: the fields of an author follow the order of the schema."""
    desc = _description_el(
        Description(
            TitleInfo(
                authors=(Author("I", "P", "S", "nick", ("a@b",), ("https://x",)),),
            )
        )
    )
    # Порядок строго по XSD (gribuser/fb2, authorType): home-page перед email.
    assert _names(desc[0][0]) == [
        "first-name",
        "middle-name",
        "last-name",
        "nickname",
        "home-page",
        "email",
    ]


def test_date_attributes() -> None:
    """С72: the attributes of a date are written."""
    desc = _description_el(Description(TitleInfo(dates=(Date("1900", "ru", "1900-01-01"),))))
    date = desc[0][0]
    assert date.text == "1900"
    assert date.get("value") == "1900-01-01"
    assert date.get("{http://www.w3.org/XML/1998/namespace}lang") == "ru"


def test_sequence_number_is_string_attribute() -> None:
    """С72: the number of a series is a string attribute."""
    desc = _description_el(Description(TitleInfo(sequences=(Sequence("S", 3),))))
    seq = desc[0][0]
    assert (seq.get("name"), seq.get("number")) == ("S", "3")


def test_publish_info_and_document_info_order_and_fields() -> None:
    """С71: the fields of the document info and of the publish info keep the order."""
    desc = _description_el(
        Description(
            TitleInfo(title="T"),
            DocumentInfo(
                authors=(Author(last_name="A"),),
                program_used="fb2kit",
                dates=(Date("2026"),),
                source_url="https://x",
                source_ocr="ocr",
                ids=("i",),
                version="1.0",
                history=("h1", "h2"),
                publisher="P",
            ),
            PublishInfo("B", "P", "C", "2020", "978", (Sequence("S", 1),)),
        )
    )
    doc, pub = desc[1], desc[2]
    assert _names(doc) == [
        "author",
        "program-used",
        "date",
        "src-url",
        "src-ocr",
        "id",
        "version",
        "history",
        "publisher",
    ]
    assert [p.text for p in doc.findall(f"{{{FB2_NS}}}history/{{{FB2_NS}}}p")] == ["h1", "h2"]
    assert _names(pub) == ["book-name", "publisher", "city", "year", "isbn", "sequence"]


def test_custom_info_keeps_info_type() -> None:
    """С72: a custom info keeps its info type."""
    desc = _description_el(Description(TitleInfo(), custom_info=(CustomInfo("my", "text"),)))
    el = next(c for c in desc if c.tag.rpartition("}")[2] == "custom-info")
    assert el.get("info-type") == "my"
    assert el.text == "text"


def test_description_extra_is_preserved() -> None:
    """С73: the extra of the description is preserved."""
    from fb2kit.model.inline import Raw

    desc = _description_el(
        Description(
            TitleInfo(title="T"),
            extra=(Raw("my-tag", "y"),),
        )
    )
    assert "my-tag" in [c.tag.rpartition("}")[2] for c in desc]


def test_src_title_info_goes_right_after_title_info() -> None:
    """С73: src-title-info goes right after title-info."""
    from fb2kit.model.inline import Raw

    desc = _description_el(
        Description(
            TitleInfo(title="T"),
            document_info=DocumentInfo(ids=("i",)),
            extra=(Raw("src-title-info", "src"),),
        )
    )
    assert [c.tag.rpartition("}")[2] for c in desc] == [
        "title-info",
        "src-title-info",
        "document-info",
    ]


def test_output_goes_to_the_end_of_the_description() -> None:
    """С51: the output goes to the end of the description."""
    from fb2kit.model.inline import Raw

    desc = _description_el(
        Description(
            TitleInfo(title="T"),
            custom_info=(CustomInfo("my", "text"),),
            extra=(Raw("output", "out"),),
        )
    )
    assert [c.tag.rpartition("}")[2] for c in desc] == [
        "title-info",
        "custom-info",
        "output",
    ]
