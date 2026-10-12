# Parsing pipeline

```text
source ──► open_container ──► decode_source ──► parse_tree ──► bind ──► FictionBook
 path,      zip? max_size,     BOM, prolog,      repair (tol.),  model,     + ParseReport
 bytes,     DOCTYPE in bytes   UTF-8, guessing   XML backend,    links,
 file                          (tol.)            heal (tol.),    cover
                                                 namespace
```

Each stage is a separate module, and each adds its own diagnostics to the shared report:

| Stage | Module | What it does | Errors | Diagnostics |
|---|---|---|---|---|
| Source | `source.py` | Reads bytes with a `max_size` limit, unpacks zip, rejects a DTD in the bytes | `Fb2SourceError`, `Fb2UnsafeInputError` | `container.*` |
| Encoding | `source.py` | Bytes → `str` in the order from [Encodings](../how-to/encodings.md) | `Fb2EncodingError` | `encoding.*` |
| Text repair | `repair.py` | Tolerant only: `&` → `&amp;`, removal of forbidden characters (except in CDATA and comments) | — | `xml.bare-amp`, `xml.control-chars` |
| Tree | `parser.py` | XML → `Element` on stdlib or lxml; in tolerant mode, on error: declare the xlink prefix, close truncated tags, lxml `recover`; depth check; namespace normalization | `Fb2ParseError` | `xml.*`, `namespace.*` |
| Model | `model/bind.py` | `Element` → frozen dataclass; unknown → `Raw`; `id` index | `Fb2ParseError` (no description, strict) | `element.*`, `id.duplicate`, `cover.missing`, `notes.body-name` |
| Links | `model/links.py` | Checks that `#id` links lead into the index | — | `link.unresolved` |
| Export | `export.py` | Model → `TextBlock`, `book_meta` | — | — |

## Why two modes

FB2 in the wild is hundreds of thousands of files from a dozen converters: cp1251 without a prolog,
unescaped `&`, truncated tails, `l:href` without a declared prefix. A parser that rejects them is
useless for a collection; a parser that silently repairs them hides from you that the text may have
been distorted.

Hence:

- **strict by default**: nothing unexpected slips through unnoticed; this is the mode for your own files
  and for testing converters;
- **tolerant is enabled explicitly** and repairs only *structure* (escaping, tags, namespace,
  encoding), never rewriting words. Every decision is an entry in `report`, so the result can be
  audited and books with suspicious repairs can be filtered out.

Content defects (an unknown tag, a broken link, no cover) do not prevent reading the book, so in both
modes they are diagnostics rather than exceptions.

## Why an immutable model

After parsing, a book is a value: it can be hashed, compared (`parse(path) == parse(bytes)`),
cached and passed between threads without locks. The `tuple` and `frozen` dataclass types give
`mypy --strict` a complete picture of the tree without `Any`. To change something, use `dataclasses.replace`.

The escape hatch to XML (`FictionBook.element`, `Raw.element`) does not take part in comparison and stays
a mutable ElementTree object: do not modify it if the book is cached somewhere.
