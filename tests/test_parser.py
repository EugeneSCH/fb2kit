# tests/test_parser.py
from pathlib import Path

import pytest

import fb2kit.report as report
from fb2kit.backends import Backend, resolve_backend
from fb2kit.errors import Fb2Error, Fb2ParseError
from fb2kit.parser import FB2_NS, XLINK_NS, parse_tree
from fb2kit.report import Mode

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_minimal_document() -> None:
    tree = parse_tree(_read("minimal.fb2"))
    assert tree.root.tag == f"{{{FB2_NS}}}FictionBook"
    assert tree.backend in {"stdlib", "lxml"}


def test_missing_namespace_is_substituted_and_reported() -> None:
    tree = parse_tree("<FictionBook><description/></FictionBook>")
    assert tree.root.tag == f"{{{FB2_NS}}}FictionBook"
    assert [d.code for d in tree.diagnostics] == [report.NS_MISSING]


def test_foreign_namespace_is_reported() -> None:
    tree = parse_tree('<FictionBook xmlns="http://example.org/other"/>')
    assert tree.root.tag == f"{{{FB2_NS}}}FictionBook"
    assert [d.code for d in tree.diagnostics] == [report.NS_FOREIGN]


def test_malformed_xml_in_strict_carries_location() -> None:
    with pytest.raises(Fb2ParseError) as exc:
        parse_tree("<FictionBook><description></FictionBook>")
    assert exc.value.path is not None or exc.value.line is not None


def test_not_xml_at_all_is_a_parse_error() -> None:
    with pytest.raises(Fb2ParseError):
        parse_tree("just a text file")


def test_explicit_stdlib_backend_works_without_lxml() -> None:
    assert resolve_backend(Backend.STDLIB) == "stdlib"


def test_explicit_lxml_backend_requires_the_extra() -> None:
    try:
        import lxml  # noqa: F401
    except ImportError:
        with pytest.raises(Fb2Error, match="lxml"):
            resolve_backend(Backend.LXML)
    else:
        assert resolve_backend(Backend.LXML) == "lxml"


def test_auto_prefers_lxml_when_available() -> None:
    import importlib.util

    expected = "lxml" if importlib.util.find_spec("lxml") else "stdlib"
    assert resolve_backend(Backend.AUTO) == expected


def test_xml_declaration_with_encoding_is_accepted_by_any_backend() -> None:
    text = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        f'<FictionBook xmlns="{FB2_NS}"><body/></FictionBook>'
    )
    for backend in (Backend.STDLIB, Backend.AUTO):
        assert parse_tree(text, backend=backend).root.tag == f"{{{FB2_NS}}}FictionBook"


def test_comments_and_pis_are_not_children() -> None:
    tree = parse_tree(f'<FictionBook xmlns="{FB2_NS}"><!-- c --><?pi x?><body/></FictionBook>')
    assert [el.tag for el in tree.root] == [f"{{{FB2_NS}}}body"]


def _backends() -> list[Backend]:
    import importlib.util

    return [Backend.STDLIB] + ([Backend.LXML] if importlib.util.find_spec("lxml") else [])


@pytest.mark.parametrize("backend", _backends())
@pytest.mark.parametrize(("depth", "ok"), [(200, True), (201, False)])
def test_nesting_depth_limit_is_the_same_for_all_backends(
    backend: Backend,
    depth: int,
    ok: bool,
) -> None:
    text = (
        f'<FictionBook xmlns="{FB2_NS}">'
        + "<section>" * (depth - 1)
        + "</section>" * (depth - 1)
        + "</FictionBook>"
    )
    for mode in (Mode.STRICT, Mode.TOLERANT):
        if ok:
            assert parse_tree(text, backend=backend, mode=mode).root is not None
        else:
            with pytest.raises(Fb2ParseError, match="depth"):
                parse_tree(text, backend=backend, mode=mode)


@pytest.mark.parametrize("backend", _backends())
def test_backends_build_the_same_tree(backend: Backend) -> None:
    tree = parse_tree(_read("minimal.fb2"), backend=backend)
    ref = parse_tree(_read("minimal.fb2"), backend=Backend.STDLIB)
    assert [(el.tag, el.text, dict(el.attrib)) for el in tree.root.iter()] == [
        (el.tag, el.text, dict(el.attrib)) for el in ref.root.iter()
    ]


def test_any_xlink_prefix_is_normalized() -> None:
    tree = parse_tree(
        f'<FictionBook xmlns="{FB2_NS}" xmlns:xlink="{XLINK_NS}">'
        '<body><image xlink:href="#c"/></body></FictionBook>'
    )
    image = next(el for el in tree.root.iter() if el.tag.endswith("}image"))
    assert image.get(f"{{{XLINK_NS}}}href") == "#c"


def test_missing_namespace_is_applied_to_all_descendants() -> None:
    tree = parse_tree("<FictionBook><body><section><p>x</p></section></body></FictionBook>")
    assert all(el.tag.startswith(f"{{{FB2_NS}}}") for el in tree.root.iter())


@pytest.mark.parametrize("text", ["", "   ", "<html><body/></html>"])
def test_empty_or_foreign_root_is_a_parse_error(text: str) -> None:
    for mode in (Mode.STRICT, Mode.TOLERANT):
        with pytest.raises(Fb2ParseError):
            parse_tree(text, mode=mode)


def test_lone_surrogate_in_strict_is_a_parse_error_not_unicode_error() -> None:
    with pytest.raises(Fb2ParseError):
        parse_tree(f'<FictionBook xmlns="{FB2_NS}"><p>\ud800</p></FictionBook>', mode=Mode.STRICT)


def test_crlf_is_normalized_in_text() -> None:
    tree = parse_tree(f'<FictionBook xmlns="{FB2_NS}"><p>a\r\nb</p></FictionBook>')
    assert tree.root[0].text == "a\nb"


def test_parse_error_reports_the_line() -> None:
    with pytest.raises(Fb2ParseError) as exc:
        parse_tree(f'<FictionBook xmlns="{FB2_NS}">\n<body>\n<p>x</body>\n</FictionBook>')
    assert exc.value.line == 3
