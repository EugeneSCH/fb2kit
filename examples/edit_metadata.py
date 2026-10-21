"""Fix the metadata of a book and write the result next to it.

python edit_metadata.py BOOK [--title TITLE] [--lang LANG] [-o OUT]
The result goes to <stem>.edited.fb2 by default; the original file is not touched.
"""

import argparse
from pathlib import Path

import fb2kit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", type=Path)
    parser.add_argument("--title", help="new book title")
    parser.add_argument("--lang", help="new book language, for example ru")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="file to write; <stem>.edited.fb2 by default",
    )
    args = parser.parse_args()

    book = fb2kit.parse(args.book, mode=fb2kit.Mode.TOLERANT)
    changes: dict[str, object] = {}
    if args.title is not None:
        changes["title"] = args.title
    if args.lang is not None:
        changes["lang"] = args.lang
    if not changes:
        parser.error("nothing to change: give --title and/or --lang")

    edited = fb2kit.edit_metadata(book, **changes)
    out = args.output or args.book.with_name(f"{args.book.stem}.edited.fb2")

    report = fb2kit.validate(edited)
    for problem in report.warnings:
        print(f"warning {problem.code}: {problem.message}")

    edited.write(out)

    print(f"written: {out}")
    print(f"  title: {edited.description.title_info.title}")
    print(f"  lang: {edited.description.title_info.lang}")
    print(f"  author: {', '.join(a.full_name for a in edited.description.title_info.authors)}")


if __name__ == "__main__":
    main()
