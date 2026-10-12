"""Open FB2 sources: paths, bytes, file objects and fbz containers."""

from __future__ import annotations

import codecs
import math
import os
import re
import zipfile
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import IO, Final

from fb2kit.errors import Fb2EncodingError, Fb2SourceError, Fb2UnsafeInputError
from fb2kit.report import (
    CONTAINER_ENTRY_SNIFFED,
    CONTAINER_FBZ,
    ENC_DECLARED_MISMATCH,
    ENC_FALLBACK,
    ENC_GUESSED,
    Diagnostic,
    Mode,
    Severity,
)

SourceLike = str | os.PathLike[str] | bytes | bytearray | IO[bytes]

DEFAULT_MAX_SIZE: Final = 256 * 1024 * 1024
_SNIFF_BYTES: Final = 4096
_MAX_SNIFFED_ENTRIES: Final = 1000
_ZIP_MAGIC: Final = (b"PK\x03\x04", b"PK\x05\x06")  # entry header, empty archive
_FB_MARKERS: Final = (
    b"<FictionBook",
    "<FictionBook".encode("utf-16-le"),
    "<FictionBook".encode("utf-16-be"),
)


_UNSAFE_BYTES: Final = re.compile(rb"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_UNSAFE_TEXT: Final = re.compile(r"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)


def check_safe_input(raw: bytes | str) -> None:
    """Reject DTD/entity declarations anywhere in the input (comments and CDATA included)."""
    found = _UNSAFE_BYTES.search(raw) if isinstance(raw, bytes) else _UNSAFE_TEXT.search(raw)
    if found:
        raise Fb2UnsafeInputError("refusing to parse input containing a DTD/entity declaration")


@dataclass(frozen=True, slots=True)
class OpenedSource:
    raw: bytes
    container: str | None
    path: str | None
    diagnostics: tuple[Diagnostic, ...]


def too_big(max_size: int) -> Fb2SourceError:
    return Fb2SourceError(f"input exceeds max_size={max_size}")


def _limit(head: bytes, max_size: int) -> int:
    # The packed archive is bounded by the default cap; max_size bounds the unpacked entry.
    return DEFAULT_MAX_SIZE if head.startswith(_ZIP_MAGIC) else max_size


def read_bytes(source: SourceLike, *, max_size: int = DEFAULT_MAX_SIZE) -> tuple[bytes, str | None]:
    """Return the raw bytes of a source and its file name, if it has one."""
    if isinstance(source, bytes | bytearray):
        data, name = bytes(source), None
        if len(data) > _limit(data, max_size):
            raise too_big(max_size)
    elif isinstance(source, str | os.PathLike):
        path = Path(source)
        name = path.name
        try:
            with path.open("rb") as fh:
                data = fh.read(4)
                limit = _limit(data, max_size)
                data += fh.read(limit + 1 - len(data))
        except OSError as exc:
            raise Fb2SourceError(f"cannot read {path}: {exc}") from exc
        if len(data) > limit:
            raise too_big(max_size)
    elif hasattr(source, "read"):
        name = None
        data = source.read(4)
        if isinstance(data, str):
            raise Fb2SourceError("expected a binary file object")
        limit = _limit(data, max_size)
        data += source.read(limit + 1 - len(data))
        if len(data) > limit:
            raise too_big(max_size)
    else:
        raise TypeError(f"unsupported source type: {type(source).__name__}")
    if not data:
        raise Fb2SourceError("empty input")
    return data, name


def pick_entry(zf: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, bool]:
    """Return the entry holding the book and whether it was found by sniffing."""
    files = [i for i in zf.infolist() if not i.is_dir()]
    for info in files:
        if info.filename.lower().endswith(".fb2"):
            return info, False
    for info in files[:_MAX_SNIFFED_ENTRIES]:
        with zf.open(info) as fh:
            head = fh.read(_SNIFF_BYTES)
        if any(marker in head for marker in _FB_MARKERS):
            return info, True
    names = [i.filename for i in files]
    if "mimetype" in names:
        hint = "looks like EPUB, "
    elif "[Content_Types].xml" in names:
        hint = "looks like DOCX/OOXML, "
    else:
        hint = ""
    limit = (
        f" in first {_MAX_SNIFFED_ENTRIES} inspected" if len(files) > _MAX_SNIFFED_ENTRIES else ""
    )
    raise Fb2SourceError(f"archive {hint}has no FictionBook entry{limit}: {', '.join(names[:5])}")


def open_container(source: SourceLike, *, max_size: int = DEFAULT_MAX_SIZE) -> OpenedSource:
    data, name = read_bytes(source, max_size=max_size)
    if not data.startswith(_ZIP_MAGIC):
        check_safe_input(data)
        return OpenedSource(data, None, name, ())
    label = name or "<memory>"
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            info, sniffed = pick_entry(zf)
            with zf.open(info) as fh:
                raw = fh.read(max_size + 1)
    except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError, ValueError, OSError) as exc:
        raise Fb2SourceError(f"cannot read archive {label}: {exc}") from exc
    if len(raw) > max_size:
        raise too_big(max_size)
    check_safe_input(raw)
    diagnostics = [Diagnostic(CONTAINER_FBZ, f"unpacked {info.filename}", Severity.INFO)]
    if sniffed:
        diagnostics.append(
            Diagnostic(
                CONTAINER_ENTRY_SNIFFED,
                f"FictionBook found in entry {info.filename}",
                Severity.INFO,
            )
        )
    return OpenedSource(raw, "fbz", name, tuple(diagnostics))


# --- Encoding detection ---------------------------------------------------------------------

# Russian letter frequencies, % (NKRYa), case-insensitive; alphabet order
# U+0430..U+044F, then U+0451 (yo).
_RU_FREQ_VALUES: Final = (
    8.01,
    1.59,
    4.54,
    1.70,
    2.98,
    8.45,
    0.94,
    1.65,
    7.35,
    1.21,
    3.49,
    4.40,
    3.21,
    6.70,
    10.97,
    2.81,
    4.73,
    5.47,
    6.26,
    2.62,
    0.26,
    0.97,
    0.48,
    1.44,
    0.73,
    0.36,
    0.04,
    1.90,
    1.74,
    0.32,
    0.64,
    2.01,
    0.04,
)
_RU_LETTERS: Final = [chr(c) for c in range(0x430, 0x450)] + ["\u0451"]
_RU_FREQ: Final = dict(zip(_RU_LETTERS, _RU_FREQ_VALUES, strict=True))
# Log-frequency against uniform (1/33): losing letters to punctuation costs score.
_LOG_FREQ: Final = {c: math.log(p / 100 * 33) for c, p in _RU_FREQ.items()}
_RARE: Final = math.log(0.0005 * 33)  # Cyrillic outside the Russian alphabet
_CANDIDATES: Final = ("cp1251", "koi8-r", "cp866", "iso8859-5", "mac-cyrillic")
_PREFIX: Final = 64 * 1024
# Guillemets, dashes, ellipsis, numero, nbsp, quotes, degree.
_TYPOGRAPHY: Final = frozenset(
    "\u00ab\u00bb\u2014\u2013\u2026\u2116 \u201e\u201c\u201d\u2018\u2019\u00b0"
)
_MIN_LETTERS: Final = 16  # fewer Cyrillic letters means no signal
_MIN_MARGIN: Final = 0.3  # lead over the runner-up, per letter
_SAME_TEXT: Final = 0.02  # a candidate differing in <=2% of chars is not a rival


def _is_cyrillic(ch: str) -> bool:
    return "\u0400" <= ch <= "\u04ff"


def _score(text: str) -> tuple[float, int]:
    score, letters_seen = 0.0, 0
    for ch in text:
        if ord(ch) > 127 and not _is_cyrillic(ch) and ch not in _TYPOGRAPHY:
            score -= 30
    for word in text.split():
        letters = [c for c in word if c.isalpha()]
        cyr = [c for c in letters if _is_cyrillic(c)]
        if not cyr:
            continue
        letters_seen += len(cyr)
        score += sum(_LOG_FREQ.get(c.lower(), _RARE) for c in cyr)
        tail = "".join(cyr[1:])
        if (len(cyr) > 2 and not (tail.islower() or tail.isupper())) or (
            tail.isupper() and cyr[0].islower()
        ):
            score -= 8  # mixed case inside a word
        if len(cyr) < len(letters):
            score -= 8  # Cyrillic and Latin in one word
    return score, letters_seen


def guess_cyrillic(raw: bytes) -> str | None:
    """Guess a single-byte Cyrillic encoding by letter frequencies; None if the signal is weak."""
    head = raw[:_PREFIX]
    scored: list[tuple[float, int, str, str]] = []
    for enc in _CANDIDATES:
        try:
            text = head.decode(enc)
        except UnicodeDecodeError:
            continue
        scored.append((*_score(text), text, enc))
    if not scored:
        return None
    # sort is stable: on a tie the earlier candidate wins.
    scored.sort(key=lambda item: item[0], reverse=True)
    best, letters_seen, best_text, enc = scored[0]
    if letters_seen < _MIN_LETTERS:
        return None
    for score, _, text, _ in scored[1:]:
        # Single-byte encodings give equal-length strings, so compare char by char.
        if sum(a != b for a, b in zip(text, best_text, strict=True)) <= _SAME_TEXT * letters_seen:
            continue
        if best - score < _MIN_MARGIN * letters_seen:
            return None
        break
    return enc


@dataclass(frozen=True, slots=True)
class DecodedSource:
    text: str
    encoding: str
    declared_encoding: str | None
    diagnostics: tuple[Diagnostic, ...]


_PROLOG: Final = re.compile(r"<\?xml[^>]*?encoding\s*=\s*([\"'])(.*?)\1", re.IGNORECASE)
_SIGNATURES: Final = (  # XML 1.0 Appendix F.1; longer signatures first
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"<\x00\x00\x00", "utf-32-le"),
    (b"\x00\x00\x00<", "utf-32-be"),
    (b"<\x00?\x00", "utf-16-le"),
    (b"\x00<\x00?", "utf-16-be"),
)


def _canon(name: str) -> str | None:
    try:
        info = codecs.lookup(name)
    except (LookupError, ValueError):
        return None
    try:  # bytes-to-bytes codecs (rot13, hex, base64...) are not text encodings
        ok = isinstance(info.decode(b"<")[0], str)
    except Exception:
        ok = False
    return info.name.replace("_", "-") if ok else None


def _prolog_encoding(raw: bytes, text: str | None = None) -> str | None:
    found = _PROLOG.search(raw[:400].decode("latin-1"))
    if not found and text is not None:
        found = _PROLOG.search(text[:400])
    return found.group(2) if found else None


def _plausible(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("<") and "\x00" not in stripped[:200]


def _decode(raw: bytes, enc: str) -> str | None:
    try:
        return raw.decode(enc).removeprefix("\ufeff")
    except (UnicodeError, LookupError):
        return None


def _contradicts(declared: str | None, enc: str) -> bool:
    if declared is None:
        return False
    canon = _canon(declared)
    # "utf-16"/"utf-32" in the prolog agree with the signature-detected LE/BE variant.
    return canon is None or not (canon == enc or enc.startswith(canon + "-"))


def _finish(
    raw: bytes, text: str | None, enc: str, declared: str | None, diagnostics: list[Diagnostic]
) -> DecodedSource:
    if text is None or not _plausible(text):
        raise Fb2EncodingError(f"input does not look like XML text in {enc}")
    return DecodedSource(text, enc, declared, tuple(diagnostics))


def _mismatch(declared: str, enc: str, severity: Severity = Severity.INFO) -> Diagnostic:
    msg = f"declared encoding {declared!r} does not match {enc}"
    return Diagnostic(ENC_DECLARED_MISMATCH, msg, severity)


def decode_source(raw: bytes, *, encoding: str | None = None, mode: Mode) -> DecodedSource:
    """Decode bytes: explicit encoding, signature, prolog, UTF-8, then (tolerant) a guess."""
    if encoding is not None:
        enc = _canon(encoding)
        if enc is None:
            raise Fb2EncodingError(f"unknown encoding: {encoding}")
        text = _decode(raw, enc)
        declared = _prolog_encoding(raw, text)
        diagnostics = [_mismatch(declared, enc)] if declared and _contradicts(declared, enc) else []
        return _finish(raw, text, enc, declared, diagnostics)

    for signature, enc in _SIGNATURES:
        if raw.startswith(signature):
            text = _decode(raw, enc)
            declared = _prolog_encoding(raw, text)
            diagnostics = (
                [_mismatch(declared, enc)] if declared and _contradicts(declared, enc) else []
            )
            return _finish(raw, text, enc, declared, diagnostics)

    declared = _prolog_encoding(raw)
    diagnostics = []
    if declared is not None:
        enc = _canon(declared)
        text = _decode(raw, enc) if enc else None
        if enc and text is not None:
            return _finish(raw, text, enc, declared, [])
        if mode is Mode.STRICT:
            raise Fb2EncodingError(f"cannot decode input as declared encoding {declared!r}")
    text = _decode(raw, "utf-8")
    if text is not None:  # with a declaration, it failed but the bytes are valid UTF-8
        mismatch = [_mismatch(declared, "utf-8")] if declared else []
        return _finish(raw, text, "utf-8", declared, mismatch)
    if mode is Mode.STRICT:
        raise Fb2EncodingError("input is not valid UTF-8 and declares no other encoding")
    guessed = guess_cyrillic(raw)
    enc = guessed or "cp1251"
    if declared is not None:
        diagnostics = [_mismatch(declared, enc, Severity.WARNING)]
    elif guessed:
        diagnostics = [Diagnostic(ENC_GUESSED, f"encoding guessed as {enc}", Severity.WARNING)]
    else:
        diagnostics = [Diagnostic(ENC_FALLBACK, f"weak signal, assuming {enc}", Severity.WARNING)]
    text = _decode(raw, enc)
    if text is None:  # weak guess hit an undefined byte: still give tolerant mode a text
        text = raw.decode(enc, errors="replace").removeprefix("\ufeff")
    return _finish(raw, text, enc, declared, diagnostics)
