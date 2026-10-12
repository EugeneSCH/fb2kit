# tests/test_inline.py
from xml.etree import ElementTree as ET

import pytest

from fb2kit.builder import Builder
from fb2kit.model.inline import Image, Link, Raw, Style, Text
from fb2kit.parser import FB2_NS, XLINK_NS


def _p(inner: str) -> ET.Element:
    return ET.fromstring(f'<p xmlns="{FB2_NS}" xmlns:l="{XLINK_NS}">{inner}</p>')


def _bind(inner: str):
    ctx = Builder(diagnostics=[], index={})
    return ctx, __import__("fb2kit.model.bind", fromlist=["x"]).bind_inline(_p(inner), ctx)


def test_bare_text_becomes_text_run() -> None:
    _, nodes = _bind("hello")
    assert nodes == (Text("hello"),)


def test_style_kinds_are_mapped() -> None:
    _, nodes = _bind(
        "<strong>a</strong><emphasis>b</emphasis><strikethrough>c</strikethrough><code>d</code>"
    )
    assert [n.kind for n in nodes if isinstance(n, Style)] == [
        "strong",
        "emphasis",
        "strikethrough",
        "code",
    ]


def test_styles_nest() -> None:
    _, nodes = _bind("<strong>bold <emphasis>both</emphasis></strong>")
    style = nodes[0]
    assert isinstance(style, Style) and isinstance(style.children[1], Style)


def test_link_keeps_href_children_and_noteness() -> None:
    _, nodes = _bind('<a l:href="#n1" type="note">1</a>')
    link = nodes[0]
    assert isinstance(link, Link)
    assert link.href == "#n1" and link.is_note is True
    assert link.children == (Text("1"),)


def test_link_without_type_is_not_a_note() -> None:
    _, nodes = _bind('<a l:href="#s1">see</a>')
    assert nodes[0].is_note is False


def test_a_without_href_is_raw() -> None:
    ctx, nodes = _bind('<a id="top"/>')
    assert isinstance(nodes[0], Raw) and nodes[0].tag == "a"
    assert nodes[0].element is not None and nodes[0].element.get("id") == "top"
    assert ctx.diagnostics


def test_image_reads_href_alt_title() -> None:
    _, nodes = _bind('<image l:href="#img1" alt="cover" title="Cover"/>')
    assert nodes[0] == Image(href="#img1", alt="cover", title="Cover")


def test_unknown_element_is_preserved_as_raw_and_reported() -> None:
    import fb2kit.report as report

    ctx, nodes = _bind("<foo>bar</foo>")
    assert nodes[0] == Raw(tag="foo", text="bar")
    assert [d.code for d in ctx.diagnostics] == [report.ELEMENT_UNKNOWN]


def test_inline_nodes_are_frozen_and_hashable() -> None:
    _, nodes = _bind("<strong>a</strong>")
    hash(nodes[0])


def test_tail_text_after_inline_is_kept_in_order() -> None:
    _, nodes = _bind("a<strong>b</strong>c")
    assert nodes == (Text("a"), Style("strong", (Text("b"),)), Text("c"))


def test_whitespace_inside_paragraph_is_preserved_verbatim() -> None:
    _, nodes = _bind("  a \n b  ")
    assert nodes == (Text("  a \n b  "),)


def test_empty_paragraph_has_no_inline_nodes() -> None:
    assert _bind("")[1] == ()


@pytest.mark.parametrize("kind", ["sub", "sup", "style"])
def test_remaining_style_kinds(kind: str) -> None:
    _, nodes = _bind(f"<{kind}>x</{kind}>")
    assert nodes == (Style(kind, (Text("x"),)),)


def test_named_style_keeps_its_name() -> None:
    _, nodes = _bind('<style name="poem-line">x</style>')
    assert nodes[0] == Style("style", (Text("x"),), name="poem-line")


def test_unprefixed_href_is_a_fallback() -> None:
    _, nodes = _bind('<a href="#n1">1</a>')
    assert isinstance(nodes[0], Link) and nodes[0].href == "#n1"


def test_raw_keeps_nested_children_in_element() -> None:
    _, nodes = _bind("<foo><bar>x</bar></foo>")
    raw = nodes[0]
    assert isinstance(raw, Raw) and raw.element is not None and len(raw.element) == 1


def test_raw_equality_ignores_element() -> None:
    assert Raw("foo", "x", element=_p("<foo/>")) == Raw("foo", "x")


def test_inline_nodes_cannot_be_mutated() -> None:
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        Text("a").value = "b"  # type: ignore[misc]
