# Writing a book

fb2kit writes FB2: it serializes a book back to XML, creates a new one from scratch and edits an
existing one. Everything here works on the immutable model, so a write never touches the book you
parsed.

## Write a parsed book

`write()` takes a path and writes the file. The write is atomic: the bytes go to a temporary file
in the target directory and then replace the target, so a failed write leaves the old file intact.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
book.write("out.fb2")
```

The output is UTF-8, compact (one line, no line breaks between the elements) and deterministic: the
same model always gives the same bytes. `to_bytes()` and `to_xml()` give the same content without
touching the disk.

```python
data = book.to_bytes()  # bytes with an XML declaration
text = book.to_xml()  # the same text without the declaration
print(len(data), text[:40])
```

## Create a book from scratch

`new_book()` returns a `BookBuilder`. It is mutable, and `build()` gives a frozen book.

```python
import fb2kit
from fb2kit import Author, Link, Style, Text

builder = fb2kit.new_book(
    title="Новая книга",
    lang="ru",
    authors=(Author(first_name="Анна", last_name="Пример"),),
).add_genre("sf")

chapter = builder.add_section("Глава 1")
note_id = builder.add_note("Текст сноски", title="1")
chapter.add_paragraph("Текст ", Style("emphasis", (Text("курсивом"),)))
chapter.add_paragraph("Сноска", Link(f"#{note_id}", "note", (Text("1"),)))

built = builder.build()
built.write("new.fb2")
```

The builder fills the metadata (`add_author`, `add_genre`, `set_keywords`, `set_sequence`,
`set_annotation`) and the text (`add_section` → `add_paragraph`, `add_subtitle`, `add_empty_line`,
`add_poem`, `add_image`, and a nested `add_section` for a subsection). `add_note` puts a footnote
into the notes body and returns its `id`, which is what the link in the text points to.

## Attach a cover

`add_binary` takes the bytes of a file and returns a `Binary`; `set_cover` makes it the cover of
the book, and the `<coverpage>` is written with it.

```python
import fb2kit

builder = fb2kit.new_book(title="Книга с обложкой")
cover = builder.add_binary(b"\x89PNG\r\n\x1a\n", "image/png")
builder.set_cover(cover)
chapter = builder.add_section("Глава 1")
chapter.add_image(cover, alt="Обложка")
illustrated = builder.build()
print(illustrated.cover.id, illustrated.cover.content_type)  # bin-1 image/png
```

`build()` refuses a book without a title or without a body: it raises `Fb2WriteError` with the
problems that blocked it.

## Fix the metadata of an existing book

`edit_metadata` changes the fields of `<title-info>` and returns a **new** book; the parsed one stays
as it was.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
edited = fb2kit.edit_metadata(book, title="Новое название", lang="en")
print(edited.description.title_info.title)  # Новое название
print(book.description.title_info.title)  # Пример книги -- the original is untouched
```

The accepted fields are those of `TitleInfo`: `title`, `authors`, `genres`, `keywords`,
`annotation`, `dates`, `coverpage`, `lang`, `src_lang`, `translators`, `sequences`. An unknown field
raises `TypeError`.

For everything else use the other helpers, all of which return a new book and rebuild its `element`
and its `index`:

| Function | What it does |
|---|---|
| `book.replace(**changes)` | Replaces the fields of the book: `description`, `bodies`, `binaries`, `cover`, `extra`, `report` |
| `fb2kit.with_description(book, description)` | Another `<description>` |
| `fb2kit.with_binaries(book, binaries)` | Other attachments; the cover is kept only if it is still among them |
| `fb2kit.with_cover(book, binary)` | Another cover; only the first image of the `<coverpage>` changes, the other pictures stay |
| `fb2kit.replace_node(book, target, replacement)` | Replaces a node found **by identity** (two equal sections are different nodes) |
| `fb2kit.reindex(book)` | Rebuilds `element` and `index` after a change of the model |

The method is called `replace` and not `with`: `with` is a keyword in Python, so it cannot be a
method name.

```python
from fb2kit import Paragraph, Section, Text

book = fb2kit.parse("book.fb2")
target = book.by_id("ch1")
edited = fb2kit.replace_node(book, target, Section("ch1", (Paragraph((Text("NEW"),)),)))
print(edited.by_id("ch1").children[0].children[0].value)  # NEW
```

## Write `.fb2` and `.fbz`

The suffix of the path decides the format: `.fbz`, `.fb2.zip` and `.zip` give a zip archive with one
book inside; anything else gives a plain file. `compress=True` or `compress=False` forces the
choice.

```python
import zipfile

import fb2kit

book = fb2kit.parse("book.fb2")
book.write("book.fbz")
with zipfile.ZipFile("book.fbz") as zf:
    print(zf.namelist())  # ['book.fb2']
```

The archive is deterministic: the entry has a fixed date (1980-01-01) and the creator is always
unix, so the same book gives the same bytes on every platform.

## `strict=False`

By default `write()` and `to_bytes()` validate the book first and refuse to write a broken one.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
broken = book.replace(bodies=())
try:
    broken.write("out.fb2")
except fb2kit.Fb2WriteError as exc:
    print(exc)  # the book has no <body> (1 problems)
    print(exc.problems[0].code)  # write.no-body
```

`strict=False` skips the check: the file is written even if the book has no title or no body. Use it
when you know what you are doing -- for example, to save a book that you are going to fix. The
problems are still available through `validate()`.

```python
broken.write("out.fb2", strict=False)
```

`to_xml()` never validates: it is a preview of the tree.

## Pretty output

`pretty=True` indents the file. The elements, their order, their attributes and their text are the
same as in the compact output.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
print(book.to_xml(pretty=True)[:60])
```

The guarantee "one model → the same bytes → the same model" holds for the **compact** output only.
The indentation is whitespace, and whitespace is text: read back, the pretty file has extra
whitespace-only text nodes. The pretty output is for reading and for diffing, not for round-trips.

```python
import fb2kit

xml = (
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
    "<description><title-info><book-title>T</book-title></title-info></description>"
    "<body><section><p><emphasis>x</emphasis></p></section></body></FictionBook>"
)
book = fb2kit.parse_string(xml)
compact = fb2kit.parse(book.to_bytes())
pretty = fb2kit.parse(book.to_bytes(pretty=True))
print(compact.bodies == pretty.bodies)  # False: the indentation became text
```

## Validate before writing
`validate()` returns a `WriteReport`: `.problems`, `.errors`, `.warnings` and `.ok`. The problems
have a code, a message, a severity and, when it is known, a path.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
report = fb2kit.validate(book)
print(report.ok)  # True
for problem in report.warnings:
    print(problem.code, problem.message)
```

| Code | Severity | When |
|---|---|---|
| `write.no-title` | error | The book has no `<book-title>` |
| `write.no-body` | error | The book has no `<body>` |
| `write.duplicate-id` | error | Two nodes share one `id` |
| `write.invalid-id` | error | An `id` attribute is not an ASCII identifier (`^[A-Za-z_][A-Za-z0-9._-]*$`) |
| `write.invalid-char` | error | The text holds a character XML 1.0 does not allow |
| `write.invalid-tag` | error | An unknown element or attribute has a name no parser accepts: an unbound prefix (`a:b`) or an invalid character |
| `write.missing-binary` | warning | An `<image>` points to a binary that is not in the book |
| `write.dangling-link` | warning | A link points to an `id` that does not exist |
| `write.empty-body` | warning | A `<body>` has no children |
| `write.lost-id` | warning | An `id` of the original file is not kept by the model and will be lost |
| `write.no-genre` | warning | The book has no `<genre>` (the schema requires one) |
| `write.no-author` | warning | The book has no `<author>` (the schema requires one) |
| `write.incomplete-author` | warning | An author has neither a first name with a last name nor a nickname |

Errors block the write; warnings do not. A warning is a promise the writer keeps and reports: the
file is written, and something in it changed ([Limitations](../limitations.md)).

`write.invalid-id` applies to the **attribute** `id` only. The `<document-info><id>` element holds
free text (a UUID, for example) and is not checked.

## What the writer does not keep

The round-trip is semantic, not byte-for-byte. The names of the elements, their order, the
attributes and their values, the text, the unknown elements and the bytes of the attachments all
survive. The formatting does not: the indentation, the order of the attributes, the original
encoding, the comments and the processing instructions are gone. The full list is in
[Limitations](../limitations.md).

Ready-made scripts: `examples/make_book.py` builds a book and writes it, `examples/edit_metadata.py`
fixes the metadata of an existing one.
