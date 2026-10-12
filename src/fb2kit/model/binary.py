"""Attached files, decoded lazily."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field

_NON_B64 = re.compile(r"[^A-Za-z0-9+/]")


def decode_b64(payload: str) -> bytes:
    """Lenient base64: drops whitespace and junk, appends `=`, never raises.

    Args:
        payload: Base64 text from `<binary>`.

    Returns:
        Decoded bytes; `b""` if the data does not decode.
    """
    clean = _NON_B64.sub("", payload)
    if len(clean) % 4 == 1:
        return b""
    try:
        return base64.b64decode(clean + "=" * (-len(clean) % 4))
    except binascii.Error:
        return b""


@dataclass(frozen=True, slots=True)
class Binary:
    """An attached `<binary>` file, usually an image.

    Attributes:
        id: The element's `id`; `Image.href` (`#id`) points to it.
        content_type: MIME type from `content-type` (`application/octet-stream` if absent).
    """

    id: str
    content_type: str
    _b64: str = field(repr=False)
    _cache: dict[str, bytes] = field(default_factory=dict, compare=False, repr=False, init=False)

    @property
    def data(self) -> bytes:
        """Decoded bytes; base64 is decoded on first access, broken data gives `b""`."""
        if "data" not in self._cache:
            self._cache["data"] = decode_b64(self._b64)
        return self._cache["data"]

    @property
    def size(self) -> int:
        """Size of the decoded data in bytes."""
        return len(self.data)
