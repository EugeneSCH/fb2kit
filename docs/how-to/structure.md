# Walking the structure

## How the tree is organized

```text
FictionBook
├── description            metadata (Description)
├── bodies[0]              main text (Body, name=None)
│   ├── Title, Epigraph, Image
│   └── Section ─┬─ Title, Epigraph, Image, Annotation
│                ├─ blocks: Paragraph, Subtitle, EmptyLine, Poem, Cite, Table, Image, Raw…
│                └─ Section (nested)
├── bodies[1]              notes (Body, name="notes")
└── binaries               images (Binary)
```

Nodes are `frozen` dataclasses from `fb2kit.model`. For `Section` and `Body`, all content lies in
`children` in document order, and the `title`, `epigraph`, `image`, `sections` and `blocks` properties
are selections from it. In real books, blocks and nested sections can be interleaved, so take the order
from `children`.

Inside a paragraph are inline nodes (`Inline`): `Text`, `Style` (`emphasis`, `strong`, …), `Link`,
`Image`, `Raw`.

## Sections and paragraphs

```python
import fb2kit
from fb2kit.model import Paragraph, Section, Style, Text

book = fb2kit.parse("book.fb2")


def inline_text(nodes) -> str:
    out = []
    for n in nodes:
        if isinstance(n, Text):
            out.append(n.value)
        elif hasattr(n, "children"):  # Style, Link
            out.append(inline_text(n.children))
    return "".join(out)


def title_text(section: Section) -> str:
    lines = section.title.children if section.title else ()
    return " ".join(inline_text(p.children) for p in lines if isinstance(p, Paragraph))


def walk(section: Section, depth: int = 1) -> None:
    title = title_text(section)
    print("  " * depth + f"§ {title}")
    for child in section.children:
        if isinstance(child, Section):
            walk(child, depth + 1)
        elif isinstance(child, Paragraph):
            print("  " * depth + "  " + inline_text(child.children))


for section in book.bodies[0].sections:
    walk(section)
```

If you only need the text without markup, use `fb2kit.iter_blocks` ([RAG export](rag.md)): it already
handles all block kinds, `Raw` and whitespace.

## Poems

`Poem` → `stanzas` → `Stanza.verses` → `Verse.children`.

```python
from fb2kit.model import Poem

for section in book.iter_sections():
    for poem in (b for b in section.blocks if isinstance(b, Poem)):
        for stanza in poem.stanzas:
            print("\n".join(inline_text(v.children) for v in stanza.verses))
```

## Tables

`Table.rows` → `Row.cells` → `Cell` with `header`, `colspan`, `rowspan`, `align`.

```python
from fb2kit.model import Table

for section in book.iter_sections():
    for table in (b for b in section.blocks if isinstance(b, Table)):
        for row in table.rows:
            print(" | ".join(inline_text(c.children) for c in row.cells))
```

## Notes and internal links

A note reference in the text is a `Link` with `link_type="note"` (`is_note`). `book.resolve(link)` returns
the node for `#id`, usually a `Section` in the notes body. `book.notes_body` is the first body holding
notes.

```python
from fb2kit.model import Link, iter_nodes

for node in iter_nodes(book.bodies[0]):
    if isinstance(node, Link) and node.is_note:
        target = book.resolve(node)  # Section | None
        print(inline_text(node.children), "→", target.id if target else None)
```

A link to a nonexistent `id` yields `None` and the `link.unresolved` diagnostic. An external link
(`https://…`) also yields `None`. `iter_nodes` walks any node or tuple of nodes depth-first.

## Images

`Image.href` is the `#id` of an attachment. An image can sit in a section (`section.image` or a block in
`children`), inside a paragraph, or on the cover.

```python
from fb2kit.model import Image

for node in iter_nodes(book.bodies):
    if isinstance(node, Image) and node.href and node.href.startswith("#"):
        binary = book.by_id(node.href[1:])  # Binary | None
        print(node.href, binary.content_type if binary else "no attachment")
```

## Unknown elements

An element that is not in the FB2 schema is not dropped: it becomes `Raw(tag, text, element)` with the
`element.unknown` diagnostic. `Raw.element` is the original `xml.etree.ElementTree.Element`, if you need
to process it yourself; `book.element` is the root of the whole document.
