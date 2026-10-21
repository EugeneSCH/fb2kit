# Writing: how it works

The writer turns a book into a file. The interesting part is not the XML -- it is what the writer
decides to keep and what it gives up, and why.

## Why the tree is built from the model, not patched

A parsed book holds two things: the **model** (`description`, `bodies`, `binaries`) and the
**original tree** (`book.element`). The original tree knows the indentation, the comments and every
unknown element; the model knows the structure and the text.

Patching the original tree would leave two sources of truth: `book.bodies` would say one thing and
`book.element` another, and nothing would tell the reader which one the file came from. So the
writer builds a **new** tree from the model, and the original tree is only a source for what the
model does not understand (`Raw.element`).

The result is that a book parsed from a file and a book built by `new_book()` go through the same
code: there is one place that knows the shape of an FB2 file
(`fb2kit/write/serialize.py`), and the builder and the editor do not form XML themselves.

After a change the tree is rebuilt from the model again (`reindex`), so the escape hatch
`book.element` never describes a book that is not there any more.

## Why the output is compact

The default output is one line: no line breaks between the elements.

The obvious alternative -- `ET.indent` -- writes the newlines into the `tail` of the last child of
an element. The `tail` is text, and text is part of the model: read back, the file has extra
whitespace-only text nodes that the original did not have. The round-trip promise ("one model →
the same bytes → the same model") would be broken by the indentation alone.

The compact output has no whitespace to invent, so the model that comes back is the model that went
in. The cost is unreadable files, and that is what `pretty=True` is for: a printer of its own that
builds a string and never touches the `tail` of an element. The pretty output describes the same
document -- the same elements, the same order, the same attributes, the same text -- but the
indentation is whitespace, and whitespace is text. The guarantee holds for the compact output only.

## Why the clone of an unknown element drops the tail of its root

An unknown element (`<foo>`) is kept in the model as `Raw`: its tag, its text and the original
element itself.

The original element carries a `tail`: the text that follows it. In the model that text is already
there, as a separate `Text` node -- the parser splits the text of a paragraph into `Text` nodes
around the elements. Copying the tail into the clone would write the text **twice**: once from the
`Text` node of the model and once from the tail of the clone.

The tails of the **descendants** are a different matter: the model does not keep them anywhere
(`Raw.text` is the glued text of the whole subtree), so a clone that dropped them would silently
destroy text. The clone therefore drops the tail of the root it copies and keeps the tails of
everything below it.

## Why the base64 is written verbatim

An attachment is a `<binary>` element with the payload in base64. The model keeps the original
string of the payload (`Binary._b64`) and decodes it only when the bytes are asked for.

The writer puts the string back as it is. Re-packing it into lines of 76 characters would be
tidier, and it would change the bytes of the file for no reason: the decoded image would be the
same, but the file would differ from the one that was read. Verbatim is also the honest choice: a
payload that does not decode is written back unchanged, and the file stays exactly as broken as it
was.

## Why a missing binary is a warning

An `<image>` in the text points to an attachment with `#id`. In real books that attachment is often
missing: the converter kept the reference and dropped the file. Two fixtures of the test suite show
it, and books from real collections show it all the time.

If that were an error, the writer would refuse to write books that are perfectly readable -- the
reader sees a missing picture, not a broken book. So a missing binary is a warning: the file is
written, and the report says what is not in it. The same holds for a link to a target that does not
exist.

What is an error is a book that no reader can use at all: no title, no body, a duplicated `id`, an
`id` that is not a valid name, a character XML does not allow. Those block the write, and
`strict=False` is the way to write such a book anyway.

## What the round-trip keeps

The guarantee is **semantic**, not byte-for-byte.

| Keeps | Loses |
|---|---|
| The names of the elements and their order | The indentation and the formatting |
| The attributes and their values | The order of the attributes |
| The text and the tails | The original encoding (the output is always UTF-8) |
| The unknown elements, with their subtree | The comments, the processing instructions, the CDATA |
| The bytes of the attachments and their `content-type` | The way the entities were spelled |
| `description.extra` and `FictionBook.extra` | The `id` of the elements the model does not keep |
| | The mutual order of `<email>` and `<home-page>` |

The last two rows of the right column are the price of a v0.1 model: the model has no place for the
`id` of a `<title>`, an `<empty-line>`, an `<epigraph>`, an `<annotation>`, a `<stanza>`, a `<tr>`, a
`<style>` or a `<body>`, so those `id`s cannot come back. The writer does not lose them silently: it
reports every one of them as `write.lost-id`.

The same holds for the order of `<email>` and `<home-page>`: the model keeps them in two separate
tuples, so their mutual order is not in it. The writer puts them in the order of the schema
(`home-page` before `email`), which is what makes the output valid.

## Why the output is deterministic

The same model always gives the same bytes. There is no `datetime.now()`, no `uuid4`, no random
name: the identifiers come from the model or from the builder, which counts them
(`note-1`, `note-2`).

The namespace prefixes are assigned locally as well. `ET.register_namespace` would change a global
registry, and then the same model in the same process could give different bytes depending on what
happened before -- the writer renders the tree itself and never touches a global state.

The zip archive is deterministic too: the entry has a fixed date (1980-01-01) and the creator is
always unix, so an archive written on Windows is the same as one written on macOS.
