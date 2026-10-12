# tests/test_links.py
from pathlib import Path

import pytest

import fb2kit.report as report
from fb2kit.builder import Builder
from fb2kit.model.bind import bind_body
from fb2kit.model.inline import Link
from fb2kit.model.links import check_links
from fb2kit.model.structure import Body, Section
from fb2kit.parser import parse_tree
from fb2kit.report import Severity

FIXTURES = Path(__file__).parent / "fixtures"


def _bodies(ctx: Builder) -> list[Body]:
    tree = parse_tree((FIXTURES / "notes-and-links.fb2").read_text(encoding="utf-8"))
    bodies = [bind_body(e, ctx) for e in tree.root if e.tag.endswith("}body")]
    check_links(bodies, ctx)
    return bodies


def test_ids_are_indexed() -> None:
    ctx = Builder(diagnostics=[], index={})
    _bodies(ctx)
    assert "n1" in ctx.index and isinstance(ctx.index["n1"], Section)


def test_notes_body_is_detected_by_name() -> None:
    ctx = Builder(diagnostics=[], index={})
    bodies = _bodies(ctx)
    assert [b.is_notes for b in bodies] == [False, True, True]


def test_non_standard_notes_name_is_reported() -> None:
    ctx = Builder(diagnostics=[], index={})
    _bodies(ctx)
    assert report.NOTES_BODY_NAME in [d.code for d in ctx.diagnostics]


def test_link_targets_a_section() -> None:
    ctx = Builder(diagnostics=[], index={})
    _bodies(ctx)
    assert isinstance(ctx.index["s2"], Section)


def test_broken_link_is_reported_as_warning_not_error() -> None:
    ctx = Builder(diagnostics=[], index={})
    _bodies(ctx)
    broken = [d for d in ctx.diagnostics if d.code == report.LINK_UNRESOLVED]
    assert broken and all(d.severity is Severity.WARNING for d in broken)


def test_note_link_is_flagged() -> None:
    ctx = Builder(diagnostics=[], index={})
    bodies = _bodies(ctx)
    links = [n for b in bodies for s in b.sections for n in _walk_links(s)]
    notes = [link for link in links if link.is_note]
    assert [link.href for link in notes] == ["#n1"]


def test_duplicate_id_is_reported_once() -> None:
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS

    el = ET.fromstring(
        f'<body xmlns="{FB2_NS}"><section id="d"><p>x</p></section>'
        '<section id="d"><p>y</p></section></body>'
    )
    ctx = Builder(diagnostics=[], index={})
    bind_body(el, ctx)
    assert [d.code for d in ctx.diagnostics].count(report.DUPLICATE_ID) == 1


def test_iter_nodes_reaches_links_in_poem_titles() -> None:
    from fb2kit.model import iter_nodes
    from fb2kit.model.structure import Paragraph, Poem, Title

    link = Link(href="#x")
    poem = Poem(title=Title(children=(Paragraph(children=(link,)),)))
    assert link in list(iter_nodes(poem))


def _walk_links(node):
    from fb2kit.model import iter_nodes
    from fb2kit.model.inline import Link

    return [n for n in iter_nodes(node) if isinstance(n, Link)]


def _check(href: str) -> list[str]:
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS, XLINK_NS

    el = ET.fromstring(
        f'<body xmlns="{FB2_NS}" xmlns:l="{XLINK_NS}"><section id="s"><p id="p1">'
        f'<a l:href="{href}">x</a></p></section></body>'
    )
    ctx = Builder(diagnostics=[], index={})
    check_links([bind_body(el, ctx)], ctx)
    return [d.code for d in ctx.diagnostics]


@pytest.mark.parametrize(
    ("href", "codes"),
    [
        ("#p1", []),
        ("#s", []),
        ("#", [report.LINK_UNRESOLVED]),
        ("#nope", [report.LINK_UNRESOLVED]),
        ("http://example.com/x", []),
        ("mailto:a@b.c", []),
        ("relative.html", []),
    ],
)
def test_link_classes(href: str, codes: list[str]) -> None:
    assert _check(href) == codes


def test_duplicate_id_across_bodies_keeps_first() -> None:
    import xml.etree.ElementTree as ET

    from fb2kit.parser import FB2_NS

    ctx = Builder(diagnostics=[], index={})
    first = bind_body(
        ET.fromstring(f'<body xmlns="{FB2_NS}"><section id="d"><p>a</p></section></body>'), ctx
    )
    bind_body(
        ET.fromstring(
            f'<body xmlns="{FB2_NS}" name="notes"><section id="d"><p>b</p></section></body>'
        ),
        ctx,
    )
    assert ctx.index["d"] is first.sections[0]
    assert [d.code for d in ctx.diagnostics].count(report.DUPLICATE_ID) == 1


@pytest.mark.parametrize(
    ("name", "is_notes"), [(None, False), ("main", False), ("", False), ("notes", True)]
)
def test_body_name_classification(name: str | None, is_notes: bool) -> None:
    assert Body(name=name).is_notes is is_notes
