# fb2kit

A FictionBook 2 (FB2 2.0–2.2) parser for Python 3.11+. It returns a book as an immutable, typed
tree (`mypy --strict`), reads `.fbz`/`.fb2.zip`, detects the encoding and, in tolerant mode, repairs
broken files, recording every repair in a report. No required dependencies.

```python
import fb2kit

book = fb2kit.parse("book.fb2")
print(book.description.title_info.title)
```

## Documentation map

| Section | Contents |
|---|---|
| [Installation and quickstart](tutorial/quickstart.md) | From `pip install` to the book text in five minutes |
| [How-to guides](how-to/metadata.md) | Recipes: metadata, walking the structure, modes and diagnostics, encodings, sources, RAG |
| [API reference](reference/api.md) | Every public function, class and field with types |
| [Parsing pipeline](explanation/architecture.md) | How parsing works and why there are two modes |
| [Security](explanation/security.md) | What is rejected and why |
| [Limitations](limitations.md) | What the library does not do |
| [FAQ](faq.md) | Frequently asked questions |

Example scripts live in the repository's `examples/` directory: folder metadata to CSV, a book to
Markdown and to plain text, image extraction, JSONL export for RAG, folder check.

A short API map for LLM agents: [llms.txt](llms.txt).
