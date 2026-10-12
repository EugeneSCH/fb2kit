import dataclasses

import pytest

import fb2kit.report as report
from fb2kit.report import Diagnostic, Mode, ParseReport, Severity


def test_report_splits_by_severity() -> None:
    rep = ParseReport(
        diagnostics=(
            Diagnostic(report.ELEMENT_UNKNOWN, "unknown <foo>", path="body[0]"),
            Diagnostic(report.CONTAINER_FBZ, "unpacked", severity=Severity.INFO),
        )
    )
    assert [d.code for d in rep.warnings] == [report.ELEMENT_UNKNOWN]


def test_diagnostic_defaults_to_warning() -> None:
    assert Diagnostic("x.y", "msg").severity is Severity.WARNING


def test_report_is_frozen_and_hashable() -> None:
    rep = ParseReport(source_encoding="cp1251", container="fbz")
    hash(rep)
    assert rep.container == "fbz"


def test_mode_enum_values() -> None:
    assert [m.value for m in Mode] == ["strict", "tolerant"]


def test_report_and_diagnostic_are_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        ParseReport().backend = "lxml"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Diagnostic("x.y", "m").code = "z"  # type: ignore[misc]


def test_info_only_report_has_no_warnings() -> None:
    rep = ParseReport(diagnostics=(Diagnostic("x.y", "m", severity=Severity.INFO),))
    assert rep.warnings == ()


def test_diagnostic_codes_are_unique_dotted_strings() -> None:
    codes = [v for k, v in vars(report).items() if k.isupper() and isinstance(v, str)]
    assert len(codes) == len(set(codes)) >= 17
    assert all("." in c and c == c.lower() for c in codes)
