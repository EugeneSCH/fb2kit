# Limitations

What fb2kit does **not** do at the moment.

| Limitation | Workaround |
|---|---|
| Read-only: no writing or editing of FB2 | The model is immutable; for your own export use `dataclasses.replace` and your own serializer |
| No validation against the FictionBook XSD | An external validator (`xmllint --schema`) |
| FB3 and EPUB are not supported | An EPUB in a zip raises `Fb2SourceError` with a `looks like EPUB` hint |
| Only the first `*.fb2` is taken from an archive with several books | Unpack with `zipfile` yourself and pass each book's bytes to `parse` |
| No streaming parse: the book and tree are held in memory in full | Limit with `max_size`; books larger than a few hundred MB do not occur in practice |
| Encoding detection covers only single-byte Cyrillic, by the frequencies of **Russian** letters; the signal is weak on short texts | Use `encoding=`; for Ukrainian and Belarusian books without a prolog, being explicit is more reliable |
| EBCDIC and other exotic encodings only via `encoding=` | `encoding="cp500"` and the like |
| HTML entities (`&nbsp;`, `&mdash;`): strict raises `Fb2ParseError`, tolerant leaves them as the text `&nbsp;` | Replace them in the text after export |
| A mismatched closing tag is not repaired on stdlib | Install the `fast` extra (lxml `recover`) |
| `parse_string` does not detect the encoding | Pass bytes to `parse` |
| Content is not sanitized (links, image MIME types) | See [Security](explanation/security.md#yours) |
| Styles (`<stylesheet>`) are not applied, only kept in `book.extra` as `Raw` | Parse `Raw.text` yourself |
