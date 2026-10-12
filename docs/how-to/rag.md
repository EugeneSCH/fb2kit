# RAG export

Two calls: `book_meta(book)` is the book card, `iter_blocks(book)` is the text, block by block, in
document order. Splitting into token-sized chunks is up to the indexer: the library does not know your
tokenizer, and the blocks give exact boundaries at which it is safe to cut.

```python
import fb2kit

book = fb2kit.parse("book.fb2", mode=fb2kit.Mode.TOLERANT)
print(fb2kit.book_meta(book))
# The sample book is Russian, so the values below are Russian:
# {'title': 'Пример книги', 'authors': ['Анна Пример'], 'genres': ['sf', 'adventure'],
#  'lang': 'ru', 'sequence': ['Примеры #1'], 'annotation': 'Небольшая книга для документации fb2kit.'}

for block in fb2kit.iter_blocks(book):
    print(block.ordinal, block.kind, block.section_idx, block.heading_path, block.text[:30])
```

## `TextBlock` fields

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | The text: whitespace collapsed; poem lines, table rows and the paragraphs of a composite block are joined with `\n`; cells with ` | ` |
| `kind` | `str` | The block kind, see below |
| `heading_path` | `tuple[str, ...]` | Titles of enclosing sections, outermost first; for `title`, including its own; for `note`, without its own |
| `section_idx` | `tuple[int, ...]` | Section numbers within the body, 1-based: `(1, 2)` is the second subsection of the first section; `()` is outside sections |
| `depth` | `int` | `len(section_idx)` |
| `section_id` | `str | None` | `id` of the nearest section |
| `node_id` | `str | None` | `id` of the block itself; for `note`, the note's `id`, and for a note without an `id`, a synthetic `notes{body_idx}-{section_idx}` (for example `notes1-2.1`) |
| `ordinal` | `int` | Running block number from 0: the coordinate for a citation |
| `note_refs` | `tuple[str, ...]` | `node_id`s of the `note` blocks this block references |
| `body` | `str | None` | `None` is the main text, otherwise the body name (`"notes"`) |
| `body_idx` | `int` | Index of the body in `book.bodies` |

## Block kinds (`kind`)

| `kind` | Source |
|---|---|
| `paragraph` | `<p>`; text outside `<p>` also becomes a paragraph |
| `subtitle` | `<subtitle>` |
| `title` | `<title>` of a section or body |
| `poem-title` | `<title>` of a poem |
| `epigraph` | the whole `<epigraph>`, including its author |
| `annotation` | `<annotation>` of a section |
| `cite` | the whole `<cite>`, including its author |
| `stanza` | `<stanza>`: lines joined with `\n` |
| `text-author` | `<text-author>` outside an epigraph or cite (for example, on a poem) |
| `date` | `<date>` of a poem |
| `table` | `<table>`: rows joined with `\n`, cells with ` | ` |
| `note` | A note: a leaf section in the notes body or a `<p id>` directly in it |
| `raw` | An unknown element; nested blocks joined with `\n` |

Images and empty blocks are skipped.

## Grouping by chapter

The chapter key is `(body_idx, section_idx)`: it exists even for sections without an `id` and does not
mix two unnamed bodies. Join **consecutive** blocks with the same key. The key is not unique: the blocks
of a section that follow a nested subsection form a separate group with the same key, which is why you
use `itertools.groupby` rather than a `dict`.

## Notes {#notes}

A block with a note marker knows the note through `note_refs`; the notes themselves are `kind="note"`
blocks with the same `node_id`. Collect them into a dict and attach to a chunk the text of the notes it
references: this way the explanation lands in the context next to the place it belongs to. The marker
(`[1]`) stays in the text.

## Example: chunks to JSONL

```python
import itertools
import json

MAX_CHARS = 1500

book = fb2kit.parse("book.fb2", mode=fb2kit.Mode.TOLERANT)
meta = fb2kit.book_meta(book)
blocks = list(fb2kit.iter_blocks(book))
notes = {b.node_id: b.text for b in blocks if b.kind == "note"}

chunks = []
for (body_idx, section_idx), group in itertools.groupby(
    (b for b in blocks if b.body is None),  # main text only
    key=lambda b: (b.body_idx, b.section_idx),
):
    group = list(group)
    heading = " › ".join(group[0].heading_path)
    # the section heading is already in heading; poem titles stay in the text
    parts = [b for b in group if not (b.kind == "title" and b.heading_path)]
    batch: list = []
    for block in parts + [None]:  # None is the signal to "flush the remainder"
        size = sum(len(b.text) for b in batch)
        if batch and (block is None or size + len(block.text) > MAX_CHARS):
            refs = dict.fromkeys(r for b in batch for r in b.note_refs)
            chunks.append(
                {
                    "book": meta.get("title"),
                    "heading": heading,
                    "section_idx": list(section_idx),
                    "ordinal": batch[0].ordinal,  # where to look up the quote
                    "text": "\n\n".join(b.text for b in batch),
                    "notes": [notes[r] for r in refs if r in notes],
                }
            )
            batch = []
        if block is not None:
            batch.append(block)

with open("chunks.jsonl", "w", encoding="utf-8") as fh:
    for chunk in chunks:
        fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(len(chunks), chunks[2]["heading"], chunks[2]["notes"])
# 4 Часть первая › Глава 1 ['1\nТекст первой сноски.']  (Russian sample book: "Part One › Chapter 1", "Text of the first note.")
```

A block longer than `MAX_CHARS` goes into a chunk whole: splitting a paragraph is the tokenizer's job.
A ready-made script with arguments is `examples/rag_jsonl.py`.
