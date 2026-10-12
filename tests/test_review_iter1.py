"""Regression tests for review iter1 findings."""

import contextlib
import io
import time
import zipfile

import pytest

import fb2kit
from fb2kit import Mode
from fb2kit.backends import Backend, resolve_backend
from fb2kit.errors import (
    Fb2EncodingError,
    Fb2ParseError,
    Fb2SourceError,
    Fb2UnsafeInputError,
)
from fb2kit.repair import close_unterminated, repair_text
from fb2kit.source import _canon

NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
BOOK = (
    f'<FictionBook xmlns="{NS}"><description><title-info><book-title>T</book-title></title-info>'
    "</description><body><section><p>{p}</p></section></body></FictionBook>"
)
BACKENDS = [Backend.STDLIB, *([Backend.LXML] if resolve_backend(Backend.AUTO) == "lxml" else [])]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("junk", ["\x00", "\x01", "\ud800"])
def test_dtd_hidden_by_control_chars_is_rejected(backend: Backend, junk: str) -> None:
    doc = f'<!DOC{junk}TYPE FictionBook [<!ATTLIST p id CDATA "injected">]>' + BOOK.format(p="x")
    with pytest.raises(Fb2UnsafeInputError):
        fb2kit.parse_string(doc, mode=Mode.TOLERANT, backend=backend)
    if junk != "\ud800":
        pad = "<!-- " + "x" * 210 + " -->"
        with pytest.raises(Fb2UnsafeInputError):
            fb2kit.parse((pad + doc).encode(), mode=Mode.TOLERANT, backend=backend)


@pytest.mark.parametrize("name", ["rot13", "hex", "base64", "zlib", "bz2", "quopri", "uu"])
@pytest.mark.parametrize("mode", [Mode.STRICT, Mode.TOLERANT])
def test_binary_codec_is_an_unknown_encoding(name: str, mode: Mode) -> None:
    raw = f'<?xml version="1.0" encoding="{name}"?>'.encode() + BOOK.format(p="x").encode()
    if mode is Mode.STRICT:
        with pytest.raises(Fb2EncodingError):
            fb2kit.parse(raw, mode=mode)
    else:  # the bogus declaration is ignored, the bytes are valid UTF-8
        assert fb2kit.parse(raw, mode=mode).report.source_encoding == "utf-8"
    with pytest.raises(Fb2EncodingError):
        fb2kit.parse(raw, encoding=name, mode=mode)


def test_punycode_does_not_leak_unicode_error() -> None:
    raw = b'<?xml version="1.0" encoding="punycode"?>' + BOOK.format(p="x").encode()
    assert fb2kit.parse(raw, mode=Mode.TOLERANT).report.source_encoding == "utf-8"
    with pytest.raises(Fb2EncodingError):
        fb2kit.parse(raw, encoding="punycode", mode=Mode.TOLERANT)


def _zip(data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.fb2", data)
    return buf.getvalue()


def test_zip_value_error_becomes_source_error() -> None:
    raw = bytes.fromhex(
        "504b0304140000750800dd664c5dedce41977c000000c400000008000000626f6f6b2e66623255ce410ec2201005d0ab98eecb372ecd380b179ec01340a94eac408086f6f6b692185cfe3f2f3f43373159bcbb7aff3a2cefc9a54bf7cc399c81528a7a44d173b251c519db1563d57ad338a963c734d864cf84bd65ca9227db8b1b3dd36efa6fc1774293082dc3df80f6c3ca94aca931f042081bfa35a802cddbfc01504b01021403140000000800dd664c5dedce41977c000000c4000000080000000000000000000000800100000000626f6f6b2e666232504b0506000000000100010036000000ac0000000000"
    )
    with pytest.raises(Fb2SourceError):
        fb2kit.parse(raw, mode=Mode.TOLERANT)


def test_close_unterminated_is_linear() -> None:
    start = time.perf_counter()
    close_unterminated("<a " * 20000)
    assert time.perf_counter() - start < 1
    start = time.perf_counter()
    with contextlib.suppress(Fb2ParseError):  # lxml recovers, stdlib gives up
        fb2kit.parse_string("<FictionBook>" + "<a " * 20000, mode=Mode.TOLERANT)
    assert time.perf_counter() - start < 1


def test_close_unterminated_still_closes_before_truncated_tag() -> None:
    assert close_unterminated("<a><b>x<c ").text == "<a><b>x<c </b></a>"


@pytest.mark.parametrize("backend", BACKENDS)
def test_huge_binary_parses_on_every_backend(backend: Backend) -> None:
    big = BOOK.replace(
        "</FictionBook>",
        '<binary id="b" content-type="image/png">'
        + "QUJD" * (11 * 1024 * 1024 // 4)
        + "</binary></FictionBook>",
    )
    book = fb2kit.parse(big.format(p="x").encode(), backend=backend)
    assert len(book.binaries[0].data) == 3 * (11 * 1024 * 1024 // 4)


@pytest.mark.parametrize("mode", [Mode.STRICT, Mode.TOLERANT])
def test_prolog_regex_only_strips_leading_declaration(mode: Mode) -> None:
    doc = BOOK.format(p="<![CDATA[<?xml v?>]]>z")
    book = fb2kit.parse_string(doc, mode=mode, backend=Backend.STDLIB)
    assert book.bodies[0].sections[0].blocks[0].children[0].value == "<?xml v?>z"  # type: ignore[union-attr]


def test_cdata_survives_tolerant() -> None:
    doc = BOOK.format(p="<![CDATA[a & b]]> &")
    strict_doc = BOOK.format(p="<![CDATA[a & b]]> &amp;")
    t = fb2kit.parse_string(doc, mode=Mode.TOLERANT, backend=Backend.STDLIB)
    s = fb2kit.parse_string(strict_doc, backend=Backend.STDLIB)
    assert t.bodies == s.bodies


def test_string_mode_and_backend_are_coerced_or_rejected() -> None:
    raw = BOOK.format(p="a & b").encode()
    assert fb2kit.parse(raw, mode="tolerant").bodies  # type: ignore[arg-type]
    assert fb2kit.parse(raw, mode="tolerant", backend="stdlib").report.backend == "stdlib"  # type: ignore[arg-type]
    with pytest.raises(Fb2ParseError):
        fb2kit.parse(raw, mode="strict")  # type: ignore[arg-type]
    for bad in ("bogus", 5, None):
        with pytest.raises(TypeError):
            fb2kit.parse(raw, mode=bad)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            fb2kit.parse_string("<x/>", backend=bad)  # type: ignore[arg-type]


def test_tolerant_decodes_undefined_cp1251_byte_with_replacement() -> None:
    raw = b"<FictionBook><description/><body><section><p>Hi \x98</p></section></body></FictionBook>"
    book = fb2kit.parse(raw, mode=Mode.TOLERANT)
    assert book.bodies


def test_title_keeps_inline_text() -> None:
    doc = BOOK.replace("<section>", "<section><title><strong>T</strong></title>").format(p="x")
    title = fb2kit.parse_string(doc, mode=Mode.TOLERANT).bodies[0].sections[0].title
    assert title is not None and title.children


@pytest.mark.parametrize("unit", ["<!-- ", "<![CDATA[ ", "<a "])
def test_repair_is_linear_on_unterminated_constructs(unit: str) -> None:
    for n in (5000, 20000):
        start = time.perf_counter()
        with contextlib.suppress(Fb2ParseError):
            fb2kit.parse_string("<FictionBook>" + unit * n, mode=Mode.TOLERANT)
        assert time.perf_counter() - start < 1, (unit, n)


@pytest.mark.parametrize("unit", ["<!-- ", "<![CDATA[ "])
def test_repair_time_grows_linearly(unit: str) -> None:
    def run(n: int) -> float:
        start = time.perf_counter()
        repair_text(unit * n)
        return time.perf_counter() - start

    run(1000)
    small, big = min(run(10000) for _ in range(3)), min(run(40000) for _ in range(3))
    assert big < small * 8  # 4x input: linear ~4x, quadratic ~16x


def test_bare_lt_does_not_close_stack() -> None:
    assert close_unterminated("<a><b>1 < 2</b>").text == "<a><b>1 < 2</b></a>"


@pytest.mark.parametrize("name", ["base64", "hex", "rot13", "bz2", "zlib", "uu", "quopri"])
def test_canon_rejects_non_text_codecs(name: str) -> None:
    assert _canon(name) is None


def test_canon_accepts_text_codecs() -> None:
    assert _canon("utf8") == "utf-8"
    assert _canon("cp1251") == "cp1251"


def test_strict_never_replaces_undecodable_bytes() -> None:
    with pytest.raises(Fb2EncodingError):
        fb2kit.parse(b"<FictionBook>\x98\xff\x81</FictionBook>", mode=Mode.STRICT)
