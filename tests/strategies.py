"""Hypothesis strategies producing valid FB2 documents."""

from conftest import fixture_text
from hypothesis import strategies as st

NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
_WORD = (
    st.text(alphabet="abcdxyz " + fixture_text("alphabet.txt"), min_size=1, max_size=12)
    .map(str.strip)
    .filter(bool)
)
_ID = st.sampled_from(["n1", "n2", "s1", "missing"])


@st.composite
def _para(draw: st.DrawFn) -> str:
    text = draw(_WORD)
    if draw(st.booleans()):
        text += f'<a l:href="#{draw(_ID)}">{draw(_WORD)}</a>'
    return f"<p>{text}</p>"


@st.composite
def _block(draw: st.DrawFn) -> str:
    kind = draw(st.sampled_from(["p", "subtitle", "empty-line", "poem", "cite", "table"]))
    if kind == "p":
        return draw(_para())
    if kind == "subtitle":
        return f"<subtitle>{draw(_WORD)}</subtitle>"
    if kind == "empty-line":
        return "<empty-line/>"
    if kind == "poem":
        return f"<poem><stanza><v>{draw(_WORD)}</v><v>{draw(_WORD)}</v></stanza></poem>"
    if kind == "cite":
        return f"<cite>{draw(_para())}</cite>"
    return f"<table><tr><td>{draw(_WORD)}</td><th>{draw(_WORD)}</th></tr></table>"


@st.composite
def fb2_document(draw: st.DrawFn) -> str:
    authors = "".join(
        f"<author><first-name>{draw(_WORD)}</first-name><last-name>{draw(_WORD)}</last-name></author>"
        for _ in range(draw(st.integers(0, 3)))
    )
    sections = "".join(
        f'<section id="s{i + 1}"><title><p>{draw(_WORD)}</p></title>'
        + "".join(draw(st.lists(_block(), max_size=5)))
        + "</section>"
        for i in range(draw(st.integers(1, 3)))
    )
    notes = '<body name="notes"><section id="n1"><p>note</p></section></body>'
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<FictionBook xmlns="{NS}" xmlns:l="http://www.w3.org/1999/xlink">'
        f"<description><title-info><genre>prose</genre>{authors}"
        f"<book-title>{draw(_WORD)}</book-title><lang>ru</lang></title-info></description>"
        f"<body>{sections}</body>{notes}</FictionBook>"
    )


def binary_payload() -> st.SearchStrategy[bytes]:
    return st.binary(min_size=0, max_size=4096)
