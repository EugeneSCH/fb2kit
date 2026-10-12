"""XML backend selection: stdlib ElementTree or optional lxml."""

from __future__ import annotations

import importlib.util
from enum import StrEnum
from typing import Any

from fb2kit.errors import Fb2Error


class Backend(StrEnum):
    """XML backend: `AUTO` -- lxml if installed (the `fast` extra), otherwise `STDLIB`."""

    AUTO = "auto"
    STDLIB = "stdlib"
    LXML = "lxml"


def resolve_backend(backend: Backend) -> str:
    has_lxml = importlib.util.find_spec("lxml") is not None
    if backend is Backend.LXML and not has_lxml:
        raise Fb2Error("lxml backend requested but lxml is not installed: pip install fb2kit[fast]")
    if backend is Backend.STDLIB:
        return "stdlib"
    return "lxml" if has_lxml else "stdlib"


def lxml_etree() -> Any:
    """Lazy import keeps the core free of third-party dependencies."""
    import importlib

    return importlib.import_module("lxml.etree")
