# Sources and archives

## What `parse` accepts

| `source` | Example | Note |
|---|---|---|
| `str` or `os.PathLike` | `"book.fb2"`, `Path("book.fbz")` | A string is **always a path**, not XML |
| `bytes` / `bytearray` | `path.read_bytes()` | |
| Binary file object | `open(..., "rb")`, `BytesIO` | A text one (`"r"`) raises `Fb2SourceError` |
| XML string | — | Only via `parse_string` |

```python
from pathlib import Path

import fb2kit

a = fb2kit.parse("book.fb2")
b = fb2kit.parse(Path("book.fb2").read_bytes())
with open("book.fb2", "rb") as fh:
    c = fb2kit.parse(fh)
d = fb2kit.parse_string(Path("book.fb2").read_text(encoding="utf-8"))
assert a == b == c  # books are compared by content
```

## `.fbz` and `.fb2.zip` archives

A zip is recognized by the `PK` signature; the extension does not matter. The first `*.fb2` file is taken
from the archive; if there is none, the first of the first 1000 files that starts with `<FictionBook`
(`container.entry-sniffed`). Other books in the archive are ignored.

```python
book = fb2kit.parse("book.fbz")
print(book.report.container)  # fbz
print([d.message for d in book.report.diagnostics])  # ['unpacked book.fb2']
```

An archive without a book raises `Fb2SourceError` with a hint: `looks like EPUB` or `looks like DOCX/OOXML`
if the format is recognized.

## `max_size`

`max_size` (bytes, 256 MiB by default) limits the input and, for an archive, the unpacked book: at most
`max_size + 1` bytes are read from the archive, so a zip bomb does not inflate memory. The archive itself
is limited to 256 MiB regardless of `max_size`. `parse_string` also accepts `max_size` (the text size in
UTF-8 bytes).

```python
try:
    fb2kit.parse("book.fb2", max_size=1024)
except fb2kit.Fb2SourceError as exc:
    print(exc)  # input exceeds max_size=1024
```

The whole book is read into memory: there is no streaming parse.

## Source errors

| Situation | Exception |
|---|---|
| No file, no permissions | `Fb2SourceError("cannot read …")` |
| Empty input | `Fb2SourceError("empty input")` |
| Larger than `max_size` | `Fb2SourceError("input exceeds max_size=…")` |
| Broken zip, no book in the archive | `Fb2SourceError` |
| File object in text mode | `Fb2SourceError("expected a binary file object")` |
| `int`, `list` and the like | `TypeError` |
