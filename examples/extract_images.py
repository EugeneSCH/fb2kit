"""The cover and all book images into a folder: python extract_images.py BOOK OUT_DIR."""

import argparse
import mimetypes
import re
from pathlib import Path

import fb2kit


def safe_name(binary_id: str, content_type: str) -> str:
    """An id from the book is not a path: keep safe characters and append the extension."""
    stem = re.sub(r"[^\w.-]", "_", binary_id).lstrip(".") or "binary"
    ext = mimetypes.guess_extension(content_type) or ".bin"
    return stem if stem.lower().endswith(ext) else stem + ext


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()

    book = fb2kit.parse(args.book, mode=fb2kit.Mode.TOLERANT)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for binary in book.binaries:
        if not binary.data:
            print(f"skip {binary.id}: empty or broken base64")
            continue
        name = safe_name(binary.id, binary.content_type)
        (args.out_dir / name).write_bytes(binary.data)
        mark = " (cover)" if binary is book.cover else ""
        print(f"{name}\t{binary.content_type}\t{binary.size}{mark}")


if __name__ == "__main__":
    main()
