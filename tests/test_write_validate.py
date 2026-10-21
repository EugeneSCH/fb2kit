from fb2kit.errors import Fb2Error, Fb2WriteError
from fb2kit.write.validate import (
    WRITE_NO_BODY,
    Problem,
    WriteReport,
    WriteSeverity,
    validate,
)


def test_write_error_is_an_fb2_error() -> None:
    """С87: the write error is an Fb2Error."""
    assert issubclass(Fb2WriteError, Fb2Error)


def test_report_splits_errors_and_warnings() -> None:
    """С86: the report splits the errors and the warnings."""
    rep = WriteReport(
        (
            Problem(WRITE_NO_BODY, "book has no body", WriteSeverity.ERROR),
            Problem("write.dangling-link", "no target", WriteSeverity.WARNING),
        )
    )
    assert rep.ok is False
    assert [p.code for p in rep.errors] == [WRITE_NO_BODY]
    assert [p.code for p in rep.warnings] == ["write.dangling-link"]


def test_report_is_ok_without_errors() -> None:
    """С86: the report is ok while it has no errors."""
    assert WriteReport().ok is True
    assert WriteReport((Problem("x", "w"),)).ok is True


def test_error_message_mentions_first_problem_and_count() -> None:
    """С87: the message of the error names the first problem and their number."""
    err = Fb2WriteError(
        (
            Problem(WRITE_NO_BODY, "book has no body", WriteSeverity.ERROR),
            Problem("write.no-title", "no title", WriteSeverity.ERROR),
        )
    )
    assert "book has no body" in str(err)
    assert "2" in str(err)
    assert len(err.problems) == 2


def test_problem_is_frozen_and_hashable() -> None:
    """С87: a problem is frozen and hashable."""
    hash(Problem("x", "msg"))


def test_validate_is_callable() -> None:
    """С86: the validation is callable."""
    assert callable(validate)
