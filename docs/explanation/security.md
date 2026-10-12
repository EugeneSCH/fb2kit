# Security

FB2 often comes from untrusted sources: libraries, torrents, user uploads. fb2kit is built for such
input and, in **both** modes, rejects or limits the following.

| Threat | What fb2kit does | Why |
|---|---|---|
| XXE (`<!ENTITY x SYSTEM "file:///etc/passwd">`) | `Fb2UnsafeInputError` on any `<!DOCTYPE` or `<!ENTITY` | FB2 needs no DTD; it is safer to reject than to parse selectively |
| "Billion laughs" (nested entities) | Same | Same reason |
| A DTD hidden in UTF-16, comments, CDATA | Checked in the raw bytes, in the decoded text, and after tolerant repair | So that a bypass through the encoding or a "repair" does not work |
| Zip bomb | At most `max_size + 1` bytes are read from the archive; the archive itself is ≤ 256 MiB | Memory is bounded before unpacking, not after |
| Huge file | `max_size` (256 MiB by default) | A predictable memory ceiling |
| An archive of thousands of files | The search for a book by content covers at most 1000 entries of 4 KiB each | Search time is bounded |
| Deep nesting | `Fb2ParseError` at depth > 200 | Protects consumers of recursive traversal from stack overflow |
| Network and files during parsing | Not used: external entities are forbidden, lxml runs with `no_network=True`, `resolve_entities=False` | Parsing is a pure function of the bytes |
| Repair regular expressions | Linear (possessive groups) | Malicious input does not cause catastrophic backtracking |

```python
import fb2kit

try:
    fb2kit.parse("unsafe.fb2", mode=fb2kit.Mode.TOLERANT)
except fb2kit.Fb2UnsafeInputError as exc:
    print(exc)  # refusing to parse input containing a DTD/entity declaration
```

`Fb2UnsafeInputError` is a subclass of `Fb2SourceError`, so a general `except fb2kit.Fb2Error` catches it
too.

## What remains on you {#yours}

- **Content is not sanitized.** Text, links (`Link.href` may be `javascript:`) and images are data from
  the file. When rendering to HTML, escape the text and filter URL schemes.
- **`Binary.data` is not verified** against `content_type`: an image can turn out to be anything.
  Do not trust the MIME type when saving and serving.
- **Names from the book** (`Binary.id`) are not paths: sanitize them when saving to disk, as in
  `examples/extract_images.py`.
- **lxml with `huge_tree=True`** lifts libxml2's internal limits on text node size; the input is bounded
  by `max_size` and the DTD is rejected up front, so this is safe, but do not disable `max_size`.
