import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from fb2kit.model.inline import Image, Link, Raw, Style, Text
from fb2kit.parser import FB2_NS, XLINK_NS
from fb2kit.write.serialize import _append_inline, _clone, _el, _inline_el, _raw_el, serialize_bytes


@contextmanager
def _fb2_prefixes() -> Iterator[None]:
    """The FB2 prefixes for `ET.tostring`, restored after the block.

    The writer never claims the prefixes in the global registry of `xml.etree`:
    a test that wants a readable `ET.tostring` asks for the prefixes itself.
    """
    before = dict(ET._namespace_map)
    ET._namespace_map[FB2_NS] = ""
    ET._namespace_map[XLINK_NS] = "l"
    try:
        yield
    finally:
        ET._namespace_map.clear()
        ET._namespace_map.update(before)


def _xml(el: ET.Element) -> str:
    with _fb2_prefixes():
        return ET.tostring(el, encoding="unicode")


def test_el_uses_fb2_namespace_and_attribute_order() -> None:
    """С8: an element uses the namespace of the format and keeps the order of its attributes."""
    el = _el("p", (("id", "p1"), ("style", "x")), text="hi")
    assert el.tag == f"{{{FB2_NS}}}p"
    assert list(el.attrib) == ["id", "style"]


def test_inline_text_is_put_in_text_and_tail() -> None:
    """С81: the text of an inline node goes to text and to tail."""
    p = _el("p")
    _append_inline(p, (Text("a"), Style("strong", (Text("b"),)), Text(" c")))
    assert p.text == "a"
    assert p[0].tail == " c"
    assert p[0].tag == f"{{{FB2_NS}}}strong"


def test_adjacent_text_nodes_are_merged() -> None:
    """С81: the adjacent text nodes are merged."""
    p = _el("p")
    _append_inline(p, (Text("a"), Text("b"), Style("emphasis", (Text("c"),)), Text("d")))
    assert p.text == "ab"
    assert p[-1].tail == "d"


def test_link_emits_xlink_href_type_and_id() -> None:
    """С82: a link emits the href, the type and the id."""
    el = _inline_el(Link("#n1", "note", (Text("1"),), id="a1"))
    assert el.tag == f"{{{FB2_NS}}}a"
    assert el.get(f"{{{XLINK_NS}}}href") == "#n1"
    assert el.get("type") == "note"
    assert el.get("id") == "a1"


def test_style_name_is_emitted_only_for_style() -> None:
    """С82: the name is emitted for a style only."""
    assert _inline_el(Style("style", (), name="code")).get("name") == "code"
    assert _inline_el(Style("strong", ())).get("name") is None


def test_image_attributes() -> None:
    """С82: an image emits its alt, its title and its id."""
    el = _inline_el(Image(href="#img", alt="a", title="t", id="i1"))
    assert el.get(f"{{{XLINK_NS}}}href") == "#img"
    assert (el.get("alt"), el.get("title"), el.get("id")) == ("a", "t", "i1")


def test_paragraph_with_mixed_inline_escapes_correctly() -> None:
    """С6: a paragraph with an inline node escapes the special characters."""
    p = _el("p")
    _append_inline(p, (Text("A & B < C "), Style("emphasis", (Text("курсив"),))))
    out = _xml(p)
    assert "<emphasis>курсив</emphasis>" in out
    assert "A &amp; B &lt; C" in out


def test_raw_with_element_keeps_the_subtree() -> None:
    """С83: a raw with an element keeps the subtree."""
    src = ET.fromstring("<foo><bar a='1'>x</bar>y</foo>")
    out = _raw_el(Raw("foo", "xy", src))
    assert _xml(out) == '<foo><bar a="1">x</bar>y</foo>'


def test_clone_drops_tail() -> None:
    """С36: the clone of a raw drops the tail of its root."""
    # The tail is already in the model as a separate Text; copying it would write the text twice.
    src = ET.fromstring("<foo/>")
    src.tail = " after"
    assert _clone(src).tail is None


def test_raw_element_tail_is_not_duplicated() -> None:
    """С36: the tail of a raw is not written twice."""
    # <p>word <em>x</em> word</p>: <em> is an unknown tag, the model keeps it as Raw.
    p = _el("p")
    em = ET.fromstring("<em>x</em>")
    em.tail = " word"
    _append_inline(p, (Text("word "), Raw("em", "x", em), Text(" word")))
    out = _xml(p)
    assert out.count("word") == 2  # 'word ' before <em> and ' word' after -- each exactly once
    assert "> word<" not in out.replace("</em> word<", "SENTINEL")


def test_clone_keeps_descendant_tails() -> None:
    """С36: the clone of a raw keeps the tails of the descendants."""
    # The tail of the cloned root is already in the model as a separate Text, but the tails of the
    # descendants are not stored anywhere -- a recursive clone must keep them.
    src = ET.fromstring("<foo>mid<i>x</i>after</foo>")
    clone = _clone(src)
    assert clone[0].tail == "after"


def test_clone_copies_an_lxml_element() -> None:
    """С36: the clone of a raw copies an lxml element."""
    # The book may be parsed with the lxml backend, then Raw.element is an lxml element.
    lxml_etree = pytest.importorskip("lxml.etree")
    src = lxml_etree.fromstring("<foo a='1'>mid<i>x</i>after</foo>")
    clone = _clone(src)
    assert clone.tag == "foo"
    assert clone.get("a") == "1"
    assert clone.text == "mid"
    assert clone[0].tail == "after"


def test_raw_without_element_falls_back_to_text() -> None:
    """С83: a raw without an element falls back to its text."""
    out = _raw_el(Raw("foo", "bar"))
    assert _xml(out) == f'<foo xmlns="{FB2_NS}">bar</foo>'


def test_serialize_bytes_has_declaration_and_trailing_newline() -> None:
    """С41: the bytes have a declaration and a trailing newline."""
    root = _el("FictionBook")
    root.append(_el("description"))
    data = serialize_bytes(root)
    assert data.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    assert data.endswith(b"\n")
    assert b"\n  " not in data  # компактный вывод: отступов нет


def test_serialize_bytes_declares_the_namespaces_it_uses() -> None:
    """С84: the bytes declare the namespaces they use."""
    root = _el("FictionBook")
    link = ET.Element(f"{{{FB2_NS}}}a")
    link.set(f"{{{XLINK_NS}}}href", "#n1")
    root.append(link)
    data = serialize_bytes(root)
    assert b'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"' in data
    assert b'xmlns:l="http://www.w3.org/1999/xlink"' in data
    assert b"l:href" in data


def test_serialize_bytes_declares_namespaces_on_a_childless_root() -> None:
    """С84: the namespaces are declared on a root without children."""
    # The declarations belong to the start tag: after the '/' of a self-closing tag the file
    # is not well-formed and no parser can read it.
    lxml_etree = pytest.importorskip("lxml.etree")
    root = _el("FictionBook")
    data = serialize_bytes(root)
    assert b'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"' in data
    ET.fromstring(data)  # does not raise: the declarations are inside the start tag
    lxml_etree.fromstring(data)


def test_serialize_bytes_declares_namespaces_inside_the_start_tag() -> None:
    """С84: the namespaces are declared inside the start tag."""
    # The declaration goes right after the name of the root, before the attributes.
    root = _el("FictionBook", (("id", "book1"),))
    data = serialize_bytes(root)
    assert b'<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" id="book1"/>' in data
    ET.fromstring(data)


def test_serialize_bytes_declares_namespaces_before_an_attribute_with_a_gt() -> None:
    """С84: the namespaces are declared before an attribute with a gt."""
    # A '>' inside an attribute value must not be taken for the end of the start tag.
    root = _el("FictionBook", (("id", "a>b"),))
    data = serialize_bytes(root)
    ET.fromstring(data)
    assert ET.fromstring(data).get("id") == "a>b"
    assert b'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"' in data


def test_serialize_bytes_output_is_valid_xml() -> None:
    """С84: the bytes are a valid XML document."""
    root = _el("FictionBook")
    link = ET.Element(f"{{{FB2_NS}}}a")
    link.set(f"{{{XLINK_NS}}}href", "#n1")
    root.append(link)
    data = serialize_bytes(root)
    ET.fromstring(data)  # не падает: префиксы объявлены


def test_serialize_bytes_keeps_a_foreign_namespace() -> None:
    """С84: the bytes keep a foreign namespace."""
    # An attribute of an unknown subtree must not lose its namespace.
    src = ET.fromstring("<foo xmlns:z='http://example.com/ns' z:attr='v'/>")
    root = _el("p")
    root.append(_raw_el(Raw("foo", "x", src)))
    data = serialize_bytes(root)
    assert b"http://example.com/ns" in data
    assert b"z:attr" not in data  # the prefix is ours, the namespace is kept
    again = ET.fromstring(data)
    attr = next(iter(again[0].attrib))
    assert attr == "{http://example.com/ns}attr"


def test_the_writer_does_not_mutate_the_global_namespace_map() -> None:
    """С85: the writer does not change the global namespace map."""
    # The prefixes of the written file are the writer's own business: the global registry
    # of xml.etree belongs to the whole process and must not be touched.
    before = dict(ET._namespace_map)
    root = _el("FictionBook")
    root.append(_el("description"))
    serialize_bytes(root)
    assert ET._namespace_map == before


def test_importing_the_writer_does_not_mutate_the_global_namespace_map() -> None:
    """С85: the import of the writer does not change the global map."""
    # The import must not claim the FB2 prefixes in the registry of the whole process:
    # a foreign tree serialized with ET.tostring would get a default namespace instead
    # of an ns0 prefix.
    code = (
        "import xml.etree.ElementTree as ET;"
        "import fb2kit.write.serialize;"
        "print(sorted(ET._namespace_map.items()))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    expected = subprocess.run(
        [
            sys.executable,
            "-c",
            "import xml.etree.ElementTree as ET;print(sorted(ET._namespace_map.items()))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == expected


def test_the_output_does_not_depend_on_the_global_namespace_map() -> None:
    """С85: the output does not depend on the global namespace map."""
    # A foreign registration must not change a single byte of the output.
    root = _el("FictionBook")
    link = ET.Element(f"{{{FB2_NS}}}a")
    link.set(f"{{{XLINK_NS}}}href", "#n1")
    root.append(link)
    expected = serialize_bytes(root)
    before = dict(ET._namespace_map)
    try:
        ET.register_namespace("x", FB2_NS)
        assert serialize_bytes(root) == expected
    finally:
        ET._namespace_map.clear()
        ET._namespace_map.update(before)


def test_a_tag_with_an_unbound_prefix_is_sanitized() -> None:
    """С94: strict=False still writes a file every parser can read."""
    src = ET.fromstring("<unknown/>")
    src.set("o:style", "x")
    raw = Raw("o:p", "x", src)
    root = _el("FictionBook")
    p = _el("p")
    _append_inline(p, (Text("a"), raw, Text("c")))
    root.append(p)
    out = serialize_bytes(root)
    assert b"o:p" not in out and b"o:style" not in out
    ET.fromstring(out)
