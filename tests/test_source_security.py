from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fb2kit.errors import Fb2UnsafeInputError
from fb2kit.source import check_safe_input, open_container

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["xxe-doctype.fb2", "entity-bomb.fb2"])
def test_doctype_and_entities_are_rejected(name: str) -> None:
    with pytest.raises(Fb2UnsafeInputError):
        check_safe_input((FIXTURES / name).read_bytes())


@pytest.mark.parametrize("name", ["xxe-doctype.fb2", "entity-bomb.fb2"])
def test_rejected_before_any_parsing(name: str) -> None:
    with pytest.raises(Fb2UnsafeInputError):
        open_container(FIXTURES / name)


def test_marker_is_found_in_any_case_and_position() -> None:
    with pytest.raises(Fb2UnsafeInputError):
        check_safe_input(b"<?xml version='1.0'?><a><!doctype b></a>")


def test_clean_document_passes() -> None:
    check_safe_input((FIXTURES / "minimal.fb2").read_bytes())


def test_comment_mentioning_doctype_is_rejected_too() -> None:
    # Deliberate over-match: a false positive is safer than trying to "cleverly" parse DOCTYPE.
    with pytest.raises(Fb2UnsafeInputError):
        check_safe_input(b"<a><!-- <!DOCTYPE x> --></a>")


@pytest.mark.parametrize("text", ["<a><!DOCTYPE b></a>", "<!EnTiTy x 'y'><a/>"])
def test_text_input_is_scanned_too(text: str) -> None:
    with pytest.raises(Fb2UnsafeInputError):
        check_safe_input(text)


def test_byte_scan_does_not_see_utf16_by_design() -> None:
    # The byte-scan limitation is pinned by a test: UTF-16 is caught by the repeated text scan (Task 14).
    check_safe_input("<!DOCTYPE x><a/>".encode("utf-16-le"))


def test_cdata_mentioning_entity_is_rejected_too() -> None:
    with pytest.raises(Fb2UnsafeInputError):
        check_safe_input(b"<a><![CDATA[<!ENTITY x 'y'>]]></a>")


@given(st.binary().filter(lambda b: b"<!" not in b))
def test_input_without_markup_declarations_always_passes(data: bytes) -> None:
    check_safe_input(data)
