# Book and metadata

All metadata lives in `book.description` (`Description`): book information in `title_info`, file
information in `document_info`, publication information in `publish_info`. A missing field is `None` or
an empty tuple; no exceptions are raised.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
ti = book.description.title_info

print(ti.title)  # Пример книги ("Sample Book"; the fixture book is Russian)
for author in ti.authors:
    print(author.first_name, author.last_name, "|", author.full_name)
print(ti.genres)  # FB2 genre codes as is: ('sf', 'adventure')
print(ti.lang, ti.src_lang)  # ru None
for seq in ti.sequences:
    print(seq.name, seq.number)  # Примеры 1  (number is an int or None)
for date in ti.dates:
    print(date.value, date.iso)  # 2024 2024-05-01
```

`Author.full_name` joins the non-empty first name, middle name and last name; if there are none, it is
the nickname.

## Annotation

The annotation is a tuple of blocks (usually `Paragraph`) or `None`. The easiest way to get plain text is
`book_meta`:

```python
meta = fb2kit.book_meta(book)
print(meta["annotation"])  # Небольшая книга для документации fb2kit. (Russian)
print(meta)  # title, authors, genres, lang, sequence, annotation
```

`book_meta` omits empty fields, so access them through `meta.get(...)`.

## File and publication

```python
doc = book.description.document_info
if doc is not None:
    print(doc.program_used, doc.ids, doc.version)

pub = book.description.publish_info
if pub is not None:
    print(pub.publisher, pub.city, pub.year, pub.isbn)  # year is a string as in the file
```

`custom_info` is a tuple of `CustomInfo(info_type, text)`; unknown `<description>` elements go to
`description.extra` as `Raw`.

## Cover and images

`book.cover` is the `Binary` referenced by the first `<coverpage><image>`, or `None`. If the reference
exists but the image does not, the report contains `cover.missing`. All attachments are in `book.binaries`.

```python
for binary in book.binaries:
    print(binary.id, binary.content_type, binary.size)  # cover.png image/png 69, map.png ...
```

`Binary.data` decodes base64 on first access and caches the result; broken base64 yields `b""`
rather than an exception. The `examples/extract_images.py` script saves all images.

## Parse report

```python
report = book.report
print(report.source_encoding, report.declared_encoding)  # utf-8 utf-8
print(report.container, report.backend)  # None stdlib|lxml
print(len(report.diagnostics))  # 0 -- the book is clean
```
