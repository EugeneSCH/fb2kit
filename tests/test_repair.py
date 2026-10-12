# tests/test_repair.py
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

import fb2kit.report as report
from fb2kit.backends import Backend
from fb2kit.errors import Fb2ParseError
from fb2kit.parser import FB2_NS, parse_tree
from fb2kit.repair import close_unterminated, repair_text
from fb2kit.report import Mode

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_bare_amp_is_escaped_without_touching_entities() -> None:
    res = repair_text("<p>A &amp; B & C &lt; D</p>")
    assert "&amp; B" in res.text and "& C " not in res.text
    assert "&lt;" in res.text and "&#" not in res.text.replace("&amp;", "")
    assert [d.code for d in res.diagnostics] == [report.XML_BARE_AMP]


def test_numeric_references_survive() -> None:
    assert "&#1055;" in repair_text("<p>&#1055; &</p>").text


def test_control_chars_are_removed_and_reported() -> None:
    res = repair_text("<p>a\x0cb</p>")
    assert res.text == "<p>ab</p>"
    assert [d.code for d in res.diagnostics] == [report.XML_CONTROL_CHARS]


def test_html_named_entity_becomes_literal_text() -> None:
    res = repair_text("<p>a&nbsp;b</p>")
    assert res.text == "<p>a&amp;nbsp;b</p>"
    assert [d.code for d in res.diagnostics] == [report.XML_BARE_AMP]


def test_invalid_xml_chars_beyond_c0_are_removed() -> None:
    assert repair_text("<p>a\ufffeb\ud800c</p>").text == "<p>abc</p>"


def test_clean_text_needs_no_repair() -> None:
    res = repair_text("<p>ok</p>")
    assert res.text == "<p>ok</p>" and res.diagnostics == ()


def test_unterminated_tags_are_closed_in_reverse_order() -> None:
    res = close_unterminated("<FictionBook><body><section><p>x")
    assert res.text.endswith("</p></section></body></FictionBook>")
    assert [d.code for d in res.diagnostics] == [report.XML_AUTO_CLOSED]


def test_self_closing_and_comments_do_not_confuse_the_stack() -> None:
    res = close_unterminated("<a><b/><!-- <c> --><d>")
    assert res.text.endswith("</d></a>")


def test_unbound_xlink_prefix_is_repaired_in_tolerant() -> None:
    text = (
        f'<FictionBook xmlns="{FB2_NS}">'
        "<body><section><p><a l:href='#n1'>1</a></p></section></body></FictionBook>"
    )
    with pytest.raises(Fb2ParseError):
        parse_tree(text, mode=Mode.STRICT)
    tree = parse_tree(text, mode=Mode.TOLERANT)
    assert tree.root.tag == f"{{{FB2_NS}}}FictionBook"
    assert [d.code for d in tree.diagnostics] == [report.NS_PREFIX_INJECTED]


@pytest.mark.parametrize("name", ["bare-amp.fb2", "unclosed-tag.fb2", "control-chars.fb2"])
def test_tolerant_parses_every_defect(name: str) -> None:
    tree = parse_tree(_read(name), mode=Mode.TOLERANT)
    assert tree.root.tag.endswith("}FictionBook")
    assert tree.diagnostics


@pytest.mark.parametrize("name", ["bare-amp.fb2", "control-chars.fb2", "unclosed-tag.fb2"])
def test_strict_fails_on_the_same_files(name: str) -> None:
    with pytest.raises(Fb2ParseError):
        parse_tree(_read(name), mode=Mode.STRICT)


def test_tolerant_does_not_alter_text_content() -> None:
    tree = parse_tree(_read("bare-amp.fb2"), mode=Mode.TOLERANT)
    paragraphs = [el.text for el in tree.root.iter() if el.tag.endswith("}p")]
    assert any(text and "&" in text for text in paragraphs if text)


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        ("<p>a &</p>", "<p>a &amp;</p>"),
        ("<p>&amp x</p>", "<p>&amp;amp x</p>"),
        ("<p>&#x41; &#;</p>", "<p>&#x41; &amp;#;</p>"),
        ("<p>&quot;&apos;&gt;</p>", "<p>&quot;&apos;&gt;</p>"),
        ("<p a='x & y'>z</p>", "<p a='x &amp; y'>z</p>"),
    ],
)
def test_ampersand_repair_edge_cases(raw: str, fixed: str) -> None:
    assert repair_text(raw).text == fixed


@pytest.mark.parametrize(
    ("raw", "tail"),
    [
        ("<a><![CDATA[<x>]]><b>", "</b></a>"),
        ("<a><?pi <x>?><b>", "</b></a>"),
        ("<a t='>'><b>", "</b></a>"),
    ],
)
def test_close_unterminated_skips_cdata_pi_and_quoted_gt(raw: str, tail: str) -> None:
    assert close_unterminated(raw).text == raw + tail


def test_balanced_text_is_not_touched_by_close_unterminated() -> None:
    res = close_unterminated("<a><b/>x</a>")
    assert res.text == "<a><b/>x</a>" and res.diagnostics == ()


def test_only_xlink_prefix_is_injected() -> None:
    text = f'<FictionBook xmlns="{FB2_NS}"><body><fb:p>x</fb:p></body></FictionBook>'
    with pytest.raises(Fb2ParseError):
        parse_tree(text, mode=Mode.TOLERANT, backend=Backend.STDLIB)


def test_mismatched_close_tag_is_not_repaired_on_stdlib() -> None:
    text = f'<FictionBook xmlns="{FB2_NS}"><body><section><p>x</p></body></FictionBook>'
    with pytest.raises(Fb2ParseError):
        parse_tree(text, mode=Mode.TOLERANT, backend=Backend.STDLIB)


@given(
    st.text(
        alphabet=st.characters(blacklist_characters="&<>", blacklist_categories=("Cc", "Cs", "Cn"))
    )
)
def test_repair_is_identity_on_clean_text(text: str) -> None:
    res = repair_text(f"<p>{text}</p>")
    assert res.text == f"<p>{text}</p>" and res.diagnostics == ()
