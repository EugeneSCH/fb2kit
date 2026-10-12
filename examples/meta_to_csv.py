"""Metadata of all books in a folder as CSV: python meta_to_csv.py BOOKS_DIR [-o books.csv]."""

import argparse
import csv
import sys
from pathlib import Path

import fb2kit

PATTERNS = ("*.fb2", "*.fbz", "*.fb2.zip")
FIELDS = ["file", "title", "authors", "genres", "lang", "sequence", "encoding", "warnings", "error"]


def row(path: Path) -> dict[str, str]:
    try:
        book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
    except fb2kit.Fb2Error as exc:
        return {"file": str(path), "error": f"{type(exc).__name__}: {exc}"}
    meta = fb2kit.book_meta(book)
    return {
        "file": str(path),
        "title": str(meta.get("title", "")),
        "authors": "; ".join(meta.get("authors", [])),
        "genres": "; ".join(meta.get("genres", [])),
        "lang": str(meta.get("lang", "")),
        "sequence": "; ".join(meta.get("sequence", [])),
        "encoding": book.report.source_encoding,
        "warnings": str(len(book.report.warnings)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="CSV file; stdout by default")
    args = parser.parse_args()

    paths = sorted({p for pat in PATTERNS for p in args.folder.rglob(pat)})
    out = args.output.open("w", newline="", encoding="utf-8") if args.output else sys.stdout
    writer = csv.DictWriter(out, FIELDS, restval="")
    writer.writeheader()
    for path in paths:
        writer.writerow(row(path))
    if args.output:
        out.close()


if __name__ == "__main__":
    main()
