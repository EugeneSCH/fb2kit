"""Typed immutable FB2 model. All nodes are frozen dataclasses with slots."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

from fb2kit.model.binary import Binary, decode_b64
from fb2kit.model.inline import Image, Inline, Link, Raw, Style, Text
from fb2kit.model.metadata import (
    Author,
    CustomInfo,
    Date,
    Description,
    DocumentInfo,
    PublishInfo,
    Sequence,
    TitleInfo,
)
from fb2kit.model.structure import (
    Annotation,
    Block,
    Body,
    Cell,
    Cite,
    EmptyLine,
    Epigraph,
    Node,
    Paragraph,
    Poem,
    Row,
    Section,
    Stanza,
    Subtitle,
    Table,
    TextAuthor,
    Title,
    Verse,
)

__all__ = [
    "Annotation",
    "Author",
    "Binary",
    "Block",
    "Body",
    "Cell",
    "Cite",
    "CustomInfo",
    "Date",
    "Description",
    "DocumentInfo",
    "EmptyLine",
    "Epigraph",
    "Image",
    "Inline",
    "Link",
    "Node",
    "Paragraph",
    "Poem",
    "PublishInfo",
    "Raw",
    "Row",
    "Section",
    "Sequence",
    "Stanza",
    "Style",
    "Subtitle",
    "Table",
    "Text",
    "TextAuthor",
    "Title",
    "TitleInfo",
    "Verse",
    "decode_b64",
    "iter_nodes",
]


def iter_nodes(node: object) -> Iterator[object]:
    """Depth-first walk over all model nodes in document order.

    Fields with `compare=False` (`Raw.element`, `FictionBook.element`) are not traversed.

    Args:
        node: A node, tuple or list of nodes (for example `book.bodies`).

    Yields:
        The node itself and all nested dataclass nodes.
    """
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tuple | list):
            stack.extend(reversed(cur))
        elif dataclasses.is_dataclass(cur) and not isinstance(cur, type):
            yield cur
            stack.extend(
                getattr(cur, f.name) for f in reversed(dataclasses.fields(cur)) if f.compare
            )
