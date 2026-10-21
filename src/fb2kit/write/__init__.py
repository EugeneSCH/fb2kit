"""Writing FB2 books: serialization, validation, building and editing."""

from fb2kit.write.build import BookBuilder, IdGenerator, SectionBuilder, new_book
from fb2kit.write.edit import (
    edit_metadata,
    reindex,
    replace_node,
    with_binaries,
    with_cover,
    with_description,
)
from fb2kit.write.validate import (
    WRITE_DANGLING_LINK,
    WRITE_DUPLICATE_ID,
    WRITE_EMPTY_BODY,
    WRITE_INVALID_CHAR,
    WRITE_INVALID_ID,
    WRITE_LOST_ID,
    WRITE_MISSING_BINARY,
    WRITE_NO_BODY,
    WRITE_NO_TITLE,
    Problem,
    WriteReport,
    WriteSeverity,
    validate,
)

__all__ = [
    "WRITE_DANGLING_LINK",
    "WRITE_DUPLICATE_ID",
    "WRITE_EMPTY_BODY",
    "WRITE_INVALID_CHAR",
    "WRITE_INVALID_ID",
    "WRITE_LOST_ID",
    "WRITE_MISSING_BINARY",
    "WRITE_NO_BODY",
    "WRITE_NO_TITLE",
    "BookBuilder",
    "IdGenerator",
    "Problem",
    "SectionBuilder",
    "WriteReport",
    "WriteSeverity",
    "edit_metadata",
    "new_book",
    "reindex",
    "replace_node",
    "validate",
    "with_binaries",
    "with_cover",
    "with_description",
]
