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

**Robustness — a boolean failure is NOT proof of no clash.** ``BRepAlgoAPI_Common``
can *raise* on two deeply interpenetrating solids (a genuine kernel robustness
failure), which is the identical exception surface as the harmless
grazing/degenerate contact. Swallowing both to ``0.0`` would report "clear" for
parts that physically collide — the DANGEROUS false negative for a
collision-detection tool. So on the exception path we do NOT blindly return
``0.0``: we fall back to a cheap, ROBUST solved-world AABB-overlap test (a
bounding box is a linear pass over the B-rep and never hits ``Common``'s contact
degeneracies). Disjoint AABBs ⇒ a real interference is geometrically impossible ⇒
genuinely no clash. Overlapping AABBs ⇒ the boolean failure is masking a *possible*
real interference ⇒ the pair is reported ``unresolved`` (see
:class:`OverlapProbe`), for the user to inspect, never hidden as clear.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Compound, ShapeList, Solid

from geometry.kernel.properties import measure_shape
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape

#: Kernel linear tolerance expressed in mm (``1e-7 m``), single-sourced in
#: :mod:`geometry.kernel.tolerances` — this module keeps the local name it was
#: written with, but no longer its own copy of the number (CLAUDE.md DRY).
_KERNEL_LINEAR_TOL_MM = KERNEL_LINEAR_TOL_MM

#: Minimum common-solid volume (mm³) that counts as a real interference: one
#: kernel-tolerance CUBE (module docstring). An overlap below this is within
#: modelling noise (the bodies merely touch), never reported as a clash.
CLASH_VOLUME_FLOOR_MM3 = _KERNEL_LINEAR_TOL_MM**3


@dataclass(frozen=True)
class OverlapProbe:
    """Outcome of a two-body clash probe — kernel-internal, never crosses a boundary.

    Three cases, distinguished so the assembly layer never reports a masked
    boolean failure as "clear":

    * **Exact** (``unresolved`` / ``boolean_failed`` both ``False``):
      ``BRepAlgoAPI_Common`` succeeded; ``volume_mm3`` is the exact overlap-solid
      volume (``0.0`` for a disjoint or merely-grazing pair). The normal path.
    * **Unresolved** (``unresolved`` and ``boolean_failed`` both ``True``): the
      boolean RAISED but the two solved-world AABBs overlap, so a real
      interference is possible and could not be measured. ``volume_mm3`` is the
      AABB-overlap volume — a coarse magnitude HINT (it bounds the true overlap
      from above), not an exact clash volume. Must be surfaced for inspection.
    * **Degenerate-clear** (``boolean_failed`` ``True``, ``unresolved`` ``False``):
      the boolean RAISED on a grazing/degenerate contact whose AABBs are disjoint,
      so a real interpenetration is geometrically impossible → genuinely no clash
      (``volume_mm3 == 0.0``). ``boolean_failed`` stays ``True`` so the caller
      logs the exception path for observability.
    """

    volume_mm3: float
    unresolved: bool = False
    boolean_failed: bool = False


def _aabb_overlap_volume(a: BodyShape, b: BodyShape) -> float:
    """Volume (mm³) of the intersection of two bodies' axis-aligned bounding boxes.

    The cheap, ROBUST fallback for the exception path: a bounding box is a linear
    pass over the B-rep vertices and never raises the contact degeneracies
    ``BRepAlgoAPI_Common`` can. Zero when the boxes are disjoint along ANY axis
    (a real solid interference is then impossible). Non-optimal (axis-aligned)
    box on purpose — it is the fast, robust one, and an over-estimate here is the
    SAFE direction (it can only over-report a possible clash, never hide one).
    """
    ba = a.bounding_box()
    bb = b.bounding_box()
    dx = min(ba.max.X, bb.max.X) - max(ba.min.X, bb.min.X)
    dy = min(ba.max.Y, bb.max.Y) - max(ba.min.Y, bb.min.Y)
    dz = min(ba.max.Z, bb.max.Z) - max(ba.min.Z, bb.min.Z)
    if dx <= 0.0 or dy <= 0.0 or dz <= 0.0:
        return 0.0
    return dx * dy * dz


def probe_overlap(a: BodyShape, b: BodyShape) -> OverlapProbe:
    """Probe the overlap of two world-placed bodies, robust to a boolean failure.

    Runs ``BRepAlgoAPI_Common`` (via build123d ``Shape.intersect``) and, on
    success, integrates the resulting solid(s) through the shared mass-property
    path (:func:`measure_shape`) → an EXACT overlap volume (``0.0`` for a
    disjoint/grazing pair). On the exception path — a genuine OCCT robustness
    failure that is indistinguishable from a harmless degeneracy — it does NOT
    return ``0.0`` blindly: it falls back to the robust AABB-overlap test so a
    deep interpenetration the boolean choked on is surfaced as ``unresolved``, not
    hidden. See :class:`OverlapProbe`. Non-negative and deterministic (module
    docstring); total (never raises).
    """
    try:
        # intersect carries a Shape[Unknown] type param upstream (the same gap
        # boolean.py / tessellate.py document) and returns a ShapeList of the
        # common lumps, or None for an empty common — scoped ignores only.
        common: ShapeList[Solid] | None = a.intersect(b)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
    except Exception:  # OCCT contact-degeneracy / robustness faults share a surface
        # The boolean could not form a common solid. This is EITHER a harmless
        # grazing/degenerate touch OR a robustness failure masking a deep
        # interpenetration — the two share an exception surface, so decide with a
        # cheap, robust AABB-overlap test rather than assume "clear".
        aabb = _aabb_overlap_volume(a, b)
        if aabb <= 0.0:
            # Disjoint bounding boxes ⇒ a real interference is impossible ⇒ this
            # is a genuine touch, not an interpenetration → no reportable clash.
            return OverlapProbe(volume_mm3=0.0, boolean_failed=True)
        # Overlapping bounding boxes ⇒ the boolean failure is masking a POSSIBLE
        # real interference → surface it as unresolved (the AABB overlap is a
        # magnitude hint), never as clear.
        return OverlapProbe(volume_mm3=aabb, unresolved=True, boolean_failed=True)
    solids: list[Solid] = list(common.solids()) if common is not None else []  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if not solids:
        return OverlapProbe(volume_mm3=0.0)
    overlap: BodyShape = solids[0] if len(solids) == 1 else Compound(children=solids)
    return OverlapProbe(volume_mm3=float(measure_shape(overlap).volume))


def intersection_volume(a: BodyShape, b: BodyShape) -> float:
    """Exact overlap volume of two world-placed bodies (mm³) — the scalar view.

    Convenience wrapper over :func:`probe_overlap` returning just its
    ``volume_mm3``: the exact common-solid volume on the normal path, ``0.0`` for
    a disjoint/grazing pair, and — on a masked boolean failure whose AABBs overlap
    — the AABB-overlap HINT (a positive lower guard) rather than a false ``0.0``.
    Callers that must distinguish a real clash from an *unresolved* one use
    :func:`probe_overlap` directly (the assembly clash scan does). Non-negative
    and deterministic (module docstring).
    """
    return probe_overlap(a, b).volume_mm3
