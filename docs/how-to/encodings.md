# Encodings

## Detection order

`parse` tries the sources in order and stops at the first one that applies:

1. **`encoding=`**: an explicit argument overrides everything. If the prolog says otherwise,
   `encoding.declared-mismatch` (info) is recorded.
2. **BOM / signature**: UTF-8 BOM, UTF-16/32 LE/BE with and without BOM (by `<?` in the matching width,
   XML 1.0, appendix F).
3. **Prolog** `<?xml version="1.0" encoding="..."?>`. If the declared encoding is unknown or the bytes
   do not match it: strict raises `Fb2EncodingError`; tolerant moves on. If the bytes are valid UTF-8,
   that is used (`encoding.declared-mismatch`, info); otherwise guessing (step 5) kicks in and
   `encoding.declared-mismatch` becomes a warning.
4. **UTF-8** without a declaration.
5. **Tolerant** only: guessing single-byte Cyrillic (`cp1251`, `koi8-r`, `cp866`,
   `iso8859-5`, `mac-cyrillic`) from the frequencies of Russian letters in the first 64 KiB. A confident
   guess is `encoding.guessed`; a weak signal (fewer than 16 Cyrillic letters or close candidates)
   falls back to `cp1251` with `encoding.fallback`. In strict mode this step raises `Fb2EncodingError`.

The result is always in the report:

```python
import fb2kit

book = fb2kit.parse("cp1251.fb2", mode=fb2kit.Mode.TOLERANT)
print(book.report.source_encoding)  # cp1251
print(book.report.declared_encoding)  # None -- there is no prolog
print([d.code for d in book.report.diagnostics])  # ['encoding.guessed']
```

## When to pass `encoding=`

- You know the collection's encoding in advance: pass it, it is faster and more reliable than guessing.
- The file is EBCDIC or another exotic encoding: guessing does not look for those.
- Strict mode on books without a prolog in cp1251/koi8-r: without `encoding=` you get `Fb2EncodingError`.

```python
book = fb2kit.parse("cp1251.fb2", encoding="cp1251")  # strict, no diagnostics
print(book.description.title_info.title)  # Тест ("Test"; the fixture title is Russian)
```

The encoding name can be anything `codecs` knows: `"windows-1251"`, `"cp1251"`, `"KOI8-R"`. An unknown
name or a non-text codec (`rot13`, `base64`) raises `Fb2EncodingError`.

## `parse_string`

`parse_string` receives an already decoded `str`: the encoding is not detected, the prolog is ignored,
and `report.source_encoding` is always `"utf-8"`. If you read the file yourself, pass bytes to `parse`
so that the whole order above applies.
