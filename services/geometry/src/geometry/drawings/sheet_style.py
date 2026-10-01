"""Drawing tokens and text rows shared by the SVG, PDF and DXF emitters.

Split out of :mod:`geometry.drawings.compose` (SPLIT-COMPOSE): the ``drawing`` token
palette, stroke weights, title-block free-text rows, bend/thread table cells and the
layout-issue banner. One source, so the three export formats print the same sheet.
"""

# The drawings modules were split out of one file (SPLIT-COMPOSE) and share their
# underscore helpers and tokens: underscore here means private to the drawings
# package, not to one module.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import NamedTuple

from loft_wire.drawings import (
    BendTableRow,
    ComposedSheet,
    ComposedTitleBlock,
    ThreadCalloutRow,
)

from geometry.drawings.layout import (
    _BANNER_LINE_MM,
    _BANNER_MAX_LINES,
)


def _fit(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars, eliding the overflow with a single "…".

    The title-block fit posture, factored out so the drawing ``title`` and the
    free-text ``author``/``date``/``notes`` share ONE truncation rule. ``len(text) ==
    limit`` is kept verbatim (no ellipsis); ``> limit`` keeps ``limit - 1`` chars + "…".
    """
    return f"{text[: limit - 1]}…" if len(text) > limit else text


# @loft/design `drawing` token palette (tokens.ts) — the SAME colours the on-screen
# sheet renders, as inline attributes (one palette, N renderers).
#
# ONE DELIBERATE DIVERGENCE: the page fill. The screen token `drawing.paper` is a soft
# grey (#ECEFF2) because on screen a sheet must read AS A SHEET against dark app
# chrome. An EXPORTED artifact is not a UI surface — it is a print, and a print's paper
# is white. Filling it #ECEFF2 meant every PDF a shop received was a grey A3 (audit N5)
# with a full page of toner behind the drawing. So the exported page — and every
# knockout that has to match it (the dimension-text halo, the annotation-block backers)
# — is WHITE, from this one constant. The strokes below are shared with the screen
# unchanged; only the paper differs, because only the medium does.
_PAPER = "#FFFFFF"
_PAPER_EDGE = "#C9CFD7"
_INK = "#1B222B"
_EDGE_VISIBLE = "#1B222B"
_EDGE_HIDDEN = "#6E7A88"
#: Flat-pattern fold-line stroke (sheet-metal.md §6/§7) — a distinct dashed-blue, NOT
#: the visible/hidden body-edge styling. The SINGLE source is the frontend
#: `drawing.bend`
#: design token (packages/design/src/tokens.ts), which the on-screen sheet + SVG/PDF/DXF
#: renderers all read; this constant is the byte-export twin (the cross-renderer token
#: duplication the module header notes) — keep the two hexes in lock-step.
_EDGE_BEND = "#2F6FEB"
#: Section crosshatch stroke (drawings-section.md §5) — a quiet thin graphite, the
#: conventional ANSI section-line ink, distinct from the body-edge and dimension inks.
#: Export-only in v1 (§5); the paired DOM sheet hatch is a BACKLOG follow-on that adds
#: the matching `drawing.hatch` design token (the cross-renderer token duplication the
#: module header notes) so the on-screen and exported hatch stay one colour.
_HATCH_INK = "#7A8695"
_LABEL = "#48525E"
_DIM_INK = "#2A3542"
_DIM_TEXT = "#1B222B"
_DIM_FLAG = "#B23A2E"

# Stroke weights (mm) — @loft/design `drawing` token weights.
_BORDER_W = 0.7
_VISIBLE_W = 0.5
_HIDDEN_W = 0.35
_DIM_W = 0.3
_EXT_W = 0.25
_PAPER_EDGE_W = 0.6
_HIDDEN_DASH = "2 1.4"  # hiddenDashMm + hiddenGapMm
_BEND_W = 0.4  # flat-pattern fold-line weight (sheet-metal.md §7)
_BEND_DASH = "3 1.6"  # bend fold-line dash (distinct from the hidden-edge dash)
_HATCH_W = 0.25  # section crosshatch stroke weight (drawings-section.md §5)

#: Monospace stack (font.data) — the drafting vernacular. Emitted with escaped
#: quotes so the attribute stays valid standalone XML.
_FONT = "&quot;Fragment Mono&quot;, ui-monospace, monospace"

#: Free-text note height (mm) — a sibling of the dimension/title-block value stamp
#: (`drawing.dimensionTextMm`), so a note reads as ordinary sheet body text in graphite
#: ink. The SINGLE size the SVG/PDF/DXF note serializers share; the paired DOM sheet
#: half (BACKLOG follow-on) adds the matching `drawing.noteTextMm` design token so the
#: on-screen note and the exported note are the SAME height (the cross-renderer token
#: duplication the module header notes).
_NOTE_TEXT_MM = 3.2

# --- title-block free-text fields (author/date/notes) — AUDIT-ENGINEERING D1 -------
# The optional TitleBlock free-text is stamped as three secondary labeled rows in the
# left cell's mid-band (below the drawing title, above the "LOFT · PART DRAWING"
# footer), a caption + value per row. Smaller than the primary title (a real block's
# secondary fields are), sized to fit without touching the existing title/scale/size
# placement — so a block with NO free-text emits none of these rows and stays
# byte-identical (the additive posture). The SINGLE source of the captions, sizes, and
# row offsets, shared by the SVG/PDF/DXF serializers via `_tb_fields` (the cross-
# renderer parity the bend-table/notes fields carry). The paired on-screen DrawingSheet
# .tsx block is the BACKLOG DOM follow-on; it mirrors these captions/rows.
_TB_FIELD_CAP_MM = 2.1  # secondary-field caption height (mm)
_TB_FIELD_VAL_MM = 2.4  # secondary-field value height (mm)
_TB_FIELD_CAP_DX = 4.0  # caption x offset from the block left edge (mm)
_TB_FIELD_VAL_DX = 18.0  # value x offset from the block left edge (mm)
#: Per-row baseline y offsets from the block TOP edge (mm), in field order.
_TB_FIELD_ROWS_DY: tuple[float, ...] = (20.5, 23.5, 26.5)
#: Fixed captions, in field order (author, date, notes).
_TB_FIELD_CAPTIONS: tuple[str, ...] = ("DRAWN", "DATE", "NOTES")
#: Field keys (for the SVG/DOM ``data-testid``), in the SAME field order.
_TB_FIELD_KEYS: tuple[str, ...] = ("author", "date", "notes")


class TitleBlockFieldRow(NamedTuple):
    caption: str  # the fixed label ("DRAWN" / "DATE" / "NOTES")
    value: str  # the truncated free-text value (never None — Nones are skipped)
    dy: float  # baseline y offset from the block top edge (mm)
    key: str  # field key ("author" / "date" / "notes"), for the data-testid


def _tb_fields(tb: ComposedTitleBlock) -> list[TitleBlockFieldRow]:
    """The free-text rows to stamp for a title block, in field order.

    The ONE place the "which free-text rows render" decision lives: a ``None`` field
    (unset / blank) is skipped, so all three serializers stamp the SAME rows at the SAME
    offsets and an empty title block yields ``[]`` (nothing emitted → byte-identical).
    """
    out: list[TitleBlockFieldRow] = []
    for caption, value, dy, key in zip(
        _TB_FIELD_CAPTIONS,
        (tb.author, tb.date, tb.notes),
        _TB_FIELD_ROWS_DY,
        _TB_FIELD_KEYS,
        strict=True,
    ):
        if value is not None:
            out.append(TitleBlockFieldRow(caption, value, dy, key))
    return out


def _bend_row_cells(row: BendTableRow) -> tuple[str, str, str, str, str]:
    """Canonical per-column cell strings for one bend-table row.

    CANONICAL SPEC — mirrors apps/web/src/components/DrawingSheet.tsx `BendTable`
    VERBATIM so every export format matches the on-screen table (see the
    ``_BEND_TABLE_CAPTIONS`` note). Columns are ``(BEND, ANGLE, RADIUS, DIR, ALLOW)``::

        BEND   = bend_id
        ANGLE  = f"{angle_deg:.1f}°"          (1 dp + degree glyph)
        RADIUS = f"R{radius_mm:.2f}"          (R-prefixed, 2 dp)
        DIR    = "UP" | "DOWN"
        ALLOW  = f"{bend_allowance_mm:.2f}"   (bare 2 dp mm — the caption carries "mm")

    ONE format, shared by the SVG/PDF/DXF serializers (each is a pure layout pass
    over these cells). Do NOT reformat per renderer — that DRY break is exactly what
    let the PDF/DXF drift to a run-together 3-dp ``BA``-line diverging from the screen.
    Fixed-decimal formatting is byte-stable across an interpreter restart (§8.3).
    """
    return (
        row.bend_id,
        f"{row.angle_deg + 0.0:.1f}°",
        f"R{row.radius_mm + 0.0:.2f}",
        "UP" if row.direction == "up" else "DOWN",
        f"{row.bend_allowance_mm + 0.0:.2f}",
    )


def _thread_row_cells(row: ThreadCalloutRow) -> tuple[str, str, str]:
    """Canonical per-column cell strings for one thread-schedule row (BACKLOG #50).

    Columns are ``(QTY, THREAD, TAP DRILL)``::

        QTY       = f"{quantity}x"            ("4x" — how a print counts holes)
        THREAD    = designation               ("M6x1", ASCII, kernel-formatted)
        TAP DRILL = f"{tap_drill_mm:.2f}"     (bare 2 dp mm; the caption says what)

    ONE format shared by the SVG/PDF/DXF serializers (each is a pure layout pass over
    these cells) — the same DRY lock the bend table uses, for the same reason. Fixed
    decimals are byte-stable across an interpreter restart (§8.3).
    """
    return (f"{row.quantity}x", row.designation, f"{row.tap_drill_mm:.2f}")


#: Severity prefix for a stamped banner line (audit N2) — the machinist reads the
#: severity first. Shared by all three serializers.
_BANNER_PREFIX: dict[str, str] = {
    "error": "LAYOUT ERROR: ",
    "warning": "LAYOUT WARNING: ",
}


class BannerLine(NamedTuple):
    """One stamped banner line: position, text, and whether it is an error."""

    x: float
    y: float
    text: str
    error: bool


def banner_lines(composed: ComposedSheet) -> list[BannerLine]:
    """The sheet's layout-issue banner, as stamped text lines (audit N2).

    THE single banner layout the SVG / PDF / DXF serializers share (CLAUDE.md DRY): the
    first :data:`_BANNER_MAX_LINES` issues at their composed anchors, plus a "+N MORE"
    tail line when there are more, so an unreadable sheet announces itself on the print
    in every format and a pathological sheet still cannot paper itself over. Empty for a
    clean sheet — which is why a clean sheet's bytes are unchanged."""
    issues = composed.layout_issues
    lines = [
        BannerLine(
            x=issue.at.x_mm,
            y=issue.at.y_mm,
            text=_BANNER_PREFIX.get(issue.severity, "") + issue.message,
            error=issue.severity == "error",
        )
        for issue in issues[:_BANNER_MAX_LINES]
    ]
    remaining = len(issues) - len(lines)
    if remaining > 0 and lines:
        last = lines[-1]
        lines.append(
            BannerLine(
                x=last.x,
                y=last.y + _BANNER_LINE_MM,
                text=f"+{remaining} MORE LAYOUT ISSUE(S)",
                error=any(i.severity == "error" for i in issues[_BANNER_MAX_LINES:]),
            )
        )
    return lines
