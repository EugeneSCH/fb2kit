import fb2kit


def test_version_is_exposed() -> None:
    assert isinstance(fb2kit.__version__, str)
    assert fb2kit.__version__ == "0.1.0"


def test_py_typed_marker_is_shipped() -> None:
    from pathlib import Path

    assert (Path(fb2kit.__file__).parent / "py.typed").is_file()


def test_version_matches_distribution_metadata() -> None:
    from importlib.metadata import version

    assert version("fb2kit") == fb2kit.__version__
