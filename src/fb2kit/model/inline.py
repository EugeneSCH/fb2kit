"""Inline nodes: text, formatting, links, images and unknown elements."""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree.ElementTree import Element


@dataclass(frozen=True, slots=True)
class Text:
    """A piece of text.

    Attributes:
        value: Text as in the XML, whitespace not normalized.
    """

    value: str


@dataclass(frozen=True, slots=True)
class Style:
    """Formatting: `emphasis`, `strong`, `strikethrough`, `sub`, `sup`, `code` or `style`.

    Attributes:
        kind: Element name (`emphasis`, `strong`, ...).
        children: Nested content.
        name: Value of the `name` attribute of `<style>`, `None` for the others.
    """

    kind: str
    children: tuple[Inline, ...] = ()
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Link:
    """Link `<a>`.

    Attributes:
        href: Value of `l:href` (or `href`): `#id` for internal links, a URL for external ones.
        link_type: The `type` attribute; `"note"` for footnotes.
        children: Link text.
        id: The element's `id`, if any.
    """

    href: str
    link_type: str | None = None
    children: tuple[Inline, ...] = ()
    id: str | None = None

    @property
    def is_note(self) -> bool:
        """`True` for a footnote (`type="note"`)."""
        return self.link_type == "note"


@dataclass(frozen=True, slots=True)
class Image:
    """Image `<image>`: inline, in a section or on the cover.

    Attributes:
        href: Reference to a `Binary` (`#id`) or `None`.
        alt: The `alt` attribute.
        title: The `title` attribute.
        id: The element's `id`.
    """

    href: str | None = None
    alt: str | None = None
    title: str | None = None
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Raw:
    """Unknown element: kept, not dropped.

    Attributes:
        tag: Local element name.
        text: All text of the element and its descendants.
        element: The original `Element` for custom parsing; not used in comparisons.
    """

    tag: str
    text: str | None = None
    element: Element | None = field(default=None, compare=False, repr=False)


Inline = Text | Style | Link | Image | Raw
