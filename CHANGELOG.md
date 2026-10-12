# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions: [SemVer](https://semver.org/).

## [Unreleased]

### Added

- Documentation structured per Diátaxis: quickstart, how-to guides, API reference generated from
  docstrings (mkdocstrings), explanations, limitations, FAQ, `docs/llms.txt`.
- `examples/` scripts: metadata to CSV, Markdown, plain text, images, JSONL for RAG, folder check.
- `tests/test_docs_examples.py`: executes the code in README and docs and runs the examples.

### Added

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
