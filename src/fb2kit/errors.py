"""fb2kit exception hierarchy."""

from __future__ import annotations

from typing import Any


class Fb2Error(Exception):
    """Base class of all fb2kit errors."""


class Fb2SourceError(Fb2Error):
    """The input is unusable: no file, empty, larger than `max_size` or a broken archive."""


class Fb2UnsafeInputError(Fb2SourceError):
    """The input contains a `<!DOCTYPE` or `<!ENTITY` declaration; such input is always rejected."""


class Fb2EncodingError(Fb2Error):
    """The encoding could not be detected, or the bytes contradict it."""


class Fb2ParseError(Fb2Error):
    """The document is not valid XML or not a FictionBook.

    Attributes:
        path: The element where the error occurred, if known (for example `FictionBook`).
        line: XML error line number, if the parser reported it.
    """

    def __init__(self, message: str, *, path: str | None = None, line: int | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.line = line

    def __reduce__(self) -> tuple[Any, ...]:
        return (_rebuild_parse_error, (str(self), self.path, self.line))

    def __repr__(self) -> str:
        return f"Fb2ParseError({str(self)!r}, path={self.path!r}, line={self.line!r})"


def _rebuild_parse_error(message: str, path: str | None, line: int | None) -> Fb2ParseError:
    return Fb2ParseError(message, path=path, line=line)
