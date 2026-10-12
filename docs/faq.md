# FAQ

## `parse("<FictionBook ...>")` says "cannot read". Why?

A string passed to `parse` is always a file path. Use `parse_string` for XML in a string and
`parse(data)` for bytes.

## A cp1251 book fails to open: `Fb2EncodingError`

In strict mode the encoding is not guessed when there is no prolog. Pass `encoding="cp1251"` or enable
`mode=Mode.TOLERANT`; the report then contains `encoding.guessed` with the chosen encoding.

## How can I tell whether a book was "repaired"?

An empty `book.report.diagnostics` means the book was parsed as is. The `xml.*`, `encoding.guessed` and
`encoding.fallback` codes mean the text may differ from what the file's author intended. The
`examples/check_folder.py` script builds such a report for a folder.

## How do I get the text of a note?

In the model, use `book.resolve(link)` for a `Link` with `is_note`. In the export, use `TextBlock.note_refs`
and the `kind="note"` blocks with the same `node_id` ([RAG export](how-to/rag.md#notes)).

## Where are `Paragraph`, `Section` and the other types?

Right in `fb2kit`: `from fb2kit import Paragraph, Section`. These are the same classes as in `fb2kit.model`;
they are defined there, and `fb2kit` re-exports them together with `__all__`.

## Do I need lxml?

No. `fb2kit[fast]` installs lxml: it is faster on large books and, in tolerant mode, repairs mismatched
tags. The model is the same on both backends.

## Can I modify a book and save it?

The model is immutable and there is no FB2 writer yet. `dataclasses.replace` gives you a modified
copy, but you have to write the serialization yourself.
