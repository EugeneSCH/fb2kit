"""The public write API: `to_xml`, `to_bytes`, `write` and `FictionBook.with`."""

import os
import zipfile
from pathlib import Path

import pytest

import fb2kit
from fb2kit.errors import Fb2SourceError, Fb2WriteError

FIXTURES = Path(__file__).parent / "fixtures"


def _book():
    return fb2kit.parse(FIXTURES / "structure-rich.fb2")


def _content(book):
    return (
        book.description,
        book.bodies,
        book.extra,
        tuple((b.id, b.content_type, b.data) for b in book.binaries),
        None if book.cover is None else (book.cover.id, book.cover.content_type, book.cover.data),
    )


def test_to_xml_returns_text_without_declaration() -> None:
    """С41: to_xml gives the text without the XML declaration."""
    xml = _book().to_xml()
    assert xml.startswith("<FictionBook")
    assert "<?xml" not in xml
    assert xml.endswith("\n")


def test_to_xml_can_include_declaration() -> None:
    """С41: to_xml can prepend the XML declaration."""
    assert _book().to_xml(declaration=True).startswith("<?xml")


def test_to_bytes_is_utf8_and_reparsable() -> None:
    """С41: to_bytes is UTF-8 with a declaration and is re-parsable."""
    data = _book().to_bytes()
    assert data.startswith(b"<?xml") and data.endswith(b"\n")
    again = fb2kit.parse(data, mode=fb2kit.Mode.STRICT)
    assert _content(again) == _content(_book())


def test_write_plain_file(tmp_path: Path) -> None:
    """С42: write creates a plain file with the book."""
    out = tmp_path / "book.fb2"
    _book().write(out)
    assert out.read_bytes().startswith(b"<?xml")
    assert fb2kit.parse(out) == _book()


def test_write_fbz_by_suffix(tmp_path: Path) -> None:
    """С22: the .fbz suffix gives an archive with one book inside."""
    out = tmp_path / "book.fbz"
    _book().write(out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert len(names) == 1 and names[0] == "book.fb2"
        assert zf.read(names[0]).startswith(b"<?xml")


def test_write_forced_compress(tmp_path: Path) -> None:
    """С43: compress=True writes an archive whatever the suffix is."""
    out = tmp_path / "book.dat"
    _book().write(out, compress=True)
    assert zipfile.is_zipfile(out)


def test_write_is_atomic_on_failure(tmp_path: Path, monkeypatch) -> None:
    """С21: a failed write leaves the old file and removes the temporary one."""
    out = tmp_path / "book.fb2"
    out.write_bytes(b"old")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _book().write(out)
    assert out.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["book.fb2"]  # временный файл убран


def test_write_keeps_permissions_of_existing_file(tmp_path: Path) -> None:
    """С44: the permissions of an existing file survive the write."""
    out = tmp_path / "book.fb2"
    out.write_bytes(b"old")
    out.chmod(0o640)
    _book().write(out)
    assert out.stat().st_mode & 0o777 == 0o640


def test_new_file_gets_umask_permissions(tmp_path: Path) -> None:
    """С44: a new file gets the ordinary permissions of the umask."""
    # Not 0600 as NamedTemporaryFile gives: a book is not a secret, the file gets
    # the ordinary permissions of the umask.
    out = tmp_path / "book.fb2"
    _book().write(out)
    assert out.stat().st_mode & 0o777 != 0o600
    assert out.stat().st_mode & 0o040 != 0  # the group can read it


def test_write_follows_symlink_target(tmp_path: Path) -> None:
    """С42: write follows the target of a symlink."""
    real = tmp_path / "real.fb2"
    link = tmp_path / "link.fb2"
    real.write_bytes(b"old")
    link.symlink_to(real)
    _book().write(link)
    assert link.is_symlink()
    assert real.read_bytes().startswith(b"<?xml")


def test_write_into_missing_directory_is_a_source_error(tmp_path: Path) -> None:
    """С45: a write into a missing directory is a source error."""
    with pytest.raises(Fb2SourceError):
        _book().write(tmp_path / "nope" / "book.fb2")


def test_strict_write_reports_errors(tmp_path: Path) -> None:
    """С19: a strict write of a broken book raises Fb2WriteError."""
    broken = _book().replace(bodies=())
    with pytest.raises(Fb2WriteError):
        broken.write(tmp_path / "x.fb2")
    assert not (tmp_path / "x.fb2").exists()


def test_non_strict_write_emits_even_a_broken_book(tmp_path: Path) -> None:
    """С20: a non-strict write emits even a broken book."""
    broken = _book().replace(bodies=())
    out = tmp_path / "x.fb2"
    broken.write(out, strict=False)
    assert out.exists()


def test_zip_output_is_deterministic(tmp_path: Path) -> None:
    """С23: two writes of one book give the same bytes."""
    # One model, one set of bytes: the name of the entry follows the target, so
    # both archives are written under the same name.
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a, b = a_dir / "book.fbz", b_dir / "book.fbz"
    _book().write(a)
    _book().write(b)
    assert a.read_bytes() == b.read_bytes()


def test_with_rebuilds_element_and_index() -> None:
    """С50: replace rebuilds the element and the index."""
    book = fb2kit.parse(FIXTURES / "notes-and-links.fb2")
    edited = book.replace(description=book.description)
    assert edited.element is not None
    assert edited.by_id("n1") is not None


def test_fbz_entry_metadata_is_fixed(tmp_path: Path) -> None:
    """С46: the entry of the archive has fixed metadata."""
    out = tmp_path / "book.fbz"
    _book().write(out)
    with zipfile.ZipFile(out) as zf:
        info = zf.infolist()[0]
    assert info.date_time == (1980, 1, 1, 0, 0, 0)
    assert info.create_system == 3
    assert info.compress_type == zipfile.ZIP_DEFLATED
    # The creator is written into the central directory of the entry: without
    # it the bytes of the archive differ between Windows and unix.
    raw = out.read_bytes()
    central = raw.find(b"PK\x01\x02")
    assert central != -1
    made_by = int.from_bytes(raw[central + 4 : central + 6], "little")
    assert made_by >> 8 == 3


def test_fb2_zip_suffix_is_also_compressed(tmp_path: Path) -> None:
    """С43: the .fb2.zip suffix writes an archive too."""
    out = tmp_path / "book.fb2.zip"
    _book().write(out)
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["book.fb2"]


def test_write_accepts_a_string_path(tmp_path: Path) -> None:
    """С42: write accepts a path given as a string."""
    out = tmp_path / "book.fb2"
    _book().write(str(out))
    assert out.exists()


def test_pretty_output_is_readable(tmp_path: Path) -> None:
    """С47: the pretty output is indented and is valid XML."""
    xml = _book().to_xml(pretty=True)
    assert "<FictionBook" in xml
    assert xml.count("\n") > 5
    # The pretty output is still valid XML.
    fb2kit.parse_string(xml)


def test_to_bytes_pretty_is_parseable() -> None:
    """С47: the pretty bytes are parsed in strict mode."""
    data = _book().to_bytes(pretty=True)
    assert data.startswith(b"<?xml")
    fb2kit.parse(data, mode=fb2kit.Mode.STRICT)


def test_write_honours_pretty(tmp_path: Path) -> None:
    """С47: write honours the pretty parameter."""
    # The parameter promises an indented file: the bytes on the disk have to
    # differ from the compact ones.
    out = tmp_path / "book.fb2"
    _book().write(out, pretty=True)
    data = out.read_bytes()
    assert b"\n  <" in data
    assert data != _book().to_bytes()


def test_write_without_pretty_is_compact(tmp_path: Path) -> None:
    """С47: write without pretty gives the compact bytes."""
    out = tmp_path / "book.fb2"
    _book().write(out)
    assert out.read_bytes() == _book().to_bytes()


def test_write_pretty_is_readable_again(tmp_path: Path) -> None:
    """С47: the pretty file is read back in strict mode."""
    out = tmp_path / "book.fb2"
    _book().write(out, pretty=True)
    again = fb2kit.parse(out, mode=fb2kit.Mode.STRICT)
    assert _content(again) == _content(_book())


def test_to_bytes_strict_rejects_a_broken_book() -> None:
    """С19: to_bytes in strict mode refuses a broken book."""
    broken = _book().replace(bodies=())
    with pytest.raises(Fb2WriteError):
        broken.to_bytes()
    assert broken.to_bytes(strict=False)


def test_to_xml_does_not_validate() -> None:
    """С48: to_xml never validates the book."""
    # to_xml never blocks: it is a preview of the tree.
    broken = _book().replace(bodies=())
    assert broken.to_xml()


def test_write_does_not_touch_the_model(tmp_path: Path) -> None:
    """С49: the write does not change the model."""
    book = _book()
    before = _content(book)
    book.write(tmp_path / "book.fb2")
    assert _content(book) == before


def test_write_pretty_inside_a_zip(tmp_path: Path) -> None:
    """С98: pretty is not ignored when the target is an archive."""
    out = tmp_path / "book.fbz"
    _book().write(out, pretty=True)
    with zipfile.ZipFile(out) as zf:
        data = zf.read(zf.namelist()[0])
    assert b"\n  <" in data


def test_replace_drops_the_cover_when_its_binary_is_gone() -> None:
    """С99: replace(binaries=()) keeps the book coherent."""
    book = fb2kit.parse(FIXTURES / "binary-cover.fb2")
    edited = book.replace(binaries=())
    assert edited.cover is None
