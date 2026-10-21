import base64
import xml.etree.ElementTree as ET

from fb2kit.model.binary import Binary
from fb2kit.write.serialize import _binary_el, build_tree


def test_binary_id_and_content_type_and_verbatim_base64() -> None:
    """С10: a binary keeps its id, its content type and its base64."""
    payload = base64.b64encode(b"x" * 120).decode()
    el = _binary_el(Binary("cover", "image/png", payload))
    assert el.get("id") == "cover"
    assert el.get("content-type") == "image/png"
    assert el.text == payload  # дословно, без переупаковки
    assert base64.b64decode(el.text or "") == b"x" * 120


def test_undecodable_binary_keeps_original_base64() -> None:
    """С11: a binary that does not decode keeps its base64."""
    el = _binary_el(Binary("bad", "image/png", "!!!"))
    assert el.text == "!!!"


def test_root_order_is_extra_description_bodies_binaries() -> None:
    """С51: the children of the root keep the order of the schema."""
    from fb2kit.api import FictionBook
    from fb2kit.model.inline import Raw, Text
    from fb2kit.model.metadata import Description, TitleInfo
    from fb2kit.model.structure import Body, Paragraph, Section

    book = FictionBook(
        description=Description(TitleInfo(title="T")),
        bodies=(Body(children=(Section(children=(Paragraph((Text("x"),)),)),)),),
        binaries=(Binary("b", "image/png", base64.b64encode(b"1").decode()),),
        element=ET.fromstring('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"/>'),
        extra=(Raw("stylesheet", "css"),),
    )
    root = build_tree(book)
    assert [c.tag.rpartition("}")[2] for c in root] == [
        "stylesheet",
        "description",
        "body",
        "binary",
    ]


def test_root_output_is_moved_into_the_description() -> None:
    """С51: the output of the root moves into the description."""
    # In the schema <output> lives inside <description>; at the root it is invalid.
    from fb2kit.api import FictionBook
    from fb2kit.model.inline import Raw
    from fb2kit.model.metadata import Description, TitleInfo

    book = FictionBook(
        description=Description(TitleInfo(title="T")),
        bodies=(),
        binaries=(),
        element=ET.fromstring('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"/>'),
        extra=(Raw("output", "out"),),
    )
    root = build_tree(book)
    assert "output" not in [c.tag.rpartition("}")[2] for c in root]
    description = root[0]
    assert "output" in [c.tag.rpartition("}")[2] for c in description]
