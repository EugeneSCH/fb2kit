"""Every ```python block in README.md and docs/ and every script in examples/ runs on fixtures."""

import csv
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from conftest import TITLE, cases

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
_BLOCK = re.compile(r"^```python\n(.*?)^```", re.S | re.M)

# Names the docs use, mapped to fixtures.
_FILES = {
    "book.fb2": "sample.fb2",
    "messy.fb2": "bare-amp.fb2",
    "cp1251.fb2": "cp1251-no-prolog.fb2",
    "unsafe.fb2": "xxe-doctype.fb2",
}

# Output fragments that pin the claims made in the docs' comments.
_DATA = cases("docs_examples")
_EXPECTED = _DATA["expected"]


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, fixture in _FILES.items():
        shutil.copy(FIXTURES / fixture, tmp_path / name)
    with zipfile.ZipFile(tmp_path / "book.fbz", "w") as zf:
        zf.write(FIXTURES / "sample.fb2", "book.fb2")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _page_id(page: Path) -> str:
    return page.name if page.parent == ROOT else page.relative_to(ROOT / "docs").as_posix()


@pytest.mark.parametrize("page", PAGES, ids=_page_id)
def test_page_code_blocks_run(page: Path, workdir: Path) -> None:
    blocks = _BLOCK.findall(page.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "__docs__"}
    out = io.StringIO()
    with redirect_stdout(out):
        for i, code in enumerate(blocks):
            exec(compile(code, f"{page.name}[block {i}]", "exec"), namespace)
    for fragment in _EXPECTED.get(_page_id(page), []):
        assert fragment in out.getvalue(), fragment


def test_every_page_with_code_has_expectations() -> None:
    with_code = {_page_id(p) for p in PAGES if _BLOCK.search(p.read_text(encoding="utf-8"))}
    assert with_code == set(_EXPECTED)


def _run(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / script), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert (proc.returncode == 0) is ok, proc.stderr
    return proc


def test_meta_to_csv(tmp_path: Path) -> None:
    out = tmp_path / "books.csv"
    _run("meta_to_csv.py", FIXTURES, "-o", out)
    rows = {Path(r["file"]).name: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    assert rows["sample.fb2"]["title"] == _DATA["book_title"]
    assert rows["sample.fb2"]["authors"] == _DATA["author"]
    assert rows["cp1251-no-prolog.fb2"]["encoding"] == "cp1251"
    assert rows["container.fbz"]["title"] == TITLE
    assert rows["xxe-doctype.fb2"]["error"].startswith("Fb2UnsafeInputError")


def test_to_text() -> None:
    full = _run("to_text.py", FIXTURES / "sample.fb2").stdout
    assert all(f in full for f in _DATA["text_fragments"])
    assert _DATA["note"] in full
    assert _DATA["note"] not in _run("to_text.py", FIXTURES / "sample.fb2", "--no-notes").stdout


def test_to_markdown(tmp_path: Path) -> None:
    out = tmp_path / "book.md"
    _run("to_markdown.py", FIXTURES / "sample.fb2", "-o", out)
    md = out.read_text(encoding="utf-8")
    for fragment in _DATA["markdown"]:
        assert fragment in md, fragment


def test_extract_images(tmp_path: Path) -> None:
    out = _run("extract_images.py", FIXTURES / "sample.fb2", tmp_path).stdout
    assert "cover.png\timage/png\t69 (cover)" in out
    for name in ("cover.png", "map.png"):
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG")


def test_extract_images_sanitises_ids() -> None:
    sys.path.insert(0, str(EXAMPLES))
    try:
        from extract_images import safe_name
    finally:
        sys.path.remove(str(EXAMPLES))
    assert safe_name("../../etc/passwd", "image/png") == "_.._etc_passwd.png"
    assert safe_name("cover.jpg", "image/jpeg") == "cover.jpg"


def test_rag_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "chunks.jsonl"
    _run("rag_jsonl.py", FIXTURES / "sample.fb2", FIXTURES / "xxe-doctype.fb2", "-o", out)
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in records] == [f"sample.fb2#{i}" for i in range(len(records))]
    assert all(r["book"]["title"] == _DATA["book_title"] for r in records)
    chapter1 = [r for r in records if r["section_idx"] == [1, 1]]
    assert chapter1[0]["heading"] == _DATA["heading"]
    assert chapter1[0]["notes"] == [f"1\n{_DATA['note']}"]
    assert not any(_DATA["second_note"] in r["text"] for r in records)  # notes are not chunks


def test_check_folder(tmp_path: Path) -> None:
    out = _run("check_folder.py", FIXTURES, ok=False).stdout
    assert re.search(r"^strict +sample\.fb2", out, re.M)
    assert re.search(r"^tolerant +bare-amp\.fb2 +xml\.bare-amp", out, re.M)
    assert re.search(r"^failed +xxe-doctype\.fb2 +Fb2UnsafeInputError", out, re.M)
    shutil.copy(FIXTURES / "sample.fb2", tmp_path)
    assert "strict=1" in _run("check_folder.py", tmp_path).stdout
