"""Uniform-thickness shell — hollow the body, opening picked faces.

The kernel half of the shell feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`), the
resolved set of faces to REMOVE (from :func:`geometry.kernel.faces.resolve_faces`
— the picked-FACE sibling of the edge selector, reusing the SAME stage-1
planar-face signature the ``on_face`` datum resolves, NOT a parallel taxonomy),
and the validated wall thickness. This module owns only the OCCT/build123d
hollow call. Failures raise the typed exceptions below with **sanitized
messages** (no kernel internals), which the feature layer maps 1:1 onto the
``shell_thickness_too_large`` / ``shell_failed`` ``FeatureError`` codes so
geometry outcomes stay values at the boundary.

The hollow is a UNIFORM INWARD offset (build123d ``Solid.hollow`` /
``BRepOffsetAPI_MakeThickSolid`` with a NEGATIVE thickness): the wall grows into
the solid, so the outer envelope is unchanged and the named faces are left open.
An empty ``faces_to_remove`` list produces a sealed (fully-enclosed) hollow.

HONEST OCCT-SHELL SUBTLETY (measured 2026-07-13, build123d 0.11.1 / OCCT 7.9 —
docs/GEOMETRY-QA.md): a thickness too large for the local wall geometry (the
inward cavity self-intersects / collapses) surfaces TWO ways, and this module
catches BOTH rather than shipping a wrong body:

* OCCT sometimes RAISES (``StdFail_NotDone``);
* OCCT sometimes SILENTLY returns the un-hollowed body (the walls merged, no
  material removed), caught by the MATERIAL-REMOVED invariant: a valid inward
  shell strictly reduces the volume.

Either way the error is chosen by the geometry, not by how OCCT failed
(:func:`_refusal`, SHELL-WRONG-SOLID below): :class:`ShellThicknessError` →
``shell_thickness_too_large`` when no cavity fits, :class:`ShellError` →
``shell_failed`` when one does and the kernel did not build it. An un-hollowed
body is not always a too-thick wall: a box with every edge filleted r2 comes back
un-hollowed at t = 2.0001, where a 35.9998 x 20.9998 x 5.9998 cavity fits.

A THIRD mode (finding CM-4, docs/GEOMETRY-QA.md 2026-07-25): the hollow
completes, removes the right material, and returns a **non-conformal** solid —
OCCT leaves a face's corners sitting mid-edge on a neighbour instead of splitting
that edge. The geometry is right and ``BRepCheck`` says invalid, and a STEP
round-trip does not preserve it (the reader sews and gains edges). Every shelled
lump therefore goes through :func:`~geometry.kernel.healing.conform_solid`, which
no-ops on the valid bodies (all goldens) and heals that one — see that module for
the measured evidence.

A FOURTH mode, the one CM-4's heal made survivable rather than sound (finding
SH-1, docs/GEOMETRY-QA.md 2026-07-30): where an internal wall of the body is
**exactly 2 x the thickness**, the two inward offsets land on the SAME plane, the
cavity pinches to zero width, and the result carries a **zero-width slit** — two
coincident faces with no material between them. That is refused here, before the
heal, via the shared :func:`~geometry.kernel.degenerate.find_zero_width_slits`
predicate (see :class:`ShellThicknessError` for why it is an error and not a
success-with-warning).

A FIFTH mode, and the one no invariant above sees (SHELL-WRONG-SOLID,
2026-09-30): OCCT returns ONE valid solid that removed material and is still the
wrong part. A 40 x 20 x 10 plate bored r7 at y = 1, sealed at t = 2, must hollow
into two pockets and read 4438.70 mm^3; both joins keep one pocket and read
5449.66. A tube of radii 10 / 7 has a 3 mm wall, no room for two 2 mm walls; both
joins return 75.40 mm^3 of something. Every result is therefore checked against
the definition of a shell, by :mod:`geometry.kernel.shell_walls`, which measures
point distances to the input and never offsets anything: the cavity faces are
``t`` from the kept faces, and every cavity is there. A result that fails is
refused, and so is every other failure above, by :func:`_refusal`, which asks the
same module whether any cavity fits at all. If none does the error is
:class:`ShellThicknessError` with the thickest wall that would fit; if one does,
the kernel failed on a body with room, and :class:`ShellError` names where and
the likely cause (a pocket split, a round of radius near ``t``, B-spline faces).
Over the 173-body sweep in ``tests/test_shell_walls.py`` 7 wrong solids shipped
before and none does now. The check grows with the faces, not their square:
it adds 6 to 83 ms on small bodies and about a tenth to a vented lid of 710 or
910 faces (kernel/shell_walls.py measures it).

Determinism (RESEARCH §9, SHELL-SEALED-DETERMINISM): the slit probe and the
heal are pure functions of their input, but the OCCT hollow with the default Arc
join is NOT a pure function of ``(body, faces, thickness)``.
``BRepOffset_MakeOffset::BuildOffsetByArc`` (OCCT 7.9.3) walks ``MapSF``, a hash
map keyed by the input's TShape ADDRESSES, to register the offset faces it then
intersects. Every face adjacent to an opened face is taken out of that map first
(``ToContext``), so an open shell of a prism (at most one other face left: the
floor) comes out the same every time. A SEALED hollow leaves every face in the
map: the cavity's faces came back in a different order on every build, the edges
between them were intersected in a different order, and on a spline wall the
fitted edges (and the volume, by up to 1.8e-5 mm^3) moved with it.

:func:`_hollow` therefore ALSO builds a sealed hollow with the INTERSECTION
join, which intersects in a fixed order, and ships that result instead of Arc's
when all three hold:

- OCCT's own edge analysis finds no concave edge, where Arc would put a tube.
  Convex fillets and chamfers qualify, including a fillet smaller than the wall,
  where both joins collapse it to a sharp cavity corner;
- every face is analytic (plane, cylinder, cone, sphere, torus). On a spline
  wall the Intersection route read up to 1.84e-2 mm^3 off the truth;
- Arc built the hollow and the two agree in shells, faces, volume and area
  (:func:`_same_hollow`). On its own the Intersection join can return a
  plausible wrong solid: where the cavity should split into separate pockets
  it keeps one, and a bored plate came out 20% to 65% heavy where Arc raises.

Arc's outcome is what the user gets either way; the Intersection route only
makes its bytes reproducible, so it gets a budget (SHELL-INTERSECTION-SLOW,
2026-10-02). A 40 x 20 x 10 plate bored r2.991 and cross-bored r1.424, sealed
at t 2.39, hollows right by Arc in 0.16 s and held the Intersection join for 68
to 133 s, past the gateway's 90 s. It now runs first in a child of the blend
server (:mod:`geometry.kernel.fillet_isolation`) under
:data:`INTERSECTION_CPU_SECONDS`; past it, or where it fails or disagrees, Arc's
result ships in canonical order. Over the 220 sweep bodies that take the route
it needed at most 1.4 s together with Arc, so the budget decides nothing else.
Only a build that finished and agrees is built again in-process, where its outer
faces are the input's, so what ships is byte for byte what shipped before.

The Arc offset itself grows with the faces squared where one face borders many
(OCCT intersects each pair of offset faces through a boolean over both faces'
edges): a 240 x 160 x 6 plate with 225 slots, opened at the top at t 1, takes 77
to 89 s of CPU. A body of :data:`ISOLATED_ARC_FACES` or more is offset in a
child under :data:`ARC_CPU_SECONDS` and refused past it with a typed
:class:`ShellTimeout`. A body of several lumps takes that path lump by lump,
on ONE budget for the whole feature (:class:`_Budget`, SHELL-MULTIBODY-HANG):
two 906-face lids side by side took 163 s in-process and are refused at 45 s.

With the Intersection route, measured over 4 processes x 3 rebuilds
(2026-09-25), BREP bytes and mass properties were identical for a box, a
cylinder, a cone, a sphere, a torus, a stadium and a hex prism, a plate with a
hole, a chamfered box, and boxes with filleted vertical or all edges. Hollows
that still ship Arc's result while two or more faces stay in the map:

- a concave edge, which Arc rounds with a tube;
- fillets the Intersection join refuses (a box with filleted bottom edges);
- a spline (or other non-analytic) face;
- an OPEN shell that leaves two or more faces non-adjacent to every opened face,
  such as a top-open box with filleted bottom edges.

Those get their faces put in a canonical order (:func:`_canonical_face_order`).
That fixes the topology across rebuilds but not the bytes, because the edges are
still intersected in hash order. The same measurement left 12/12 distinct BREPs
for both a sealed L and a sealed bottom-filleted box. The filleted box's volume
spread 5e-11 mm^3 on 2869 mm^3, and the L's centroid moved in its last bit. A
sealed spline wall moves further: its fitted edges, and the volume by up to
1.8e-5 mm^3.

The hash order can also decide VALIDITY. Where a cavity touches itself at a point
(a rod r10 with an r6 cross-bore at t = 2), about half of all layouts leave a
face spanning both sides of the pinch. :mod:`geometry.kernel.shell_heal` splits
such a face before the heal, so the outcome no longer depends on the layout.
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
import time
from dataclasses import dataclass

import numpy as np
from build123d import Compound, Face, Kind, Solid, Vector
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepOffset import BRepOffset_Analyse
from OCP.ChFiDS import ChFiDS_TypeOfConcavity
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Dir, gp_Pnt, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp
from OCP.TopoDS import (
    TopoDS,
    TopoDS_Compound,
    TopoDS_Face,
    TopoDS_Iterator,
    TopoDS_Shape,
    TopoDS_Shell,
    TopoDS_Solid,
)
from OCP.TopTools import TopTools_IndexedMapOfShape

from geometry.kernel.degenerate import find_zero_width_slits
from geometry.kernel.fillet_isolation import BlendTimedOut, CpuMeter, run_isolated
from geometry.kernel.healing import HealingError, clean_shape, conform_solid
from geometry.kernel.lumps import assemble_lumps, group_faces_by_lump
from geometry.kernel.naming import OpHistory
from geometry.kernel.offset_edges import tighten_offset_edges
from geometry.kernel.properties import volume_properties
from geometry.kernel.provenance import surface_key
from geometry.kernel.shell_heal import split_pinched_faces
from geometry.kernel.shell_walls import FaultKind, ShellDefinition, WallFault
from geometry.kernel.tolerances import KERNEL_LINEAR_TOL_MM
from geometry.kernel.types import BodyShape
from geometry.kernel.working_faces import NotABodyFaceError, working_copy_faces

#: A valid inward shell strictly REMOVES material (the cavity), so the shelled
#: volume is below the original. The margin absorbs GProp float noise while
#: staying orders of magnitude below the material any non-degenerate wall
#: removes: the thinnest useful shell of an authored part removes a cavity of
#: whole mm^3, so a result within this margin of the original is a COLLAPSED
#: cavity (walls merged), never a genuine thin shell (mm-scale linear tolerance,
#: matching the kernel's 1e-7 m posture).
_MATERIAL_REMOVED_MARGIN_MM3 = 1e-6


#: build123d's ``hollow`` tolerance (its default), which OCCT's offset also
#: uses to classify edges (:func:`_concave_edge_count`).
_HOLLOW_TOL_MM = 1e-4

#: ``Precision::Confusion()``, in OCCT's edge-analysis angle below.
_CONFUSION_MM = 1e-7

#: How closely the Intersection hollow must match Arc's before it replaces it
#: (relative). On the analytic bodies both joins built (2026-09-30: box,
#: cylinder, cone, sphere, torus, stadium, hex prism, bored plate, chamfered
#: and filleted boxes at t = 0.5 to 3 mm) they agree to 1.1e-15 in volume and
#: 3.5e-16 in area. The dropped pockets reproduced were 20% to 65% heavy.
_AGREE_REL = 1e-9

#: Decimals the canonical face order rounds its key to (mm, mm^2): far above
#: the offset's float noise, far below any two faces' separation.
_ORDER_DECIMALS = 6


class ShellError(RuntimeError):
    """The kernel did not build the shell, on a body with room for its cavity
    (``shell_failed``).

    OCCT raised (an ``StdFail_NotDone`` from ``MakeThickSolid``, and others),
    returned other than one solid, returned a body that is not valid, returned the
    body un-hollowed, or returned a solid that is not the shell by definition
    (:mod:`geometry.kernel.shell_walls`). The message says which, where, and what
    to change. When the thickness leaves no cavity at all the error is
    :class:`ShellThicknessError` instead, whichever way OCCT failed."""


class ShellThicknessError(ValueError):
    """The wall thickness collapses, self-intersects, or PINCHES the inward cavity.

    Two measured causes, one user action ("change the thickness"), so one code:

    * no cavity fits: every point of the body is within the thickness of a kept
      face (:meth:`~geometry.kernel.shell_walls.ShellDefinition.cavity_exists`),
      whatever OCCT did about it (raised, returned the body un-hollowed, or
      returned a wrong solid). The message quotes the deepest point found, a wall
      under which leaves a cavity;
    * the hollow completes, removes the right material, and leaves a **zero-width
      slit** because an internal wall is exactly ``2 x thickness`` wide (SH-1,
      docs/GEOMETRY-QA.md 2026-07-30).

    The feature layer maps both onto ``shell_thickness_too_large`` — a legible "the
    wall is too thick for this body", never a silently wrong solid.

    WHY THE SLIT IS AN ERROR AND NOT A SUCCESS-WITH-WARNING (the P3-labelled
    honesty question, decided on measured evidence — GEOMETRY-QA SH-1):

    1. **At exactly 2 x t the hollow is unreliable in KIND, not just in topology.**
       Two bodies one fillet apart: the CM-4 body (r3 on the Z edges) returns the
       analytically CORRECT 6171.186 mm^3 with a 112 mm^2 slit, while the same
       chain without the fillet returns **14172.183 mm^3 where 6308.531 is
       correct** — 2.25x the material, only 227.8 of 8091.5 mm^3 of cavity cut.
       That second body is caught today only by luck (``ShapeFix`` happens to fail
       on it); the material-removed invariant passes it, because material WAS
       removed. A success we cannot tell apart from a 2.25x-too-heavy body is not
       a success.
    2. **We cannot make the body sound.** ``ShapeFix_Shape``, a self-fuse and
       ``ShapeUpgrade_UnifySameDomain`` all leave the coincident pair in place
       (measured — :mod:`geometry.kernel.degenerate`), so "succeed and heal" is not
       on the table; the choice is refuse or ship a cracked body.
    3. **The user loses nothing.** The knife edge is a single value: on the same
       CM-4 layout t=1.9 mm gives a sound 0.2 mm cavity (5901.709 mm^3) and
       t=2.1 mm gives a sound merged rib (6411.437 mm^3) — the two things the user
       could have meant. The message names both moves.

    A `warning` channel would be the better UX for case 3 (`ok` + advice) but
    ``FeatureResult`` has no such field, and inventing half of one — a warning
    smuggled into a success message the frontend does not model — is worse than an
    honest refusal. Filed instead (BACKLOG P3): a typed ``warnings`` list on
    ``FeatureResult`` plus a distinct ``shell_pinched_wall`` code, both py-kit
    schema changes owned outside the kernel. Until then this rides
    ``shell_thickness_too_large``, whose documented remedy ("reduce below the
    smallest half-wall") is exactly the boundary being hit."""


def shell_body(
    body: BodyShape,
    faces_to_remove: list[Face],
    thickness_mm: float,
    *,
    history: OpHistory | None = None,
) -> BodyShape:
    """Hollow *body* to a uniform inward *thickness_mm*, opening *faces_to_remove*.

    An empty *faces_to_remove* produces a sealed (fully-enclosed) hollow; a
    non-empty list leaves those faces open.

    *body* is never modified. ``MakeThickSolid`` writes to the body it hollows
    (every sealed hollow of the blade-hub bodies cleared the ``Checked`` flag of
    an input ``TShape``, measured 2026-10-02), so the hollow runs on a working
    copy (:mod:`geometry.kernel.working_faces`). *history*, when given, receives
    that copy in ``worked_on`` (the result's untouched faces are the copy's).

    Multi-body (§MB-4): a single :class:`~build123d.Solid` hollows exactly as
    before (byte-identical). A multi-lump :class:`~build123d.Compound` is shelled
    PER LUMP — OCCT's ``MakeThickSolid`` cannot run on a whole compound, so each
    lump is hollowed independently (opening the picked faces that belong to it;
    lumps with no picked face become sealed hollows) and the results reassemble in
    the explicit lump order. Every lump is hollowed, so the lump count is
    preserved and the material-removed invariant is checked per lump.

    Every lump takes the single solid's path (SHELL-MULTIBODY-HANG): a lump of
    :data:`ISOLATED_ARC_FACES` faces or more is offset in a child, as it would
    be alone. The time budgets are the whole feature's (:class:`_Budget`), not
    each lump's, so a body of many lumps answers in the time one solid does.

    Raises:
        ShellThicknessError: the thickness collapses the cavity on some lump (the
            hollow completed but removed no material — OCCT's silent too-thick
            path), or PINCHES it to zero width on some lump (an internal wall
            exactly ``2 * thickness_mm`` wide, leaving coincident faces with no
            material between them — SH-1; see that class for why this is an error).
        ShellError: the OCCT hollow failed to complete, or left other than
            exactly one solid per lump (single body chain per lump, design §7.6),
            or a face to open is not a face of *body*.
    """
    if thickness_mm <= 0:
        raise ValueError(f"thickness_mm must be > 0, got {thickness_mm}")

    try:
        work, opened = working_copy_faces(body, faces_to_remove)
    except NotABodyFaceError as exc:
        raise ShellError(
            "Shell failed: a face to open is not a face of the body."
        ) from exc
    built_on: BodyShape = work
    budget = _Budget.for_body(len(work.faces()))
    if isinstance(work, Compound):
        solids = work.solids()
        groups = group_faces_by_lump(solids, opened)
        lumps = [
            _shell_one_lump(solid, groups.get(index, []), thickness_mm, budget)
            for index, solid in enumerate(solids)
        ]
        shelled: BodyShape = assemble_lumps([lump for lump, _on in lumps])
        if any(
            on is not solid for (_lump, on), solid in zip(lumps, solids, strict=True)
        ):
            # An isolated lump was built on its copy: the result's untouched
            # faces are the copies', in the body's face order (lump by lump).
            built_on = Compound([on for _lump, on in lumps])
    else:
        shelled, built_on = _shell_one_lump(work, opened, thickness_mm, budget)
    if history is not None:
        history.worked_on = built_on
    return shelled


def _shell_one_lump(
    body: Solid,
    faces_to_remove: list[Face],
    thickness_mm: float,
    budget: "_Budget",
) -> tuple[Solid, Solid]:
    """Hollow ONE lump (a single solid) — the byte-identical single-body path.

    Shared by the single-solid fast path and each lump of the multi-lump path
    (§MB-4). Returns a new single cleaned solid that passed the definition check
    (:mod:`geometry.kernel.shell_walls`), and the body it was built on (*body*,
    or the isolated copy of a large one, :func:`_arc`), or raises
    :func:`_refusal`: a :class:`ShellThicknessError` when the thickness leaves no
    cavity, a :class:`ShellError` naming what the kernel got wrong otherwise.
    Its children draw on the feature's *budget*: a large body's offset is
    refused past it (:class:`ShellTimeout`).
    """
    original_volume = body.volume
    definition = ShellDefinition(body, faces_to_remove, thickness_mm)
    try:
        solids, canonicalise, built_on = _hollow(
            body, faces_to_remove, thickness_mm, budget
        )
    except ShellTimeout:
        raise
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise _refusal(
            definition, body, f"the kernel's offset failed ({type(exc).__name__})"
        ) from exc

    if len(solids) != 1:
        raise _refusal(
            definition, body, f"the kernel's offset produced {len(solids)} solids"
        )
    # A spline wall's offset meets its neighbours along loosely FITTED edges;
    # rebuild them on the offset's exact isolines (GEOMETRY-QA 2026-09-25 F1).
    # A body without such edges is returned as is.
    tightened = tighten_offset_edges(solids[0], faces_to_remove)
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    cleaned = clean_shape(tightened)

    # Zero-width-slit guard (SH-1), BEFORE the heal for two reasons: the heal
    # cannot remove a slit (measured - kernel/degenerate.py), so healing first
    # would only spend a ShapeFix on a body we refuse; and the probe then reports
    # what OCCT actually produced. Sub-millisecond on a sound body (0.33 ms on the
    # 6-face box, 0.56 ms on the 11-face golden tray, 2.0 ms on the 36-face CM-4
    # layout vs 58-82 ms for shell+heal): the antiparallel/coincident-plane test is
    # float arithmetic, and on a sound body no pair ever reaches the boolean.
    slits = find_zero_width_slits(cleaned)
    if slits:
        worst = slits[0]
        raise ShellThicknessError(
            f"Wall thickness {thickness_mm} mm leaves a zero-width slit: an "
            f"internal wall of this body is exactly {2 * thickness_mm} mm thick "
            f"(2 x the wall thickness), so the two inward offsets land on the same "
            f"plane and the cavity pinches to nothing over "
            f"{worst.area_mm2:.6g} mm^2 around (x {worst.at[0]:.6g}, "
            f"y {worst.at[1]:.6g}, z {worst.at[2]:.6g}): two coincident faces "
            f"with no material between them. Change the thickness so it is not "
            f"exactly half that wall - a little thinner leaves a thin cavity "
            f"there, a little thicker merges the two walls into solid material."
        )

    # conform_solid() returns a VALID result untouched and heals the non-conformal
    # T-junction case (CM-4, module docstring) — never a silent reshape: it raises
    # if the heal would move material.
    # A cavity that touches itself at a point can come back with a face spanning
    # both sides of the pinch, depending on OCCT's hash order: split it first
    # (kernel/shell_heal.py, SHELL-HEAL-NONDETERMINISM).
    # Both return a valid body as it is: ask BRepCheck once (1.7 s on a
    # 2936-face shell).
    try:
        shelled = (
            cleaned
            if BRepCheck_Analyzer(cleaned.wrapped).IsValid()
            else conform_solid(split_pinched_faces(cleaned))
        )
    except HealingError as exc:
        raise _refusal(
            definition, body, "the kernel's result is not a valid solid"
        ) from exc

    # Material-removed invariant: a valid inward shell strictly reduces the
    # volume. OCCT can quietly return the un-hollowed body, both where the
    # thickness leaves no cavity and where it failed to build one.
    if shelled.volume >= original_volume - _MATERIAL_REMOVED_MARGIN_MM3:
        raise _refusal(
            definition, body, "the kernel returned the body without its cavity"
        )
    if canonicalise:
        shelled = _canonical_face_order(shelled)
    # The definition check: the walls are the thickness everywhere and every
    # cavity is there. OCCT can return one valid solid that removed material and
    # is still the wrong part (SHELL-WRONG-SOLID, kernel/shell_walls.py). It
    # reads the faces in their final order, so a refusal names the same place on
    # every rebuild.
    fault = definition.fault(shelled)
    if fault is not None:
        # A missing cavity on a result whose cavity faces all check out is a
        # whole pocket missing: the cavity splits, and the kernel kept only
        # some of it (kernel/shell_walls.py).
        split = fault.kind is FaultKind.MISSING
        raise _refusal(definition, body, _describe(fault), split=split)
    return shelled, built_on


def _refusal(
    definition: ShellDefinition, body: Solid, what: str, split: bool = False
) -> ShellError | ShellThicknessError:
    """The error for a shell the kernel did not build right. When the thickness
    leaves no cavity at all, that is the cause whatever the kernel did, and the
    message says how thin a wall would leave one. Otherwise the kernel failed on
    a body that has room: say what went wrong, and what to change. The pocket
    advice is given only when *split* says the cavity was seen to split: on a
    sphere boss or a tee nothing splits, and saying so would mislead."""
    thickness = definition.thickness_mm
    if not definition.cavity_exists:
        depth, where = definition.room()
        advice = (
            f"The deepest point found is {depth:.3g} mm from the walls, at "
            f"{_point(where)}: use a wall under {depth:.3g} mm."
            if depth > 0
            else "Use a much thinner wall."
        )
        return ShellThicknessError(
            f"Wall thickness {thickness} mm is too large for this body: every "
            f"point of it is within {thickness} mm of a wall, so the walls meet "
            f"and no cavity is left. {advice}"
        )
    radii = sorted({_convex_radius(face) or 0.0 for face in body.faces()} - {0.0})
    near = [r for r in radii if abs(r - thickness) <= _ROUND_NEAR_REL * thickness]
    under = [r for r in radii if r < thickness]
    if split:
        hint = (
            "The cavity splits into separate pockets here, and the kernel's offset "
            "kept only some of them. Change the thickness so the cavity stays in "
            "one piece, or open a face there."
        )
    elif near:
        radius = min(near, key=lambda r: (abs(r - thickness), r))
        gap = abs(radius - thickness)
        relation = "equals" if gap < 1e-9 else f"is within {gap:.3g} mm of"
        hint = (
            f"The thickness {relation} the {radius:.4g} mm radius of a rounded "
            f"face, which the offset shrinks to an edge: use a thickness further "
            f"from {radius:.4g} mm."
        )
    elif under:
        hint = (
            f"A rounded face has a {under[0]:.4g} mm radius, under the thickness, "
            f"so the offset must shrink it away, which the kernel cannot always "
            f"do: use a thickness under {under[0]:.4g} mm, or a larger round."
        )
    elif not _all_analytic(body):
        hint = (
            "The kernel's offset fails on some freeform (B-spline) faces, such as "
            "a sphere or cylinder converted to B-splines on import. Try another "
            "thickness, or rebuild those faces with sketch features."
        )
    else:
        hint = (
            "The kernel's offset could not build this cavity. Try a slightly "
            "different thickness, or open a face."
        )
    return ShellError(
        f"Shell could not build a {thickness} mm wall on this body: {what}. {hint}"
    )


def _point(at: tuple[float, float, float]) -> str:
    return f"(x {at[0]:.4g}, y {at[1]:.4g}, z {at[2]:.4g})"


def _describe(fault: WallFault) -> str:
    """What the kernel's result got wrong, for a message."""
    where = _point(fault.at)
    if fault.kind is FaultKind.WALL:
        return f"its result has a {fault.wall_mm:.4g} mm wall at {where}"
    if fault.kind is FaultKind.MISSING:
        return f"its result is missing the cavity at {where}"
    return f"its result lost the body's face at {where}"


#: How close (relative) the thickness must be to a rounded face's radius for
#: the message to blame that face. OCCT's offset collapses such a face to an
#: edge: a box with every edge filleted r2 fails at t = 2 and 2.0001 and builds
#: at 1.999 and 2.01.
_ROUND_NEAR_REL = 0.05


def _convex_radius(face: Face) -> float | None:
    """The radius of *face* when it is a convex round: a cylinder, sphere or
    torus tube whose centre is inside the material (a fillet or a boss, not a
    bore). An inward offset shrinks exactly these, to an edge at t = radius."""
    surface = BRepAdaptor_Surface(face.wrapped)
    kind = surface.GetType()
    point = face.position_at(0.5, 0.5)
    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        radius, axis = cylinder.Radius(), cylinder.Axis()
        centre = Vector(axis.Location()) + Vector(axis.Direction()) * (
            (point - Vector(axis.Location())).dot(Vector(axis.Direction()))
        )
    elif kind == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = surface.Sphere()
        radius, centre = sphere.Radius(), Vector(sphere.Location())
    elif kind == GeomAbs_SurfaceType.GeomAbs_Torus:
        torus = surface.Torus()
        radius, axis = torus.MinorRadius(), torus.Axis()
        origin, up = Vector(axis.Location()), Vector(axis.Direction())
        radial = (point - origin) - up * (point - origin).dot(up)
        centre = origin + radial.normalized() * torus.MajorRadius()
    else:
        return None
    return radius if face.normal_at(0.5, 0.5).dot(point - centre) > 0 else None


def _hollow(
    body: Solid, faces_to_remove: list[Face], thickness_mm: float, budget: "_Budget"
) -> tuple[list[Solid], bool, Solid]:
    """OCCT's inward hollow of *body*, whether its face order still needs
    :func:`_canonical_face_order` (module docstring), and the body it was built
    on (*body*, or the isolated copy :func:`_arc` returns).

    Negative thickness shells INWARD (the wall grows into the solid); the faces
    list is removed (left open).

    Arc always runs first and decides the outcome: when it raises or returns
    other than one solid, that is what the caller gets, exactly as before the
    Intersection route existed. A sealed hollow with no concave edge is then
    ALSO built by the Intersection join, when every face of the body is
    analytic (:func:`_all_analytic`). That result replaces Arc's only when
    :func:`_same_hollow` finds the two agree, so it adds deterministic bytes
    and never changes what the user gets. It is not trusted on its own: where
    the cavity should split into separate pockets (a plate bored nearly through
    its width), the Intersection join returns one valid solid that keeps one
    pocket and drops the rest, while Arc raises.

    Arc alone decides the outcome, so the Intersection join is built first in a
    child under :data:`INTERSECTION_CPU_SECONDS` (SHELL-INTERSECTION-SLOW: a
    cross-bored plate whose Arc hollow takes 0.16 s kept it 68 to 133 s). Past
    the budget, or where it fails or disagrees, Arc's result ships, in canonical
    face order; only a build that finished in time and agrees is built again
    here, where its outer faces are *body*'s.
    """
    free = _free_face_count(body, faces_to_remove)
    # An open shell with two free faces is canonicalised whatever its edges
    # are, so it skips the edge analysis (0.7 s on a 906-face lid).
    blends = (
        0 if faces_to_remove and free > 1 else _concave_edge_count(body, thickness_mm)
    )
    arc, built_on = _arc(body, faces_to_remove, thickness_mm, budget)
    canonicalise = free + blends > 1
    if faces_to_remove or blends or len(arc) != 1 or not _all_analytic(body):
        return arc, canonicalise, built_on
    try:
        _copy, probe = budget.intersection.run(body, thickness_mm)
    except Exception:  # refused, over budget, or the isolation failed: keep Arc
        return arc, canonicalise, built_on
    if len(probe) != 1 or not _same_hollow(arc[0], probe[0]):
        return arc, canonicalise, built_on
    try:
        intersection = intersection_hollow(body, [], thickness_mm, None)
    except Exception:  # the Intersection join refuses some bodies: keep Arc
        return arc, canonicalise, built_on
    if len(intersection) == 1 and _same_hollow(arc[0], intersection[0]):
        return [intersection[0]], False, body
    return arc, canonicalise, built_on


#: The blend server's name for :func:`intersection_hollow`
#: (``kernel/_fillet_worker.py``).
INTERSECTION_OP = "hollow-intersection"

#: CPU seconds one isolated Intersection build may take before Arc's result
#: ships instead (``RLIMIT_CPU``, so machine load does not move it). Over the
#: 220 sweep bodies that take the route (2026-10-02) it took at most 1.4 s
#: together with Arc's; the cross-bored plate of SHELL-INTERSECTION-SLOW takes
#: 68 to 133 s.
INTERSECTION_CPU_SECONDS = 10.0
#: Wall-clock backstop for a child that is starved rather than computing.
INTERSECTION_WALL_SECONDS = 30.0
#: How many builds' worth of :data:`INTERSECTION_CPU_SECONDS` (and wall) the
#: lumps of one Shell share (:class:`_Budget`). With two, one lump that runs
#: out its budget leaves every other lump the budget it has alone, so a body
#: with one slow lump ships what its lumps would alone; a second slow lump
#: spends the rest, and the lumps after it ship Arc's result.
INTERSECTION_BUILDS = 2


def intersection_hollow(
    body: Solid, _edges: object, thickness_mm: float, _history: object
) -> list[Solid]:
    """The sealed inward hollow of *body* by the Intersection join, in the
    blend server's op signature (its child runs it as :data:`INTERSECTION_OP`;
    there are no edges and no history)."""
    return list(body.hollow([], -thickness_mm, kind=Kind.INTERSECTION).solids())


#: Faces from which a body's Arc offset runs isolated, under
#: :data:`ARC_CPU_SECONDS`. OCCT's offset intersects every pair of offset faces
#: whose boxes meet, each pair through a boolean over both faces' edges: on a
#: 240 x 160 x 6 plate with 225 slots (906 faces), opened at the top at t 1,
#: that took 77 to 89 s of CPU (2026-10-02, 4-core sandbox under load). Under
#: this many faces it stays in-process: a 410-face vented lid takes 5.5 s.
ISOLATED_ARC_FACES = 500

#: CPU seconds the Arc offsets of one Shell may take, over all its lumps and
#: wherever they run (:class:`_Budget`), before the shell is refused
#: (:class:`ShellTimeout`): with the check, the heal and the mesh after it,
#: the request still answers inside the gateway's 90 s.
ARC_CPU_SECONDS = 40.0
#: Wall-clock backstop for a child that is starved rather than computing.
ARC_WALL_SECONDS = 60.0

#: The blend server's name for :func:`isolated_arc` (``kernel/_fillet_worker.py``).
ARC_OP = "hollow-arc"


class ShellTimeout(ShellError):
    """The kernel's offset ran past its time budget (:data:`ARC_CPU_SECONDS`)
    on a large body, or a body of many lumps, and was stopped: a typed refusal
    (``shell_failed``), never a request left to hang."""


def _arc(
    body: Solid, faces_to_remove: list[Face], thickness_mm: float, budget: "_Budget"
) -> tuple[list[Solid], Solid]:
    """Arc's hollow of *body*, and the body it was built on, on the feature's
    Arc budget (:class:`_Budget`): once it is spent, the shell is refused
    (:class:`ShellTimeout`).

    A body of :data:`ISOLATED_ARC_FACES` faces or more is hollowed in a child
    of the blend server, which is stopped when the budget runs out. The opened
    faces ride in the body's compound, so they arrive as the copy's own faces,
    and the result's untouched faces are the returned copy's. A smaller body is
    hollowed here and charged the CPU it took; the budget can run out on it
    only by as much as one such body takes."""
    if budget.arc.cpu_seconds <= 0:
        raise budget.timeout()
    if len(body.faces()) < ISOLATED_ARC_FACES:
        start = time.thread_time()
        try:
            return list(body.hollow(faces_to_remove, -thickness_mm).solids()), body
        finally:
            budget.arc.cpu_seconds -= time.thread_time() - start
    try:
        copy, solids = budget.arc.run(
            Compound(_carrier(body, faces_to_remove)), thickness_mm
        )
    except BlendTimedOut as exc:
        raise budget.timeout() from exc
    built_on, _opened = _carried(copy.wrapped)
    return solids, built_on


@dataclass
class _Allowance:
    """What the children of one Shell feature that run *op* may still spend,
    and what any one of them may (*child_cpu_seconds*, *child_wall_seconds*).

    Each child gets the CPU left, up to its own limit, as its ``RLIMIT_CPU``
    and is charged what it reports it used
    (:class:`~geometry.kernel.fillet_isolation.CpuMeter`), or its wall time
    when it reports nothing (it crashed); one stopped is charged its limit.
    A child's limit is whole seconds, rounded up, so the children together
    stop within 1 s of the allowance however many there are."""

    op: str
    cpu_seconds: float
    wall_seconds: float
    child_cpu_seconds: float
    child_wall_seconds: float

    def run(
        self, shape: BodyShape, thickness_mm: float
    ) -> tuple[BodyShape, list[Solid]]:
        """*op* on *shape* in a child: the copy it was built on, and the solids.

        Raises what :func:`~geometry.kernel.fillet_isolation.run_isolated`
        raises, and :class:`BlendTimedOut` when the CPU is already spent."""
        if self.cpu_seconds <= 0:
            raise BlendTimedOut(self.op)
        cpu = min(self.cpu_seconds, self.child_cpu_seconds)
        meter = CpuMeter()
        start = time.monotonic()
        timed_out = False
        try:
            copy, _none, solids = run_isolated(
                self.op,
                shape,
                [],
                thickness_mm,
                None,
                cpu_seconds=cpu,
                wall_seconds=max(min(self.wall_seconds, self.child_wall_seconds), 0),
                meter=meter,
            )
        except BlendTimedOut:
            timed_out = True
            raise
        finally:
            elapsed = time.monotonic() - start
            self.wall_seconds -= elapsed
            if timed_out:
                self.cpu_seconds -= math.ceil(cpu)
            else:
                self.cpu_seconds -= elapsed if meter.seconds is None else meter.seconds
        return copy, solids


@dataclass
class _Budget:
    """The time budgets of ONE Shell feature, shared by every lump of its body
    (SHELL-MULTIBODY-HANG).

    A multi-lump body is shelled lump by lump, each exactly as that solid
    alone would be, so which faces open and how each lump is offset do not
    change, and neither does where it runs (a lump is isolated by its own
    faces, :data:`ISOLATED_ARC_FACES`, as the cost of its offset is). What the
    lumps share is the time. The Arc offsets get :data:`ARC_CPU_SECONDS` for
    the whole feature, in-process or isolated, so a body of N lumps is refused
    when one solid would be, not after N times as long. The Intersection
    builds, which only make bytes reproducible, get :data:`INTERSECTION_BUILDS`
    times one build's budget between them (that constant says why)."""

    faces: int
    arc: _Allowance
    intersection: _Allowance

    @classmethod
    def for_body(cls, faces: int) -> "_Budget":
        """The budget of a Shell of a body of *faces* faces (all lumps)."""
        return cls(
            faces=faces,
            arc=_Allowance(
                ARC_OP,
                ARC_CPU_SECONDS,
                ARC_WALL_SECONDS,
                ARC_CPU_SECONDS,
                ARC_WALL_SECONDS,
            ),
            intersection=_Allowance(
                INTERSECTION_OP,
                INTERSECTION_BUILDS * INTERSECTION_CPU_SECONDS,
                INTERSECTION_BUILDS * INTERSECTION_WALL_SECONDS,
                INTERSECTION_CPU_SECONDS,
                INTERSECTION_WALL_SECONDS,
            ),
        )

    def timeout(self) -> ShellTimeout:
        """The refusal once the Arc budget is spent."""
        return ShellTimeout(
            f"Shell stopped: the kernel's offset of this {self.faces}-face "
            f"body ran past its {ARC_CPU_SECONDS:.0f} s limit. Its cost grows with "
            f"the faces the walls run along: shell the body before cutting many "
            f"small features (vents, slots, hole patterns) into it, then add them."
        )


def isolated_arc(
    carrier: Compound, _edges: object, thickness_mm: float, _history: object
) -> list[Solid]:
    """Arc's hollow of the solid in *carrier*, opening the faces carried with
    it, in the blend server's op signature (its child runs it as
    :data:`ARC_OP`)."""
    body, opened = _carried(carrier.wrapped)
    return list(body.hollow(opened, -thickness_mm).solids())


def _carrier(body: Solid, faces: list[Face]) -> TopoDS_Compound:
    """*body* and its *faces* in one compound: written together, the faces stay
    the body's own (shared) through the blend server's BRep transfer."""
    builder = BRep_Builder()
    carrier = TopoDS_Compound()
    builder.MakeCompound(carrier)
    builder.Add(carrier, body.wrapped)
    for face in faces:
        builder.Add(carrier, face.wrapped)
    return carrier


def _carried(carrier: TopoDS_Shape) -> tuple[Solid, list[Face]]:
    """The body and faces :func:`_carrier` packed, in order."""
    members = TopoDS_Iterator(carrier, True, True)
    body = Solid(TopoDS.Solid_s(members.Value()))
    members.Next()
    faces: list[Face] = []
    while members.More():
        faces.append(Face(TopoDS.Face_s(members.Value())))
        members.Next()
    return body, faces


#: Surfaces whose inward offset is the same kind of surface, so both joins meet
#: them along exactly computed edges.
_ANALYTIC = frozenset(
    {
        GeomAbs_SurfaceType.GeomAbs_Plane,
        GeomAbs_SurfaceType.GeomAbs_Cylinder,
        GeomAbs_SurfaceType.GeomAbs_Cone,
        GeomAbs_SurfaceType.GeomAbs_Sphere,
        GeomAbs_SurfaceType.GeomAbs_Torus,
    }
)


def _all_analytic(body: Solid) -> bool:
    """Whether every face of *body* is a plane, cylinder, cone, sphere or torus.

    A spline wall is left to Arc. On the case-2 spline prism (40 x 20), sealed
    through the whole shell pipeline, the Intersection route read 1.84e-2 mm^3
    under the true volume at t = 0.5 and 5.0e-4 over at t = 1, where Arc stays
    within 4.4e-5. At t = 1 the two raw hollows differ by only 1.6e-9 relative
    (the error enters when the offset edges are tightened), so comparing them
    would not have caught it."""
    return all(
        BRepAdaptor_Surface(face.wrapped).GetType() in _ANALYTIC
        for face in body.faces()
    )


def _same_hollow(arc: Solid, intersection: Solid) -> bool:
    """Whether the Intersection join built Arc's hollow: valid, the same
    shells and faces, and the same volume, area, centroid and inertia tensor
    (module docstring). Centroids are compared relative to the bounding-box
    diagonal and the tensor relative to its largest entry; on the bodies the
    route takes the two joins agree to 3e-15 in both (2026-09-30)."""
    if not intersection.is_valid:
        return False
    if len(intersection.shells()) != len(arc.shells()):
        return False
    if len(intersection.faces()) != len(arc.faces()):
        return False
    arc_volume = volume_properties(arc).volume
    volume_gap = abs(volume_properties(intersection).volume - arc_volume)
    if volume_gap > _AGREE_REL * abs(arc_volume):
        return False
    if abs(intersection.area - arc.area) > _AGREE_REL * arc.area:
        return False
    arc_centre, arc_inertia = _moments(arc)
    centre, inertia = _moments(intersection)
    size = arc.bounding_box().diagonal
    if any(
        abs(a - b) > _AGREE_REL * size for a, b in zip(arc_centre, centre, strict=True)
    ):
        return False
    scale = max(abs(value) for value in arc_inertia)
    return all(
        abs(a - b) <= _AGREE_REL * scale
        for a, b in zip(arc_inertia, inertia, strict=True)
    )


def _moments(solid: Solid) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Centroid and inertia tensor (about the centroid) of *solid*. Only
    analytic bodies are compared (:func:`_hollow`), where OCCT's plain volume
    integration is exact to rounding."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid.wrapped, props)
    centre = props.CentreOfMass()
    matrix = props.MatrixOfInertia()
    return (
        (centre.X(), centre.Y(), centre.Z()),
        tuple(matrix.Value(row, col) for row in (1, 2, 3) for col in (1, 2, 3)),
    )


def _concave_edge_count(body: Solid, thickness_mm: float) -> int:
    """Edges OCCT's inward offset of *body* puts a tube on: concave by OCCT's own
    analysis (``BRepOffset_Analyse`` at the angle ``BRepOffset_MakeOffset``
    derives from the tolerance and offset). With none, the Arc and Intersection
    joins build the same offset faces."""
    coefficient = min(_HOLLOW_TOL_MM / (thickness_mm / 2 + _CONFUSION_MM), 1.0)
    analysis = BRepOffset_Analyse(body.wrapped, 4 * math.asin(coefficient))
    return sum(
        any(
            interval.Type() == ChFiDS_TypeOfConcavity.ChFiDS_Concave
            for interval in analysis.Type(edge.wrapped)
        )
        for edge in body.edges()
    )


def _free_face_count(body: Solid, faces_to_remove: list[Face]) -> int:
    """Faces of *body* neither opened nor sharing an edge with an opened face:
    the ones the Arc offset keeps in its address-ordered map (module
    docstring)."""
    # Maps compare by IsSame; a lid opened at a face with 900 edges made the
    # pairwise test take 1.9 s (2026-10-02).
    opened_faces = TopTools_IndexedMapOfShape()
    opened_edges = TopTools_IndexedMapOfShape()
    for face in faces_to_remove:
        opened_faces.Add(face.wrapped)
        TopExp.MapShapes_s(face.wrapped, TopAbs_ShapeEnum.TopAbs_EDGE, opened_edges)
    return sum(
        1
        for face in body.faces()
        if not opened_faces.Contains(face.wrapped)
        and not any(opened_edges.Contains(edge.wrapped) for edge in face.edges())
    )


def _face_key(face: TopoDS_Face) -> tuple[float, ...]:
    """Sort key for :func:`_canonical_face_order`: area centroid and area,
    then tiebreaks for faces that round to the same of both (without them,
    ``sorted`` keeps such a pair in OCCT's hash order): surface type,
    orientation, the second moments about the centroid, and the tight bounding
    box. Only faces congruent AND coincident could still tie, and a valid shell
    has none."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    centre = props.CentreOfMass()
    inertia = props.MatrixOfInertia()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(face, box, False, False)
    return (
        round(centre.X(), _ORDER_DECIMALS),
        round(centre.Y(), _ORDER_DECIMALS),
        round(centre.Z(), _ORDER_DECIMALS),
        round(props.Mass(), _ORDER_DECIMALS),
        float(BRepAdaptor_Surface(face).GetType().value),
        float(face.Orientation().value),
        *(
            round(inertia.Value(row, column), _ORDER_DECIMALS)
            for row, column in ((1, 1), (1, 2), (1, 3), (2, 2), (2, 3), (3, 3))
        ),
        *(round(bound, _ORDER_DECIMALS) for bound in box.Get()),
    )


def _canonical_face_order(solid: Solid) -> Solid:
    """*solid* with each shell's faces sorted by :func:`_face_key`: the same
    faces, the same shells in the same order, only the order within a shell
    fixed (module docstring, R2-F1)."""
    builder = BRep_Builder()
    rebuilt = TopoDS_Solid()
    builder.MakeSolid(rebuilt)
    shells = TopoDS_Iterator(solid.wrapped, False, False)
    while shells.More():
        shell = TopoDS.Shell_s(shells.Value())
        faces: list[TopoDS_Face] = []
        members = TopoDS_Iterator(shell, False, False)
        while members.More():
            faces.append(TopoDS.Face_s(members.Value()))
            members.Next()
        ordered = TopoDS_Shell()
        builder.MakeShell(ordered)
        for face in sorted(faces, key=_face_key):
            builder.Add(ordered, face)
        ordered.Closed(shell.Closed())
        ordered.Orientation(shell.Orientation())
        builder.Add(rebuilt, ordered)
        shells.Next()
    rebuilt.Orientation(solid.wrapped.Orientation())
    return Solid(rebuilt)


def offset_history(
    body: BodyShape, shelled: BodyShape, thickness_mm: float
) -> list[tuple[Face, Face]]:
    """Each face the shell CREATED, paired with the face of *body* it is the
    inward offset of (DESIGN-INTENT-REFS step 3: OCCT's ``Modified`` of the
    offset, read back from the geometry because the result has been tightened,
    cleaned, healed and re-ordered since). A face of *shelled* that *body*
    already had (the same face, or one on the same surface) is not created.

    The offset is checked, not assumed, and only for the surfaces whose offset
    is the same kind: a plane one wall behind the source's with the opposite
    outward normal, or a coaxial cylinder whose radius differs by the wall. A
    face several sources could offset to is paired with none of them (a wrong
    name is worse than none), and so is any other face: it stays unnamed.
    """
    sources = body.faces()
    kept = {surface_key(face) for face in sources} - {None}
    own = TopTools_IndexedMapOfShape()  # IsSame: the same TShape and location
    for source in sources:
        own.Add(source.wrapped)
    near = _OffsetCandidates(sources, thickness_mm)
    out: list[tuple[Face, Face]] = []
    for face in shelled.faces():
        if own.Contains(face.wrapped):
            continue
        if surface_key(face) in kept:
            continue
        offsets = [
            sources[index]
            for index in near.of(face)
            if _offsets_to(sources[index], face, thickness_mm)
        ]
        if len(offsets) == 1:
            out.append((offsets[0], face))
    return out


#: How much looser than :func:`_offsets_to` the candidate filter is (mm, and
#: in the cosine): it only has to keep every pair that test can accept.
_CANDIDATE_SLACK = 1e-6


class _OffsetCandidates:
    """The sources :func:`_offsets_to` could accept for a face, found with
    array arithmetic: a superset, in source order, that the exact test then
    decides. Asking it of every source made :func:`offset_history` quadratic:
    111 s on a 906-face lid whose shell has 2936 faces (2026-10-02)."""

    def __init__(self, sources: list[Face], thickness_mm: float) -> None:
        self._t = thickness_mm
        planes: list[tuple[int, Coordinates, Coordinates]] = []
        cylinders: list[tuple[int, Coordinates, Coordinates, float]] = []
        for index, source in enumerate(sources):
            surface = BRepAdaptor_Surface(source.wrapped)
            kind = surface.GetType()
            if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
                location = surface.Plane().Location()
                planes.append((index, _plane_normal(source), _coordinates(location)))
            elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
                cylinder = surface.Cylinder()
                cylinders.append(
                    (
                        index,
                        _coordinates(cylinder.Axis().Direction()),
                        _coordinates(cylinder.Location()),
                        cylinder.Radius(),
                    )
                )
        self._plane_index = np.array([p[0] for p in planes], dtype=np.int64)
        self._plane_normal = np.array([p[1] for p in planes]).reshape(-1, 3)
        self._plane_at = np.array([p[2] for p in planes]).reshape(-1, 3)
        self._cylinder_index = np.array([c[0] for c in cylinders], dtype=np.int64)
        self._axis = np.array([c[1] for c in cylinders]).reshape(-1, 3)
        self._centre = np.array([c[2] for c in cylinders]).reshape(-1, 3)
        self._radius = np.array([c[3] for c in cylinders], dtype=np.float64)

    def of(self, face: Face) -> list[int]:
        """Indices (ascending) of the sources *face* may be the offset of."""
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        slack = _CANDIDATE_SLACK
        reach = KERNEL_LINEAR_TOL_MM + slack
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane and len(self._plane_index):
            inward = np.array(_plane_normal(face))
            at = np.array(_coordinates(surface.Plane().Location()))
            facing = self._plane_normal @ inward <= -1.0 + _PARALLEL_TOL + slack
            gap = ((at - self._plane_at) * self._plane_normal).sum(axis=1)
            hits = facing & (np.abs(gap + self._t) <= reach)
            return self._plane_index[hits].tolist()
        if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder and len(self._cylinder_index):
            cylinder = surface.Cylinder()
            axis = np.array(_coordinates(cylinder.Axis().Direction()))
            centre = np.array(_coordinates(cylinder.Location()))
            aligned = np.abs(self._axis @ axis) >= 1.0 - _PARALLEL_TOL - slack
            apart = centre - self._centre
            along = (apart * self._axis).sum(axis=1)
            off_axis = np.linalg.norm(apart - self._axis * along[:, None], axis=1)
            step = np.abs(np.abs(self._radius - cylinder.Radius()) - self._t)
            hits = aligned & (off_axis <= reach) & (step <= reach)
            return self._cylinder_index[hits].tolist()
        return []


Coordinates = tuple[float, float, float]


def _coordinates(xyz: gp_Pnt | gp_Dir) -> Coordinates:
    return (xyz.X(), xyz.Y(), xyz.Z())


def _plane_normal(face: Face) -> Coordinates:
    """The outward unit normal of a planar *face* (its orientation applied),
    as ``Face.normal_at`` gives it, without the parameter box it reads."""
    normal = gp_Vec()
    BRepGProp_Face(face.wrapped).Normal(0.0, 0.0, gp_Pnt(), normal)
    normal.Normalize()
    return (normal.X(), normal.Y(), normal.Z())


def _offsets_to(source: Face, face: Face, thickness_mm: float) -> bool:
    """Whether *face* lies on the inward offset of *source*'s surface by
    *thickness_mm* (kernel linear tolerance; normals to ``_PARALLEL_TOL``)."""
    a, b = BRepAdaptor_Surface(source.wrapped), BRepAdaptor_Surface(face.wrapped)
    kind = a.GetType()
    if kind != b.GetType():
        return False
    if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
        outward, inward = source.normal_at(), face.normal_at()
        if outward.dot(inward) > -1.0 + _PARALLEL_TOL:
            return False
        gap = Vector(b.Plane().Location()) - Vector(a.Plane().Location())
        return abs(gap.dot(outward) + thickness_mm) <= KERNEL_LINEAR_TOL_MM
    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        ca, cb = a.Cylinder(), b.Cylinder()
        axis = Vector(ca.Axis().Direction())
        if abs(axis.dot(Vector(cb.Axis().Direction()))) < 1.0 - _PARALLEL_TOL:
            return False
        apart = Vector(cb.Location()) - Vector(ca.Location())
        off_axis = (apart - axis * apart.dot(axis)).length
        step = abs(abs(ca.Radius() - cb.Radius()) - thickness_mm)
        return off_axis <= KERNEL_LINEAR_TOL_MM and step <= KERNEL_LINEAR_TOL_MM
    return False


#: Two unit normals or axes closer than this to (anti-)parallel are taken as
#: such: the resolve-side normal tolerance class (authored walls are exact).
_PARALLEL_TOL = 1e-9
