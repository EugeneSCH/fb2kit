"""A book as plain text: python to_text.py BOOK [-o book.txt] [--no-notes]."""

import argparse
import sys
from pathlib import Path

import fb2kit


def to_text(book: fb2kit.FictionBook, notes: bool = True) -> str:
    blocks = [b for b in fb2kit.iter_blocks(book) if notes or b.body is None]
    return "\n\n".join(b.text for b in blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="TXT file; stdout by default")
    parser.add_argument("--no-notes", action="store_true", help="skip the notes body")
    args = parser.parse_args()

    book = fb2kit.parse(args.book, mode=fb2kit.Mode.TOLERANT)
    text = to_text(book, notes=not args.no_notes)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
