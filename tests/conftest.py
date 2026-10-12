import json
import os
from pathlib import Path
from typing import Any

from hypothesis import settings

# Parse time includes a one-off lxml import; a wall-clock deadline only produces flaky failures.
settings.register_profile("fb2kit", deadline=None)
settings.load_profile("fb2kit")

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"


def fixture_text(name: str) -> str:
    """UTF-8 fixture without the trailing newline, so fragments splice cleanly into markup."""
    return (FIXTURES / name).read_text(encoding="utf-8").removesuffix("\n")


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


TITLE, PROSE, CAPS, YES = fixture_text("encodings-source.txt").splitlines()


def cases(area: str) -> Any:
    """Parsed tests/cases/<area>.json; plain function so parametrize can call it at collection."""
    return json.loads((HERE / "cases" / f"{area}.json").read_text(encoding="utf-8"))


def case(area: str, case_id: str) -> dict[str, Any]:
    return next(c for c in cases(area) if c["id"] == case_id)


def corpus_files() -> list[Path]:
    """Books under $FB2KIT_CORPUS; a plain function because skipif/parametrize call it at collection."""
    root = os.environ.get("FB2KIT_CORPUS")
    if not root or not Path(root).is_dir():
        return []
    found = {p for pat in ("*.fb2", "*.fbz", "*.fb2.zip") for p in Path(root).rglob(pat)}
    return sorted(found)
