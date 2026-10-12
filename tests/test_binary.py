# tests/test_binary.py
import base64
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import fb2kit.report as report
from fb2kit.builder import Builder
from fb2kit.model.binary import Binary, decode_b64
from fb2kit.model.bind import bind_binaries, resolve_cover
from fb2kit.parser import FB2_NS, parse_tree

FIXTURES = Path(__file__).parent / "fixtures"


def _ctx() -> Builder:
    return Builder(diagnostics=[], index={})


def _tree():
    return parse_tree((FIXTURES / "binary-cover.fb2").read_text(encoding="utf-8"))


def test_decoder_ignores_whitespace_and_garbage() -> None:
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    messy = payload[:4] + "\n  " + payload[4:] + "\r\n!!!\n"
    assert decode_b64(messy) == b"\x89PNG\r\n\x1a\n"


def test_decoder_fixes_missing_padding() -> None:
    assert decode_b64("QUJD") == b"ABC"
    assert decode_b64("QUJ") == b"AB"


def test_binaries_are_collected_with_content_types() -> None:
    bins = bind_binaries(_tree().root, _ctx())
    assert len(bins) == 3
    assert bins[0].content_type == "image/png"


def test_data_is_decoded_lazily_and_cached() -> None:
    bins = bind_binaries(_tree().root, _ctx())
    assert bins[0]._cache == {}
    first = bins[0].data
    assert first.startswith(b"\x89PNG")
    assert bins[0]._cache != {} and bins[0].data is first


def test_size_matches_decoded_length() -> None:
    binary = Binary(id="x", content_type="image/png", _b64=base64.b64encode(b"12345").decode())
    assert binary.size == 5


def test_cover_is_resolved_from_coverpage() -> None:
    ctx = _ctx()
    tree = _tree()
    bins = bind_binaries(tree.root, ctx)
    from fb2kit.model.bind import bind_description

    desc = bind_description(next(e for e in tree.root if e.tag.endswith("}description")), ctx)
    cover = resolve_cover(desc, bins, ctx)
    assert cover is not None and cover.id == "cover"


def test_missing_cover_reference_is_reported() -> None:
    from fb2kit.model.inline import Image
    from fb2kit.model.metadata import Description, TitleInfo

    desc = Description(title_info=TitleInfo(coverpage=(Image(href="#cover"),)))
    ctx = _ctx()
    assert resolve_cover(desc, (), ctx) is None
    assert [d.code for d in ctx.diagnostics] == [report.COVER_MISSING]


def test_absent_coverpage_is_silent() -> None:
    from fb2kit.model.metadata import Description, TitleInfo

    ctx = _ctx()
    assert resolve_cover(Description(title_info=TitleInfo()), (), ctx) is None
    assert ctx.diagnostics == []


def test_unparsable_binary_is_not_fatal() -> None:
    el = ET.fromstring(
        f'<FictionBook xmlns="{FB2_NS}"><binary id="b" content-type="image/png">!!!</binary></FictionBook>'
    )
    bins = bind_binaries(el, _ctx())
    assert bins[0].data == b""


def test_binary_is_hashable() -> None:
    hash(Binary(id="a", content_type="image/png", _b64="QUJD"))


def _bins(inner: str, ctx: Builder | None = None) -> tuple[Binary, ...]:
    el = ET.fromstring(f'<FictionBook xmlns="{FB2_NS}">{inner}</FictionBook>')
    return bind_binaries(el, ctx or _ctx())


def test_empty_binary_has_empty_data() -> None:
    assert _bins('<binary id="e" content-type="image/png"/>')[0].data == b""


def test_binary_without_id_is_skipped_and_reported() -> None:
    ctx = _ctx()
    assert _bins('<binary content-type="image/png">QUJD</binary>', ctx) == ()
    assert [d.code for d in ctx.diagnostics] == [report.ELEMENT_MISSING]


def test_missing_content_type_defaults_to_octet_stream() -> None:
    assert _bins('<binary id="b">QUJD</binary>')[0].content_type == "application/octet-stream"


def test_duplicate_binary_id_is_reported_and_cover_takes_first() -> None:
    from fb2kit.model.inline import Image
    from fb2kit.model.metadata import Description, TitleInfo

    ctx = _ctx()
    bins = _bins(
        '<binary id="c" content-type="image/png">QQ==</binary><binary id="c" content-type="image/png">Qg==</binary>',
        ctx,
    )
    assert [d.code for d in ctx.diagnostics] == [report.DUPLICATE_ID]
    desc = Description(title_info=TitleInfo(coverpage=(Image(href="#c"),)))
    assert resolve_cover(desc, bins, ctx) is bins[0]


@pytest.mark.parametrize("href", ["c", "", "#"])
def test_cover_href_must_be_an_internal_reference(href: str) -> None:
    from fb2kit.model.inline import Image
    from fb2kit.model.metadata import Description, TitleInfo

    ctx = _ctx()
    bins = _bins('<binary id="c" content-type="image/png">QQ==</binary>')
    desc = Description(title_info=TitleInfo(coverpage=(Image(href=href),)))
    assert resolve_cover(desc, bins, ctx) is None
    assert [d.code for d in ctx.diagnostics] == [report.COVER_MISSING]


def test_first_of_several_coverpage_images_wins() -> None:
    from fb2kit.model.inline import Image
    from fb2kit.model.metadata import Description, TitleInfo

    bins = _bins(
        '<binary id="a" content-type="image/png">QQ==</binary><binary id="b" content-type="image/png">Qg==</binary>'
    )
    desc = Description(title_info=TitleInfo(coverpage=(Image(href="#b"), Image(href="#a"))))
    cover = resolve_cover(desc, bins, _ctx())
    assert cover is not None and cover.id == "b"


def test_binary_equality_ignores_cache() -> None:
    a = Binary(id="a", content_type="image/png", _b64="QUJD")
    _ = a.data
    assert a == Binary(id="a", content_type="image/png", _b64="QUJD")
