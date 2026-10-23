"""Sheets cut from the modelled panels (SHEET-COUNT-PIECES, RESEARCH §27).

How many whole sheets a line of sheet-good panels is cut from, under one
deterministic rule (:func:`sheets_to_cut`): largest panels first, each from
the smallest offcut that covers it else a new sheet, a 1/8 in kerf lost at
every real cut (SHEET-KERF) and absorbed once by APA's 1/8 in panel gap
(SHEET-KERF-GAP), floor panels never turned off their strength axis
(SUBFLOOR-GRAIN). Pure; :mod:`loft_wire.cut_list` builds its sheet lines on
it.
"""

from collections.abc import Iterable
from typing import Final

from loft_wire.lumber import MM_PER_INCH
from loft_wire.sheet_goods import SHEET_FIT_TOLERANCE_MM, SheetSize

#: Panels are ordered when equal to this many decimals of a millimetre, as
#: :data:`loft_wire.cut_list.LENGTH_DECIMALS`.
LENGTH_DECIMALS: Final = 3

#: The saw kerf lost at every cut of a sheet (mm): 1/8 in, a circular saw's
#: or panel saw's blade (SHEET-KERF). The panel gap absorbs one (two 48 in
#: halves come from a 96 in sheet); kerfs past it do not (three 16 in rips
#: do not come from one 48 in sheet).
SHEET_KERF_MM: Final = 0.125 * MM_PER_INCH

#: APA's gap between sheathing panels (mm): 1/8 in. A panel side within it
#: of the sheet's is a full side, laid uncut (SHEET-KERF-HALVES).
SHEET_GAP_MM: Final = 0.125 * MM_PER_INCH


Rect = tuple[float, float]


def _fits(panel: Rect, rect: Rect) -> bool:
    """Whether a ``(long, short)`` *panel* is cut from *rect*: each side at
    most :data:`SHEET_GAP_MM` short of the modelled panel's (SHEET-KERF-GAP).
    Panels are laid with APA's 1/8 in gap, so a piece 1/8 in short on an
    edge fills the panel and the gap absorbs the kerf: a 4x8 cut in half
    gives two 47 15/16 in pieces that fill two 48 in squares."""
    slack = SHEET_GAP_MM + SHEET_FIT_TOLERANCE_MM
    return panel[0] <= rect[0] + slack and panel[1] <= rect[1] + slack


def _leftovers(rect: Rect, panel: Rect, *, turn: bool) -> list[Rect]:
    """What is left of *rect* once *panel* is cut from its corner, long side
    along *rect*'s first side, a kerf (:data:`SHEET_KERF_MM`) lost at each
    cut: the RIP the full length beside it, then the END across the panel's
    width; slivers dropped. With *turn*, each is ``(long, short)``, so a
    later panel may lie either way in it; without, each keeps the sheet's
    frame, ``(along its length, along its width)``, so no panel turns.

    A side within :data:`SHEET_GAP_MM` of *rect*'s is NOT cut (SHEET-KERF-
    HALVES): a framer lays a full sheet, or a full-width rip, edge to edge
    in APA's 1/8 in panel gap, so that side leaves no offcut and loses no
    kerf. Only a side actually cut loses one.

    The END is as wide as the material, not the panel: a panel may be up to
    :data:`SHEET_GAP_MM` wider than *rect* (:func:`_fits`), and the end
    recording the panel's width would let that 1/8 in compound, piece after
    piece. So no piece is ever more than 1/8 in short."""
    out: list[Rect] = []
    pieces: list[Rect] = []
    if panel[1] < rect[1] - SHEET_GAP_MM:
        pieces.append((rect[0], rect[1] - panel[1] - SHEET_KERF_MM))
    if panel[0] < rect[0] - SHEET_GAP_MM:
        pieces.append((rect[0] - panel[0] - SHEET_KERF_MM, min(panel[1], rect[1])))
    for a, b in pieces:
        if min(a, b) > SHEET_FIT_TOLERANCE_MM:
            out.append((max(a, b), min(a, b)) if turn else (a, b))
    return out


def sheets_to_cut(
    panels: Iterable[Rect], sheet: SheetSize, *, turn: bool = True
) -> int:
    """How many sheets of *sheet* the ``(length, width)`` *panels* are cut from
    (SHEET-COUNT-PIECES): the yard sells whole sheets, so count what the
    modelled panels are actually cut from, not their area.

    Deterministic: the panels go largest face first (then longest, then
    widest). Each is cut from the smallest offcut that covers it whole (the
    earliest of equal ones), else from a new sheet. A panel is cut from a
    corner, long side along the sheet's, leaving a rip the full length
    beside it and an end across it, both offcuts for later panels, less a
    1/8 in kerf at each cut (SHEET-KERF), a piece up to 1/8 in short still
    filling its panel in the panel gap (:func:`_fits`): three 16 in rips
    take two 48 in sheets, two 24 in rips one. With *turn* false (a floor's
    panels, SUBFLOOR-GRAIN) each panel is ``(across the joists, along
    them)`` and is placed so: its across side along the sheet's length, the
    strength axis, in the sheet and in every offcut, never turned; with
    *turn* (wall sheathing) a panel may lie either way in an offcut.
    Openings are not credited: a panel is its whole face, as framers
    sheathe over an opening and cut it out."""
    # A wall panel may turn, so it goes (long, short); a floor panel keeps
    # the (across, along) it was given, across along the sheet's length.
    rects = sorted(
        ((max(a, b), min(a, b)) if turn else (a, b) for a, b in panels),
        key=lambda r: (
            -round(r[0] * r[1], LENGTH_DECIMALS),
            -round(r[0], LENGTH_DECIMALS),
            -round(r[1], LENGTH_DECIMALS),
        ),
    )
    if not rects:
        return 0
    smallest = (min(r[0] for r in rects), min(r[1] for r in rects))
    whole: Rect = (sheet.length_mm, sheet.width_mm)
    offcuts: list[Rect] = []
    sheets = 0
    for panel in rects:
        best: int | None = None
        for index, offcut in enumerate(offcuts):
            if _fits(panel, offcut) and (
                best is None
                or offcut[0] * offcut[1] < offcuts[best][0] * offcuts[best][1]
            ):
                best = index
        if best is None:
            sheets += 1
            source = whole
        else:
            source = offcuts.pop(best)
        # An offcut no panel could fit is dropped, keeping the scan short.
        offcuts.extend(
            r for r in _leftovers(source, panel, turn=turn) if _fits(smallest, r)
        )
    return sheets
