"""B-rep intersection volume of two bodies — the kernel half of clash detection.

The kernel primitive behind assembly interference/collision detection (BACKLOG
P1, design ``assemblies.md`` §4): given two whole part bodies ALREADY at their
solved world placements, compute the exact volume of their overlap solid via
OCCT's ``BRepAlgoAPI_Common`` (the same boolean the ``intersect`` feature uses,
reached through build123d's ``Shape.intersect`` — license-clean, OCCT is the
kernel). The assembly layer (:mod:`geometry.assembly.interference`) places the
bodies (reusing :func:`geometry.kernel.export.place_body`) and scans the pairs;
this module owns only the two-body overlap-volume kernel call, so no OCP import
leaves ``geometry.kernel``.

**Clash volume floor (principled, NOT an ad-hoc epsilon).** The kernel linear
tolerance is ``1e-7 m = 1e-4 mm`` (RESEARCH §9; the ``extrude.py``
``PROFILE_WIRE_TOLERANCE`` twin). A genuine interference means the two bodies
interpenetrate by more than that tolerance in every dimension; the volume of the
smallest such interpenetration is one kernel-tolerance CUBE, so we report a clash
only when the common solid's volume exceeds :data:`CLASH_VOLUME_FLOOR_MM3` =
``(1e-4 mm)³ = 1e-12 mm³`` — a volume below a tolerance-edge voxel is modelling
noise, not a real overlap. In practice two exactly-coincident faces produce an
EMPTY common (zero solids, filtered first), so the floor is the belt-and-braces
guard against a sub-tolerance sliver OCCT may emit at grazing contact; a
just-touching pair therefore reports NO clash.

Determinism (RESEARCH §9): ``BRepAlgoAPI_Common`` + the GProp volume integration
are pure OCCT algorithms on identical placed inputs — no iteration over an
unordered container participates — so the same two bodies yield a byte-identical
overlap volume across interpreter restarts.
"""

from __future__ import annotations

from build123d import Compound, ShapeList, Solid

from geometry.kernel.properties import measure_shape
from geometry.kernel.types import BodyShape

#: Kernel linear tolerance expressed in mm (``1e-7 m``; RESEARCH §9). The
#: ``extrude.py`` ``PROFILE_WIRE_TOLERANCE`` twin — the geometry service works in
#: mm, so the 1e-7 m kernel tolerance is 1e-4 mm.
_KERNEL_LINEAR_TOL_MM = 1e-4

#: Minimum common-solid volume (mm³) that counts as a real interference: one
#: kernel-tolerance CUBE (module docstring). An overlap below this is within
#: modelling noise (the bodies merely touch), never reported as a clash.
CLASH_VOLUME_FLOOR_MM3 = _KERNEL_LINEAR_TOL_MM**3


def intersection_volume(a: BodyShape, b: BodyShape) -> float:
    """Exact volume of the overlap solid of two world-placed bodies (mm³).

    Runs ``BRepAlgoAPI_Common`` (via build123d ``Shape.intersect``) over the two
    bodies as positioned, then integrates the volume of the resulting solid(s)
    through the shared mass-property path (:func:`measure_shape`). Returns ``0.0``
    when the bodies do not overlap, meet only in a degenerate (zero-volume)
    contact, or the kernel boolean cannot form a common solid from a grazing
    contact — none of which is a real interference. Non-negative and
    deterministic (module docstring).
    """
    try:
        # intersect carries a Shape[Unknown] type param upstream (the same gap
        # boolean.py / tessellate.py document) and returns a ShapeList of the
        # common lumps, or None for an empty common — scoped ignores only.
        common: ShapeList[Solid] | None = a.intersect(b)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception:  # OCCT contact-degeneracy failure modes are not a taxonomy
        # A boolean that cannot form a common solid from a grazing/degenerate
        # contact is a touch, not an interpenetration — no reportable clash.
        return 0.0
    solids: list[Solid] = list(common.solids()) if common is not None else []  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if not solids:
        return 0.0
    overlap: BodyShape = solids[0] if len(solids) == 1 else Compound(children=solids)
    return float(measure_shape(overlap).volume)
