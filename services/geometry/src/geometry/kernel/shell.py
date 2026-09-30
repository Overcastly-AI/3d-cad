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
makes its bytes reproducible. Measured over 4 processes x 3 rebuilds
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
"""
# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math

from build123d import Compound, Face, Kind, Solid, Vector
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepOffset import BRepOffset_Analyse
from OCP.ChFiDS import ChFiDS_TypeOfConcavity
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Iterator, TopoDS_Shell, TopoDS_Solid

from geometry.kernel.degenerate import find_zero_width_slits
from geometry.kernel.healing import HealingError, clean_shape, conform_solid
from geometry.kernel.lumps import assemble_lumps, group_faces_by_lump
from geometry.kernel.offset_edges import tighten_offset_edges
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell_walls import FaultKind, ShellDefinition, WallFault
from geometry.kernel.types import BodyShape

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
    body: BodyShape, faces_to_remove: list[Face], thickness_mm: float
) -> BodyShape:
    """Hollow *body* to a uniform inward *thickness_mm*, opening *faces_to_remove*.

    An empty *faces_to_remove* produces a sealed (fully-enclosed) hollow; a
    non-empty list leaves those faces open.

    Multi-body (§MB-4): a single :class:`~build123d.Solid` hollows exactly as
    before (byte-identical). A multi-lump :class:`~build123d.Compound` is shelled
    PER LUMP — OCCT's ``MakeThickSolid`` cannot run on a whole compound, so each
    lump is hollowed independently (opening the picked faces that belong to it;
    lumps with no picked face become sealed hollows) and the results reassemble in
    the explicit lump order. Every lump is hollowed, so the lump count is
    preserved and the material-removed invariant is checked per lump.

    Raises:
        ShellThicknessError: the thickness collapses the cavity on some lump (the
            hollow completed but removed no material — OCCT's silent too-thick
            path), or PINCHES it to zero width on some lump (an internal wall
            exactly ``2 * thickness_mm`` wide, leaving coincident faces with no
            material between them — SH-1; see that class for why this is an error).
        ShellError: the OCCT hollow failed to complete, or left other than
            exactly one solid per lump (single body chain per lump, design §7.6).
    """
    if thickness_mm <= 0:
        raise ValueError(f"thickness_mm must be > 0, got {thickness_mm}")

    if isinstance(body, Compound):
        solids = body.solids()
        groups = group_faces_by_lump(solids, faces_to_remove)
        return assemble_lumps(
            [
                _shell_one_lump(solid, groups.get(index, []), thickness_mm)
                for index, solid in enumerate(solids)
            ]
        )
    return _shell_one_lump(body, faces_to_remove, thickness_mm)


def _shell_one_lump(
    body: Solid, faces_to_remove: list[Face], thickness_mm: float
) -> Solid:
    """Hollow ONE lump (a single solid) — the byte-identical single-body path.

    Shared by the single-solid fast path and each lump of the multi-lump path
    (§MB-4). Returns a new single cleaned solid that passed the definition check
    (:mod:`geometry.kernel.shell_walls`), or raises :func:`_refusal`: a
    :class:`ShellThicknessError` when the thickness leaves no cavity, a
    :class:`ShellError` naming what the kernel got wrong otherwise.
    """
    original_volume = body.volume
    definition = ShellDefinition(body, faces_to_remove, thickness_mm)
    try:
        solids, canonicalise = _hollow(body, faces_to_remove, thickness_mm)
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
    try:
        shelled = conform_solid(cleaned)
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
    return shelled


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
    body: Solid, faces_to_remove: list[Face], thickness_mm: float
) -> tuple[list[Solid], bool]:
    """OCCT's inward hollow of *body*, and whether its face order still needs
    :func:`_canonical_face_order` (module docstring).

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
    """
    blends = _concave_edge_count(body, thickness_mm)
    arc = list(body.hollow(faces_to_remove, -thickness_mm).solids())
    canonicalise = _free_face_count(body, faces_to_remove) + blends > 1
    if faces_to_remove or blends or len(arc) != 1 or not _all_analytic(body):
        return arc, canonicalise
    try:
        intersection = body.hollow([], -thickness_mm, kind=Kind.INTERSECTION).solids()
    except Exception:  # the Intersection join refuses some bodies: keep Arc
        return arc, canonicalise
    if len(intersection) == 1 and _same_hollow(arc[0], intersection[0]):
        return [intersection[0]], False
    return arc, canonicalise


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
    opened_edges = [edge.wrapped for face in faces_to_remove for edge in face.edges()]
    return sum(
        1
        for face in body.faces()
        if not any(face.wrapped.IsSame(opened.wrapped) for opened in faces_to_remove)
        and not any(
            edge.wrapped.IsSame(opened)
            for edge in face.edges()
            for opened in opened_edges
        )
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
