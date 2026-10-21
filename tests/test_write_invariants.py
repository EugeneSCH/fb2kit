"""Invariants of the writer: they must hold for every book, generated or not."""

from hypothesis import given
from strategies import fb2_document

import fb2kit
from fb2kit.report import Mode


@given(fb2_document())
def test_generated_books_roundtrip_to_the_same_bytes(text: str) -> None:
    """С2: a generated book gives the same bytes after a round trip."""
    book = fb2kit.parse_string(text, mode=Mode.TOLERANT)
    out = book.to_bytes(strict=False)
    assert fb2kit.parse(out, mode=Mode.TOLERANT).to_bytes(strict=False) == out


@given(fb2_document())
def test_output_is_utf8_and_deterministic(text: str) -> None:
    """С23: the output of one book is UTF-8 and the same every time."""
    book = fb2kit.parse_string(text, mode=Mode.TOLERANT)
    first = book.to_bytes(strict=False)
    assert first.decode("utf-8")
    assert book.to_bytes(strict=False) == first


@given(fb2_document())
def test_the_output_keeps_the_model(text: str) -> None:
    """С1: the output of a generated book keeps the model."""
    book = fb2kit.parse_string(text, mode=Mode.TOLERANT)
    again = fb2kit.parse(book.to_bytes(strict=False), mode=Mode.TOLERANT)
    assert again.description == book.description
    assert again.bodies == book.bodies
    assert again.extra == book.extra
