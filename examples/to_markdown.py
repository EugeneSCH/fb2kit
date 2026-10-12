"""A book as Markdown: python to_markdown.py BOOK [-o book.md].

Sections become headings by depth, footnotes become `[^id]` with definitions at the end,
verses are lines with line breaks, tables are Markdown tables, images are links `images/<id>`
(they can be exported with the extract_images.py script).
"""

import argparse
import sys
from pathlib import Path

import fb2kit
from fb2kit import (
    Annotation,
    Cite,
    Epigraph,
    Image,
    Link,
    Paragraph,
    Poem,
    Raw,
    Section,
    Style,
    Subtitle,
    Table,
    Text,
    TextAuthor,
    Title,
)

MARKS = {"emphasis": "*", "strong": "**", "strikethrough": "~~", "code": "`"}


def inline(nodes) -> str:
    out = []
    for n in nodes:
        if isinstance(n, Text):
            out.append(n.value)
        elif isinstance(n, Style):
            mark = MARKS.get(n.kind, "")
            out.append(f"{mark}{inline(n.children)}{mark}")
        elif isinstance(n, Link) and n.is_note and n.href.startswith("#"):
            out.append(f"[^{n.href[1:]}]")
        elif isinstance(n, Link) and not n.href.startswith("#"):
            out.append(f"[{inline(n.children)}]({n.href})")
        elif isinstance(n, Link):
            out.append(inline(n.children))
        elif isinstance(n, Image):
            out.append(image(n))
        elif isinstance(n, Raw):
            out.append(n.text or "")
    return " ".join("".join(out).split())  # collapse newlines and indentation from the XML


def image(img: Image) -> str:
    href = img.href or ""
    return f"![{img.alt or ''}](images/{href.lstrip('#')})" if href.startswith("#") else ""


def title_text(title: Title | None) -> str:
    if title is None:
        return ""
    return " ".join(inline(p.children) for p in title.children if isinstance(p, Paragraph))


def blocks(children, depth: int) -> list[str]:
    out: list[str] = []
    for c in children:
        if isinstance(c, Section):
            out += [f"{'#' * min(depth + 1, 6)} {title_text(c.title)}".rstrip()]
            out += blocks((x for x in c.children if not isinstance(x, Title)), depth + 1)
        elif isinstance(c, Title):
            out.append(f"{'#' * depth} {title_text(c)}")
        elif isinstance(c, Paragraph | TextAuthor):
            out.append(inline(c.children))
        elif isinstance(c, Subtitle):
            out.append(f"**{inline(c.children)}**")
        elif isinstance(c, Epigraph | Cite | Annotation):
            quoted = "\n\n".join(blocks(c.children, depth)).split("\n")
            out.append("\n".join(f"> {line}".rstrip() for line in quoted))
        elif isinstance(c, Poem):
            if c.title:
                out.append(f"**{title_text(c.title)}**")
            for st in c.stanzas:
                out.append("  \n".join(inline(v.children) for v in st.verses))
        elif isinstance(c, Table):
            rows = [[inline(cell.children) for cell in r.cells] for r in c.rows]
            width = max(map(len, rows), default=0)
            rows = [r + [""] * (width - len(r)) for r in rows]
            if rows:
                out.append(
                    "\n".join(
                        ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
                        + ["| " + " | ".join(r) + " |" for r in rows[1:]]
                    )
                )
        elif isinstance(c, Image):
            out.append(image(c))
        elif isinstance(c, Raw) and c.text:
            out.append(c.text.strip())
    return [x for x in out if x.strip()]


def to_markdown(book: fb2kit.FictionBook) -> str:
    parts: list[str] = []
    if not any(isinstance(c, Title) for b in book.bodies[:1] for c in b.children):
        parts.append(f"# {book.description.title_info.title or ''}")
    for body in book.bodies:
        if not body.is_notes:
            parts += blocks(body.children, 1)
    for body in book.bodies:
        if body.is_notes:
            for note in body.sections:
                text = " ".join(blocks((x for x in note.children if not isinstance(x, Title)), 1))
                if note.id:
                    parts.append(f"[^{note.id}]: {text}")
    return "\n\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="MD file; stdout by default")
    args = parser.parse_args()

    md = to_markdown(fb2kit.parse(args.book, mode=fb2kit.Mode.TOLERANT))
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
