import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import fb2kit.report as report
from fb2kit.errors import Fb2SourceError
from fb2kit.source import open_container, read_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def test_opens_path() -> None:
    opened = open_container(FIXTURES / "minimal.fb2")
    assert opened.raw.startswith(b"<?xml")
    assert opened.container is None and opened.diagnostics == ()


def test_opens_bytes_and_bytearray() -> None:
    data = (FIXTURES / "minimal.fb2").read_bytes()
    assert open_container(data).raw == data
    assert open_container(bytearray(data)).raw == data


def test_opens_binary_file_object() -> None:
    with (FIXTURES / "minimal.fb2").open("rb") as fh:
        assert open_container(fh).raw == (FIXTURES / "minimal.fb2").read_bytes()


def test_unpacks_fbz_and_reports_container() -> None:
    opened = open_container(FIXTURES / "container.fbz")
    assert opened.raw == (FIXTURES / "minimal.fb2").read_bytes()
    assert opened.container == "fbz"
    assert [d.code for d in opened.diagnostics] == [report.CONTAINER_FBZ]


def test_zip_picks_fb2_entry_not_first() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "noise")
        zf.writestr("book.fb2", (FIXTURES / "minimal.fb2").read_bytes())
    assert open_container(buf.getvalue()).raw.startswith(b"<?xml")


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_fb2_under_other_suffix_is_sniffed_and_reported() -> None:
    fb2 = (FIXTURES / "minimal.fb2").read_bytes()
    opened = open_container(_zip({"cover.jpg": b"\xff\xd8", "book.fbd": fb2}))
    assert opened.raw == fb2
    assert [d.code for d in opened.diagnostics] == [
        report.CONTAINER_FBZ,
        report.CONTAINER_ENTRY_SNIFFED,
    ]
    assert "book.fbd" in opened.diagnostics[1].message


@pytest.mark.parametrize("enc", ["utf-16-le", "utf-16-be"])
def test_utf16_fb2_without_suffix_is_sniffed(enc: str) -> None:
    fb2 = (FIXTURES / "minimal.fb2").read_text(encoding="utf-8").encode(enc)
    assert open_container(_zip({"book": fb2})).raw == fb2


@pytest.mark.parametrize(
    ("entries", "fragment"),
    [
        ({"mimetype": b"application/epub+zip", "OEBPS/x.xhtml": b"<html/>"}, "looks like EPUB"),
        (
            {"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"},
            "looks like DOCX",
        ),
        ({"a.txt": b"hello"}, "no FictionBook entry: a.txt"),
        ({"a.xhtml": b"<html/>", "x.png": b"\x89PNG"}, "no FictionBook entry: a.xhtml"),
    ],
)
def test_archive_without_fictionbook_is_a_source_error(
    entries: dict[str, bytes], fragment: str
) -> None:
    with pytest.raises(Fb2SourceError, match="no FictionBook entry") as exc:
        open_container(_zip(entries))
    assert fragment in str(exc.value)


def test_sniff_limit_exhausted_is_a_source_error() -> None:
    with pytest.raises(Fb2SourceError, match="no FictionBook entry in first 1000 inspected"):
        open_container(_zip({f"f{i}.txt": b"x" for i in range(1001)}))


def test_fb2_suffix_found_past_the_sniff_limit() -> None:
    entries = {f"f{i}.txt": b"x" for i in range(1499)} | {"book.fb2": b"<FictionBook/>"}
    assert open_container(_zip(entries)).raw == b"<FictionBook/>"


def test_empty_zip_is_a_source_error() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    with pytest.raises(Fb2SourceError):
        open_container(buf.getvalue())


def test_missing_path_is_a_source_error() -> None:
    with pytest.raises(Fb2SourceError):
        open_container(FIXTURES / "no-such-file.fb2")


def test_unknown_extension_is_read_as_plain_bytes(tmp_path: Path) -> None:
    weird = tmp_path / "book.txt"
    weird.write_bytes(b"<?xml version='1.0'?>")
    assert open_container(weird).container is None


def test_read_bytes_returns_name_for_path() -> None:
    _, name = read_bytes(FIXTURES / "minimal.fb2")
    assert name == "minimal.fb2"


def test_oversized_zip_entry_is_a_source_error() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.fb2", b"<a>" + b" " * 100_000 + b"</a>")
    with pytest.raises(Fb2SourceError, match="max_size"):
        open_container(buf.getvalue(), max_size=10_000)


def test_oversized_plain_input_is_a_source_error() -> None:
    with pytest.raises(Fb2SourceError, match="max_size"):
        open_container(b"<a>" + b" " * 100, max_size=10)


def test_corrupt_zip_is_a_source_error() -> None:
    with pytest.raises(Fb2SourceError):
        open_container(b"PK\x03\x04" + b"\x00" * 40)


@pytest.mark.parametrize(("size", "ok"), [(100, True), (101, False)])
def test_max_size_boundary_for_plain_input(size: int, ok: bool) -> None:
    data = b"<a>" + b" " * (size - 7) + b"</a>"
    assert len(data) == size
    if ok:
        assert open_container(data, max_size=100).raw == data
    else:
        with pytest.raises(Fb2SourceError, match="max_size"):
            open_container(data, max_size=100)


@pytest.mark.parametrize(("size", "ok"), [(100, True), (101, False)])
def test_max_size_boundary_for_zip_entry(size: int, ok: bool) -> None:
    data = b"<a>" + b" " * (size - 7) + b"</a>"
    raw = _zip({"book.fb2": data})
    if ok:
        assert open_container(raw, max_size=100).raw == data
    else:
        with pytest.raises(Fb2SourceError, match="max_size"):
            open_container(raw, max_size=100)


@pytest.mark.parametrize(("offset", "found"), [(4096 - 12, True), (4096 - 11, False)])
def test_sniff_window_is_exactly_4096_bytes(offset: int, found: bool) -> None:
    data = b" " * offset + b"<FictionBook/>"
    raw = _zip({"book.dat": data})
    if found:
        assert open_container(raw).raw == data
    else:
        with pytest.raises(Fb2SourceError, match="no FictionBook entry"):
            open_container(raw)


def test_exactly_1000_entries_are_sniffed() -> None:
    entries = {f"f{i}.txt": b"x" for i in range(999)}
    entries["book.dat"] = (FIXTURES / "minimal.fb2").read_bytes()
    assert open_container(_zip(entries)).raw.startswith(b"<?xml")


@pytest.mark.parametrize("name", ["BOOK.FB2", "dir/book.fb2"])
def test_fb2_suffix_is_case_insensitive_and_found_in_subdirs(name: str) -> None:
    data = (FIXTURES / "minimal.fb2").read_bytes()
    opened = open_container(_zip({"a.txt": b"x", name: data}))
    assert opened.raw == data and [d.code for d in opened.diagnostics] == [report.CONTAINER_FBZ]


def test_str_path_is_a_path() -> None:
    assert open_container(str(FIXTURES / "minimal.fb2")).raw.startswith(b"<?xml")


def test_directory_is_a_source_error(tmp_path: Path) -> None:
    with pytest.raises(Fb2SourceError):
        open_container(tmp_path)


def test_text_file_object_is_a_source_error() -> None:
    from io import StringIO

    with pytest.raises(Fb2SourceError, match="binary"):
        open_container(StringIO("<a/>"))  # type: ignore[arg-type]


def test_non_seekable_file_object_is_read() -> None:
    class Stream:
        def __init__(self, data: bytes) -> None:
            self._buf = BytesIO(data)

        def read(self, n: int = -1) -> bytes:
            return self._buf.read(n)

    data = (FIXTURES / "minimal.fb2").read_bytes()
    assert open_container(Stream(data)).raw == data  # type: ignore[arg-type]


def test_empty_input_is_a_source_error() -> None:
    with pytest.raises(Fb2SourceError, match="empty"):
        open_container(b"")


def test_unsupported_source_type_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        open_container(42)  # type: ignore[arg-type]
