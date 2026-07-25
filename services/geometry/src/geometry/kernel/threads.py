"""ISO metric screw threads — the COSMETIC thread representation (v1).

The kernel half of a TAPPED hole. This module owns no OCCT geometry at all, and
that is the whole decision:

DECISION (v1, 2026-07-25 — the trade-off the BACKLOG tail records): a tapped
hole is a **tap-drill bore plus a typed thread callout**, NOT modelled helical
geometry. What the kernel cuts is exactly the plain cylinder a simple hole cuts
(so a tapped hole composes with mirror/pattern/shell/STEP identically, with zero
new boolean risk); what the tap adds is *metadata* — the designation, carried in
the feature params, from which drawings/BOM/export callouts are DERIVED (never
stored, never stale — the assembly-BOM posture).

WHY COSMETIC (and what would have to change to model threads later):

* Modelled helices explode the face count of every fastener hole (a single
  M6 x 1 through-thread is hundreds of faces where the cosmetic bore is one) and
  that cost multiplies through patterns, mirrors, tessellation, STEP export and
  the drawing projector — the exact downstream performance wreck the incumbents
  avoid by defaulting to cosmetic threads (SolidWorks "Straight Tap",
  Fusion "Modeled: off", Onshape's thread cosmetic). A daily driver must stay
  fast on a plate with 40 tapped holes.
* The manufactured feature IS the tap-drill bore: a thread is cut by a tap, not
  by the mill, so the modelled solid that matches the shop floor is the bore.
* Mass properties: the cosmetic bore is a rigorous OVER-estimate of removed
  material by less than the thread's own crest volume, and — unlike a modelled
  helix — its volume is closed-form, which is what makes the golden analytic.

To add MODELLED threads later (an additive, non-breaking follow-up): add a
``modelled: bool = False`` flag to the thread spec, build the helical sweep tool
in this module (``Solid.sweep`` of the ISO 68-1 truncated-triangle profile along
a helix of the given pitch), cut it after the bore in
``geometry.features.evaluate._evaluate_hole``, and give the modelled case its
OWN golden + tolerance tier (a swept helix is NOT analytic — the golden would
assert against a cross-checked kernel value, not a closed form). The cosmetic
path must remain the default; nothing above changes.

TYPED DEGRADATION (never a 500, never a silent fallback to a plain hole — the
feature layer maps these 1:1 onto ``hole_thread_unsupported`` /
``hole_thread_mismatch``):

* :class:`ThreadUnsupportedError` — the (nominal, pitch) pair is not a real ISO
  261 combination this kernel knows. A designation the kernel cannot honour must
  never degrade to "just a hole with a wrong callout on the drawing".
* :class:`ThreadBoreMismatchError` — the authored bore is not a tappable hole for
  the designation (outside ``[minor diameter, nominal diameter)``), e.g. an M6
  callout on a 20 mm bore.

Determinism (RESEARCH §9): every value here is closed-form arithmetic over the
committed table; no iteration order, no floating-point search.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

#: Basic internal-thread MINOR diameter: ``D1 = D - 2*(5/8)*H`` with the ISO 68-1
#: fundamental triangle height ``H = (sqrt(3)/2)*P`` — i.e. ``D - 1.0825*P``.
#: Written as the exact expression rather than the rounded 1.0825 so the bound is
#: the standard's, not a transcription.
_MINOR_DIAMETER_FACTOR = 1.25 * math.sqrt(3.0) / 2.0

#: Match tolerance (mm) when looking an authored ``(nominal, pitch)`` pair up in
#: the table. Real designations differ by >= 0.05 mm in pitch and >= 0.4 mm in
#: nominal diameter, so 1e-9 mm can only ever absorb float representation noise
#: (e.g. a client computing 0.7000000000000001) — never merge two designations.
_DESIGNATION_TOL = 1e-9

#: ISO 261 metric screw-thread series: nominal diameter (mm) -> the pitches (mm)
#: this kernel accepts, COARSE first then the fine pitches in descending order.
#: Source: ISO 261 (general purpose metric screw threads, general plan), M1.6
#: through M64. Adding a designation is a one-line table edit here plus its unit
#: test — deliberately data, not code, so the manufacturing knowledge has one
#: home (CLAUDE.md DRY) and an unknown combination stays a TYPED error rather
#: than a silently-accepted invention.
ISO_METRIC_PITCHES: Mapping[float, tuple[float, ...]] = {
    1.6: (0.35, 0.2),
    2.0: (0.4, 0.25),
    2.5: (0.45, 0.35),
    3.0: (0.5, 0.35),
    3.5: (0.6, 0.35),
    4.0: (0.7, 0.5),
    5.0: (0.8, 0.5),
    6.0: (1.0, 0.75),
    8.0: (1.25, 1.0, 0.75),
    10.0: (1.5, 1.25, 1.0, 0.75),
    12.0: (1.75, 1.5, 1.25, 1.0),
    14.0: (2.0, 1.5, 1.0),
    16.0: (2.0, 1.5, 1.0),
    18.0: (2.5, 2.0, 1.5, 1.0),
    20.0: (2.5, 2.0, 1.5, 1.0),
    22.0: (2.5, 2.0, 1.5, 1.0),
    24.0: (3.0, 2.0, 1.5),
    27.0: (3.0, 2.0, 1.5),
    30.0: (3.5, 3.0, 2.0, 1.5),
    33.0: (3.5, 3.0, 2.0, 1.5),
    36.0: (4.0, 3.0, 2.0, 1.5),
    39.0: (4.0, 3.0, 2.0, 1.5),
    42.0: (4.5, 4.0, 3.0, 2.0, 1.5),
    45.0: (4.5, 4.0, 3.0, 2.0, 1.5),
    48.0: (5.0, 4.0, 3.0, 2.0, 1.5),
    52.0: (5.0, 4.0, 3.0, 2.0, 1.5),
    56.0: (5.5, 4.0, 3.0, 2.0, 1.5),
    60.0: (5.5, 4.0, 3.0, 2.0, 1.5),
    64.0: (6.0, 4.0, 3.0, 2.0, 1.5),
}


class ThreadError(ValueError):
    """Base: a thread callout could not be honoured (per-feature, never a 500)."""


class ThreadUnsupportedError(ThreadError):
    """The (nominal, pitch) pair is not an ISO 261 combination this kernel knows."""


class ThreadBoreMismatchError(ThreadError):
    """The bore is not a tappable hole for the designation.

    The drilled diameter must lie in ``[minor diameter, nominal diameter)``: below
    the minor diameter a tap cannot enter at all, at or above the nominal (major)
    diameter there is no material left for the tap to cut. The ISO recommended
    tap drill ``D - P`` sits strictly inside that band.
    """


@dataclass(frozen=True)
class ResolvedThread:
    """A resolved ISO metric thread: the designation plus its derived diameters.

    Pure derived data (the feature params carry only ``nominal``/``pitch``): the
    designation string and the tap-drill / minor diameters are computed here so
    drawings, BOM and export callouts read ONE source rather than re-deriving the
    formulae (CLAUDE.md DRY — the assembly-BOM "derived, never stored" posture).
    """

    nominal_diameter_mm: float
    pitch_mm: float
    #: Human/drawing designation, e.g. ``"M10x1.5"`` (ASCII ``x``, never U+00D7).
    designation: str
    #: The ISO recommended tap drill ``D - P`` (mm) — 5.0 for M6x1, 8.5 for
    #: M10x1.5, matching the published metric tap-drill tables.
    tap_drill_diameter_mm: float
    #: Basic internal minor diameter ``D - 1.0825*P`` (mm): 100% thread depth, the
    #: SMALLEST hole a tap can enter.
    minor_diameter_mm: float


def _num(value: float) -> str:
    """A designation number without trailing zeros (``10`` / ``1.5`` / ``0.35``)."""
    return f"{value:g}"


def format_designation(nominal_diameter_mm: float, pitch_mm: float) -> str:
    """``M<nominal>x<pitch>`` — e.g. ``M6x1``, ``M10x1.5``, ``M3x0.5``.

    ASCII ``x`` deliberately (CLAUDE.md: reserve the U+00D7 glyph for markdown);
    the pitch is always spelled out, so a coarse and a fine thread of the same
    nominal diameter can never read alike."""
    return f"M{_num(nominal_diameter_mm)}x{_num(pitch_mm)}"


def resolve_iso_metric_thread(
    nominal_diameter_mm: float, pitch_mm: float
) -> ResolvedThread:
    """Resolve an authored ISO metric designation against :data:`ISO_METRIC_PITCHES`.

    Returns the designation plus its derived tap-drill and minor diameters.

    Raises:
        ThreadUnsupportedError: the nominal diameter is not in the ISO 261 series,
            or the pitch is not one of that diameter's standard pitches. A
            designation the kernel cannot honour is ALWAYS this error — never a
            silent fallback to an untapped hole (which would ship a part whose
            drawing calls out a thread nobody can cut).
    """
    pitches = next(
        (
            available
            for nominal, available in ISO_METRIC_PITCHES.items()
            if abs(nominal - nominal_diameter_mm) <= _DESIGNATION_TOL
        ),
        None,
    )
    if pitches is None:
        known = ", ".join(f"M{_num(d)}" for d in ISO_METRIC_PITCHES)
        raise ThreadUnsupportedError(
            f"M{_num(nominal_diameter_mm)} is not an ISO 261 metric thread size. "
            f"Supported nominal diameters: {known}."
        )
    if not any(abs(pitch - pitch_mm) <= _DESIGNATION_TOL for pitch in pitches):
        offered = ", ".join(_num(pitch) for pitch in pitches)
        raise ThreadUnsupportedError(
            f"{format_designation(nominal_diameter_mm, pitch_mm)} is not an ISO 261 "
            f"combination: M{_num(nominal_diameter_mm)} is standardised at pitch "
            f"{offered} mm (coarse first). Choose one of those pitches."
        )
    return ResolvedThread(
        nominal_diameter_mm=nominal_diameter_mm,
        pitch_mm=pitch_mm,
        designation=format_designation(nominal_diameter_mm, pitch_mm),
        tap_drill_diameter_mm=nominal_diameter_mm - pitch_mm,
        minor_diameter_mm=nominal_diameter_mm - _MINOR_DIAMETER_FACTOR * pitch_mm,
    )


def check_tap_drill_bore(thread: ResolvedThread, bore_diameter_mm: float) -> None:
    """Assert *bore_diameter_mm* is a hole this *thread* can actually be tapped in.

    The bore is what the kernel CUTS (a tapped hole's geometry is its tap-drill
    bore — see the module decision), so the callout and the bore must agree or the
    part is silently wrong: an M6 callout on a 20 mm bore is not a tapped hole.
    The accepted band is ``[minor diameter, nominal diameter)`` — wide enough to
    accept both the closed-form ``D - P`` and the rounded stock drill a shop table
    lists (e.g. 6.8 for M8x1.25, where ``D - P`` is 6.75), narrow enough that a
    wrong designation can never pass.

    Raises:
        ThreadBoreMismatchError: the bore is outside that band.
    """
    if not (
        thread.minor_diameter_mm - _DESIGNATION_TOL
        <= bore_diameter_mm
        < thread.nominal_diameter_mm
    ):
        raise ThreadBoreMismatchError(
            f"A {thread.designation} thread cannot be tapped in a "
            f"{_num(bore_diameter_mm)}mm bore: the drilled hole must be at least "
            f"the minor diameter {thread.minor_diameter_mm:.4f}mm and smaller than "
            f"the nominal diameter {_num(thread.nominal_diameter_mm)}mm. Use the "
            f"tap drill {_num(thread.tap_drill_diameter_mm)}mm "
            f"(nominal - pitch), or change the thread."
        )
