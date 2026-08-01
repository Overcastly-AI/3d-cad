"""B-rep healing and the two body-integrity guards every kernel op shares.

Three things live here, and they are three answers to ONE question — *what do
we do when OCCT hands back a body that is not what it claims to be?*

* :func:`conform_solid` — REPAIR the repairable (CM-4: a T-junction that
  ``BRepCheck`` rejects and a STEP round-trip silently re-splits);
* :func:`clean_shape` — REFUSE a SIMPLIFICATION that changes material (CM-6,
  2026-07-30: ``Shape.clean()`` welded a void shut and inflated a mirrored body
  by 1072.330 mm^3, 3.48 %);
* :func:`body_is_valid` — the ONE validity predicate the feature evaluator asks
  of every body before it becomes the part's body (CM-6's durable half: nothing
  in the pipeline used to ask, so a body OCCT itself calls invalid was
  tessellated, measured and exported to STEP).

The companion module is :mod:`geometry.kernel.degenerate`, which draws the
fourth line: a body MISSING MATERIAL (a zero-width slit) is neither repaired nor
silently accepted — it is refused by the op that made it (SH-1).

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

WHAT THIS IS **NOT** (finding SH-1, docs/GEOMETRY-QA.md 2026-07-30 — the boundary
between healing and refusing). The CM-4 body carries TWO distinct defects, and
this module fixes exactly one of them. The T-junction is a topology error and
``ShapeFix`` repairs it. The **zero-width slit** underneath it — the pinched
cavity's two coincident faces, 112 mm² of boundary with no material between them
— is MISSING MATERIAL, and no repair pass removes it: measured on that body,
``ShapeFix_Shape`` leaves the pair (and splits it into two pairs),
``ShapeUpgrade_UnifySameDomain`` is a no-op on it, a self-fuse reproduces it and
``BOPAlgo_Builder`` on the single argument returns zero solids. A body this module
calls healed can therefore still be degenerate, so ``shell_body`` asks
:func:`geometry.kernel.degenerate.find_zero_width_slits` FIRST and refuses that
input rather than laundering it through here. Consequence to keep honest: the
CM-4 chain at t=2 mm is now a typed feature error, so this module's live evidence
lives at kernel level in ``tests/test_healing.py`` (raw ``hollow`` output, no
``shell_body``) — it is defence-in-depth for the next op OCCT surprises us on,
not dead code, and the fixture test fails loudly if OCCT stops producing the
non-conformal body at all.

CM-6 (docs/GEOMETRY-QA.md 2026-07-30) — **a SIMPLIFICATION that changed the
material, and a body nobody asked about.** Every kernel op finishes its boolean
with ``Shape.clean()`` (``ShapeUpgrade_UnifySameDomain``) so redundant seam
faces collapse and topology counts stay golden-assertable. On one measured body
that simplification WELDED A VOID SHUT: a 40x40x10 block whose revolved annular
groove is tangent to the block's own x=0 wall, mirrored about the plane the
groove straddles, fuses to a correct and ``BRepCheck``-VALID 30793.6284 mm^3 and
then ``clean()``s to **31865.9587 mm^3, invalid** — +1072.330 mm^3, 3.48 % of
material that is not in the model, with every feature reporting ``ok``. Two
distinct holes, and this module now closes both:

* ``clean()`` is a TOPOLOGY op, so it must not move material. :func:`clean_shape`
  is the guarded call every kernel op uses in its place — it keeps the
  pre-simplification shape and hands it back untouched when the simplification
  changes the volume. Discarding a simplification is always safe (the un-cleaned
  body carries redundant seams, nothing worse); shipping a re-melted one is not.
* NOTHING in the pipeline asked ``is_valid``. :func:`body_is_valid` is that
  question, asked ONCE per body-affecting feature at the three
  :class:`geometry.features.evaluate.EvaluationState` methods that are the only
  way a shape becomes the part's body — see :func:`body_is_valid` for why the
  gate belongs at that funnel rather than in each of the twenty-odd kernel ops.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import copy
from collections.abc import Sequence

from build123d import Solid
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Shape
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape

from geometry.kernel.types import BodyShape

#: Largest volume change a heal may introduce before we refuse its result, in
#: mm^3. Healing rebuilds topology, never material: the CM-4 body moves
#: -2.7e-12 mm^3 (float noise on a 6171 mm^3 solid). The bound is the PLANAR
#: golden tier (1e-9), i.e. ~370x the measured worst case and still 100x tighter
#: than the STEP round-trip bound the gate asserts — so a heal that actually
#: moved material could not hide inside it.
CONFORM_VOLUME_TOL_MM3 = 1e-9

#: Largest volume change a SIMPLIFICATION may introduce before we discard it,
#: RELATIVE to the volume it started from. Scale-free on purpose: ``clean()``
#: re-partitions the faces GProp integrates over, so its float noise scales with
#: the body, and an absolute mm^3 bound would be either meaningless on a 10 mm
#: bracket or unenforceable on a 1 m weldment. Measured over the whole geometry
#: suite (2026-07-30, see the module docstring): TOLERANCE_EVIDENCE
CLEAN_VOLUME_REL_TOL = 1e-9

#: Absolute floor under :data:`CLEAN_VOLUME_REL_TOL`, in mm^3 — the same 1e-9
#: planar tier :data:`CONFORM_VOLUME_TOL_MM3` uses. It exists so the relative
#: bound does not collapse to exactly zero on a zero-volume shape (a compound of
#: faces), which would reject a simplification over pure float noise.
CLEAN_VOLUME_FLOOR_MM3 = 1e-9


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


def clean_shape[ShapeT: BodyShape](shape: ShapeT) -> ShapeT:
    """``Shape.clean()``, but never at the cost of material (CM-6).

    Generic over the shape kinds a kernel op simplifies — a
    :class:`~build123d.Solid`, a multi-lump :class:`~build123d.Compound`, or the
    raw boolean result before its solids are taken — and it returns the SAME type
    it was given, so a caller's ``.solids()`` / ``.volume`` reads are unchanged.

    THE ONE call site of ``Shape.clean()`` in this service. Every kernel op ends
    its boolean with a simplification so redundant seam faces/edges collapse and
    topology counts stay meaningful (and golden-assertable); this wraps that call
    with the invariant it always had implicitly and never checked: *a
    simplification re-describes a body, it does not re-melt it.* If
    ``ShapeUpgrade_UnifySameDomain`` moves the volume by more than
    :data:`CLEAN_VOLUME_REL_TOL` (floor :data:`CLEAN_VOLUME_FLOOR_MM3`), the
    simplification is DISCARDED and the pre-clean shape is returned.

    Discarding is always the safe direction, which is why this needs no error
    channel and no caller change: the un-simplified body carries redundant seam
    faces (CM-6's mirrored plate reads 12 faces where a well-behaved clean would
    give 10) and nothing worse — same material, same validity, and measured to
    STEP round-trip with EXACTLY the same topology. A welded one is a wrong
    solid. Rejection is silent by design rather than a warning nobody can act on;
    a body that is ALSO invalid is caught downstream by :func:`body_is_valid`.

    Why a spare copy rather than an undo: ``clean()`` mutates its receiver — it
    replaces ``self.wrapped``, and ``ShapeUpgrade_UnifySameDomain`` also modifies
    the ORIGINAL ``TopoDS_Shape``'s underlying ``TShape`` in place (measured:
    stashing ``shape.wrapped`` before the call and restoring it afterwards yields
    the CORRUPTED 31865.9587, not the 30793.6284 it held a moment earlier). So
    the pre-clean state has to be a real ``BRepBuilderAPI_Copy``
    (``Shape.__deepcopy__``), taken before the call.

    COST, corrected 2026-07-31 (docs/PERF.md): this docstring used to quote
    "~0.6 ms ... plus two GProp integrations (~1.3 ms)", measured on the 12-face
    CM-6 toy. Both halves scale with the BODY, not with the op: at 442 faces one
    ``VolumeProperties_s`` is **5.8 ms** and the copy ~3 ms, so a boolean on a
    real part pays ~15 ms here, not 1.9 — and across an N=200 rebuild the two
    integrations alone are **1.36 s of 25.3 s (5.3 %)**. Both are KEPT anyway:
    they bracket a mutation (the "before" volume must be read before ``clean()``
    rewrites the TShape in place, the "after" from the simplified shape), so
    dropping either does not make the guard cheaper — it makes it absent. The
    proportional saving available at this funnel was the validity gate, not this
    one; see :func:`new_geometry_is_valid`.

    Determinism (RESEARCH §9): the accepted path returns the SAME object
    ``clean()`` returned, so every shipped golden's GLB stays byte-identical —
    the spare copy is built, unused and dropped. The rejected path returns a
    copy, but a copy of a shape OCCT built deterministically from deterministic
    inputs, taken at a point that is itself a pure function of those inputs.
    """
    wrapped = shape.wrapped
    if wrapped is None:  # pragma: no cover - kernel ops never clean an empty shape
        return shape.clean()
    before = _volume(wrapped)
    spare = copy.deepcopy(shape)
    cleaned = shape.clean()
    moved = abs(_volume(cleaned.wrapped) - before)
    if moved <= max(CLEAN_VOLUME_FLOOR_MM3, CLEAN_VOLUME_REL_TOL * abs(before)):
        return cleaned
    return spare


def body_is_valid(shape: BodyShape) -> bool:
    """Does OCCT itself call *shape* a valid B-rep? (``BRepCheck_Analyzer``.)

    WHERE THIS BELONGS, and why (CM-6, the durable half). The defect that
    produced this function was not that a mirror welded a void — it was that a
    body ``Shape.is_valid`` reports FALSE was tessellated into the viewport,
    measured for mass properties and written to STEP, because **nothing in the
    pipeline ever asked**. Three candidate homes:

    1. *every kernel op, after its boolean.* Rejected: twenty-odd sites, each
       able to be forgotten — exactly how CM-5's tool recording went missing for
       three verbs, and how ``removal_reaches_body`` was written once and missed
       twice. A gate you can forget to install is not a gate.
    2. *the tessellate / measure / export boundary.* Rejected: it is downstream
       of everything, so it fires too late to name WHICH feature made the bad
       body, and it would fail the whole part rather than degrade to the
       last-good prefix (§4.3) the rest of the evaluator is built around.
    3. *the three ``EvaluationState`` methods that install a shape as a body*
       (``set_active_body`` / ``start_body`` / ``combine_bodies``). CHOSEN: they
       are the only way a shape becomes part of ``state.bodies``, so every
       body-affecting verb — shipped, and every verb we add — passes through one
       of them exactly once, and everything downstream (properties, GLB, STEP,
       overlay, drawings, sheet-metal unfold) reads from there. The failure
       becomes a typed per-feature ``invalid_body`` error pinned to the feature
       that produced it, and the last-good body still tessellates.

    The check costs ~2 ms on the CM-6 body, once per body-affecting feature (a
    rebuild pays it once per verb, not once per boolean) — see docs/GEOMETRY-QA.md
    for the measured rebuild delta against the RESEARCH §9 2 s ceiling.

    ``True`` for an empty shape: "no body yet" is not a malformed body, and the
    callers already treat an absent body as its own state.
    """
    if shape.wrapped is None:
        return True
    return bool(BRepCheck_Analyzer(shape.wrapped).IsValid())


#: Above this share of the body's faces, the "incremental" check is checking most
#: of the body anyway, so :func:`new_geometry_is_valid` runs the WHOLE-body
#: analyzer instead — same answer, no compound to build, and it keeps the
#: strictly-stronger check on the ops that rebuild everything (a shell, a draft, a
#: simplification that re-partitions every face). Measured on the docs/PERF.md
#: tray: an ordinary body-affecting feature changes 3-11 of 70-442 faces (8.5 %
#: over a 50-feature rebuild), so the proportional path is what a real part takes.
INCREMENTAL_CHECK_MAX_FACE_SHARE = 0.5


def _face_map(shape: TopoDS_Shape) -> TopTools_IndexedMapOfShape:
    """Every FACE of *shape*, indexed (OCCT identity: same TShape + location)."""
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    return faces


def new_geometry_is_valid(shape: BodyShape, previous: Sequence[BodyShape]) -> bool:
    """:func:`body_is_valid`, made PROPORTIONAL to what the op actually changed.

    WHY (docs/PERF.md 2026-07-31, fix #2). ``body_is_valid`` is a whole-body
    ``BRepCheck_Analyzer``, run once per body-affecting feature at the
    :class:`~geometry.features.evaluate.EvaluationState` funnel — so its cost is
    O(features x faces) and it is **5.65 s of a 25.3 s N=200 rebuild (22 %)**:
    125 whole-body passes at ~53 ms each. The analyzer is ~4.7 ms of fixed cost
    plus ~0.19 ms per face (measured), and an OCCT boolean REUSES the argument's
    face TShapes for every face it did not touch — so the faces a feature
    actually creates are 3-11 of a 70-442-face body, and checking exactly those
    is ~5 ms and does not grow with the tree.

    WHY *EXACTLY* THE CHANGED FACES, and not "changed plus their neighbours"
    (which is what docs/PERF.md proposed). Two reasons, one principled and one
    measured. **Principled:** OCCT shape identity is TShape identity, and a
    TShape owns its whole sub-tree — so a face that is the SAME face as before
    has the same wires, edges, pcurves and vertices as before, and the analyzer's
    verdict on it cannot have changed. A boolean that touches a neighbour
    (inserts a vertex, re-splits an edge) necessarily gives that neighbour a NEW
    TShape, which puts it in the changed set anyway. Neighbour expansion is
    therefore redundant, not conservative. **Measured (2026-07-31):** it is also
    ruinous on exactly the parts this fix is for — on the docs/PERF.md tray one
    big top face borders every pocket, so one hole's 3 changed faces expand to
    **71 % of the body** (1378 of 1924 faces over a 50-feature rebuild), tripping
    the whole-body fallback every single time while adding 17 ms per feature of
    ancestor-map building: the "incremental" gate measured **27 % SLOWER** than
    the whole-body one it replaced.

    WHAT IS STILL GUARANTEED, and what is not — stated exactly, because this is
    the CM-6/QA-1 guard and softening it silently is the failure mode:

    * **Malformed NEW geometry is still refused at the feature that made it**, with
      the same typed ``invalid_body`` error and the same last-good-prefix
      degradation. That is what the per-feature gate was for.
    * **A body invalidated ELSEWHERE — in a face this op never touched — is no
      longer caught here.** It cannot be: measured on the CM-6 body, the flagged
      face (``BRepCheck_UnorientableShape``) is NOT in the changed set, and no
      cheap whole-body proxy sees it either (``BRepCheck_Solid`` and
      ``BRepCheck_Shell``, run directly, both report ``NoError``;
      ``BRepCheck_Analyzer(GeomControls=False)`` does see it but still costs
      38 ms of the 46 ms, i.e. it is not proportional to anything). That class is
      caught by the PUBLISH-TIME whole-body re-check in
      :func:`~geometry.features.evaluate.evaluate_tree`, which withholds the
      properties, the mesh and every export and blames the last-good feature —
      so the invariant the gate exists for, **no invalid body reaches the
      viewport, mass properties or STEP, is preserved end to end**. Measured on
      the CM-6 regression: identical statuses (``ok`` x6 + ``error``), identical
      ``invalid_body`` code, identical withheld artifacts.
    * The residual is DIAGNOSTIC, not geometric: a tree that keeps going after
      such an in-place invalidation now blames the last body-affecting feature
      rather than the first one to notice.

    *previous* is the body (or bodies) this op consumed — the operand(s) whose
    faces the result may reuse. Empty (a body being STARTED: the first extrude, a
    ``merge=False`` second body, an IMPORT — the one shape the kernel did not
    build) falls back to the whole-body check, which is right: there is nothing
    to diff against, and an imported body is the one to trust least.
    """
    if shape.wrapped is None:
        return True
    if not previous:
        return body_is_valid(shape)

    faces = _face_map(shape.wrapped)
    known = TopTools_IndexedMapOfShape()
    for body in previous:
        if body.wrapped is not None:
            TopExp.MapShapes_s(body.wrapped, TopAbs_FACE, known)
    changed = [
        faces.FindKey(index)
        for index in range(1, faces.Extent() + 1)
        if not known.Contains(faces.FindKey(index))
    ]
    # Nothing new to look at (an op that only re-parented existing faces) — fall
    # back rather than declare a body valid on the strength of an empty check.
    if not changed:
        return body_is_valid(shape)

    if len(changed) >= INCREMENTAL_CHECK_MAX_FACE_SHARE * faces.Extent():
        return body_is_valid(shape)

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face in changed:
        builder.Add(compound, face)
    return bool(BRepCheck_Analyzer(compound).IsValid())


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
