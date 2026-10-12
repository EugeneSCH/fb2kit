"""Mutable context shared by the model binders."""

from __future__ import annotations

from dataclasses import dataclass, field

from fb2kit import report
from fb2kit.report import Diagnostic, Severity


@dataclass(slots=True)
class Builder:
    diagnostics: list[Diagnostic]
    index: dict[str, object]
    _seen: set[tuple[str, str | None, str]] = field(default_factory=set, repr=False)

    def warn(
        self,
        code: str,
        message: str,
        path: str | None = None,
        severity: Severity = Severity.WARNING,
    ) -> None:
        key = (code, path, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self.diagnostics.append(Diagnostic(code, message, severity, path))

    def register(self, node: object) -> None:
        node_id = getattr(node, "id", None)
        if node_id is not None:
            self.register_id(node_id, node)

    def register_id(self, node_id: str, node: object) -> None:
        if node_id in self.index:
            self.warn(report.DUPLICATE_ID, f"duplicate id {node_id!r}")
        else:
            self.index[node_id] = node
