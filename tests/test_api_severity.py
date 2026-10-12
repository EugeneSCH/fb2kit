from fb2kit.report import ParseReport, Severity


def test_no_error_severity() -> None:
    assert {s.name for s in Severity} == {"INFO", "WARNING"}
    assert not hasattr(ParseReport, "ok") and not hasattr(ParseReport, "errors")
