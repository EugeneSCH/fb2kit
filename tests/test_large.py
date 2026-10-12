import base64
import os
from pathlib import Path

import fb2kit
from fb2kit.parser import FB2_NS, XLINK_NS


def _big_book(path: Path, n_bins: int = 40, bin_size: int = 360_000) -> Path:
    payload = base64.encodebytes(os.urandom(bin_size)).decode()
    with path.open("w", encoding="utf-8") as fh:
        fh.write(
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<FictionBook xmlns="{FB2_NS}" xmlns:l="{XLINK_NS}">'
        )
        fh.write(
            "<description><title-info><book-title>Big</book-title>"
            '<coverpage><image l:href="#b0"/></coverpage></title-info></description>'
        )
        fh.write("<body><section><p>" + "x" * 200 + "</p></section></body>")
        for i in range(n_bins):
            fh.write(f'<binary id="b{i}" content-type="image/png">{payload}</binary>')
        fh.write("</FictionBook>")
    return path


def test_parse_does_not_decode_binaries_on_large_book(tmp_path: Path) -> None:
    book = fb2kit.parse(_big_book(tmp_path / "big.fb2"))
    assert len(book.binaries) == 40
    assert book.cover is not None and book.cover.id == "b0"
    assert all(b._cache == {} for b in book.binaries)
    assert len(book.cover.data) == 360_000
    assert sum(1 for b in book.binaries if b._cache) == 1
