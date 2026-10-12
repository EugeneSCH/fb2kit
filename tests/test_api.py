# tests/test_api.py
from pathlib import Path

import pytest
from conftest import TITLE

import fb2kit
from fb2kit.model.inline import Link
from fb2kit.model.structure import Body, Section
from fb2kit.report import Mode, Severity

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_a_path_end_to_end() -> None:
    book = fb2kit.parse(FIXTURES / "notes-and-links.fb2")
    assert book.description.title_info.title
    assert isinstance(book.bodies[0], Body)


def test_parse_bytes_and_tolerant_mode() -> None:
    raw = (FIXTURES / "bare-amp.fb2").read_bytes()
    book = fb2kit.parse(raw, mode=Mode.TOLERANT)
    assert any(d.severity is Severity.WARNING for d in book.report.warnings)


def test_notes_body_and_resolution() -> None:
    book = fb2kit.parse(FIXTURES / "notes-and-links.fb2")
    assert book.notes_body is not None
    assert isinstance(book.by_id("n1"), Section)


def test_resolve_link_returns_target_or_none() -> None:
    book = fb2kit.parse(FIXTURES / "notes-and-links.fb2")
    link = Link(href="#n1", link_type="note")
    assert isinstance(book.resolve(link), Section)
    assert book.resolve(Link(href="#missing")) is None


def test_cover_is_available() -> None:
    book = fb2kit.parse(FIXTURES / "binary-cover.fb2")
    assert book.cover is not None and book.cover.data


def test_iter_sections_walks_depth_first_in_order() -> None:
    book = fb2kit.parse(FIXTURES / "structure-rich.fb2")
    titles = [s.title for s in book.iter_sections()]
    assert len(titles) >= 2 and titles[0] is not None


def test_report_accumulates_source_and_backend() -> None:
    book = fb2kit.parse(FIXTURES / "container.fbz")
    assert book.report.container == "fbz"
    assert book.report.backend in {"stdlib", "lxml"}
    assert book.report.source_encoding == "utf-8"


def test_element_escape_hatch_is_present_but_not_compared() -> None:
    book = fb2kit.parse(FIXTURES / "minimal.fb2")
    assert book.element is not None
    assert fb2kit.parse(FIXTURES / "minimal.fb2") == book


def test_public_api_is_explicit() -> None:
    assert set(fb2kit.__all__) >= {"parse", "FictionBook", "Mode", "Backend", "Fb2Error"}
    for name in fb2kit.__all__:
        assert hasattr(fb2kit, name)


def test_doctype_is_rejected_even_in_utf16() -> None:
    # UTF-16LE/BE: the byte scan in check_safe_input misses <!DOCTYPE because of the zero bytes;
    # the scan is repeated over the decoded text inside parse().
    import pytest

    with pytest.raises(fb2kit.Fb2UnsafeInputError):
        fb2kit.parse(FIXTURES / "utf16-doctype.fb2")


def test_strict_mode_raises_on_malformed_file() -> None:
    import pytest

    with pytest.raises(fb2kit.Fb2ParseError):
        fb2kit.parse(FIXTURES / "bare-amp.fb2")


def test_str_source_is_always_a_path() -> None:
    import pytest

    assert fb2kit.parse(str(FIXTURES / "minimal.fb2")).bodies
    with pytest.raises(fb2kit.Fb2SourceError):
        fb2kit.parse("<FictionBook/>")


def test_parse_string_keeps_unknown_root_children_as_raw() -> None:
    from fb2kit.parser import FB2_NS

    book = fb2kit.parse_string(
        f'<FictionBook xmlns="{FB2_NS}"><stylesheet type="text/css">p {{}}</stylesheet>'
        "<description><title-info><book-title>T</book-title></title-info></description>"
        "<body><section><p>x</p></section></body></FictionBook>"
    )
    assert book.description.title_info.title == "T"
    assert [r.tag for r in book.extra] == ["stylesheet"]


def test_parse_string_rejects_doctype() -> None:
    import pytest

    with pytest.raises(fb2kit.Fb2UnsafeInputError):
        fb2kit.parse_string("<!DOCTYPE FictionBook><FictionBook/>")


def test_explicit_encoding_overrides_wrong_prolog() -> None:
    book = fb2kit.parse(FIXTURES / "wrong-prolog-cp1251.fb2", encoding="cp1251")
    assert book.description.title_info.title == TITLE
    assert book.report.source_encoding == "cp1251"


def test_max_size_is_enforced() -> None:
    import pytest

    with pytest.raises(fb2kit.Fb2SourceError, match="max_size"):
        fb2kit.parse(FIXTURES / "minimal.fb2", max_size=10)


def test_parse_does_not_decode_binaries() -> None:
    book = fb2kit.parse(FIXTURES / "binary-cover.fb2")
    assert book.cover is not None
    assert all(b._cache == {} for b in book.binaries)


def _backends() -> list[fb2kit.Backend]:
    import importlib.util

    return [fb2kit.Backend.STDLIB] + (
        [fb2kit.Backend.LXML] if importlib.util.find_spec("lxml") else []
    )


@pytest.mark.parametrize(
    "name",
    [
        "minimal.fb2",
        "structure-rich.fb2",
        "metadata-full.fb2",
        "notes-and-links.fb2",
        "binary-cover.fb2",
    ],
)
def test_backends_produce_equal_books(name: str) -> None:
    if len(_backends()) < 2:
        pytest.skip("lxml is not installed")
    books = [fb2kit.parse(FIXTURES / name, backend=b) for b in _backends()]
    assert books[0] == books[1]
    assert [d.code for d in books[0].report.diagnostics] == [
        d.code for d in books[1].report.diagnostics
    ]


def test_all_source_kinds_give_equal_books() -> None:
    from io import BytesIO

    path = FIXTURES / "minimal.fb2"
    books = [
        fb2kit.parse(path),
        fb2kit.parse(str(path)),
        fb2kit.parse(path.read_bytes()),
        fb2kit.parse(BytesIO(path.read_bytes())),
        fb2kit.parse_string(path.read_text(encoding="utf-8")),
    ]
    # parse_string's report differs (no source prolog) -- compare the model
    assert all(
        (b.description, b.bodies, b.binaries)
        == (books[0].description, books[0].bodies, books[0].binaries)
        for b in books
    )


def test_core_does_not_import_lxml_on_stdlib_backend() -> None:
    import subprocess
    import sys

    code = (
        "import sys, fb2kit; "
        f"fb2kit.parse({str(FIXTURES / 'minimal.fb2')!r}, backend=fb2kit.Backend.STDLIB); "
        "assert 'lxml' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_book_and_index_are_read_only() -> None:
    import dataclasses

    book = fb2kit.parse(FIXTURES / "notes-and-links.fb2")
    with pytest.raises(dataclasses.FrozenInstanceError):
        book.cover = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        book.index["x"] = book.bodies[0]  # type: ignore[index]


@pytest.mark.parametrize(("mode", "raises"), [(Mode.STRICT, True), (Mode.TOLERANT, False)])
def test_missing_description(mode: Mode, raises: bool) -> None:
    from fb2kit.parser import FB2_NS

    text = f'<FictionBook xmlns="{FB2_NS}"><body><section><p>x</p></section></body></FictionBook>'
    if raises:
        with pytest.raises(fb2kit.Fb2ParseError, match="description"):
            fb2kit.parse_string(text, mode=mode)
        return
    book = fb2kit.parse_string(text, mode=mode)
    assert book.description.title_info.title is None
    assert "element.missing" in [d.code for d in book.report.diagnostics]


@pytest.mark.parametrize("mode", [Mode.STRICT, Mode.TOLERANT])
def test_book_without_body_is_a_warning(mode: Mode) -> None:
    from fb2kit.parser import FB2_NS

    book = fb2kit.parse_string(
        f'<FictionBook xmlns="{FB2_NS}"><description><title-info><book-title>T</book-title>'
        "</title-info></description></FictionBook>",
        mode=mode,
    )
    assert book.bodies == ()
    assert "element.missing" in [d.code for d in book.report.warnings]
