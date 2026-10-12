"""Regenerate the encoding fixtures from encodings-source.txt: python tests/fixtures/make_encodings.py"""

from pathlib import Path

HERE = Path(__file__).parent
title, prose = (HERE / "encodings-source.txt").read_text(encoding="utf-8").splitlines()[:2]
NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
BOOK = (
    f'<FictionBook xmlns="{NS}"><description><title-info><book-title>{title}</book-title>'
    f"</title-info></description><body><section><p>{prose}</p></section></body></FictionBook>\n"
)


def prolog(enc: str) -> str:
    return f'<?xml version="1.0" encoding="{enc}"?>'


FILES = {
    "utf8-bom": ("﻿" + prolog("utf-8") + BOOK).encode("utf-8"),
    "cp1251-no-prolog": BOOK.encode("cp1251"),
    "koi8r-no-prolog": BOOK.encode("koi8-r"),
    "koi8r-prolog": (prolog("koi8-r") + BOOK).encode("koi8-r"),
    "wrong-prolog-cp1251": (prolog("utf-8") + BOOK).encode("cp1251"),
}

if __name__ == "__main__":
    for name, data in FILES.items():
        (HERE / f"{name}.fb2").write_bytes(data)
