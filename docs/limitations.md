# Limitations

What fb2kit does **not** do at the moment.

| Limitation | Workaround |
|---|---|
| The writer canonicalizes the output: the formatting and the order of the attributes are not preserved | Keep the original file if you need its layout; the content is preserved |
| Comments and processing instructions are not preserved -- the parser drops them | Nothing; they are not part of the model |
| The original encoding is not preserved: the output is always UTF-8 | Nothing; the text is the same |
| The `id` is not kept for `<title>`, `<empty-line>`, `<epigraph>`, `<annotation>`, `<stanza>`, `<tr>`, `<style>` and `<body>`: the model has no place for it | The writer reports every one of them as `write.lost-id` |
| The mutual order of `<email>` and `<home-page>` in the source is not preserved: the model keeps them in two separate tuples | The output follows the schema (`home-page` before `email`) |
| An unknown element with a name XML does not accept (an unbound prefix like `o:p`) cannot be written as it is: `strict` writing refuses it with `write.invalid-tag`; `strict=False` replaces the unsafe characters with `_` | Fix the source or drop the element |
| The writer does not validate against the FictionBook XSD | `validate()` checks the structure; the FB2 2.0 schema is shipped in the package (`fb2kit.write._schema`) and an external validator (`xmllint --schema`) can be used |
| In the pretty mode the model read back can differ: the indentation is whitespace, and whitespace is text | Use the compact output (the default) for round-trips |
| A `Raw` without an `element` (made by hand) is written as `<tag>text</tag>` | Give it an `element` if the subtree matters |
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
