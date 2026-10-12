import typing

import pytest

import fb2kit
from fb2kit import model


@pytest.mark.parametrize("name", model.__all__)
def test_model_types_are_reexported(name: str) -> None:
    assert getattr(fb2kit, name) is getattr(model, name)
    assert name in fb2kit.__all__


def test_by_id_annotation_admits_binary() -> None:
    hints = typing.get_type_hints(fb2kit.FictionBook.by_id)
    assert fb2kit.Binary in typing.get_args(hints["return"])
    assert fb2kit.Binary in typing.get_args(
        typing.get_args(typing.get_type_hints(fb2kit.FictionBook)["index"])[1]
    )
