"""Check a folder of books: which open in strict, which only in tolerant and with which repairs.

python check_folder.py BOOKS_DIR
Exit code 1 if at least one book did not open even in tolerant.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import fb2kit

PATTERNS = ("*.fb2", "*.fbz", "*.fb2.zip")


def check(path: Path) -> tuple[str, list[str]]:
    """Status (strict / tolerant / failed) and diagnostic codes or the error text."""
    try:
        book = fb2kit.parse(path)
        return "strict", [d.code for d in book.report.diagnostics]
    except fb2kit.Fb2UnsafeInputError as exc:
        return "failed", [f"{type(exc).__name__}: {exc}"]  # tolerant will reject it too
    except fb2kit.Fb2Error:
        pass
    try:
        book = fb2kit.parse(path, mode=fb2kit.Mode.TOLERANT)
        return "tolerant", [d.code for d in book.report.diagnostics]
    except fb2kit.Fb2Error as exc:
        return "failed", [f"{type(exc).__name__}: {exc}"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    statuses: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    for path in sorted({p for pat in PATTERNS for p in args.folder.rglob(pat)}):
        status, details = check(path)
        statuses[status] += 1
        if status != "failed":
            codes.update(set(details))
        print(f"{status:8} {path.relative_to(args.folder)}  {', '.join(details)}")

    print("\nTotal:", ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    for code, n in codes.most_common():
        print(f"  {code:28} {n}")
    sys.exit(1 if statuses["failed"] else 0)


if __name__ == "__main__":
    main()
