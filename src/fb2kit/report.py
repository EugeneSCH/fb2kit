"""Diagnostics and the parse report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class Severity(StrEnum):
    """Severity: `INFO` -- a decision made, `WARNING` -- something was repaired or lost."""

    INFO = "info"
    WARNING = "warning"


class Mode(StrEnum):
    """Parse mode: `STRICT` raises on broken input, `TOLERANT` repairs and reports."""

    STRICT = "strict"
    TOLERANT = "tolerant"


ENC_GUESSED: Final = "encoding.guessed"
ENC_FALLBACK: Final = "encoding.fallback"
ENC_DECLARED_MISMATCH: Final = "encoding.declared-mismatch"
CONTAINER_FBZ: Final = "container.fbz"
CONTAINER_ENTRY_SNIFFED: Final = "container.entry-sniffed"
NS_MISSING: Final = "namespace.missing"
NS_FOREIGN: Final = "namespace.foreign"
NS_PREFIX_INJECTED: Final = "namespace.prefix-injected"
XML_BARE_AMP: Final = "xml.bare-amp"
XML_CONTROL_CHARS: Final = "xml.control-chars"
XML_AUTO_CLOSED: Final = "xml.auto-closed"
XML_LXML_RECOVER: Final = "xml.lxml-recover"
ELEMENT_UNKNOWN: Final = "element.unknown"
ELEMENT_MISSING: Final = "element.missing"
DUPLICATE_ID: Final = "id.duplicate"
LINK_UNRESOLVED: Final = "link.unresolved"
COVER_MISSING: Final = "cover.missing"
NOTES_BODY_NAME: Final = "notes.body-name"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single parse remark.

    Attributes:
        code: Machine code, for example `xml.bare-amp`; the full list is in the
            "Strict and tolerant" guide.
        message: Human-readable explanation (in English).
        severity: Severity.
        path: Location in the document, if known.
    """

    code: str
    message: str
    severity: Severity = Severity.WARNING
    path: str | None = None


@dataclass(frozen=True, slots=True)
class ParseReport:
    """What the parser learned about and did with the input.

    Attributes:
        diagnostics: All remarks in order: source, encoding, XML repair, model.
        source_encoding: Encoding the input was decoded with (canonical Python name,
            for example `utf-8`, `cp1251`, `koi8-r`).
        declared_encoding: Encoding from the `<?xml encoding=...?>` prolog as written, or `None`.
        container: `"fbz"` if the book was unpacked from a zip, otherwise `None`.
        backend: The backend actually used: `"stdlib"` or `"lxml"`; not used when comparing
            reports.
    """

    diagnostics: tuple[Diagnostic, ...] = ()
    source_encoding: str = "utf-8"
    declared_encoding: str | None = None
    container: str | None = None
    backend: str = field(default="stdlib", compare=False)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        """Diagnostics with `Severity.WARNING`."""
        return tuple(d for d in self.diagnostics if d.severity is Severity.WARNING)
