# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- An unknown element with an unbound prefix (`<o:p>`) or an invalid name no longer produces an
  unreadable file: `validate()` reports `write.invalid-tag` (error), and `strict=False` sanitizes
  the name so the output always parses.
- An invalid XML character in the text of a root-level unknown element (`<stylesheet>` and the
  like) is now caught by `write.invalid-char`.
- `with_cover(book, None)` actually drops the cover: the coverpage image is removed, so the cover
  does not come back after a re-read.
- `write(..., pretty=True)` is no longer ignored for `.fbz` archives.
- `Fb2WriteError` survives pickling with its problems.
- `replace(binaries=...)` drops the cover when its binary is gone.
- An element name that no XML parser accepts (for example `<:body>`) is reported as
  `Fb2ParseError` instead of a bare `ValueError`.

### Added

- `new_book(..., document_date=...)` and a generated `<document-info>` in every built book: a book
  created by the builder now passes the bundled FB2 2.0 schema when a genre and an author are set.
- Validation warnings `write.no-genre`, `write.no-author` and `write.incomplete-author`.

### Changed

- An explicit `add_section(id=...)` reserves the name in the id generator, so `add_note()` never
  hands out the same id.

## [0.2.0] - 2026-10-21

### Added

- **Writing.** `FictionBook.to_xml()`, `FictionBook.to_bytes()` and `FictionBook.write(path)` write a
  book back: UTF-8, compact and deterministic. A `.fbz`/`.fb2.zip`/`.zip` suffix writes a zip
  archive with one book inside; the write is atomic.
- **Validation.** `fb2kit.validate(book) -> WriteReport` with the codes `write.no-title`,
  `write.no-body`, `write.duplicate-id`, `write.invalid-id`, `write.invalid-char`,
  `write.missing-binary`, `write.dangling-link`, `write.empty-body` and `write.lost-id`. Errors
  block the write (`Fb2WriteError`); warnings do not. `strict=False` writes a book with errors.
- **Building.** `fb2kit.new_book(...)`, `BookBuilder` and `SectionBuilder` create a book from
  scratch: metadata, chapters, paragraphs, poems, footnotes and attachments.
- **Editing.** `fb2kit.edit_metadata()`, `fb2kit.replace_node()`, `fb2kit.with_description()`,
  `fb2kit.with_binaries()`, `fb2kit.with_cover()` and `fb2kit.reindex()` return a new book; the
  model stays frozen.
- `FictionBook.replace(**changes)`: a copy of the book with the given fields changed, with the
  `element` and the `index` rebuilt. (`with` is a keyword in Python, so the method cannot be
  named `with`.)
- The FB2 2.0 schema (`gribuser/fb2`, BSD-2-Clause) is shipped in the package as
  `fb2kit.write._schema`.
- Documentation: the writing how-to (`docs/how-to/write.md`) and the writing explanation
  (`docs/explanation/writing.md`); the examples `make_book.py` and `edit_metadata.py`.

### Changed

- The output of the writer is compact by default: no line breaks between the elements, so the
  model read back is the model that went in. `pretty=True` gives an indented file, but the
  indentation is whitespace, and whitespace is text: the round-trip guarantee holds for the
  compact output only.
- The writer canonicalizes the output: the formatting, the order of the attributes, the original
  encoding, the comments and the processing instructions are not preserved. The `id` of the
  elements the model does not keep (`<title>`, `<empty-line>`, `<epigraph>`, `<annotation>`,
  `<stanza>`, `<tr>`, `<style>`, `<body>`) is lost and reported as `write.lost-id`.
- `docs/limitations.md` no longer says that fb2kit is read-only.

### Fixed

- Nothing.

## [0.1.0] - 2026-10-12

### Added

- Documentation structured per Diátaxis: quickstart, how-to guides, API reference generated from
  docstrings (mkdocstrings), explanations, limitations, FAQ, `docs/llms.txt`.
- `examples/` scripts: metadata to CSV, Markdown, plain text, images, JSONL for RAG, folder check.
- `tests/test_docs_examples.py`: executes the code in README and docs and runs the examples.
- `parse_string(..., max_size=)`: the same size limit as in `parse` (UTF-8 bytes).
- `note` blocks from sections without an `id` in a second notes body get a stable
  `node_id` of the form `notes{body_idx}-{section_idx}` (for example `notes1-2.1`), and `note_refs`
  point to it; previously `node_id` was `None`.

### Changed

- `parse` and `parse_string` annotate `mode: Mode | str` and `backend: Backend | str`
  (strings were accepted before as well).
- Model node types (`Section`, `Paragraph`, `Binary`, ...) and `iter_nodes` are re-exported from
  `fb2kit` and added to `__all__`.
- `FictionBook.by_id`, `resolve` and `index` are annotated `Node | Binary` (alias `fb2kit.Indexed`):
  they always returned `Binary` too, but the type did not say so.
- Encoding codes renamed to match their meaning: a confident guess is `encoding.guessed` (was
  `encoding.substituted`), a weak signal and fallback to `cp1251` is `encoding.fallback` (was
  `encoding.guessed`). Constants `report.ENC_GUESSED` and `report.ENC_FALLBACK`; `ENC_SUBSTITUTED` removed.
- `encoding.declared-mismatch` is a warning when a wrong prolog forced the encoding to be guessed;
  otherwise (including an explicit `encoding=`) it stays info.
- Public API docstrings use Google style (Args/Returns/Raises/Attributes).

### Removed

- `Severity.ERROR`, `ParseReport.ok` and `ParseReport.errors`: parsing never produced error diagnostics.
- The never-populated `PublishInfo.dates` field from the public model.
