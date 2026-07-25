"""B-rep healing — make a topologically non-conformal solid conformal (CM-4).

WHY THIS EXISTS. An OCCT modelling op can complete, return the geometrically
correct material, and still hand back a solid that is **not topologically
conformal**: a face whose boundary vertices land in the *interior* of a
neighbouring face's edge (a T-junction) instead of splitting it. ``BRepCheck``
calls such a solid invalid, and — critically for us — a STEP round-trip does
NOT preserve it: OCCT's reader sews the faces it reads and inserts the missing
vertices, so the re-imported body carries MORE edges than the one we exported
while the geometry is bit-for-bit the same.

That is the whole of finding **CM-4** (docs/GEOMETRY-QA.md 2026-07-25).
Measured on ``40x40x10 plate -> pocket [4,12]x[10,30] through -> fillet r3 ->
shell t2 open-top``: the exported STEP is FAITHFUL (96 ``EDGE_CURVE`` + 64
``VERTEX_POINT`` records for a 96-edge / 64-vertex body — the writer invents
nothing), the body is ``BRepCheck``-INVALID, and the re-import returns 98 edges.
The shell offsets the outer wall (x=0 -> x=2) and the pocket wall (x=4 -> x=2)
onto the SAME plane, so the 4 mm rib between them stays fully solid and the
cavity pinches to zero width: two coincident coplanar faces, the smaller one's
corners sitting mid-edge on the larger one. So the split originates on **READ**,
but the reader is not at fault — it is healing an input we should not have
written. The fix belongs at the kernel end, which is this module.

WHAT IT DOES. :func:`conform_solid` runs ``ShapeFix_Shape`` — but only on a
solid ``BRepCheck`` already rejects, so a valid body (every golden today) takes
the untouched, byte-identical path and pays only the check. Properties measured
on the CM-4 body:

* **conformal:** invalid -> valid, edges 96 -> 97 (the T-junction edge split
  once), faces 36 == 36, vertices 64 == 64;
* **geometry-preserving:** dV = -2.7e-12 mm^3, dA = 0.0, centroid moved 3.6e-14 mm
  — four orders below the planar golden tier (1e-9) and five below the STEP
  round-trip bound (1e-7). :data:`CONFORM_VOLUME_TOL_MM3` enforces this rather
  than trusting it;
* **round-trip stable:** the healed body exports and re-imports with EXACTLY 36
  faces / 97 edges / 64 vertices (dV 8.5e-11) — the CM-4 gate;
* **deterministic + idempotent** (RESEARCH §9): three fresh builds healed to
  byte-identical STEP, and ``conform(conform(x))`` is byte-identical to
  ``conform(x)``.

Scope: :mod:`geometry.kernel.shell` is the only op with evidence of producing a
non-conformal body, so it is the only caller. Other ops adopt this the day a
gate catches them (DRY: extract on the second real use, not the first imagined
one) — the helper is deliberately op-agnostic so that is a one-line change.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from build123d import Solid
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Shape
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

#: Largest volume change a heal may introduce before we refuse its result, in
#: mm^3. Healing rebuilds topology, never material: the CM-4 body moves
#: -2.7e-12 mm^3 (float noise on a 6171 mm^3 solid). The bound is the PLANAR
#: golden tier (1e-9), i.e. ~370x the measured worst case and still 100x tighter
#: than the STEP round-trip bound the gate asserts — so a heal that actually
#: moved material could not hide inside it.
CONFORM_VOLUME_TOL_MM3 = 1e-9


class HealingError(RuntimeError):
    """A non-conformal solid could not be healed into ONE valid solid.

    Raised when ``ShapeFix_Shape`` leaves the body still invalid, yields other
    than exactly one solid, or moves the volume by more than
    :data:`CONFORM_VOLUME_TOL_MM3`. Callers map it onto their own typed feature
    error (e.g. ``shell_failed``) — a body we know to be malformed is never
    shipped just because its mass properties look plausible.
    """


def _volume(shape: object) -> float:
    """Volume of a raw ``TopoDS_Shape`` (GProp, the properties-module bound)."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def conform_solid(solid: Solid) -> Solid:
    """Return *solid* made topologically conformal, or *solid* itself if it is.

    A ``BRepCheck``-valid solid is returned UNCHANGED (identity, not a copy), so
    every body the kernel produces today keeps its exact topology and its
    byte-identical exports. An invalid one is put through ``ShapeFix_Shape``,
    whose result must be a single valid solid of the same volume — see the
    module docstring for the measured determinism / geometry-preservation
    evidence.

    Raises:
        HealingError: the heal did not produce exactly one valid solid, or it
            moved the volume by more than :data:`CONFORM_VOLUME_TOL_MM3`.
    """
    shape = solid.wrapped
    if BRepCheck_Analyzer(shape).IsValid():
        return solid

    before = _volume(shape)
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    healed = fixer.Shape()

    solids: list[Solid] = []
    explorer = TopExp_Explorer(healed, TopAbs_SOLID)
    while explorer.More():
        solids.append(Solid(TopoDS.Solid_s(explorer.Current())))
        explorer.Next()
    if len(solids) != 1:
        raise HealingError(
            f"Healing a non-conformal body produced {len(solids)} solids; "
            "expected exactly one."
        )
    result = solids[0]
    if not BRepCheck_Analyzer(result.wrapped).IsValid():
        raise HealingError(
            "The body is not a valid solid and the kernel could not heal it."
        )
    moved = abs(_volume(result.wrapped) - before)
    if moved > CONFORM_VOLUME_TOL_MM3:
        raise HealingError(
            f"Healing moved the volume by {moved} mm^3 (bound "
            f"{CONFORM_VOLUME_TOL_MM3} mm^3); refusing a heal that changes "
            "material."
        )
    return result
