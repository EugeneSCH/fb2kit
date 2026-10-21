"""Entry points: `parse()`, `parse_string()` and the `FictionBook` book class."""

from __future__ import annotations

import os
import stat
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field, replace
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias, TypeVar, cast
from xml.etree.ElementTree import Element

from fb2kit import report
from fb2kit.backends import Backend
from fb2kit.builder import Builder
from fb2kit.errors import Fb2ParseError, Fb2SourceError, Fb2WriteError
from fb2kit.model import iter_nodes
from fb2kit.model.binary import Binary
from fb2kit.model.bind import (
    _full_raw,
    _raw,
    bind_binaries,
    bind_body,
    bind_description,
    local_name,
    resolve_cover,
)
from fb2kit.model.inline import Link, Raw
from fb2kit.model.links import check_links
from fb2kit.model.metadata import Description, TitleInfo
from fb2kit.model.structure import Body, Node, Section
from fb2kit.parser import parse_tree
from fb2kit.report import Diagnostic, Mode, ParseReport
from fb2kit.source import (
    DEFAULT_MAX_SIZE,
    SourceLike,
    check_safe_input,
    decode_source,
    open_container,
    too_big,
)

_EMPTY_REPORT = ParseReport()

Indexed: TypeAlias = Node | Binary
"""Anything in the `id` map: a model node or a `Binary` attachment."""

_ZIP_SUFFIXES = (".fbz", ".fb2.zip", ".zip")
_XML_DECLARATION = "<?xml version='1.0' encoding='utf-8'?>\n"
_TEMP_ATTEMPTS = 100


@dataclass(frozen=True, slots=True)
class FictionBook:
    """A parsed FB2 book: an immutable model tree and the parse report.

    Created only via [`parse`][fb2kit.parse] and [`parse_string`][fb2kit.parse_string].

    Attributes:
        description: Metadata from `<description>`; empty in tolerant mode if it is missing.
            `Description(TitleInfo())`.
        bodies: All `<body>` elements in document order; the main text is usually first, notes are
            the body with a `name` (see `notes_body`).
        binaries: Attached `<binary>` elements (images); bytes are decoded lazily.
        element: Root `xml.etree.ElementTree.Element` after namespace normalization --
            an escape hatch to the raw XML; not used when comparing books.
        cover: Cover -- the `Binary` that the first `<coverpage><image>` points to, or `None`.
        report: Parse report: encoding, container, backend and all diagnostics.
        extra: Unknown child elements of `<FictionBook>` (for example `<stylesheet>`) as `Raw`.
        index: Read-only map `id` -> node (and `Binary`); the first one wins on duplicates.
    """

    description: Description
    bodies: tuple[Body, ...]
    binaries: tuple[Binary, ...]
    element: Element = field(compare=False, repr=False)
    cover: Binary | None = None
    report: ParseReport = _EMPTY_REPORT
    extra: tuple[Raw, ...] = ()
    index: Mapping[str, Indexed] = field(default_factory=dict, compare=False, repr=False)

    @property
    def notes_body(self) -> Body | None:
        """First body with notes (its `name` is set and not `main`) or `None`."""
        return next((b for b in self.bodies if b.is_notes), None)

    def by_id(self, id_: str) -> Indexed | None:
        """Node by its `id` attribute.

        Args:
            id_: The `id` value without a leading `#`.

        Returns:
            The model node or `Binary` with this `id`; `None` if there is none.
        """
        return self.index.get(id_)

    def resolve(self, link: Link) -> Indexed | None:
        """Target of an internal link.

        Args:
            link: A link from the text (`Link`), for example a `type="note"` footnote.

        Returns:
            The node or `Binary` that `#id` points to; `None` for external links and
            missing ids.
        """
        return self.by_id(link.href[1:]) if link.href.startswith("#") else None

    def iter_sections(self) -> Iterator[Section]:
        """All sections of all bodies depth-first, in document order (children follow parents).

        Yields:
            `Section` elements, including sections of notes bodies.
        """
        return (n for n in iter_nodes(self.bodies) if isinstance(n, Section))

    def to_xml(self, *, pretty: bool = False, declaration: bool = False) -> str:
        """The book as XML text.

        The text is the compact output of the writer: one line, no line breaks
        between the elements. The `pretty` mode indents the tree, but it does
        not change the text of the document -- unlike `ET.indent`, it does not
        touch the `tail` of the elements.

        The pretty output describes the same document as the compact one: the
        elements, their order, their attributes and their text are the same.
        The **model** of a book read back from it is not: the whitespace of
        the indentation becomes the text of the elements, so the round-trip
        guarantee ("one model -> the same bytes -> the same model") holds for
        the compact output only.

        Args:
            pretty: Indented output.
            declaration: Prepend the XML declaration.

        Returns:
            The XML text; it always ends with a newline.
        """
        from fb2kit.write.pretty import render
        from fb2kit.write.serialize import build_tree, serialize_bytes

        root = build_tree(self)
        if pretty:
            body = render(root)
        else:
            body = serialize_bytes(root).decode()
            body = body[len(_XML_DECLARATION) :]
        text = f"{_XML_DECLARATION}{body}" if declaration else body
        return text if text.endswith("\n") else text + "\n"

    def to_bytes(self, *, pretty: bool = False, strict: bool = True) -> bytes:
        """The book as XML bytes.

        The output is UTF-8 and deterministic: the same model always gives the
        same bytes.

        Args:
            pretty: Indented output.
            strict: Validate the book first and refuse to write a broken one.

        Returns:
            The XML bytes with a declaration and a trailing newline.

        Raises:
            Fb2WriteError: The book has a blocking problem and `strict` is set.
        """
        from fb2kit.write.serialize import build_tree, serialize_bytes

        if strict:
            _check_writable(self)
        if pretty:
            return self.to_xml(pretty=True, declaration=True).encode()
        return serialize_bytes(build_tree(self))

    def write(
        self,
        path: str | os.PathLike[str],
        *,
        pretty: bool = False,
        strict: bool = True,
        compress: bool | None = None,
    ) -> None:
        """Write the book to a file.

        The write is atomic: the bytes go to a temporary file in the target
        directory and then replace the target. A failed write leaves the old
        file intact.

        Args:
            path: The target file. A `.fbz`, `.fb2.zip` or `.zip` suffix means
                a zip archive with the book inside.
            pretty: Indented output.
            strict: Validate the book first and refuse to write a broken one.
            compress: Force a zip archive (`True`) or a plain file (`False`);
                `None` -- decide by the suffix of the path.

        Raises:
            Fb2WriteError: The book has a blocking problem and `strict` is set.
            Fb2SourceError: The target cannot be written.
        """
        from fb2kit.write.serialize import build_tree, serialize_bytes

        if strict:
            _check_writable(self)
        target = Path(path)
        if compress is None:
            compress = target.name.lower().endswith(_ZIP_SUFFIXES)
        if compress:
            from fb2kit.write.serialize import serialize_book

            data = _zip_bytes(serialize_book(self, pretty=pretty), _entry_name(target))
        elif pretty:
            data = self.to_bytes(pretty=True, strict=False)
        else:
            data = serialize_bytes(build_tree(self))
        _atomic_write(target, data)

    def replace(self, **changes: object) -> FictionBook:
        """A copy of the book with the given fields changed.

        The `element` and the `index` are rebuilt, so the copy always matches
        the model it holds. The book itself is not modified.

        Args:
            changes: The fields to replace: `description`, `bodies`, `binaries`,
                `cover`, `extra` or `report`.

        Returns:
            The new book.

        Raises:
            TypeError: An unknown field or a value of the wrong type.
        """
        from fb2kit.write.edit import reindex

        known = {
            "description": Description,
            "bodies": tuple,
            "binaries": tuple,
            "cover": type(None),
            "extra": tuple,
            "report": ParseReport,
        }
        for name, value in changes.items():
            if name not in known:
                raise TypeError(f"unknown field of a book: {name!r}")
            expected = known[name]
            if expected is tuple:
                if not isinstance(value, tuple):
                    raise TypeError(f"{name} must be a tuple, got {type(value).__name__}")
            elif name == "cover":
                if value is not None and not isinstance(value, Binary):
                    raise TypeError(f"cover must be a Binary or None, got {value!r}")
            elif not isinstance(value, expected):
                raise TypeError(f"{name} must be a {expected.__name__}, got {value!r}")
        binaries = cast(tuple[Binary, ...], changes.get("binaries", self.binaries))
        cover = _cover_after_replace(self.cover, changes, binaries)
        return reindex(
            replace(
                self,
                description=cast(Description, changes.get("description", self.description)),
                bodies=cast(tuple[Body, ...], changes.get("bodies", self.bodies)),
                binaries=binaries,
                cover=cover,
                extra=cast(tuple[Raw, ...], changes.get("extra", self.extra)),
                report=cast(ParseReport, changes.get("report", self.report)),
            )
        )


def _build(
    text: str,
    *,
    mode: Mode,
    backend: Backend,
    pre: tuple[Diagnostic, ...] = (),
    encoding: str = "utf-8",
    declared: str | None = None,
    container: str | None = None,
) -> FictionBook:
    check_safe_input(text)
    tree = parse_tree(text, backend=backend, mode=mode)
    root = tree.root
    ctx = Builder([], {})
    kids = [(local_name(c), c) for c in root]
    desc_els = [c for n, c in kids if n == "description"]
    if desc_els:
        description = bind_description(desc_els[0], ctx)
    elif mode is Mode.STRICT:
        raise Fb2ParseError("missing description", path="FictionBook")
    else:
        ctx.warn(report.ELEMENT_MISSING, "FictionBook has no <description>")
        description = Description(TitleInfo())
    bodies = tuple(bind_body(c, ctx) for n, c in kids if n == "body")
    if not bodies:
        ctx.warn(report.ELEMENT_MISSING, "FictionBook has no <body>")
    binaries = bind_binaries(root, ctx)
    cover = resolve_cover(description, binaries, ctx)
    check_links(bodies, ctx)
    extra = tuple(
        _full_raw(c, ctx) if n == "stylesheet" else _raw(c, ctx)
        for n, c in kids
        if n not in {"description", "body", "binary"}
    )
    rep = ParseReport(
        (*pre, *tree.diagnostics, *ctx.diagnostics), encoding, declared, container, tree.backend
    )
    return FictionBook(
        description,
        bodies,
        binaries,
        root,
        cover,
        rep,
        extra,
        cast(Mapping[str, Indexed], MappingProxyType(ctx.index)),
    )


_E = TypeVar("_E", bound=StrEnum)


def _coerce(cls: type[_E], value: object) -> _E:
    try:
        return cls(value)  # type: ignore[arg-type]
    except ValueError:
        raise TypeError(f"{cls.__name__} expected, got {value!r}") from None


def parse(
    source: SourceLike,
    *,
    encoding: str | None = None,
    mode: Mode | str = Mode.STRICT,
    backend: Backend | str = Backend.AUTO,
    max_size: int = DEFAULT_MAX_SIZE,
) -> FictionBook:
    """Parse an FB2 book from a file, bytes, a file object or a `.fbz`/`.fb2.zip`.

    Args:
        source: A path (`str` or `os.PathLike`; a string is always a path, not XML),
            `bytes`/`bytearray` or a binary file object. A zip archive is detected by signature,
            not by extension.
        encoding: Overrides the BOM and the prolog; `None` -- detect automatically.
        mode: `Mode.STRICT` -- any XML or encoding error raises an exception;
            `Mode.TOLERANT` -- repair what can be repaired and record every repair in `report`.
        backend: XML backend: `AUTO` (lxml if installed), `STDLIB` or `LXML`.
        max_size: Input size limit in bytes; for an archive, of the unpacked book
            (256 MB by default).

    Returns:
        The parsed book.

    Raises:
        Fb2SourceError: The file is unreadable, empty, larger than `max_size`, a broken archive,
            or the archive contains no book.
        Fb2UnsafeInputError: The input contains `<!DOCTYPE` or `<!ENTITY` (in both modes).
        Fb2EncodingError: The encoding cannot be detected or the bytes contradict it.
        Fb2ParseError: The XML does not parse, the root is not `FictionBook`, `<description>` is
            missing (strict) or nesting is deeper than 200.
        Fb2Error: `Backend.LXML` was requested but lxml is not installed.
        TypeError: Unsupported type of `source`, `mode` or `backend`.
    """
    mode, backend = _coerce(Mode, mode), _coerce(Backend, backend)
    opened = open_container(source, max_size=max_size)
    decoded = decode_source(opened.raw, encoding=encoding, mode=mode)
    return _build(
        decoded.text,
        mode=mode,
        backend=backend,
        pre=(*opened.diagnostics, *decoded.diagnostics),
        encoding=decoded.encoding,
        declared=decoded.declared_encoding,
        container=opened.container,
    )


def parse_string(
    text: str,
    *,
    mode: Mode | str = Mode.STRICT,
    backend: Backend | str = Backend.AUTO,
    max_size: int = DEFAULT_MAX_SIZE,
) -> FictionBook:
    """Parse a book from an already decoded XML string.

    There is no encoding detection or archive unpacking here; the `<?xml ...?>` prolog is ignored.
    `report.source_encoding` is always `"utf-8"`.

    Args:
        text: The book's XML text.
        mode: Parse mode, as in [`parse`][fb2kit.parse].
        backend: XML backend, as in [`parse`][fb2kit.parse].
        max_size: Text size limit in UTF-8 bytes (256 MB by default).

    Returns:
        The parsed book.

    Raises:
        Fb2SourceError: The text is larger than `max_size`.
        Fb2UnsafeInputError: The text contains `<!DOCTYPE` or `<!ENTITY`.
        Fb2ParseError: The XML does not parse or it is not a FictionBook.
        Fb2Error: `Backend.LXML` was requested but lxml is not installed.
        TypeError: Unsupported `mode` or `backend`.
    """
    mode, backend = _coerce(Mode, mode), _coerce(Backend, backend)
    if len(text.encode(errors="surrogatepass")) > max_size:
        raise too_big(max_size)
    return _build(text, mode=mode, backend=backend)


def _cover_after_replace(
    current: Binary | None, changes: dict[str, object], binaries: tuple[Binary, ...]
) -> Binary | None:
    """The cover of the edited book.

    A cover that points to a binary the change removed is dropped: the book
    must stay coherent.

    Args:
        current: The cover of the book before the change.
        changes: The fields given to `replace`.
        binaries: The binaries of the edited book.

    Returns:
        The cover of the edited book, or `None`.
    """
    if "cover" in changes:
        return cast(Binary | None, changes["cover"])
    if "binaries" in changes and current not in binaries:
        return None
    return current


def _check_writable(book: FictionBook) -> None:
    """Raise `Fb2WriteError` if the book cannot be written.

    Args:
        book: The book to check.

    Raises:
        Fb2WriteError: The book has at least one blocking problem.
    """
    from fb2kit.write.validate import validate

    report_ = validate(book)
    if report_.errors:
        raise Fb2WriteError(report_.errors)


def _entry_name(target: Path) -> str:
    """The name of the book inside the archive.

    Args:
        target: The path of the archive.

    Returns:
        The file name of the book, for example `book.fb2`.
    """
    name = target.name
    lowered = name.lower()
    for suffix in _ZIP_SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)] + ".fb2"
    return f"{name}.fb2"


def _zip_bytes(data: bytes, entry: str) -> bytes:
    """Pack the book into a zip archive.

    The archive is deterministic: the entry has a fixed date and the creator is
    always unix, so the same book gives the same bytes on every platform.

    Args:
        data: The XML bytes of the book.
        entry: The name of the entry inside the archive.

    Returns:
        The bytes of the archive.
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(entry, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o644 << 16
        zf.writestr(info, data)
    return buffer.getvalue()


def _target_path(target: Path) -> Path:
    """The real file the write goes to.

    A symlink is followed: the link itself must survive, only its target is
    replaced.

    Args:
        target: The path the caller gave.

    Returns:
        The path of the file to write.
    """
    return Path(os.path.realpath(target))


def _target_mode(target: Path) -> int | None:
    """The permissions the written file must have.

    An existing file keeps its own permissions; a new one gets the
    permissions of an ordinary file under the current umask.

    Args:
        target: The real target path.

    Returns:
        The permission bits, or `None` for the default of the umask.
    """
    try:
        info = os.stat(target)
    except OSError:
        return None
    return stat.S_IMODE(info.st_mode)


def _atomic_write(target: Path, data: bytes) -> None:
    """Write the bytes to the target atomically.

    The bytes go to a temporary file in the target directory and then replace
    the target. A failure leaves the old file intact and removes the
    temporary one.

    Args:
        target: The path the caller gave.
        data: The bytes to write.

    Raises:
        Fb2SourceError: The directory of the target does not exist.
        OSError: The file could not be written.
    """
    real = _target_path(target)
    directory = real.parent
    if not directory.is_dir():
        raise Fb2SourceError(f"cannot write {target}: {directory} is not a directory")
    mode = _target_mode(real)
    tmp_name: str | None = None
    try:
        tmp_name = _make_temp(directory, data)
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, real)
        tmp_name = None
    finally:
        if tmp_name is not None:
            with suppress(OSError):
                os.unlink(tmp_name)


def _make_temp(directory: Path, data: bytes) -> str:
    """Write the data to a new temporary file in the directory.

    The file is created with the ordinary permissions of the current umask,
    not with the `0600` of `tempfile`: a book is not a secret.

    Args:
        directory: The directory of the target file.
        data: The bytes to write.

    Returns:
        The name of the temporary file.
    """
    for attempt in range(_TEMP_ATTEMPTS):
        name = directory / f".fb2kit-{os.getpid()}-{attempt}.tmp"
        try:
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return str(name)
    raise OSError(f"cannot create a temporary file in {directory}")
