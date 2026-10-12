import typing

import fb2kit


def test_str_mode_and_backend_are_annotated() -> None:
    for fn in (fb2kit.parse, fb2kit.parse_string):
        hints = typing.get_type_hints(fn)
        assert str in typing.get_args(hints["mode"])
        assert str in typing.get_args(hints["backend"])
