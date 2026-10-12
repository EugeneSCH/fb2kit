from pathlib import Path

import pytest
from conftest import CAPS, PROSE, TITLE, YES
from hypothesis import given
from hypothesis import strategies as st

import fb2kit.report as report
from fb2kit.errors import Fb2EncodingError
from fb2kit.report import Mode, Severity
from fb2kit.source import decode_source, guess_cyrillic

FIXTURES = Path(__file__).parent / "fixtures"
FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"  # fb2kit.parser arrives in Task 7


def _book(text: str) -> str:
    return (
        f'<FictionBook xmlns="{FB2_NS}"><description><title-info><book-title>{TITLE}</book-title>'
        f"</title-info></description><body><section><p>{text}</p></section></body></FictionBook>"
    )


@pytest.mark.parametrize(
    "name",
    [
        "minimal.fb2",
        "utf8-bom.fb2",
        "cp1251-no-prolog.fb2",
        "koi8r-no-prolog.fb2",
        "koi8r-prolog.fb2",
        "wrong-prolog-cp1251.fb2",
    ],
)
def test_title_is_read_correctly_for_every_fixture(name: str) -> None:
    decoded = decode_source((FIXTURES / name).read_bytes(), mode=Mode.TOLERANT)
    assert TITLE in decoded.text


def test_utf8_bom_is_stripped_and_reported() -> None:
    decoded = decode_source((FIXTURES / "utf8-bom.fb2").read_bytes(), mode=Mode.STRICT)
    assert decoded.text.startswith("<?xml")
    assert decoded.encoding == "utf-8"


def test_declared_encoding_is_trusted_when_correct() -> None:
    decoded = decode_source((FIXTURES / "koi8r-prolog.fb2").read_bytes(), mode=Mode.STRICT)
    assert decoded.encoding == "koi8-r"
    assert decoded.declared_encoding == "koi8-r"


def test_wrong_declaration_is_reported() -> None:
    decoded = decode_source((FIXTURES / "wrong-prolog-cp1251.fb2").read_bytes(), mode=Mode.TOLERANT)
    assert [(d.code, d.severity) for d in decoded.diagnostics] == [
        (report.ENC_DECLARED_MISMATCH, Severity.WARNING)
    ]
    assert decoded.declared_encoding == "utf-8" and decoded.encoding == "cp1251"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("cp1251-no-prolog.fb2", "cp1251"),
        ("koi8r-no-prolog.fb2", "koi8-r"),
    ],
)
def test_tolerant_guesses_cyrillic_without_prolog(name: str, expected: str) -> None:
    decoded = decode_source((FIXTURES / name).read_bytes(), mode=Mode.TOLERANT)
    assert decoded.encoding == expected and PROSE in decoded.text
    assert [d.code for d in decoded.diagnostics] == [report.ENC_GUESSED]
    assert decoded.diagnostics[0].code == "encoding.guessed"
    assert decoded.diagnostics[0].severity is Severity.WARNING


@pytest.mark.parametrize("enc", ["cp1251", "koi8-r", "cp866"])
def test_guess_cyrillic_detects_encoding(enc: str) -> None:
    assert guess_cyrillic(_book(PROSE).encode(enc)) == enc


@pytest.mark.parametrize("enc", ["cp1251", "koi8-r"])
def test_guess_cyrillic_handles_all_caps_book(enc: str) -> None:
    raw = _book(f"{CAPS} {PROSE.upper()}").replace(TITLE, TITLE.upper()).encode(enc)
    assert guess_cyrillic(raw) == enc


@pytest.mark.parametrize(
    "raw",
    [
        b"plain latin text",
        b"<FictionBook><p>Hello, world " + YES.encode("koi8-r") + b"</p></FictionBook>",
    ],
)
def test_guess_cyrillic_weak_signal_is_none(raw: bytes) -> None:
    assert guess_cyrillic(raw) is None


def test_utf8_without_prolog_and_bom_is_utf8_silently() -> None:
    decoded = decode_source(_book(PROSE).encode("utf-8"), mode=Mode.STRICT)
    assert decoded.encoding == "utf-8" and PROSE in decoded.text
    assert decoded.diagnostics == ()


@pytest.mark.parametrize("enc", ["utf-16-le", "utf-16-be"])
def test_utf16_without_bom_is_detected_by_xml_signature(enc: str) -> None:
    raw = ('<?xml version="1.0" encoding="utf-16"?>' + _book(PROSE)).encode(enc)
    decoded = decode_source(raw, mode=Mode.STRICT)
    assert decoded.encoding == enc and PROSE in decoded.text


def test_weak_signal_falls_back_to_cp1251_with_guess_diagnostic() -> None:
    raw = b"<FictionBook><p>Hello, world " + YES.encode("koi8-r") + b"</p></FictionBook>"
    decoded = decode_source(raw, mode=Mode.TOLERANT)
    assert decoded.encoding == "cp1251"
    assert [d.code for d in decoded.diagnostics] == [report.ENC_FALLBACK]
    assert decoded.diagnostics[0].code == "encoding.fallback"


def test_strict_without_prolog_and_invalid_utf8_fails() -> None:
    with pytest.raises(Fb2EncodingError):
        decode_source((FIXTURES / "cp1251-no-prolog.fb2").read_bytes(), mode=Mode.STRICT)


def test_strict_with_wrong_declaration_fails() -> None:
    with pytest.raises(Fb2EncodingError):
        decode_source((FIXTURES / "wrong-prolog-cp1251.fb2").read_bytes(), mode=Mode.STRICT)


def test_explicit_encoding_overrides_everything() -> None:
    decoded = decode_source(
        (FIXTURES / "cp1251-no-prolog.fb2").read_bytes(),
        encoding="cp1251",
        mode=Mode.STRICT,
    )
    assert decoded.encoding == "cp1251" and TITLE in decoded.text
    assert decoded.diagnostics == ()


def test_explicit_encoding_overrides_prolog_and_reports_it() -> None:
    decoded = decode_source(
        (FIXTURES / "wrong-prolog-cp1251.fb2").read_bytes(),
        encoding="cp1251",
        mode=Mode.STRICT,
    )
    assert decoded.encoding == "cp1251" and TITLE in decoded.text
    assert decoded.declared_encoding == "utf-8"
    assert [(d.code, d.severity) for d in decoded.diagnostics] == [
        (report.ENC_DECLARED_MISMATCH, Severity.INFO)
    ]


def test_undecodable_bytes_are_an_encoding_error() -> None:
    with pytest.raises(Fb2EncodingError):
        decode_source(b"\xff\xfe\x00<?xml version='1.0'?>", mode=Mode.TOLERANT)


@pytest.mark.parametrize(
    "prolog",
    [
        "<?xml version='1.0' encoding='windows-1251'?>",
        '<?xml version="1.0" encoding = "windows-1251" ?>',
        '<?xml version="1.0" ENCODING="windows-1251"?>',
        '<?xml version="1.0" encoding="WINDOWS-1251"?>',
        '<?xml version="1.0" encoding="cp1251"?>',
    ],
)
def test_prolog_variants_are_understood(prolog: str) -> None:
    decoded = decode_source((prolog + _book(PROSE)).encode("cp1251"), mode=Mode.STRICT)
    assert decoded.encoding == "cp1251" and PROSE in decoded.text and decoded.diagnostics == ()


@pytest.mark.parametrize(("mode", "ok"), [(Mode.STRICT, False), (Mode.TOLERANT, True)])
def test_unknown_encoding_name_in_prolog(mode: Mode, ok: bool) -> None:
    raw = ('<?xml version="1.0" encoding="x-unknown"?>' + _book(PROSE)).encode("cp1251")
    if not ok:
        with pytest.raises(Fb2EncodingError):
            decode_source(raw, mode=mode)
        return
    decoded = decode_source(raw, mode=mode)
    assert decoded.encoding == "cp1251"
    assert [(d.code, d.severity) for d in decoded.diagnostics] == [
        (report.ENC_DECLARED_MISMATCH, Severity.WARNING)
    ]


def test_unknown_explicit_encoding_is_an_encoding_error() -> None:
    with pytest.raises(Fb2EncodingError):
        decode_source(b"<a/>", encoding="x-unknown", mode=Mode.TOLERANT)


@pytest.mark.parametrize("raw", [b"", b"   \n"])
def test_empty_or_blank_input_is_an_encoding_error(raw: bytes) -> None:
    with pytest.raises(Fb2EncodingError):
        decode_source(raw, mode=Mode.TOLERANT)


@pytest.mark.parametrize("enc", ["utf-32-le", "utf-32-be"])
def test_utf32_is_detected_by_signature(enc: str) -> None:
    decoded = decode_source(("﻿" + _book(PROSE)).encode(enc), mode=Mode.STRICT)
    assert decoded.encoding == enc and PROSE in decoded.text


def test_bom_wins_over_contradicting_prolog() -> None:
    raw = (
        b"\xef\xbb\xbf" + ('<?xml version="1.0" encoding="windows-1251"?>' + _book(PROSE)).encode()
    )
    decoded = decode_source(raw, mode=Mode.STRICT)
    assert decoded.encoding == "utf-8" and PROSE in decoded.text
    assert [d.code for d in decoded.diagnostics] == [report.ENC_DECLARED_MISMATCH]


def test_leading_whitespace_is_plausible() -> None:
    decoded = decode_source(b"\r\n  " + _book(PROSE).encode(), mode=Mode.STRICT)
    assert decoded.encoding == "utf-8" and decoded.text.lstrip().startswith("<FictionBook")


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=200))
def test_utf8_round_trip_is_exact(body: str) -> None:
    raw = ('<?xml version="1.0" encoding="utf-8"?><a>' + body + "</a>").encode("utf-8")
    assert body in decode_source(raw, mode=Mode.STRICT).text
