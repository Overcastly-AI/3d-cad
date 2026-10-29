"""Architectural feet-inch lengths to 1/16 in (HOUSE-DRAWINGS).

How a US builder reads a print: ``24'-0"``, ``8'-1 1/8"``, ``6'-10 1/2"``; a
length under a foot as inches alone (``5 1/2"``, ``3/4"``). Rounded half up to
the nearest sixteenth, the fraction in lowest terms.

The sheet (this function) and the screen (``formatFeetInches`` in
``packages/design``) must never print different numbers, so both take the SAME
steps in IEEE doubles, which Python and JavaScript compute identically:

1. ``x = |mm| / 25.4`` and ``t = x * 32``, the length in 32nds;
2. a ``t`` within :data:`SNAP_32NDS` of a whole 32nd IS that 32nd: a length a
   model holds at 11 31/32 in arrives a hair under or over it after the mm
   round trip, and the print must read it as the half-sixteenth it is. The
   snapped 32nd is exact (a :class:`~fractions.Fraction`), and an odd 32nd is
   a half-sixteenth, rounded up;
3. otherwise ``floor(x * 16 + 0.5)``.

``packages/design/src/feetInches.vectors.json`` (10,000 values, half of them
exact half-sixteenths) pins both implementations to the same text.
"""

import math
from fractions import Fraction

#: Millimetres per inch.
MM_PER_INCH = 25.4

#: The finest fraction a print carries.
SIXTEENTHS = 16

#: How close (in 32nds of an inch, ~3e-8 in) a length must be to a whole
#: 32nd to be that 32nd: far above the mm round trip's drift, far below any
#: length a builder dimensions.
SNAP_32NDS = 1e-6


def sixteenths(value_mm: float) -> int:
    """|*value_mm*| in whole sixteenths of an inch, rounded half up."""
    x = abs(value_mm) / MM_PER_INCH
    t = x * 32
    nearest = math.floor(t + 0.5)
    if abs(t - nearest) <= SNAP_32NDS:
        # Exact: an odd 32nd is a half-sixteenth, and half goes up.
        return math.floor(Fraction(nearest, 2) + Fraction(1, 2))
    return math.floor(x * 16 + 0.5)


def feet_inches(value_mm: float) -> str:
    """*value_mm* as architectural feet-inch, rounded to 1/16 in."""
    steps = sixteenths(value_mm)
    feet, rest = divmod(steps, 12 * SIXTEENTHS)
    inches, part = divmod(rest, SIXTEENTHS)
    fraction = Fraction(part, SIXTEENTHS)
    frac = "" if part == 0 else f"{fraction.numerator}/{fraction.denominator}"
    if feet > 0:
        inch_text = f"{inches} {frac}" if frac else f"{inches}"
        text = f"{feet}'-{inch_text}\""
    elif inches > 0:
        text = f'{inches} {frac}"' if frac else f'{inches}"'
    else:
        text = f'{frac}"' if frac else '0"'
    return f"-{text}" if value_mm < 0 and steps > 0 else text
