# Installation and quickstart

## Installation

```bash
uv add fb2kit            # or: pip install fb2kit
uv add 'fb2kit[fast]'    # with lxml: faster on large books and repairs more XML breakage
```

Without the `fast` extra, `xml.etree.ElementTree` from the standard library is used. The result is the
same except for one repair (see [Strict and tolerant](../how-to/modes.md#backends)).

## Open a book

`parse` accepts a path, `bytes` or a binary file object; a `.fbz`/`.fb2.zip` archive is recognized
automatically. The default mode is strict: a broken file raises an exception.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
info = book.description.title_info
print(info.title)  # Пример книги ("Sample Book"; the fixture book is Russian)
print([a.full_name for a in info.authors])  # ['Анна Пример']
print(info.genres, info.lang)  # ('sf', 'adventure') ru
```

## Walk the chapters

Sections are chapters and parts. `iter_sections()` walks them depth-first in document order.

```python
from fb2kit import Paragraph

for section in book.iter_sections():
    paragraphs = [b for b in section.blocks if isinstance(b, Paragraph)]
    print(section.id, len(paragraphs))  # part1 0 / ch1 2 / ch2 1
```

## Get the text

The shortest path to the text is `iter_blocks`: it yields ready-made strings, block by block.

```python
for block in fb2kit.iter_blocks(book):
    print(f"[{block.kind}] {block.text}")
```

## Open a broken book

Tolerant mode repairs what it can and records what it did:

```python
book = fb2kit.parse("messy.fb2", mode=fb2kit.Mode.TOLERANT)
for d in book.report.diagnostics:
    print(d.severity, d.code, d.message)  # warning xml.bare-amp escaped 1 bare ampersand(s)
```

## Cover

```python
book = fb2kit.parse("book.fb2")
if book.cover is not None:
    with open("cover.png", "wb") as fh:
        fh.write(book.cover.data)  # base64 is decoded only now
```

Next: [metadata](../how-to/metadata.md), [structure](../how-to/structure.md),
[modes and diagnostics](../how-to/modes.md).
