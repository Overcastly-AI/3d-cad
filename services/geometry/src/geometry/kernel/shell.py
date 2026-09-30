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

* OCCT sometimes RAISES (``StdFail_NotDone``) — caught here as
  :class:`ShellError` → ``shell_failed`` (the belt-and-braces "kernel could not
  complete the offset" bucket, the fillet/chamfer precedent);
* OCCT sometimes SILENTLY returns the un-hollowed body (the walls merged, no
  material removed) — caught here by the MATERIAL-REMOVED invariant: a valid
  inward shell strictly reduces the volume, so a result whose volume is not
  below the original is a collapsed cavity → :class:`ShellThicknessError` →
  ``shell_thickness_too_large``. This invariant is the load-bearing guard: it
  is the ONLY thing standing between a too-thick shell and a silently wrong
  solid on the OCCT-returns-quietly path.

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

from build123d import Compound, Face, Kind, Solid
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
    """The OCCT hollow failed to complete (belt-and-braces ``shell_failed``).

    The kernel could not build the offset (an ``StdFail_NotDone`` from
    ``MakeThickSolid``, or a result that is not exactly one solid). For too-large
    thicknesses OCCT raises this on the paths where it does not instead return a
    quietly-collapsed body — see :class:`ShellThicknessError` for that path."""


class ShellThicknessError(ValueError):
    """The wall thickness collapses, self-intersects, or PINCHES the inward cavity.

    Two measured causes, one user action ("change the thickness"), so one code:

    * the hollow COMPLETES but the material-removed invariant fails (the walls
      merged and no cavity remains — OCCT's silent too-thick path);
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
    (§MB-4). Returns a new single cleaned solid; raises on the two too-thick
    modes (OCCT raise / silent no-op) exactly as the pre-multi-lump code did.
    """
    original_volume = body.volume
    try:
        solids, canonicalise = _hollow(body, faces_to_remove, thickness_mm)
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ShellError(
            f"Shell failed in the kernel ({type(exc).__name__}); the wall "
            f"thickness ({thickness_mm} mm) may be too large for this body."
        ) from exc

    if len(solids) != 1:
        raise ShellError(
            f"Shell produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
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
        raise ShellError(
            f"Shell produced a body the kernel could not validate ({exc}); the "
            f"wall thickness ({thickness_mm} mm) may be too large for this body."
        ) from exc

    # Material-removed invariant: a valid inward shell strictly reduces the
    # volume. OCCT can quietly return the un-hollowed body when the thickness
    # collapses the cavity — catch that here rather than ship a wrong solid.
    if shelled.volume >= original_volume - _MATERIAL_REMOVED_MARGIN_MM3:
        raise ShellThicknessError(
            f"Wall thickness {thickness_mm} mm is too large: the inward cavity "
            "collapses (no material was removed). Reduce the thickness below the "
            "smallest half-wall of the body."
        )
    return _canonical_face_order(shelled) if canonicalise else shelled


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
    shells and faces, and the same volume and area (module docstring)."""
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
    return abs(intersection.area - arc.area) <= _AGREE_REL * arc.area


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
