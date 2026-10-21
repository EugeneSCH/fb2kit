"""Editing a book without touching it.

Every function here returns a **new** book: the model is frozen, so a change
is a new object. The `element` and the `index` are always rebuilt, otherwise
they would describe the old book.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, cast

from fb2kit.api import FictionBook, Indexed
from fb2kit.model import iter_nodes
from fb2kit.model.binary import Binary
from fb2kit.model.inline import Image, Raw
from fb2kit.model.metadata import Description
from fb2kit.model.structure import Body


class _Dataclass(Protocol):
    """An instance of a dataclass: the model nodes are all of them."""

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]


def _raw_ids(raw: Raw) -> list[str]:
    """The `id` attributes of the subtree of an unknown element.

    The parser registers them, so the index of an edited book has to hold them
    too.

    Args:
        raw: The unknown node.

    Returns:
        The ids, in document order.
    """
    if raw.element is None:
        return []
    return [id_ for el in raw.element.iter() if (id_ := el.get("id")) is not None]


def _index_of(book: FictionBook) -> dict[str, Indexed]:
    """Build the index of a book.

    The first `id` wins on duplicates, exactly as in the parser. The ids
    inside an unknown element are registered too: the parser does it, and
    without them the index of an edited book would differ from the index of
    the parsed one.

    Args:
        book: The book to index.

    Returns:
        The `id` to node map.
    """
    index: dict[str, Indexed] = {}
    for node in iter_nodes((book.description, book.bodies)):
        node_id = getattr(node, "id", None)
        if node_id is not None and node_id not in index:
            index[node_id] = node  # type: ignore[assignment]  # node: Indexed, не object
    for binary in book.binaries:
        index.setdefault(binary.id, binary)
    for node in iter_nodes((book.description, book.bodies)):
        if isinstance(node, Raw):
            for node_id in _raw_ids(node):
                index.setdefault(node_id, node)
    for raw in (*book.extra, *book.description.extra):
        for node_id in _raw_ids(raw):
            index.setdefault(node_id, raw)
    return index


def reindex(book: FictionBook) -> FictionBook:
    """Rebuild the `element` and the `index` of a book.

    Use it after a change of the model: the tree and the map of the ids have
    to describe the book that is written out.

    Args:
        book: The book to rebuild.

    Returns:
        The same book with a fresh `element` and a fresh `index`.
    """
    from fb2kit.write.serialize import build_tree

    index: Mapping[str, Indexed] = MappingProxyType(_index_of(book))
    return dataclasses.replace(book, element=build_tree(book), index=index)


def _walk_sequence(
    node: tuple[object, ...] | list[object], target: object, replacement: object
) -> object:
    """Rebuild a sequence with the target replaced by the replacement.

    Args:
        node: The sequence to rebuild.
        target: The node to replace.
        replacement: The node to put in its place.

    Returns:
        The new sequence; the same object if it holds nothing to replace.
    """
    items = [_walk(item, target, replacement) for item in node]
    if all(new is old for new, old in zip(items, node, strict=True)):
        return node
    return tuple(items)


def _walk_dataclass(node: _Dataclass, target: object, replacement: object) -> object:
    """Rebuild a dataclass with the target replaced by the replacement.

    Only the fields that take part in the comparison are rebuilt: the others
    are not a part of the model.

    Args:
        node: The dataclass to rebuild.
        target: The node to replace.
        replacement: The node to put in its place.

    Returns:
        The new dataclass; the same object if it holds nothing to replace.
    """
    changes: dict[str, object] = {}
    for f in dataclasses.fields(node):
        if not f.compare:
            continue
        value = getattr(node, f.name)
        new = _walk(value, target, replacement)
        if new is not value:
            changes[f.name] = new
    if not changes:
        return node
    return dataclasses.replace(node, **changes)


def _walk(node: object, target: object, replacement: object) -> object:
    """Rebuild a node with the target replaced by the replacement.

    The replacement is found by identity, not by equality: two equal sections
    are different nodes.

    Args:
        node: The node to rebuild.
        target: The node to replace.
        replacement: The node to put in its place.

    Returns:
        The new node; the same object if it holds nothing to replace.
    """
    if node is target:
        return replacement
    if isinstance(node, tuple | list):
        return _walk_sequence(node, target, replacement)
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        return _walk_dataclass(node, target, replacement)
    return node


def replace_node(book: FictionBook, target: object, replacement: object) -> FictionBook:
    """Replace a node of the book with another one.

    The node is found by identity. The `element` and the `index` of the result
    are rebuilt, so the book and its file always agree.

    Args:
        book: The book to edit.
        target: The node to replace.
        replacement: The node to put in its place.

    Returns:
        The edited book.
    """
    changed = _walk(book.description, target, replacement)
    bodies = _walk(book.bodies, target, replacement)
    if changed is book.description and bodies is book.bodies:
        return reindex(book)
    return reindex(
        dataclasses.replace(
            book,
            description=cast(Description, changed),
            bodies=cast(tuple[Body, ...], bodies),
        )
    )


def with_description(book: FictionBook, description: Description) -> FictionBook:
    """A book with another description.

    Args:
        book: The book to edit.
        description: The new description.

    Returns:
        The edited book.
    """
    return reindex(dataclasses.replace(book, description=description))


def with_binaries(book: FictionBook, binaries: tuple[Binary, ...]) -> FictionBook:
    """A book with other binaries.

    The cover is kept only if it is still among the binaries.

    Args:
        book: The book to edit.
        binaries: The new binaries.

    Returns:
        The edited book.
    """
    cover = book.cover if book.cover is not None and book.cover in binaries else None
    return reindex(dataclasses.replace(book, binaries=binaries, cover=cover))


def with_cover(book: FictionBook, binary: Binary | None) -> FictionBook:
    """A book with another cover.

    Only the **first** image of the coverpage is changed; the other pictures
    of the cover stay. The binary is added to the binaries if it is not there
    yet.

    Args:
        book: The book to edit.
        binary: The new cover, or `None` to drop the cover.

    Returns:
        The edited book.
    """
    binaries = book.binaries
    if binary is not None and binary not in binaries:
        binaries = (*binaries, binary)
    coverpage = book.description.title_info.coverpage
    if binary is None:
        # Drop the cover itself; the other pictures of the coverpage stay.
        new_coverpage = coverpage[1:]
    elif coverpage:
        new_coverpage = (Image(href=f"#{binary.id}", alt=coverpage[0].alt), *coverpage[1:])
    else:
        new_coverpage = (Image(href=f"#{binary.id}"),)
    title_info = dataclasses.replace(book.description.title_info, coverpage=new_coverpage)
    description = dataclasses.replace(book.description, title_info=title_info)
    return reindex(
        dataclasses.replace(book, description=description, binaries=binaries, cover=binary)
    )


def edit_metadata(book: FictionBook, **changes: object) -> FictionBook:
    """A book with changed metadata.

    The changes go to the `title-info`: the title, the authors, the language,
    the genres and the keywords.

    Args:
        book: The book to edit.
        changes: The fields of the `title-info` to replace.

    Returns:
        The edited book.

    Raises:
        TypeError: An unknown field of the `title-info`.
    """
    known = {
        "genres": tuple,
        "authors": tuple,
        "title": str,
        "annotation": tuple,
        "keywords": str,
        "dates": tuple,
        "coverpage": tuple,
        "lang": str,
        "src_lang": str,
        "translators": tuple,
        "sequences": tuple,
    }
    for name, value in changes.items():
        if name not in known:
            raise TypeError(f"unknown field of the title-info: {name!r}")
        if known[name] is tuple:
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple, got {type(value).__name__}")
        elif value is not None and not isinstance(value, known[name]):
            raise TypeError(f"{name} must be a {known[name].__name__}, got {value!r}")
    title_info = dataclasses.replace(book.description.title_info, **cast(dict[str, Any], changes))
    description = dataclasses.replace(book.description, title_info=title_info)
    return reindex(dataclasses.replace(book, description=description))
