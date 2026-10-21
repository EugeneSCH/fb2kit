"""Create a book from scratch and write it: python make_book.py [-o book.fb2] [--fbz].

The book has an author, a chapter with a paragraph, a footnote and a cover image (a small
placeholder PNG, so the script needs no files and no network).
"""

import argparse
import base64
import sys
from pathlib import Path

import fb2kit
from fb2kit import Author, Link, Style, Text

# A 1x1 transparent PNG: enough to have a real attachment in the book.
COVER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def build() -> fb2kit.FictionBook:
    """The book the script writes.

    Returns:
        The new book.
    """
    builder = fb2kit.new_book(
        title="Новая книга",
        lang="ru",
        authors=(Author(first_name="Анна", last_name="Пример"),),
    ).add_genre("sf")

    cover = builder.add_binary(COVER_PNG, "image/png")
    builder.set_cover(cover)

    chapter = builder.add_section("Глава 1")
    note_id = builder.add_note("Текст сноски", title="1")
    chapter.add_paragraph("Текст ", Style("emphasis", (Text("курсивом"),)))
    chapter.add_paragraph("Сноска", Link(f"#{note_id}", "note", (Text("1"),)))
    chapter.add_image(cover, alt="Обложка")
    return builder.build()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("book.fb2"),
        help="FB2 file to write",
    )
    parser.add_argument(
        "--fbz",
        action="store_true",
        help="write a zip archive with the book inside instead of a plain file",
    )
    parser.add_argument("--pretty", action="store_true", help="indent the file")
    args = parser.parse_args()

    book = build()
    report = fb2kit.validate(book)
    for problem in report.warnings:
        print(f"warning {problem.code}: {problem.message}", file=sys.stderr)

    if args.fbz and args.output.suffix.lower() not in (".fbz", ".fb2.zip", ".zip"):
        args.output = args.output.with_suffix(".fbz")
    book.write(args.output, pretty=args.pretty)

    print(f"written: {args.output}")
    print(f"  title: {book.description.title_info.title}")
    print(f"  author: {book.description.title_info.authors[0].full_name}")
    print(f"  chapters: {len(book.bodies[0].sections)}")
    print(f"  cover: {book.cover.id if book.cover else 'none'}")


if __name__ == "__main__":
    main()
