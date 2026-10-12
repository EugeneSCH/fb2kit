"""Books as JSONL chunks for RAG: python rag_jsonl.py BOOK [BOOK ...] [-o OUT] [--max-chars N].

One chunk is consecutive blocks of one chapter (key body_idx + section_idx) up to --max-chars
characters. The chunk gets the texts of the footnotes it references and the book card attached.
"""

import argparse
import itertools
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import fb2kit


def chunks(book: fb2kit.FictionBook, max_chars: int) -> Iterator[dict[str, object]]:
    blocks = list(fb2kit.iter_blocks(book))
    notes = {b.node_id: b.text for b in blocks if b.kind == "note"}
    main_text = (b for b in blocks if b.body is None)
    for (_, section_idx), group in itertools.groupby(
        main_text, key=lambda b: (b.body_idx, b.section_idx)
    ):
        group = list(group)
        heading = list(group[0].heading_path)
        # The section heading is already in heading; the body title (no heading_path) stays as text.
        body = [b for b in group if not (b.kind == "title" and b.heading_path)]
        batch: list[fb2kit.TextBlock] = []
        for block in [*body, None]:
            size = sum(len(b.text) for b in batch)
            if batch and (block is None or size + len(block.text) > max_chars):
                refs = dict.fromkeys(r for b in batch for r in b.note_refs)
                yield {
                    "heading": heading,
                    "section_idx": list(section_idx),
                    "ordinal": batch[0].ordinal,
                    "text": "\n\n".join(b.text for b in batch),
                    "notes": [notes[r] for r in refs if r in notes],
                }
                batch = []
            if block is not None:
                batch.append(block)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books", type=Path, nargs="+")
    parser.add_argument("-o", "--output", type=Path, help="JSONL file; stdout by default")
    parser.add_argument("--max-chars", type=int, default=2000)
    args = parser.parse_args()

    out = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    for path in args.books:
        try:
            book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
        except fb2kit.Fb2Error as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            continue
        meta = fb2kit.book_meta(book)
        for i, chunk in enumerate(chunks(book, args.max_chars)):
            record = {"id": f"{path.name}#{i}", "source": str(path), "book": meta, **chunk}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    if args.output:
        out.close()


if __name__ == "__main__":
    main()
