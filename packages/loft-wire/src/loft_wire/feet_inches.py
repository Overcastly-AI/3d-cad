"""Architectural feet-inch lengths to 1/16 in (HOUSE-DRAWINGS).

How a US builder reads a print: ``24'-0"``, ``8'-1 1/8"``, ``6'-10 1/2"``; a
length under a foot as inches alone (``5 1/2"``, ``3/4"``). Rounded half up to
the nearest sixteenth, the fraction in lowest terms. The web's
``formatFeetInches`` (``packages/design``) is this function's twin, pinned to
the same cases.
"""

from fractions import Fraction

#: Millimetres per inch (exact).
MM_PER_INCH = Fraction(254, 10)

#: The finest fraction a print carries.
SIXTEENTHS = 16


def feet_inches(value_mm: float, denominator: int = SIXTEENTHS) -> str:
    """*value_mm* as architectural feet-inch, rounded to 1/*denominator* in."""
    exact = Fraction(value_mm) / MM_PER_INCH * denominator
    negative = exact < 0
    # Half up on the magnitude, on the exact binary value (no float drift).
    steps = int(abs(exact) + Fraction(1, 2))
    feet, rest = divmod(steps, 12 * denominator)
    inches, part = divmod(rest, denominator)
    fraction = Fraction(part, denominator)
    frac = "" if part == 0 else f"{fraction.numerator}/{fraction.denominator}"
    if feet > 0:
        inch_text = f"{inches} {frac}" if frac else f"{inches}"
        text = f"{feet}'-{inch_text}\""
    elif inches > 0:
        text = f'{inches} {frac}"' if frac else f'{inches}"'
    else:
        text = f'{frac}"' if frac else '0"'
    return f"-{text}" if negative and steps > 0 else text
