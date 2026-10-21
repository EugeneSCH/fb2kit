import pickle

import pytest

from fb2kit.errors import (
    Fb2EncodingError,
    Fb2Error,
    Fb2ParseError,
    Fb2SourceError,
    Fb2UnsafeInputError,
    Fb2WriteError,
)
from fb2kit.write.validate import Problem, WriteSeverity


def test_hierarchy_is_flat_under_fb2_error() -> None:
    for exc in (Fb2SourceError, Fb2ParseError, Fb2EncodingError):
        assert issubclass(exc, Fb2Error)


def test_unsafe_input_is_a_source_error() -> None:
    assert issubclass(Fb2UnsafeInputError, Fb2SourceError)


def test_parse_error_carries_location() -> None:
    err = Fb2ParseError("mismatched tag", path="FictionBook/body[0]/section[2]/p", line=41)
    assert err.path == "FictionBook/body[0]/section[2]/p"
    assert err.line == 41
    assert str(err) == "mismatched tag"


def test_parse_error_location_is_optional() -> None:
    err = Fb2ParseError("bad root")
    assert err.path is None and err.line is None


@pytest.mark.parametrize(
    "exc",
    [
        Fb2Error("e"),
        Fb2SourceError("e"),
        Fb2UnsafeInputError("e"),
        Fb2EncodingError("e"),
        Fb2ParseError("e", path="FictionBook/body[0]", line=3),
    ],
)
def test_exceptions_survive_pickle(exc: Fb2Error) -> None:
    clone = pickle.loads(pickle.dumps(exc))
    assert type(clone) is type(exc) and str(clone) == str(exc)
    assert getattr(clone, "path", None) == getattr(exc, "path", None)
    assert getattr(clone, "line", None) == getattr(exc, "line", None)


def test_parse_error_repr_shows_location() -> None:
    text = repr(Fb2ParseError("x", path="body[0]", line=41))
    assert "body[0]" in text and "41" in text


def test_write_error_survives_pickling() -> None:
    """С100: the error crosses a process boundary with its problems."""

    err = Fb2WriteError((Problem("x", "boom", WriteSeverity.ERROR),))
    restored = pickle.loads(pickle.dumps(err))
    assert restored.problems == err.problems
