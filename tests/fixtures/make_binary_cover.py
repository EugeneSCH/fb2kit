"""Generate binary-cover.fb2 with real PNG bytes: python tests/fixtures/make_binary_cover.py"""

import base64
import struct
import textwrap
import zlib
from pathlib import Path


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
    )


def _b64(data: bytes) -> str:
    return "\n".join(textwrap.wrap(base64.b64encode(data).decode(), 20))


png = _png()
xml = f"""<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info><book-title>Binaries</book-title><coverpage><image l:href="#cover"/></coverpage></title-info></description>
<body><section><p>Text</p><image l:href="#inline-img"/></section></body>
<binary id="cover" content-type="image/png">{_b64(png)}</binary>
<binary id="inline-img" content-type="image/png">{_b64(png)}</binary>
<binary id="unused" content-type="image/png">{_b64(png)}</binary>
</FictionBook>
"""
Path(__file__).with_name("binary-cover.fb2").write_text(xml, encoding="utf-8")
