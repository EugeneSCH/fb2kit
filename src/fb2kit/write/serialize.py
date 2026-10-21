"""Model to XML: the only place that knows the shape of an FB2 file.

The writer builds a **new** tree from the model. Text comes from the model
nodes, unknown elements come from `Raw.element` and binaries are written
verbatim from their base64 payload.

The output is compact (no line breaks between elements) and deterministic: the
same model always gives the same bytes.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any

from fb2kit.model.binary import Binary
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
from fb2kit.parser import FB2_NS, XLINK_NS

if TYPE_CHECKING:
    from fb2kit.api import FictionBook

_XML_NS = "http://www.w3.org/XML/1998/namespace"

_NAMESPACES: dict[str, str] = {FB2_NS: "", XLINK_NS: "l", _XML_NS: "xml"}
"""URI to prefix. Local to the writer: the output never depends on a global registry."""


def _el(tag: str, attrs: tuple[tuple[str, str], ...] = (), text: str | None = None) -> ET.Element:
    """An element in the FB2 namespace.

    Args:
        tag: Local element name.
        attrs: Attributes in the order they must be written; `id` comes first.
        text: Text content.

    Returns:
        The new element.
    """
    el = ET.Element(f"{{{FB2_NS}}}{tag}")
    for name, value in attrs:
        el.set(name, value)
    el.text = text
    return el


def _xlink(name: str) -> str:
    """Qualified name of an attribute in the xlink namespace."""
    return f"{{{XLINK_NS}}}{name}"


def _xml_lang(name: str) -> str:
    """Qualified name of an attribute in the `xml` namespace."""
    return f"{{{_XML_NS}}}{name}"


def _clone(el: Any) -> ET.Element:
    """A deep copy of an element in the stdlib tree.

    The `tail` of the copied element is dropped: the text after it is already
    in the model as a separate `Text` node, and copying it would write the
    text twice. The tails of the **descendants** are kept -- the model does not
    store them anywhere, so dropping them would silently lose text.

    Args:
        el: The element to copy; an `xml.etree` or an `lxml` element.

    Returns:
        The copy.
    """
    copy = ET.Element(el.tag)
    for name, value in el.attrib.items():
        copy.set(name, value)
    copy.text = el.text
    for child in el:
        copy.append(_clone(child))
        copy[-1].tail = child.tail
    return copy


def _raw_el(raw: Raw) -> ET.Element:
    """An element for an unknown node.

    With an original element the whole subtree is kept; without one the tag
    and the text are written as they are.

    Args:
        raw: The unknown node.

    Returns:
        The new element.
    """
    if raw.element is not None:
        return _clone(raw.element)
    return _el(raw.tag, text=raw.text)


def _style_el(node: Style) -> ET.Element:
    """An element for a formatting node."""
    style_attrs = (("name", node.name),) if node.name is not None else ()
    el = _el(node.kind, style_attrs)
    _append_inline(el, node.children)
    return el


def _link_el(node: Link) -> ET.Element:
    """An element for a link."""
    link_attrs: list[tuple[str, str]] = []
    if node.id is not None:
        link_attrs.append(("id", node.id))
    # An empty href is still an href: l:href is required by the schema, and without
    # it the <a> is read back as an unknown element.
    link_attrs.append((_xlink("href"), node.href))
    if node.link_type is not None:
        link_attrs.append(("type", node.link_type))
    el = ET.Element(f"{{{FB2_NS}}}a")
    for name, value in link_attrs:
        el.set(name, value)
    _append_inline(el, node.children)
    return el


def _image_el(image: Image) -> ET.Element:
    """An element for an image."""
    el = ET.Element(f"{{{FB2_NS}}}image")
    if image.id is not None:
        el.set("id", image.id)
    if image.href is not None:
        el.set(_xlink("href"), image.href)
    if image.alt is not None:
        el.set("alt", image.alt)
    if image.title is not None:
        el.set("title", image.title)
    return el


_INLINE_BUILDERS: Mapping[type, Callable[..., ET.Element]] = {
    Style: _style_el,
    Link: _link_el,
    Image: _image_el,
    Raw: _raw_el,
}
"""The builder of every inline node type."""


def _builder_of(
    node: object, table: Mapping[type, Callable[..., ET.Element]]
) -> Callable[..., ET.Element] | None:
    """The builder of the node, or `None` if the node has an unknown type.

    The exact type is looked up first; a subclass falls back to a scan of the
    table, so the table behaves like the chain of `isinstance` checks it
    replaces.

    Args:
        node: The node.
        table: The builder of every known type.

    Returns:
        The builder of the node, or `None`.
    """
    builder = table.get(type(node))
    if builder is not None:
        return builder
    for kind, candidate in table.items():
        if isinstance(node, kind):
            return candidate
    return None


def _inline_el(node: Inline) -> ET.Element:
    """An element for an inline node.

    Args:
        node: The inline node.

    Returns:
        The new element.

    Raises:
        TypeError: The node is not an inline node.
    """
    builder = _builder_of(node, _INLINE_BUILDERS)
    if builder is None:
        raise TypeError(f"not an inline node: {node!r}")
    return builder(node)


def _append_inline(parent: ET.Element, nodes: Iterable[Inline]) -> None:
    """Add inline content to an element.

    Text is not an element: it goes to the `text` of the parent while the
    parent has no children yet and to the `tail` of the last child afterwards.
    Neighbouring text nodes are merged.

    Args:
        parent: The element to fill.
        nodes: The inline content, in document order.
    """
    for node in nodes:
        if isinstance(node, Text):
            if len(parent):
                last = parent[-1]
                last.tail = (last.tail or "") + node.value
            else:
                parent.text = (parent.text or "") + node.value
            continue
        parent.append(_inline_el(node))


def _add(parent: ET.Element, tag: str, value: str | None) -> None:
    """Add an element with a text to the parent, if the text is there.

    An empty value means "the field is not set": the element is not written
    at all, so the file does not carry an empty `<keywords/>`.

    Args:
        parent: The element to fill.
        tag: The name of the element.
        value: The text of the element, or `None`.
    """
    if value is not None:
        parent.append(_el(tag, text=value))


def _id_attrs(id_: str | None) -> tuple[tuple[str, str], ...]:
    """The `id` attribute, if the node has one. It always comes first."""
    return (("id", id_),) if id_ is not None else ()


def _title_el(title: Title) -> ET.Element:
    """An element for a title.

    A title holds paragraphs and empty lines; free text between them is kept
    as it is.

    Args:
        title: The title.

    Returns:
        The new element.
    """
    el = _el("title")
    inline: list[Inline] = []
    for child in title.children:
        if isinstance(child, Paragraph):
            if inline:
                _append_inline(el, inline)
                inline = []
            el.append(_paragraph_el(child))
        elif isinstance(child, EmptyLine):
            if inline:
                _append_inline(el, inline)
                inline = []
            el.append(_el("empty-line"))
        else:
            inline.append(child)
    if inline:
        _append_inline(el, inline)
    return el


def _paragraph_el(paragraph: Paragraph) -> ET.Element:
    """An element for a paragraph."""
    attrs = _id_attrs(paragraph.id)
    if paragraph.style is not None:
        attrs = (*attrs, ("style", paragraph.style))
    el = _el("p", attrs)
    _append_inline(el, paragraph.children)
    return el


def _subtitle_el(subtitle: Subtitle) -> ET.Element:
    """An element for a subtitle."""
    el = _el("subtitle", _id_attrs(subtitle.id))
    _append_inline(el, subtitle.children)
    return el


def _text_author_el(author: TextAuthor) -> ET.Element:
    """An element for a text author."""
    el = _el("text-author", _id_attrs(author.id))
    _append_inline(el, author.children)
    return el


def _verse_el(verse: Verse) -> ET.Element:
    """An element for a verse line."""
    el = _el("v", _id_attrs(verse.id))
    _append_inline(el, verse.children)
    return el


def _stanza_el(stanza: Stanza) -> ET.Element:
    """An element for a stanza.

    Args:
        stanza: The stanza.

    Returns:
        The new element.
    """
    el = _el("stanza")
    if stanza.title is not None:
        el.append(_title_el(stanza.title))
    for subtitle in stanza.subtitles:
        el.append(_subtitle_el(subtitle))
    for verse in stanza.verses:
        el.append(_verse_el(verse))
    return el


def _poem_el(poem: Poem) -> ET.Element:
    """An element for a poem.

    The children follow the order of the schema: `title`, `epigraph`, `stanza`,
    `text-author`, `date`.

    Args:
        poem: The poem.

    Returns:
        The new element.
    """
    el = _el("poem", _id_attrs(poem.id))
    if poem.title is not None:
        el.append(_title_el(poem.title))
    for epigraph in poem.epigraphs:
        el.append(_epigraph_el(epigraph))
    for stanza in poem.stanzas:
        el.append(_stanza_el(stanza))
    for author in poem.text_authors:
        el.append(_text_author_el(author))
    if poem.date is not None:
        el.append(_el("date", text=poem.date))
    return el


def _epigraph_el(epigraph: Epigraph) -> ET.Element:
    """An element for an epigraph."""
    el = _el("epigraph")
    for child in epigraph.children:
        el.append(_block_el(child))
    return el


def _annotation_el(annotation: Annotation) -> ET.Element:
    """An element for an annotation.

    The model keeps the blocks of an annotation without the wrapper, so the
    wrapper is restored here.
    """
    el = _el("annotation")
    for child in annotation.children:
        el.append(_block_el(child))
    return el


def _cite_el(cite: Cite) -> ET.Element:
    """An element for a quote."""
    el = _el("cite", _id_attrs(cite.id))
    for child in cite.children:
        if isinstance(child, TextAuthor):
            el.append(_text_author_el(child))
        else:
            el.append(_block_el(child))
    return el


def _cell_el(cell: Cell) -> ET.Element:
    """An element for a table cell: `<th>` for a header, `<td>` otherwise."""
    attrs = _id_attrs(cell.id)
    if cell.colspan != 1:
        attrs = (*attrs, ("colspan", str(cell.colspan)))
    if cell.rowspan != 1:
        attrs = (*attrs, ("rowspan", str(cell.rowspan)))
    if cell.align is not None:
        attrs = (*attrs, ("align", cell.align))
    el = _el("th" if cell.header else "td", attrs)
    _append_inline(el, cell.children)
    return el


def _row_el(row: Row) -> ET.Element:
    """An element for a table row."""
    el = _el("tr")
    for cell in row.cells:
        el.append(_cell_el(cell))
    return el


def _table_el(table: Table) -> ET.Element:
    """An element for a table."""
    el = _el("table", _id_attrs(table.id))
    for row in table.rows:
        el.append(_row_el(row))
    return el


def _empty_line_el(*_: object) -> ET.Element:
    """An element for an empty line.

    The node carries nothing, so it is not looked at.

    Returns:
        The new element.
    """
    return _el("empty-line")


_BLOCK_BUILDERS: Mapping[type, Callable[..., ET.Element]] = {
    Paragraph: _paragraph_el,
    Subtitle: _subtitle_el,
    EmptyLine: _empty_line_el,
    Title: _title_el,
    Epigraph: _epigraph_el,
    Annotation: _annotation_el,
    Poem: _poem_el,
    Cite: _cite_el,
    TextAuthor: _text_author_el,
    Table: _table_el,
    Image: _image_el,
    Raw: _raw_el,
}
"""The builder of every block node type."""


def _block_el(node: Block) -> ET.Element:
    """An element for a block.

    Args:
        node: The block.

    Returns:
        The new element.

    Raises:
        TypeError: The node is not a block.
    """
    builder = _builder_of(node, _BLOCK_BUILDERS)
    if builder is None:
        raise TypeError(f"not a block: {node!r}")
    return builder(node)


def _section_el(section: Section) -> ET.Element:
    """An element for a section.

    The children keep the order of the document: blocks and nested sections
    are mixed in real books.

    Args:
        section: The section.

    Returns:
        The new element.
    """
    el = _el("section", _id_attrs(section.id))
    for child in section.children:
        if isinstance(child, Section):
            el.append(_section_el(child))
        else:
            el.append(_block_el(child))
    return el


def _body_el(body: Body) -> ET.Element:
    """An element for a body.

    The `id` of the body is **not** written: the schema of the format allows
    only `xml:lang` and `name` on a `<body>`, so an id would make the file
    invalid. The loss is reported by the validation.

    Args:
        body: The body.

    Returns:
        The new element.
    """
    attrs: tuple[tuple[str, str], ...] = ()
    if body.name is not None:
        attrs = (("name", body.name),)
    el = _el("body", attrs)
    for child in body.children:
        if isinstance(child, Section):
            el.append(_section_el(child))
        else:
            el.append(_block_el(child))
    return el


def _author_el(author: Author, tag: str = "author") -> ET.Element:
    """An element for an author.

    The children follow the order of the schema: `first-name`, `middle-name`,
    `last-name`, `nickname`, `home-page`, `email`. The `home-page` goes
    **before** the `email` -- the other order gives a schema-invalid file.

    Args:
        author: The author.
        tag: The element name: `author` or `translator`.

    Returns:
        The new element.
    """
    el = _el(tag)
    for name, value in (
        ("first-name", author.first_name),
        ("middle-name", author.middle_name),
        ("last-name", author.last_name),
        ("nickname", author.nickname),
    ):
        if value is not None:
            el.append(_el(name, text=value))
    for page in author.home_pages:
        el.append(_el("home-page", text=page))
    for email in author.emails:
        el.append(_el("email", text=email))
    return el


def _sequence_el(sequence: Sequence) -> ET.Element:
    """An element for a series."""
    attrs: tuple[tuple[str, str], ...] = ()
    if sequence.name is not None:
        attrs = (("name", sequence.name),)
    if sequence.number is not None:
        attrs = (*attrs, ("number", str(sequence.number)))
    return _el("sequence", attrs)


def _date_el(date: Date) -> ET.Element:
    """An element for a date."""
    attrs: tuple[tuple[str, str], ...] = ()
    if date.iso is not None:
        attrs = (("value", date.iso),)
    if date.lang is not None:
        attrs = (*attrs, (_xml_lang("lang"), date.lang))
    return _el("date", attrs, text=date.value)


def _title_info_el(title_info: TitleInfo) -> ET.Element:
    """An element for the book information.

    Args:
        title_info: The book information.

    Returns:
        The new element.
    """
    el = _el("title-info")
    for genre in title_info.genres:
        el.append(_el("genre", text=genre))
    for author in title_info.authors:
        el.append(_author_el(author))
    _add(el, "book-title", title_info.title)
    if title_info.annotation is not None:
        annotation = _el("annotation")
        for block in title_info.annotation:
            annotation.append(_block_el(block))
        el.append(annotation)
    _add(el, "keywords", title_info.keywords)
    for date in title_info.dates:
        el.append(_date_el(date))
    if title_info.coverpage:
        coverpage = _el("coverpage")
        for image in title_info.coverpage:
            coverpage.append(_image_el(image))
        el.append(coverpage)
    _add(el, "lang", title_info.lang)
    _add(el, "src-lang", title_info.src_lang)
    for translator in title_info.translators:
        el.append(_author_el(translator, "translator"))
    for sequence in title_info.sequences:
        el.append(_sequence_el(sequence))
    return el


def _document_info_el(document_info: DocumentInfo) -> ET.Element:
    """An element for the file information."""
    el = _el("document-info")
    for author in document_info.authors:
        el.append(_author_el(author))
    _add(el, "program-used", document_info.program_used)
    for date in document_info.dates:
        el.append(_date_el(date))
    _add(el, "src-url", document_info.source_url)
    _add(el, "src-ocr", document_info.source_ocr)
    for id_ in document_info.ids:
        el.append(_el("id", text=id_))
    _add(el, "version", document_info.version)
    if document_info.history:
        history = _el("history")
        for text in document_info.history:
            history.append(_el("p", text=text))
        el.append(history)
    _add(el, "publisher", document_info.publisher)
    return el


def _publish_info_el(publish_info: PublishInfo) -> ET.Element:
    """An element for the edition information."""
    el = _el("publish-info")
    for name, value in (
        ("book-name", publish_info.book_name),
        ("publisher", publish_info.publisher),
        ("city", publish_info.city),
        ("year", publish_info.year),
        ("isbn", publish_info.isbn),
    ):
        if value is not None:
            el.append(_el(name, text=value))
    for sequence in publish_info.sequences:
        el.append(_sequence_el(sequence))
    return el


def _custom_info_el(custom_info: CustomInfo) -> ET.Element:
    """An element for a custom information block."""
    attrs: tuple[tuple[str, str], ...] = ()
    if custom_info.info_type is not None:
        attrs = (("info-type", custom_info.info_type),)
    return _el("custom-info", attrs, text=custom_info.text)


def _description_el(description: Description, extra_output: tuple[Raw, ...] = ()) -> ET.Element:
    """An element for the metadata.

    The children follow the order of the schema: `title-info`,
    `src-title-info`, `document-info`, `publish-info`, `custom-info`,
    `output`. The unknown elements of the description are placed where the
    schema wants them: `src-title-info` goes right after the `title-info`,
    `output` goes to the end.

    Args:
        description: The metadata.
        extra_output: The `<output>` elements that were found at the root of the
            document; in the schema they live inside the description.

    Returns:
        The new element.
    """
    el = _el("description")
    el.append(_title_info_el(description.title_info))
    for raw in description.extra:
        if raw.tag == "src-title-info":
            el.append(_raw_el(raw))
    if description.document_info is not None:
        el.append(_document_info_el(description.document_info))
    if description.publish_info is not None:
        el.append(_publish_info_el(description.publish_info))
    for custom_info in description.custom_info:
        el.append(_custom_info_el(custom_info))
    for raw in description.extra:
        if raw.tag != "src-title-info":
            el.append(_raw_el(raw))
    for raw in extra_output:
        el.append(_raw_el(raw))
    return el


def _binary_el(binary: Binary) -> ET.Element:
    """An element for an attached file.

    The base64 payload is written as it is: re-packing it into lines would
    change the bytes of the file for no reason.

    Args:
        binary: The attached file.

    Returns:
        The new element.
    """
    return _el(
        "binary", (("id", binary.id), ("content-type", binary.content_type)), text=binary._b64
    )


def _escape_text(text: str) -> str:
    """Escape the characters that cannot appear in element text.

    A CR is written as a character reference: a raw CR is normalized into a LF
    by every XML parser (XML 1.0 2.11), so the text would change on the way
    back. A LF is left as it is -- it is normalized into a LF anyway.
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")
    )


def _escape_attr(text: str) -> str:
    """Escape the characters that cannot appear in an attribute value.

    A tab, a LF and a CR are written as character references: an XML parser
    normalizes all three into a space in an attribute value (XML 1.0 3.3.3).
    A CR is already a character reference after `_escape_text`.
    """
    return _escape_text(text).replace('"', "&quot;").replace("\t", "&#9;").replace("\n", "&#10;")


def _used_namespaces(root: ET.Element) -> set[str]:
    """The namespaces the tree really uses, in no particular order."""
    used: set[str] = set()
    for el in root.iter():
        for name in (el.tag, *el.attrib):
            if name.startswith("{"):
                used.add(name[1:].partition("}")[0])
    return used


def _prefixes(used: set[str]) -> dict[str, str]:
    """The prefix of every namespace the tree uses.

    The FB2 and the xlink namespaces have the prefixes the format expects; a
    foreign namespace gets a generated one (`ns0`, `ns1`, ...) so that no
    attribute of an unknown subtree loses its namespace.

    Args:
        used: The namespaces the tree uses.

    Returns:
        URI to prefix.
    """
    prefixes: dict[str, str] = {}
    for uri, prefix in _NAMESPACES.items():
        if uri in used:
            prefixes[uri] = prefix
    counter = 0
    for uri in sorted(used):
        if uri not in prefixes and uri != _XML_NS:
            prefixes[uri] = f"ns{counter}"
            counter += 1
    return prefixes


def _tag_parts(name: str) -> tuple[str, str]:
    """The namespace URI and the local name of a tag.

    Args:
        name: The tag of an element or of an attribute.

    Returns:
        The URI (empty if the name has no namespace) and the local name.
    """
    if name.startswith("{"):
        uri, _, local = name[1:].partition("}")
        return uri, local
    return "", name


_UNSAFE_NAME_CHARS = frozenset(" \t\r\n:<>/&\"'=")


def _safe_name(name: str) -> str:
    """A name that every parser reads back as a name.

    A tag of an unknown element may carry an unbound prefix (`a:b`) or a
    character XML does not allow in a name: lxml in the tolerant mode keeps
    such a tag as a plain string. Writing it as it is would produce a file no
    parser can read. `validate` blocks such a book as an error; this function
    keeps the output readable when the caller writes with `strict=False`.

    Args:
        name: The local name of an element or of an attribute.

    Returns:
        The name with the unsafe characters replaced by `_`.
    """
    if not name:
        return "_"
    safe = "".join("_" if ch in _UNSAFE_NAME_CHARS else ch for ch in name)
    if safe[0].isdigit() or safe[0] in ".-":
        safe = f"_{safe}"
    return safe


def _qualified(uri: str, local: str, prefixes: dict[str, str]) -> str:
    """The name of an element or of an attribute, with its prefix.

    Args:
        uri: The namespace URI of the name.
        local: The local name.
        prefixes: URI to prefix.

    Returns:
        The name as it is written in the file.
    """
    prefix = prefixes.get(uri, "")
    if prefix:
        return f"{prefix}:{local}"
    return _safe_name(local)


def _render_start(
    el: ET.Element, out: list[str], prefixes: dict[str, str], declarations: str
) -> str:
    """The start tag of an element.

    Args:
        el: The element.
        out: The buffer the text is appended to.
        prefixes: URI to prefix.
        declarations: Namespace declarations to write right after the name of the element.

    Returns:
        The name of the element, to close the tag with.
    """
    uri, local = _tag_parts(el.tag)
    name = _qualified(uri, local, prefixes)
    out.append(f"<{name}")
    if declarations:
        out.append(declarations)
    for attr, value in el.attrib.items():
        attr_uri, attr_local = _tag_parts(attr)
        attr_name = _qualified(attr_uri, attr_local, prefixes)
        out.append(f' {attr_name}="{_escape_attr(value)}"')
    return name


def _render_body(el: ET.Element, out: list[str], prefixes: dict[str, str], name: str) -> None:
    """The content and the end tag of an element.

    Args:
        el: The element.
        out: The buffer the text is appended to.
        prefixes: URI to prefix.
        name: The name of the element, to close the tag with.
    """
    out.append(">")
    if el.text:
        out.append(_escape_text(el.text))
    for child in el:
        _render(child, out, prefixes)
        if child.tail:
            out.append(_escape_text(child.tail))
    out.append(f"</{name}>")


def _render(
    el: ET.Element, out: list[str], prefixes: dict[str, str], declarations: str = ""
) -> None:
    """Render an element and its children into a list of strings.

    Args:
        el: The element.
        out: The buffer the text is appended to.
        prefixes: URI to prefix.
        declarations: Namespace declarations to write right after the name of the element;
            only the root has them.
    """
    name = _render_start(el, out, prefixes, declarations)
    if not len(el) and not el.text:
        out.append("/>")
        return
    _render_body(el, out, prefixes, name)


def _namespace_declarations(root: ET.Element) -> tuple[dict[str, str], str]:
    """The prefixes of the tree and the declarations the root needs.

    The prefixes are assigned locally: the output never depends on a global
    registry, so the same model always gives the same bytes.

    Args:
        root: The root element.

    Returns:
        The URI to prefix map and the declaration string for the root tag.
    """
    used = _used_namespaces(root)
    prefixes = _prefixes(used)
    declarations: list[str] = []
    default: str | None = None
    for uri in sorted(used):
        prefix = prefixes.get(uri)
        if prefix is None or prefix == "xml":
            # The `xml` namespace is predefined and needs no declaration.
            continue
        if prefix:
            declarations.append(f' xmlns:{prefix}="{_escape_attr(uri)}"')
        else:
            default = uri
    if default is not None:
        declarations.insert(0, f' xmlns="{_escape_attr(default)}"')
    return prefixes, "".join(declarations)


def _render_root(root: ET.Element) -> str:
    """Render the root element with the namespace declarations it needs."""
    prefixes, declarations = _namespace_declarations(root)
    out: list[str] = []
    _render(root, out, prefixes, declarations)
    return "".join(out)


def serialize_bytes(root: ET.Element) -> bytes:
    """Serialize an element tree to bytes.

    The output is compact: there are no line breaks between the elements. The
    namespace prefixes are assigned locally, so the result does not depend on
    any global registry.

    Args:
        root: The root element.

    Returns:
        The XML bytes with a declaration and a trailing newline.
    """
    body = _render_root(root)
    return f"<?xml version='1.0' encoding='utf-8'?>\n{body}\n".encode()


def build_tree(book: FictionBook) -> ET.Element:
    """Build the element tree of a book.

    The children of the root follow the order of the schema: `stylesheet`,
    `description`, `body`, `binary`. The `<output>` element is not allowed at
    the root -- in the schema it lives inside the `<description>`, so it is
    moved there.

    Args:
        book: The book.

    Returns:
        The root element.
    """
    root = _el("FictionBook")
    output: list[Raw] = []
    for raw in book.extra:
        if raw.tag == "output":
            output.append(raw)
            continue
        root.append(_raw_el(raw))
    root.append(_description_el(book.description, tuple(output)))
    for body in book.bodies:
        root.append(_body_el(body))
    for binary in book.binaries:
        root.append(_binary_el(binary))
    return root


def serialize_book(book: FictionBook, *, pretty: bool = False) -> bytes:
    """Serialize a book to bytes.

    Args:
        book: The book.
        pretty: Indented output; the compact output is used by default.

    Returns:
        The XML bytes.
    """
    if pretty:
        from fb2kit.write.pretty import render

        root = build_tree(book)
        return f"<?xml version='1.0' encoding='utf-8'?>\n{render(root)}\n".encode()
    return serialize_bytes(build_tree(book))
