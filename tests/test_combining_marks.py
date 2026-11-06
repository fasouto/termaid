"""A Thai label lays out exactly like an ASCII label of the same display width."""
from __future__ import annotations

import pytest

from termaid import render
from tests.conftest import FIXTURES_DIR

# Thai word -> ASCII stand-in of the same display width (3, 5, 7 columns);
# no stand-in contains another, so swapping back is exact.
STAND_INS = {"ผู้ใช้": "xqz", "น้ำแข็ง": "vbnmk", "สวัสดีครับ": "hjgfdsy"}


def swap(text: str, pairs) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


@pytest.mark.parametrize("path", sorted(FIXTURES_DIR.rglob("thai_*.mmd")), ids=lambda p: p.stem)
@pytest.mark.parametrize("use_ascii", [False, True], ids=["unicode", "ascii"])
def test_thai_renders_like_ascii_of_equal_width(path, use_ascii):
    thai_source = path.read_text()
    ascii_source = swap(thai_source, STAND_INS.items())
    expected = swap(render(ascii_source, use_ascii=use_ascii), [(a, t) for t, a in STAND_INS.items()])
    assert render(thai_source, use_ascii=use_ascii) == expected
