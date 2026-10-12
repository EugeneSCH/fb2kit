import contextlib
import time

import pytest

import fb2kit
from fb2kit.errors import Fb2Error
from fb2kit.report import Mode

UNITS = ["<!--", "<", "<![CDATA[", "<!", "<?", "&", "&#", "]]>", "<a", "</", "<a "]


def _time(unit: str, n: int, mode: Mode) -> float:
    start = time.perf_counter()
    with contextlib.suppress(Fb2Error):
        fb2kit.parse_string(unit * n, mode=mode)
    return time.perf_counter() - start


@pytest.mark.parametrize("mode", [Mode.TOLERANT, Mode.STRICT])
@pytest.mark.parametrize("unit", UNITS)
def test_parse_is_linear_on_pathological_input(unit: str, mode: Mode) -> None:
    small = _time(unit, 10_000, mode)
    big = _time(unit, 40_000, mode)
    assert big < 2
    assert big < max(small, 0.02) * 8  # 4x input: linear ~4x, quadratic ~16x
