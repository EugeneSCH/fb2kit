# tests/test_invariants.py
import base64
import contextlib
import io
import zipfile
from pathlib import Path

import pytest
from conftest import fixture_text
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from strategies import binary_payload, fb2_document

import fb2kit
import fb2kit.report as report
from fb2kit.model.binary import decode_b64
from fb2kit.model.inline import Link
from fb2kit.report import Mode

FIXTURES = Path(__file__).parent / "fixtures"


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(fb2_document())
def test_parse_never_crashes_on_generated_valid_documents(text: str) -> None:
    book = fb2kit.parse(text.encode("utf-8"), mode=Mode.TOLERANT)
    assert book.description.title_info.title is not None


@given(fb2_document())
def test_dangling_links_are_reported(text: str) -> None:
    book = fb2kit.parse(text.encode("utf-8"), mode=Mode.TOLERANT)
    codes = {d.code for d in book.report.diagnostics}
    for node in _iter(book.bodies):
        if isinstance(node, Link) and node.href.startswith("#") and node.href[1:] not in book.index:
            assert report.LINK_UNRESOLVED in codes


@given(binary_payload())
def test_binary_decode_is_lossless(payload: bytes) -> None:
    encoded = base64.encodebytes(payload).decode()
    assert decode_b64(encoded) == payload


@given(
    st.text(alphabet=fixture_text("alphabet.txt") + " ", min_size=1, max_size=40).filter(
        lambda s: s.strip() == s
    )
)
def test_text_content_survives_round_trip(title: str) -> None:
    doc = f'<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><book-title>{title}</book-title></title-info></description><body><section><p>t</p></section></body></FictionBook>'
    book = fb2kit.parse(doc.encode("utf-8"))
    assert book.description.title_info.title == title


@given(fb2_document())
def test_report_is_deterministic(text: str) -> None:
    first = fb2kit.parse(text.encode("utf-8"), mode=Mode.TOLERANT).report
    second = fb2kit.parse(text.encode("utf-8"), mode=Mode.TOLERANT).report
    assert first == second


def _iter(node):
    from fb2kit.model import iter_nodes

    yield from iter_nodes(node)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(st.binary(max_size=2048))
def test_tolerant_never_raises_anything_but_fb2_error_on_random_bytes(data: bytes) -> None:
    with contextlib.suppress(fb2kit.Fb2Error):
        fb2kit.parse(data, mode=Mode.TOLERANT)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(fb2_document(), st.data())
def test_tolerant_survives_byte_mutations_of_valid_documents(
    text: str, data: st.DataObject
) -> None:
    raw = bytearray(text.encode("utf-8"))
    for _ in range(data.draw(st.integers(1, 5))):
        pos = data.draw(st.integers(0, len(raw) - 1))
        raw[pos] = data.draw(st.integers(0, 255))
    with contextlib.suppress(fb2kit.Fb2Error):
        fb2kit.parse(bytes(raw), mode=Mode.TOLERANT)


@given(fb2_document())
def test_strict_and_tolerant_agree_on_valid_documents(text: str) -> None:
    raw = text.encode("utf-8")
    assert fb2kit.parse(raw, mode=Mode.STRICT) == fb2kit.parse(raw, mode=Mode.TOLERANT)


@given(st.text(max_size=300))
def test_repair_text_is_idempotent(text: str) -> None:
    from fb2kit.repair import repair_text

    once = repair_text(text).text
    assert repair_text(once).text == once


@given(binary_payload(), st.lists(st.sampled_from(" \n\t!*-_.:"), max_size=20), st.randoms())
def test_garbage_inside_base64_is_ignored(payload: bytes, junk: list[str], rnd) -> None:
    chars = list(base64.b64encode(payload).decode())
    for ch in junk:
        chars.insert(rnd.randint(0, len(chars)), ch)
    assert decode_b64("".join(chars)) == payload


@pytest.mark.parametrize("name", ["regression-nul-in-prolog.fb2"])
def test_regression_fixtures_do_not_escape_as_foreign_errors(name: str) -> None:
    raw = (FIXTURES / name).read_bytes()
    with contextlib.suppress(fb2kit.Fb2Error):
        fb2kit.parse(raw, mode=Mode.TOLERANT)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.sampled_from(sorted(set(__import__("encodings.aliases").aliases.aliases.values()))))
def test_any_codec_name_in_prolog_raises_only_fb2_error(codec: str) -> None:
    raw = f'<?xml version="1.0" encoding="{codec}"?><FictionBook/>'.encode()
    for mode in Mode:
        with contextlib.suppress(fb2kit.Fb2Error):
            fb2kit.parse(raw, mode=mode)
        with contextlib.suppress(fb2kit.Fb2Error):
            fb2kit.parse(raw, encoding=codec, mode=mode)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(fb2_document(), st.data())
def test_mutated_zip_raises_only_fb2_error(text: str, data: st.DataObject) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.fb2", text)
    raw = bytearray(buf.getvalue())
    for _ in range(data.draw(st.integers(1, 5))):
        raw[data.draw(st.integers(0, len(raw) - 1))] = data.draw(st.integers(0, 255))
    with contextlib.suppress(fb2kit.Fb2Error):
        fb2kit.parse(bytes(raw), mode=Mode.TOLERANT)


@settings(max_examples=100, deadline=2000, suppress_health_check=[HealthCheck.too_slow])
@given(st.text(alphabet="<>!-[]?&#/a ;CDATA", max_size=20_000))
def test_tolerant_terminates_fast_on_markup_soup(text: str) -> None:
    with contextlib.suppress(fb2kit.Fb2Error):
        fb2kit.parse_string(text, mode=Mode.TOLERANT)
