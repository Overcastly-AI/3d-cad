"""Stock lengths and splices for lumber cut-list lines (CUT-LIST, RESEARCH §27).

Split from :mod:`loft_wire.cut_list` (FILE-SIZE-RATCHET), which re-exports
every public name: the shortest stock that covers a member, and the splices
that cover one longer than the longest stock. Pure, no I/O.
"""

from collections.abc import Sequence
from functools import lru_cache
from itertools import combinations_with_replacement
from typing import Final

from loft_wire.lumber import MM_PER_INCH, STOCK_LENGTHS_FT

#: Millimetres per foot, exactly.
MM_PER_FOOT: Final = 12 * MM_PER_INCH

#: The most stock pieces one member is spliced from: 5 x 24 ft covers 120 ft
#: of dimension lumber (5 x 20 ft, 100 ft, of the rest). A longer member (a
#: modelling slip more often than a real plate) has no stock, so it is listed
#: and left unpriced, never guessed at.
MAX_SPLICE_PIECES: Final = 5


def _covers(length_mm: float, feet: int) -> bool:
    return length_mm <= feet * MM_PER_FOOT + 1e-6


def stock_length_ft(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> int | None:
    """The shortest stock of *lengths* (ft, shortest first; every standard
    length by default) that covers *length_mm*, or ``None``."""
    for feet in lengths:
        if _covers(length_mm, feet):
            return feet
    return None


@lru_cache(maxsize=1024)
def _splice_tiers(
    length_mm: float, lengths: tuple[int, ...]
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Every 2 to :data:`MAX_SPLICE_PIECES`-piece splice of *lengths* that
    covers *length_mm*, in tiers (:func:`stock_splice_tiers`), whether or
    not one stock length covers it too."""
    tiers: dict[tuple[int, int], list[tuple[int, ...]]] = {}
    for pieces in range(2, MAX_SPLICE_PIECES + 1):
        for splice in combinations_with_replacement(
            sorted(lengths, reverse=True), pieces
        ):
            feet = sum(splice)
            if _covers(length_mm, feet):
                tiers.setdefault((pieces, feet), []).append(splice)
    return tuple(tuple(sorted(tiers[key], key=_evenness)) for key in sorted(tiers))


def _evenness(splice: tuple[int, ...]) -> tuple[int, ...]:
    """Sort key among equally good splices: the most even first (the longest
    shortest piece, then the shortest longest), then the longer pieces first,
    so 24 ft is 12 + 12, then 14 + 10, then 16 + 8."""
    return (-min(splice), max(splice), *(-feet for feet in splice))


def stock_splice_tiers(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Every splice that covers a member longer than the longest stock,
    grouped into tiers of equally good splices, the best tier first
    (RESEARCH §27).

    A framer splices a plate or rim longer than stock from stock pieces, the
    joints over studs or joists (Chief Architect's materials list buys it the
    same way). A splice is a combination of at most :data:`MAX_SPLICE_PIECES`
    stock pieces covering *length_mm*, each longest piece first; tiers are
    ordered by FEWEST PIECES (joints), then LEAST WASTE (the fewest feet
    bought), and within a tier most even first (:func:`_evenness`). Joints
    must land over a stud or joist and double top-plate joints be offset 24
    in (IRC R602.3.2), so a framer orders plates and rims in the longest
    lengths and cuts blocking from the offcut: 28 ft with 8, 10 and 16 ft
    stock is 2 x 16, not 10 + 10 + 8 (SPLICE-FEWEST-PIECES). The first tier
    is the choice (:func:`stock_splices`); the later ones let
    :func:`price_lines` buy what the book prices, as a yard quotes 28 ft as
    16 + 16 when it stocks no 14 ft. *lengths* are the stock lengths (ft)
    the member is sold in (every standard length by default). Empty for a
    member that one stock length covers, or that no splice covers."""
    if stock_length_ft(length_mm, lengths) is not None:
        return ()
    return _splice_tiers(length_mm, tuple(lengths))


def stock_splices(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT
) -> tuple[tuple[int, ...], ...]:
    """The equally good fewest-piece, least-waste splices for a member longer
    than the longest stock, best first: the first tier of
    :func:`stock_splice_tiers` (26 ft is 14 + 12, 16 + 10 or 18 + 8; 37 ft
    is 20 + 18). Empty for a member that one stock length covers, or that no
    splice covers."""
    tiers = stock_splice_tiers(length_mm, lengths)
    return tiers[0] if tiers else ()


def stock_pieces_ft(
    length_mm: float, lengths: Sequence[int] = STOCK_LENGTHS_FT, *, splice: bool = True
) -> tuple[int, ...] | None:
    """The stock one member of *length_mm* is cut from: one stock length of
    *lengths*, else the best splice, or ``None`` when no splice covers it or
    the member may not be spliced (*splice* false, NO-SPLICE-SPANS)."""
    single = stock_length_ft(length_mm, lengths)
    if single is not None:
        return (single,)
    if not splice:
        return None
    splices = stock_splices(length_mm, lengths)
    return splices[0] if splices else None


def no_stock_note(member: str | None, lengths: Sequence[int], *, splice: bool) -> str:
    """Why a lumber piece has no stock (``stock_note``): a one-piece member
    past the longest stock, or any member past the longest splice."""
    longest = max(lengths)
    if not splice:
        what = (member or "member").lower()
        return f"One piece, longer than {longest} ft stock: a {what} is not spliced"
    return (
        f"Longer than {MAX_SPLICE_PIECES} x {longest} ft: no splice of stock covers it"
    )


def splice_label(pieces: Sequence[int]) -> str:
    """A member's stock as a framer writes it: ``16 ft``, ``2 x 12 ft``,
    ``14 ft + 12 ft``, ``2 x 20 ft + 8 ft`` (longest first), as the CSV writes it."""
    counts: dict[int, int] = {}
    for feet in sorted(pieces, reverse=True):
        counts[feet] = counts.get(feet, 0) + 1
    return " + ".join(
        f"{feet} ft" if n == 1 else f"{n} x {feet} ft" for feet, n in counts.items()
    )
