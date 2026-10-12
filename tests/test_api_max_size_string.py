import pytest

import fb2kit

_NS = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
_DESC = "<description><title-info><book-title>T</book-title></title-info></description>"


def test_parse_string_max_size() -> None:
    xml = f"<FictionBook {_NS}>{_DESC}<body/></FictionBook>"
    with pytest.raises(fb2kit.Fb2SourceError, match="max_size"):
        fb2kit.parse_string(xml, max_size=10)
    assert fb2kit.parse_string(xml, max_size=len(xml.encode()))
