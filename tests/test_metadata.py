# tests/test_metadata.py
from pathlib import Path

import pytest
from conftest import cases

from fb2kit.builder import Builder
from fb2kit.model.bind import bind_description
from fb2kit.model.inline import Image
from fb2kit.model.metadata import Author, Date, Sequence, TitleInfo
from fb2kit.model.structure import Paragraph
from fb2kit.parser import parse_tree

FIXTURES = Path(__file__).parent / "fixtures"
_EXP = cases("metadata")


def _description():
    tree = parse_tree((FIXTURES / "metadata-full.fb2").read_text(encoding="utf-8"))
    el = next(e for e in tree.root if e.tag.endswith("}description"))
    return bind_description(el, Builder(diagnostics=[], index={}))


def test_title_info_scalars() -> None:
    ti = _description().title_info
    assert ti.title == _EXP["title"]
    assert ti.lang == "ru" and ti.src_lang == "en"
    assert ti.genres == ("sf", "detective", "prose_classic")
    assert isinstance(ti.dates[0], Date) and ti.dates[0].lang == "ru"


def test_authors_and_translators() -> None:
    ti = _description().title_info
    assert isinstance(ti.authors[0], Author)
    assert ti.authors[0].full_name == _EXP["full_name"]
    assert ti.authors[0].emails == ("ivan@example.com",)
    assert ti.authors[0].home_pages == ("https://example.com",)
    assert ti.translators[0].last_name == _EXP["translator"]


def test_sequences_with_number() -> None:
    ti = _description().title_info
    name, number = _EXP["sequence"]
    assert Sequence(name=name, number=number) in ti.sequences


def test_annotation_is_block_content() -> None:
    ti = _description().title_info
    assert ti.annotation is not None and len(ti.annotation) == 2
    assert isinstance(ti.annotation[0], Paragraph)


def test_coverpage_is_inline_image() -> None:
    ti = _description().title_info
    assert isinstance(ti.coverpage[0], Image) and ti.coverpage[0].href == "#cover"


def test_document_info_is_populated() -> None:
    di = _description().document_info
    assert di is not None
    assert di.ids == ("fb2-test-id",) and di.version == "1.1"
    assert di.history and di.source_url is None


def test_publish_info_is_populated() -> None:
    pi = _description().publish_info
    assert pi is not None
    assert (pi.isbn, pi.year, pi.city) == ("978-5-00000-000-0", "2021", _EXP["city"])


def test_custom_info_is_typed_and_unknown_elements_are_raw() -> None:
    from fb2kit.model.inline import Raw
    from fb2kit.model.metadata import CustomInfo

    desc = _description()
    assert desc.custom_info == (CustomInfo(info_type="calibre", text="x"),)
    assert [r.tag for r in desc.extra] == ["my-tag"] and isinstance(desc.extra[0], Raw)


def test_missing_optional_sections_are_none() -> None:
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS

    el = ET.fromstring(
        f'<description xmlns="{FB2_NS}"><title-info><book-title>T</book-title>'
        "<author><nickname>nick</nickname></author></title-info></description>"
    )
    desc = bind_description(el, Builder(diagnostics=[], index={}))
    assert desc.document_info is None and desc.publish_info is None
    assert desc.title_info.authors[0].full_name == "nick"


def test_author_with_only_nickname_has_no_empty_parts() -> None:
    assert Author(nickname="nick").full_name == "nick"
    assert Author(first_name="A", last_name="B").full_name == "A B"


def _desc(inner: str):
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS

    el = ET.fromstring(f'<description xmlns="{FB2_NS}">{inner}</description>')
    return bind_description(el, Builder(diagnostics=[], index={}))


def test_empty_title_info_gives_defaults() -> None:
    assert _desc("<title-info/>").title_info == TitleInfo()


def test_scalar_whitespace_is_stripped() -> None:
    ti = _desc(
        "<title-info><book-title>\n  Title  \n</book-title><lang> ru </lang></title-info>"
    ).title_info
    assert ti.title == "Title" and ti.lang == "ru"


@pytest.mark.parametrize(("raw", "number"), [("3", 3), ("x", None), ("", None), ("2.5", None)])
def test_sequence_number_parsing(raw: str, number: int | None) -> None:
    ti = _desc(f'<title-info><sequence name="S" number="{raw}"/></title-info>').title_info
    assert ti.sequences == (Sequence(name="S", number=number),)


def test_date_keeps_text_and_iso_value() -> None:
    ti = _desc('<title-info><date value="2020-01-01">1 Jan 2020</date></title-info>').title_info
    assert ti.dates == (Date(value="1 Jan 2020", iso="2020-01-01"),)


def test_author_without_names_has_empty_full_name() -> None:
    assert Author().full_name == ""


@pytest.mark.parametrize("tag", ["output", "src-title-info"])
def test_known_but_unmodelled_elements_are_raw_without_diagnostic(tag: str) -> None:
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS

    ctx = Builder(diagnostics=[], index={})
    el = ET.fromstring(f'<description xmlns="{FB2_NS}"><title-info/><{tag}/></description>')
    desc = bind_description(el, ctx)
    assert [r.tag for r in desc.extra] == [tag] and ctx.diagnostics == []
