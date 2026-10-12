# Strict, tolerant and diagnostics

## How the modes differ

| | `Mode.STRICT` (default) | `Mode.TOLERANT` |
|---|---|---|
| Broken XML (unescaped `&`, control characters, truncated file) | `Fb2ParseError` with `line` | Repaired; the repair is in `report` |
| Encoding is not UTF-8 and not declared, or contradicts the prolog | `Fb2EncodingError` | Guessed; the decision is in `report` |
| No `<description>` | `Fb2ParseError(path="FictionBook")` | Empty `Description`, `element.missing` |
| `<!DOCTYPE>` / `<!ENTITY>` | `Fb2UnsafeInputError` | `Fb2UnsafeInputError` |
| Content defects: unknown tag, broken link, no cover, duplicate id | Diagnostic in `report` | Diagnostic in `report` |

Strict suits cases where the file is yours and an error in it is a reason to fix it. Tolerant is for
other people's collections, where reading the book matters more than rejecting it: it never changes the
text silently, and every repair is visible in `book.report.diagnostics`.

```python
import fb2kit

try:
    book = fb2kit.parse("messy.fb2")
except fb2kit.Fb2ParseError as exc:
    print("strict:", exc, "line", exc.line)
    book = fb2kit.parse("messy.fb2", mode=fb2kit.Mode.TOLERANT)

for d in book.report.diagnostics:
    print(d.severity.value, d.code, d.message)
```

`mode` and `backend` also accept strings: `mode="tolerant"`.

## Exceptions

```text
Fb2Error
├── Fb2SourceError          file unreadable, empty, > max_size, broken archive, no book in the archive
│   └── Fb2UnsafeInputError DOCTYPE/ENTITY in the input
├── Fb2EncodingError        encoding not determined or contradicts the bytes
└── Fb2ParseError           not XML / not FictionBook; fields path and line
```

Catch `fb2kit.Fb2Error` to handle any input problem in a single branch. `TypeError` is a call error
(wrong type of `source`, `mode`, `backend`); there is no need to catch it.

## Diagnostics

`Diagnostic(code, message, severity, path)`. `severity` is `info` (information about a decision) or
`warning` (something was repaired or lost). `report.warnings` shows whether there are any problems.

Repeated notices with the same code and message are recorded once.

| Code | Severity | Mode | When | What to do |
|---|---|---|---|---|
| `encoding.guessed` | warning | tolerant | Bytes are not UTF-8 and there is no prolog; the encoding was confidently guessed from Russian letter frequencies | Check the text; pass `encoding=` to be sure |
| `encoding.fallback` | warning | tolerant | Same, but the signal is weak: `cp1251` was taken (bytes it lacks become `U+FFFD`) | Pass the correct `encoding=` |
| `encoding.declared-mismatch` | info | both | The prolog says one thing, but the book was decoded as another without guessing (`encoding=`, BOM, or the bytes turned out to be valid UTF-8) | Nothing; the encoding is in `report.source_encoding` |
| `encoding.declared-mismatch` | warning | tolerant | The prolog is wrong or unknown, and the encoding had to be guessed (like `encoding.guessed`) | Check the text; pass `encoding=` |
| `container.fbz` | info | both | The book was unpacked from a zip | Nothing |
| `container.entry-sniffed` | info | both | The archive has no `*.fb2`; the book was found by content | Nothing |
| `namespace.missing` | warning | both | The root has no `xmlns`; FB2 2.0 assumed | Nothing |
| `namespace.foreign` | warning | both | The root has a foreign namespace; replaced with FB2 | Check that it really is FB2 |
| `namespace.prefix-injected` | warning | tolerant | The `l:`/`xlink:` prefix was used without a declaration; declared | Nothing |
| `xml.bare-amp` | warning | tolerant | An unescaped `&` (including `&nbsp;`) was replaced with `&amp;` | Nothing; HTML entities stay as text |
| `xml.control-chars` | warning | tolerant | Characters forbidden in XML were removed | Nothing |
| `xml.auto-closed` | warning | tolerant | The file is truncated; unclosed tags were closed at the end | The book is most likely incomplete |
| `xml.lxml-recover` | warning | tolerant, lxml | The other repairs did not help; lxml `recover` rebuilt the tree | Check the text: some of it may be lost |
| `element.unknown` | warning | both | An element outside the schema was kept as `Raw`; a block inside a paragraph was flattened; text outside `<p>` became a paragraph | Nothing; parse `Raw.element` if needed |
| `element.missing` | warning | both | No `<body>`, no `<title-info>`, a `<binary>` without `id` (skipped); no `<description>` (tolerant only) | Account for `None`/empty fields |
| `id.duplicate` | warning | both | Two nodes share one `id` | `book.index` holds the first |
| `link.unresolved` | warning | both | An internal `#id` link leads nowhere | `book.resolve` returns `None` |
| `cover.missing` | warning | both | `<coverpage>` references a missing attachment | `book.cover` is `None` |
| `notes.body-name` | info | both | The notes body is not named `notes`/`footnotes`/`comments` | Nothing; it is still treated as notes |

The codes are also available as constants of the `fb2kit.report` module (`report.XML_BARE_AMP` and so on).

## Backends {#backends}

`Backend.AUTO` picks lxml if the `fast` extra is installed, otherwise `xml.etree.ElementTree`.
The book model is the same on both. There is one difference: a mismatched closing tag
(`<p><emphasis>x</p>`) is repaired in tolerant mode only by lxml (`xml.lxml-recover`); on stdlib it is a
`Fb2ParseError`. `report.backend` shows which backend ran.

```python
book = fb2kit.parse("book.fb2", backend=fb2kit.Backend.STDLIB)
print(book.report.backend)  # stdlib
```

`Backend.LXML` without lxml installed raises `Fb2Error`.
