# fb2kit

![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![license MIT](https://img.shields.io/badge/license-MIT-green)
![mypy strict](https://img.shields.io/badge/mypy-strict-blue)

A FictionBook 2 (FB2 2.0–2.2) parser and writer for Python 3.11+. It returns a book as an
immutable, typed tree: metadata, sections, poems, tables, notes, images. Strict mode is the default;
tolerant mode handles broken files from real-world collections and reports every repair. The book
can be written back, and a new one can be created from scratch. No required dependencies.

## Installation

```bash
uv add fb2kit              # or: pip install fb2kit
uv add 'fb2kit[fast]'      # + lxml: faster and repairs more XML breakage
```

## Quickstart

```python
import fb2kit

book = fb2kit.parse("book.fb2")  # path, bytes, file object, .fbz/.fb2.zip
info = book.description.title_info
print(info.title, [a.full_name for a in info.authors])

for block in fb2kit.iter_blocks(book):  # text block by block, in order
    print(block.kind, block.heading_path, block.text)

book.write("out.fb2")  # write it back: UTF-8, compact, deterministic

messy = fb2kit.parse("messy.fb2", mode=fb2kit.Mode.TOLERANT)
print([d.code for d in messy.report.diagnostics])  # ['xml.bare-amp']
```

## Features

- **Strict and tolerant.** Strict raises `Fb2ParseError`/`Fb2EncodingError` on broken input.
  Tolerant repairs `&`, control characters, unclosed tags, undeclared prefixes and the encoding,
  never changing the words; every decision is a `Diagnostic` with a code in `book.report`.
- **Encodings.** `encoding=`, BOM, prolog, UTF-8; in tolerant mode, cp1251/koi8-r/cp866 and
  others are guessed from letter frequencies. The result is in `report.source_encoding`.
- **Sources.** A path, `bytes`, a binary file object, `.fbz`/`.fb2.zip` (detected by signature),
  an XML string via `parse_string`; a `max_size` limit (256 MiB) in `parse` and `parse_string`, including for unpacking.
- **Writing.** `book.to_xml()`, `book.to_bytes()` and `book.write(path)` give back the file;
  a `.fbz` suffix writes a zip archive. `new_book()` creates a book from scratch, `edit_metadata()`
  and `replace_node()` change one, and `validate()` checks a book before it is written.
- **Security.** `<!DOCTYPE>`/`<!ENTITY>` are rejected in both modes (XXE, billion laughs),
  zip bombs and nesting depth are bounded, and parsing touches neither the network nor files.
- **RAG export.** `iter_blocks` yields text blocks with a heading path, a chapter key
  `(body_idx, section_idx)` and note references `note_refs`; `book_meta` is the book card.
- **Types.** All nodes are `frozen` dataclasses; `mypy --strict`; unknown elements are kept as
  `Raw` rather than dropped.

## Documentation

`docs/` (MkDocs): `uv run mkdocs serve`. Ready-made scripts are in [`examples/`](examples/): folder
metadata to CSV, a book to Markdown and to plain text, images, JSONL for RAG, a book folder check,
a book from scratch, metadata editing.

## License

MIT, see [LICENSE](LICENSE).
