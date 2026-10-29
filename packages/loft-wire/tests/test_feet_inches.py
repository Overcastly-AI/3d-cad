"""Architectural feet-inch lengths (HOUSE-DRAWINGS): the cases the web's
``formatFeetInches`` (packages/design/src/feetInches.test.ts) pins too."""

import pytest
from loft_wire.feet_inches import feet_inches

IN = 25.4

CASES = [
    (288, "24'-0\""),
    (192, "16'-0\""),
    (97.125, "8'-1 1/8\""),
    (82.5, "6'-10 1/2\""),
    (60, "5'-0\""),
    (84, "7'-0\""),
    (5.5, '5 1/2"'),
    (0.75, '3/4"'),
    (0, '0"'),
    (12.03125, "1'-0 1/16\""),
    (11.99, "1'-0\""),
    (-30, "-2'-6\""),
]


@pytest.mark.parametrize(("inches", "text"), CASES)
def test_feet_inches(inches: float, text: str) -> None:
    assert feet_inches(inches * IN) == text


def test_rounds_half_up_to_the_sixteenth() -> None:
    # 0.035 in over 5 ft is 0.56 of a sixteenth (up); 0.03 in is 0.48 (down).
    assert feet_inches((60 + 0.035) * IN) == "5'-0 1/16\""
    assert feet_inches((60 + 0.03) * IN) == "5'-0\""
