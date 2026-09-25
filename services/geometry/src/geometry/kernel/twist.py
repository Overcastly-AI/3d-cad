"""Twisted extrusion: a sketch profile swept along a straight line while rotating.

The kernel half of the extrude feature's ``twist_angle_deg``
(docs/design/twisted-extrude.md). The profile travels ``distance_mm`` along the
sketch normal and turns uniformly about an axis parallel to that direction, so
every profile point traces an exact helix: a helical gear's tooth gap, a twisted
column, a drill flute's cross-section. A zero twist never reaches this module —
the feature layer keeps it on :func:`geometry.kernel.extrude.extrude_face`, so an
untwisted extrude is byte-identical to one built before this existed.

Mechanism (design §2): ``BRepOffsetAPI_MakePipeShell`` along a STRAIGHT spine in
auxiliary-spine mode, the auxiliary spine being a helix about that same line.
The section's orientation at each height is the direction from the spine to the
helix, which turns at a constant rate — an exact screw motion — and OCCT fits
each profile edge's swept surface to :data:`TWIST_SWEEP_TOLERANCE_MM`. A ruled
loft between rotated sections (the only helix route before this) joins
corresponding points by straight CHORDS and sags inside the helicoid instead.

Determinism (RESEARCH §9): the spine, helix and tolerances are pure functions of
the parameters, profile wires are swept in the face's own wire order, and the
sweep and boolean are seed-free OCCT algorithms.

The OCP wheel ships no type stubs, so the raw pipe-shell and GProp calls below
are opaque to pyright; the directives scope that relaxation to this file only
(the :mod:`geometry.kernel.properties` precedent).
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

import math

from build123d import Edge, Face, GeomType, Plane, Solid, Vector, Wire
from loft_wire.sketch import Point2D
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GeomAdaptor import GeomAdaptor_Curve
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.GeomConvert import GeomConvert_CurveToAnaCurve
from OCP.GProp import GProp_GProps
from OCP.IMeshTools import IMeshTools_Parameters
from OCP.ShapeBuild import ShapeBuild_Edge
from OCP.ShapeFix import ShapeFix_Edge
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.extrude import plane_point_to_world
from geometry.kernel.properties import VOLUME_EPS, volume_integrand
from geometry.kernel.types import BodyShape
from geometry.schemas import DEFAULT_ANGULAR_DEFLECTION

#: 3D approximation tolerance (mm) handed to ``BRepOffsetAPI_MakePipeShell``
#: (``SetTolerance(Tol3d, BoundTol, TolAngular)``) for the lateral faces. A
#: screw-swept curve is transcendental, so no B-spline represents it exactly;
#: this is how far the fit may stray. OCCT's default is 1e-4 mm (the kernel's
#: own 1e-7 m linear tolerance). 1e-7 mm is 1000x tighter at no measurable cost
#: (0.185 -> 0.196 s on the twisted-square golden) and takes that golden's
#: volume residual against its analytic value from 2.7e-4 mm^3 (at 1e-5 and
#: 1e-6) to 2.7e-7 mm^3; 1e-8 changes nothing further, so this is where the fit
#: saturates. Measured deviation of the gear tooth-gap's swept flanks from the
#: exact screw motion: 6.7e-9 mm (design §3).
TWIST_SWEEP_TOLERANCE_MM = 1e-7

#: Angular tolerance (rad) of the same fit: OCCT's default. The linear bound
#: above is the one that governs it.
TWIST_SWEEP_ANGULAR_TOLERANCE = 1e-2

#: Radius (mm) of the auxiliary helix. It sets only the DIRECTION the section
#: faces at each height (spine point -> helix point), never a position, so its
#: size is arbitrary: radius 1, 10 and 30 gave the same gear-gap surface to
#: 1e-15 mm (design §3).
TWIST_AUX_HELIX_RADIUS_MM = 1.0

#: Cavalieri guard. Every slice of a twisted extrusion is a rigid rotation of
#: the profile, so its volume is EXACTLY profile area x distance, whatever the
#: twist. A swept tool whose volume departs from that by more than this relative
#: bound is refused (:class:`TwistError`), never shipped. Healthy residuals
#: measured <= 1.7e-10 (the gear's tooth gap at 12.4 deg and at ten turns; a
#: 20 mm square over 30 mm up to 3000 deg), so this is ~6000x clear of them.
#: The failure it was built for, an INVERTED solid (volume ~ -A*d) that
#: ``BRepCheck`` still calls valid, misses by 2.0. Such exact-but-inside-out
#: sweeps are now re-oriented first (:func:`orient_closed_solid`, geometry QA
#: F3), so the guard is the net for whatever else a sweep gets wrong.
TWIST_VOLUME_REL_TOL = 1e-6


#: Largest auxiliary-helix pitch (mm per turn) the sweep will attempt. The pitch
#: is ``360 / |twist| * distance``, so a vanishing twist or a vast distance
#: drives it toward infinity, and build123d's helix normalises the direction
#: ``(2 pi, pitch)``, whose length overflows past ~1.3e154. Measured on the way
#: there: an INFINITE pitch (twist 5e-324 deg) hangs ``Edge.make_helix`` forever,
#: and a pitch past the overflow (twist 1e-160 deg) raises ``ZeroDivisionError``.
#: 1e150 stays clear of both. The wire model already folds any
#: ``|twist| < MIN_TWIST_ANGLE_DEG`` into "no twist", so from the API this bound
#: is reached only by a distance beyond ~1e138 mm; it exists so that no caller
#: of this function can hang a worker.
MAX_AUX_HELIX_PITCH_MM = 1e150


#: How close (mm) a cap edge's swept B-spline must stay to a LINE or CIRCLE for
#: the kernel to give it back its analytic curve (:func:`_restore_cap_edges`).
#: A pipe shell rebuilds even its end sections as B-splines (fits of the
#: profile's own lines and arcs at :data:`TWIST_SWEEP_TOLERANCE_MM`), so without
#: this a twisted body has no line or circle edge at all and every consumer that
#: keys on edge type (mate axes, measure directions, drawings, edge re-match)
#: misses its rims. 1e-6 mm is 10x the fit tolerance and 100x inside the
#: kernel's 1e-7 m, and it is checked at :data:`_CAP_EDGE_SAMPLES` points along
#: the edge, not just at its ends.
CAP_EDGE_RECOGNITION_TOL_MM = 1e-6

#: Points (interior + both ends) at which a cap edge must lie on its analytic
#: twin before the twin replaces it. Three would let a spline that merely
#: passes through three points of a circle be mistaken for one.
_CAP_EDGE_SAMPLES = 16


class TwistError(RuntimeError):
    """A twisted extrusion could not be swept, or the sweep came back wrong.

    Raised when OCCT's pipe-shell sweep fails outright, when a profile with
    holes does not leave one solid, when the swept tool fails the Cavalieri
    invariant (:data:`TWIST_VOLUME_REL_TOL`), or, before any sweep, when the
    twist has too many turns for its profile to build within the cost budget
    (:data:`TWIST_COST_LIMIT_S`). The feature layer reports it as
    ``twist_failed``; the message names the fix.
    """


_TOO_TIGHT = "reduce the twist angle or lengthen the extrusion"


def _sweep_wire(wire: Wire, spine: Wire, aux_helix: Wire) -> Solid:
    """Sweep one closed *wire* along the straight *spine*, turning with the helix.

    Auxiliary-spine mode (``SetMode(AuxiliarySpine, CurvilinearEquivalence=
    False)``): at each spine point P the section's normal is PQ, Q being where
    the plane through P normal to the spine meets *aux_helix*. For a straight
    spine that plane is a constant-height slice, so Q — and with it the section
    — turns by exactly ``twist * height / distance``. ``MakeSolid`` caps both
    ends with planar faces.
    """
    builder = BRepOffsetAPI_MakePipeShell(spine.wrapped)
    builder.SetMode(aux_helix.wrapped, False)
    builder.SetTolerance(
        TWIST_SWEEP_TOLERANCE_MM,
        TWIST_SWEEP_TOLERANCE_MM,
        TWIST_SWEEP_ANGULAR_TOLERANCE,
    )
    builder.Add(wire.wrapped)
    builder.Build()
    if not builder.IsDone():
        raise TwistError(f"The twisted extrusion could not be swept; {_TOO_TIGHT}.")
    if not builder.MakeSolid():
        raise TwistError(
            f"The twisted extrusion could not be closed into a solid; {_TOO_TIGHT}."
        )
    return orient_closed_solid(Solid(builder.Shape()))


def orient_closed_solid(solid: Solid) -> Solid:
    """Turn an INSIDE-OUT closed solid right side out, in place.

    Some sweeps come back with every face reversed, volume -A*d, while the
    geometry is exact (geometry QA F3, 2026-09-24: a 20 mm square over 30 mm at
    -3000, +3100 and +3600 deg; its turned vertices sit on the boundary to
    1.2e-8 mm). ``BRepLib::OrientClosedSolid`` orients the shell by
    classification and restores +A*d, so the Cavalieri guard judges the
    GEOMETRY and refuses only a sweep that is actually wrong. A shell that is
    not closed is left alone, and the guard still catches it. Module-level so a
    test can take it away to exercise the guard.
    """
    BRepLib.OrientClosedSolid_s(TopoDS.Solid_s(solid.wrapped))
    return solid


def _adaptive_area(face: Face) -> float:
    """Area of the planar profile *face* by ADAPTIVE GProp integration.

    ``Face.area`` integrates at a fixed Gauss order, exact on lines and arcs but
    not on a spline-bounded face (measured 5e-5 relative on the gear gap), which
    is coarser than the invariant the guard enforces.
    """
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, props, VOLUME_EPS, False)
    return float(props.Mass())


def _adaptive_volume(solid: Solid) -> float:
    """Volume of *solid* exactly as the reported mass properties read it: the
    same integrand (:func:`~geometry.kernel.properties.volume_integrand`, which
    swaps spline-swept faces for their exact NURBS twins) and the same adaptive
    rule (:data:`~geometry.kernel.properties.VOLUME_EPS`), so the guard can
    never pass a body the inspector then reads differently (review N1)."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(
        volume_integrand(solid), props, VOLUME_EPS, False, False
    )
    return float(props.Mass())


def _project(curve: object, point: object) -> tuple[float, float]:
    """(parameter, distance) of *point*'s nearest projection onto *curve*."""
    projector = GeomAPI_ProjectPointOnCurve(point, curve)
    if projector.NbPoints() == 0:
        return 0.0, math.inf
    return projector.LowerDistanceParameter(), projector.LowerDistance()


def _analytic_twin(edge: object) -> tuple[object, float, float] | None:
    """A LINE/CIRCLE carrying *edge* exactly, oriented and ranged like it.

    ``None`` unless OCCT recognises the edge's curve as a line or circle AND
    every one of :data:`_CAP_EDGE_SAMPLES` points along the edge lies within
    :data:`CAP_EDGE_RECOGNITION_TOL_MM` of it. The twin runs in the SAME
    direction as the edge (first vertex at ``u0``, last at ``u1``), so the
    edge's vertices and its faces' orientations stay valid when it is swapped.
    """
    adaptor = BRepAdaptor_Curve(edge)
    first, last = adaptor.FirstParameter(), adaptor.LastParameter()
    curve = BRep_Tool.Curve_s(edge, 0.0, 0.0)
    if curve is None:
        return None
    twin = GeomConvert_CurveToAnaCurve.ComputeCurve_s(
        curve, CAP_EDGE_RECOGNITION_TOL_MM, first, last, 0.0, 0.0, 0.0
    )
    if twin is None or GeomAdaptor_Curve(twin).GetType() not in (
        GeomAbs_CurveType.GeomAbs_Line,
        GeomAbs_CurveType.GeomAbs_Circle,
    ):
        return None
    start, end = curve.Value(first), curve.Value(last)
    u0, gap = _project(twin, start)
    if gap > CAP_EDGE_RECOGNITION_TOL_MM:
        return None
    # Orient the twin like the edge: tangents at the first vertex must agree.
    if curve.DN(first, 1).Dot(twin.DN(u0, 1)) < 0.0:
        twin = twin.Reversed()
        u0, _ = _project(twin, start)
    if twin.IsPeriodic():
        period = twin.Period()
        if start.Distance(end) <= CAP_EDGE_RECOGNITION_TOL_MM:
            u1 = u0 + period  # a whole circle
        else:
            u_end, _ = _project(twin, end)
            u1 = u0 + (u_end - u0) % period
    else:
        u1, _ = _project(twin, end)
    if not u1 > u0:
        return None
    for index in range(_CAP_EDGE_SAMPLES):
        param = first + (last - first) * index / (_CAP_EDGE_SAMPLES - 1)
        _, gap = _project(twin, curve.Value(param))
        if gap > CAP_EDGE_RECOGNITION_TOL_MM:
            return None
    return twin, u0, u1


def _restore_cap_edges(
    tool: Solid, origin: Vector, direction: Vector, distance_mm: float
) -> Solid:
    """Give the tool's END-CAP edges back their analytic lines and circles.

    A pipe shell rebuilds the start and end sections, too, as B-spline fits, so
    the z = 0 edges of a twisted square are B-splines where the sketch drew
    lines, and a hole's rims are B-splines where it drew a circle. Every consumer
    that keys on edge TYPE then misses them — a bore in a twisted body is no mate
    axis, a cap line has no measure direction (review of ``d823af9``). This swaps
    each cap edge's 3D curve for its exact analytic twin (:func:`_analytic_twin`)
    in place, then RE-PROJECTS that curve onto every face that carries the edge
    (``ShapeFix_Edge::FixAddPCurve`` + ``FixSameParameter``). That is exactly how
    a STEP reader rebuilds the edge from its 3D curve, and it is why the body
    round-trips: re-parametrising the OLD pcurves instead
    (``BRepLib::SameParameter``) left the in-memory body 1.0e-7 mm^3 away from
    its own STEP re-import (measured on the golden), while re-projection holds
    the round trip to the unconverted body's 4e-9. The helical lateral edges and
    faces are untouched: they are genuinely not lines, circles, planes or
    cylinders.

    Works on a copy and returns the ORIGINAL tool if the copy fails
    ``BRepCheck``; the caller's Cavalieri check then falls back to the original
    if the copy's volume is off, so this can only ever improve a body, never
    break one. Deterministic: edges are visited
    in the copy's own indexed-map order.
    """
    copy = Solid(BRepBuilderAPI_Copy(tool.wrapped).Shape())
    faces_of = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(copy.wrapped, TopAbs_EDGE, TopAbs_FACE, faces_of)
    builder = BRep_Builder()
    remover = ShapeBuild_Edge()
    fixer = ShapeFix_Edge()
    swapped = 0
    for index in range(1, faces_of.Extent() + 1):
        edge = TopoDS.Edge_s(faces_of.FindKey(index))
        wrapped = Edge(edge)
        heights = [
            (point - origin).dot(direction)
            for point in (
                wrapped.start_point(),
                wrapped.end_point(),
                wrapped.position_at(0.5),
            )
        ]
        on_start = all(abs(h) <= CAP_EDGE_RECOGNITION_TOL_MM for h in heights)
        on_end = all(
            abs(h - distance_mm) <= CAP_EDGE_RECOGNITION_TOL_MM for h in heights
        )
        if not (on_start or on_end):
            continue
        twin = _analytic_twin(edge)
        if twin is None:
            continue  # a sketch spline stays a spline
        curve, u0, u1 = twin
        tolerance = BRep_Tool.Tolerance_s(edge)
        builder.UpdateEdge(edge, curve, TopLoc_Location(), tolerance)
        builder.Range(edge, u0, u1, True)
        for face in faces_of.FindFromIndex(index):
            owner = TopoDS.Face_s(face)
            remover.RemovePCurve(edge, owner)
            fixer.FixAddPCurve(edge, owner, False, TWIST_SWEEP_TOLERANCE_MM)
        fixer.FixSameParameter(edge)
        swapped += 1
    if swapped == 0:
        return tool
    if not BRepCheck_Analyzer(copy.wrapped).IsValid():
        return tool
    return copy


def twisted_extrude_face(
    face: Face,
    plane: Plane,
    distance_mm: float,
    reverse: bool,
    twist_angle_deg: float,
    center: Point2D,
) -> Solid:
    """Extrude *face* along the plane normal while TWISTING it: a helical sweep.

    The twisted sibling of :func:`geometry.kernel.extrude.extrude_face`. The
    face travels ``distance_mm`` along the sketch normal (``reverse`` flips it,
    exactly as for a prism) and rotates uniformly by ``twist_angle_deg`` about
    the axis through *center* (sketch-local mm) parallel to that direction.

    The sign is RIGHT-HANDED ABOUT THE DIRECTION OF TRAVEL: a positive twist is
    a right-hand helix whichever way the extrusion points, because handedness is
    a property of the part, not of the direction toggle. On an XY sketch with
    ``direction: normal`` that is counter-clockwise seen from +Z.

    A face with holes sweeps each boundary on its own (a pipe shell sweeps one
    wire) and subtracts the swept holes from the swept outer boundary. The
    result must pass the Cavalieri invariant — volume == face area x distance to
    :data:`TWIST_VOLUME_REL_TOL` — before it is returned.

    Raises:
        ValueError: ``distance_mm <= 0`` or a zero twist (caller errors: a zero
            twist belongs on ``extrude_face``, byte-identically).
        TwistError: the twist is too small for its distance to sweep
            (:data:`MAX_AUX_HELIX_PITCH_MM`), predicted to cost more than
            :data:`TWIST_COST_LIMIT_S` (:func:`twist_cost_estimate_s`), the
            sweep failed, did not leave one solid, or failed the Cavalieri
            invariant.
    """
    if distance_mm <= 0:
        raise ValueError(f"distance_mm must be > 0, got {distance_mm}")
    if twist_angle_deg == 0:
        raise ValueError("a zero twist is a plain prism; call extrude_face")

    direction = plane.z_dir * (-1.0 if reverse else 1.0)
    origin = plane_point_to_world(plane, center)
    pitch = 360.0 / abs(twist_angle_deg) * distance_mm
    if not (math.isfinite(pitch) and pitch <= MAX_AUX_HELIX_PITCH_MM):
        # Checked BEFORE the helix is built: an infinite pitch hangs
        # Edge.make_helix outright (measured: twist 5e-324 deg never returned).
        raise TwistError(
            f"A {twist_angle_deg:g} deg twist over {distance_mm:g} mm is too small "
            "to sweep; set the twist to 0 for a straight extrusion."
        )
    # Before anything is swept: a twist this profile cannot sweep, check and
    # mesh within the budget is refused, not left to pin a worker (design §6.1).
    cost = twist_cost_estimate_s(
        face, plane, distance_mm, reverse, twist_angle_deg, center
    )
    if cost > TWIST_COST_LIMIT_S:
        raise TwistError(
            f"A {twist_angle_deg:g} deg twist is too many turns for this profile "
            f"to build in reasonable time (estimated {cost:.1f} s, limit "
            f"{TWIST_COST_LIMIT_S:g} s); reduce the twist angle or give the "
            "profile fewer edges."
        )

    try:
        spine = Wire([Edge.make_line(origin, origin + direction * distance_mm)])
        # make_helix's handedness is about its OWN normal, which is the direction
        # of travel here: exactly the right-hand-about-travel convention above.
        aux_helix = Wire(
            [
                Edge.make_helix(
                    pitch=pitch,
                    height=distance_mm,
                    radius=TWIST_AUX_HELIX_RADIUS_MM,
                    center=origin,
                    normal=direction,
                    lefthand=twist_angle_deg < 0,
                )
            ]
        )
        tool = _sweep_wire(face.outer_wire(), spine, aux_helix)
        holes = [_sweep_wire(inner, spine, aux_helix) for inner in face.inner_wires()]
        if holes:
            solids = list(tool.cut(*holes).solids())
            if len(solids) != 1:
                raise TwistError(
                    f"The twisted extrusion's holes did not leave one solid; "
                    f"{_TOO_TIGHT}."
                )
            tool = solids[0]
    except TwistError:
        raise
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise TwistError(
            f"The twisted extrusion failed in the kernel ({type(exc).__name__}); "
            f"{_TOO_TIGHT}."
        ) from exc

    expected = _adaptive_area(face) * distance_mm

    def cavalieri_holds(solid: Solid) -> bool:
        swept = _adaptive_volume(solid)
        return abs(swept - expected) <= TWIST_VOLUME_REL_TOL * expected

    # ONE volume integral on the common path: the restored tool is checked
    # against the Cavalieri invariant directly (it is the same check the raw
    # tool must pass), and only if the restoration broke it is the raw tool
    # tried. On a many-turn body each integral costs seconds (design §6.1).
    restored = _restore_cap_edges(tool, origin, direction, distance_mm)
    if cavalieri_holds(restored):
        return restored
    if restored is not tool and cavalieri_holds(tool):
        return tool
    raise TwistError(
        f"A {twist_angle_deg:g} deg twist over {distance_mm:g} mm did not sweep "
        f"cleanly (its volume is not profile area x distance); {_TOO_TIGHT}."
    )


# --------------------------------------------------------------------------- #
# Bounded tessellation of helicoidal flanks (geometry QA F4)                  #
# --------------------------------------------------------------------------- #

#: Estimated mesh size, in angular cells, at or above which a B-SPLINE face of a
#: twisted body is meshed with the bounded helicoid settings
#: (:func:`mesh_helicoidal_faces`). The estimate is ``(Tu / a) * (Tv / a)``, the
#: surface normal's total turning along each parameter over the angular
#: deflection ``a``: a face whose normal turns hard along BOTH parameters is what
#: drives BRepMesh's surface-deflection control into hundreds of thousands of
#: triangles. Measured (0.1 rad): the 30 deg golden's flanks 18, a 360 deg
#: square 1 414, 720 deg 3 359. 500 leaves the golden and every gentle twist on
#: the production mesher (byte-identical, the golden's mesh counts unchanged)
#: and catches every twist that costs seconds (docs/design/twisted-extrude.md
#: §6.1).
HELICOID_MESH_ESTIMATE_MIN = 500.0

#: Grid points per parameter direction for the normal-turning estimate.
_TURNING_SAMPLES = 24


def _normal_turning(face: Face) -> tuple[float, float]:
    """(Tu, Tv): the largest total turning (rad) of the surface normal along a
    u-line and along a v-line of *face*, sampled on a regular UV grid."""
    adaptor = BRepAdaptor_Surface(face.wrapped)
    u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
    v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()
    props = BRepLProp_SLProps(adaptor, 1, 1e-9)
    n = _TURNING_SAMPLES

    def normal(u: float, v: float) -> tuple[float, float, float] | None:
        props.SetParameters(u, v)
        if not props.IsNormalDefined():
            return None
        d = props.Normal()
        return (d.X(), d.Y(), d.Z())

    grid = [
        [normal(u0 + (u1 - u0) * i / n, v0 + (v1 - v0) * j / n) for j in range(n + 1)]
        for i in range(n + 1)
    ]

    def angle(
        a: tuple[float, float, float] | None, b: tuple[float, float, float] | None
    ) -> float:
        if a is None or b is None:
            return 0.0
        dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
        return math.acos(max(-1.0, min(1.0, dot)))

    along_u = max(
        sum(angle(grid[i][j], grid[i + 1][j]) for i in range(n)) for j in range(n + 1)
    )
    along_v = max(
        sum(angle(grid[i][j], grid[i][j + 1]) for j in range(n)) for i in range(n + 1)
    )
    return along_u, along_v


def helicoid_mesh_estimate(face: Face, angular_deflection: float) -> float:
    """Angular cells BRepMesh would need on *face* (0 for a non-B-spline face)."""
    if (
        BRepAdaptor_Surface(face.wrapped).GetType()
        != GeomAbs_SurfaceType.GeomAbs_BSplineSurface
    ):
        return 0.0
    along_u, along_v = _normal_turning(face)
    return max(along_u / angular_deflection, 1.0) * max(
        along_v / angular_deflection, 1.0
    )


def mesh_helicoidal_faces(
    shape: BodyShape, linear_deflection: float, angular_deflection: float
) -> int:
    """Pre-mesh a twisted body's helicoidal flanks with a BOUNDED cost.

    Called only for bodies of a tree that contains a twisted extrude, before the
    ordinary mesher. Every B-spline face whose :func:`helicoid_mesh_estimate` is
    at least :data:`HELICOID_MESH_ESTIMATE_MIN` is meshed alone, with the
    production parameters (the same linear and angular deflection, relative,
    parallel) EXCEPT ``ControlSurfaceDeflection = False``. That switch turns
    off BRepMesh's refinement loop, which on a surface whose normal turns along
    both parameters inserts nodes into the hundreds of thousands. The initial
    grid is still derived from the linear and angular deflection. Measured
    (design §6.1): the worst chord error on the bounded 360 and 720 deg
    flanks is 0.21 mm, against 0.23 mm on the production mesh of a 30 deg
    twisted flank (the relative deflection makes 0.1 mm no absolute chord
    bound on these faces).
    The ordinary mesher then keeps these triangulations, because they already
    satisfy its deflection, and meshes the remaining faces exactly as before.

    Every other face, and every body outside a twisted tree, is untouched.
    Returns how many faces were pre-meshed. Deterministic: faces are visited
    in ``shape.faces()`` order, with the production parallelism.
    """
    params = IMeshTools_Parameters()
    params.Deflection = linear_deflection
    params.DeflectionInterior = linear_deflection
    params.Angle = angular_deflection
    params.AngleInterior = angular_deflection
    params.Relative = True
    params.InParallel = True
    params.ControlSurfaceDeflection = False
    meshed = 0
    for face in shape.faces():
        if (
            helicoid_mesh_estimate(face, angular_deflection)
            < HELICOID_MESH_ESTIMATE_MIN
        ):
            continue
        BRepMesh_IncrementalMesh(face.wrapped, params)
        meshed += 1
    return meshed


#: Budget, in summed :func:`helicoid_mesh_estimate` over the faces that need
#: the bounded mesher, above which a 3MF export of a twisted body is REFUSED.
#: lib3mf's writer (build123d ``Mesher``) meshes a deep COPY of the body, so
#: the bounded pre-mesh does not reach it and the copy is meshed at full,
#: unbounded cost. Calibrated in design twisted-extrude.md §6.1.
THREE_MF_TWIST_ESTIMATE_BUDGET = 8000.0


class MeshExportTooDenseError(Exception):
    """A 3MF export of a twisted body that would take minutes to mesh.

    STL, GLB and STEP of the same body work (the first two through the bounded
    helicoid mesher); only 3MF's writer re-meshes a copy at full cost.
    """

    code = "export_mesh_too_dense"


def check_3mf_twist_budget(shape: BodyShape, angular_deflection: float) -> None:
    """Refuse a 3MF of *shape* whose helicoidal flanks exceed the 3MF budget."""
    total = 0.0
    for face in shape.faces():
        estimate = helicoid_mesh_estimate(face, angular_deflection)
        if estimate >= HELICOID_MESH_ESTIMATE_MIN:
            total += estimate
    if total > THREE_MF_TWIST_ESTIMATE_BUDGET:
        raise MeshExportTooDenseError(
            "This twisted body is too dense to export as 3MF in reasonable time "
            "(its many-turn helical faces). Export STL or STEP instead, or reduce "
            "the twist."
        )


# --------------------------------------------------------------------------- #
# Pre-sweep cost guard (geometry QA F4)                                       #
# --------------------------------------------------------------------------- #

#: The wall-clock budget (s, on the reference box) for one twisted extrude end
#: to end: sweep, Cavalieri guard, mass properties and the bounded mesh.
TWIST_COST_BUDGET_S = 5.0

#: Largest :func:`twist_cost_estimate_s` a twist may have. Anything over it is
#: refused with :class:`TwistError` before anything is swept (design
#: twisted-extrude.md §6.1). It sits below :data:`TWIST_COST_BUDGET_S` because
#: the model under-predicts by up to 0.8x: measured, every accepted stress case
#: built in <= 5.0 s and every refused one took >= 4.3 s. The estimate is a
#: pure function of the profile and the parameters, so the refusal is
#: deterministic on every machine; only its calibration refers to a clock.
TWIST_COST_LIMIT_S = 4.5

# The cost model (design §6.1), fitted by non-negative least squares on
# relative error over a 50-case stress set (0.05-9.4 s measured: polygons of
# 3-48 edges, stars, off-axis and scaled profiles, circles and holes, the gear
# tooth gap). Per profile edge, in seconds:
#
#   turns   x  a per-turn base by edge kind: the ribbon's sweep, its share of
#              the two volume integrals and its edge discretisation. A spline
#              ribbon (the gear's involute flanks) is the dear one;
#   turns^2 x  a quadratic part. The swept B-spline's pole count grows with
#              the turns and so does every evaluation on it, so the mesh cost
#              of a flank goes as turns SQUARED (measured: 0.17 s at 5 turns,
#              0.63 s at 10, one square flank). By edge:
#              - every edge: a small constant;
#              - a WIDE line flank (one the bounded mesher takes, see
#                HELICOID_MESH_ESTIMATE_MIN): a constant plus a term in the
#                angle the edge subtends at the axis, how far round it wraps;
#              - a NARROW line flank (left to the production mesher): its
#                length over its largest distance from the axis;
#              - a circle or arc: its normal turning across the edge, scaled
#                by its radius up to 5 mm. Below that the absolute 0.1 mm mesh
#                deflection coarsens the tube (measured: r 1 mm 1.5 s,
#                r 5 mm and r 50 mm 6 s, all at 10 turns).
#
# Measured prediction / actual over the set: 0.78-1.25 for all but four cases
# (two conservative: a 10 mm square over 100 mm 1.65, an r 2 mm circle 1.36;
# two under: a radial slot 0.73 at 1.5 s, a six-point star scaled 10x 0.58
# under load and 0.82 re-timed quiet). Every term is deterministic geometry;
# no clock is read.
_COST_TURN_LINE_S = 0.0136
_COST_TURN_CIRCLE_S = 0.0165
_COST_TURN_OTHER_S = 0.195
_COST_TURN2_EDGE_S = 0.00017
_COST_TURN2_WIDE_LINE_S = 0.00118
_COST_TURN2_SPAN_S = 0.00256
_COST_TURN2_NARROW_EXTENT_S = 0.00175
_COST_TURN2_CIRCLE_TURNING_S = 0.0086
_COST_CIRCLE_FULL_RADIUS_MM = 5.0
_COST_CIRCLE_MIN_SCALE = 0.25
_COST_EDGE_SAMPLES = 32


def _edge_normal_turning(
    edge: Edge, origin: Vector, direction: Vector, rate: float
) -> float:
    """Total turning (rad) of the swept surface's normal ACROSS *edge*.

    The screw motion carries a profile point p (relative to the axis) along
    P(s, z) = R(rate z) p(s) + z d, so at z = 0 the surface normal is
    t x (rate (d x p) + d) for the edge's unit tangent t: a closed form, no
    sweep needed.
    """
    previous: Vector | None = None
    total = 0.0
    for index in range(_COST_EDGE_SAMPLES + 1):
        param = index / _COST_EDGE_SAMPLES
        p = edge.position_at(param) - origin
        p = p - direction * p.dot(direction)
        normal = edge.tangent_at(param).cross(direction.cross(p) * rate + direction)
        if normal.length <= 1e-12:
            continue
        normal = normal.normalized()
        if previous is not None:
            total += math.acos(max(-1.0, min(1.0, previous.dot(normal))))
        previous = normal
    return total


def _axis_offsets(edge: Edge, origin: Vector, direction: Vector) -> list[Vector]:
    """The ends of *edge*, as offsets from the twist axis (perpendicular)."""
    offsets: list[Vector] = []
    for param in (0.0, 1.0):
        p = edge.position_at(param) - origin
        offsets.append(p - direction * p.dot(direction))
    return offsets


def twist_cost_estimate_s(
    face: Face,
    plane: Plane,
    distance_mm: float,
    reverse: bool,
    twist_angle_deg: float,
    center: Point2D,
) -> float:
    """Predicted end-to-end cost (s) of twisting *face*: cheap and pre-sweep.

    About 3 ms per profile edge (closed-form normals on 33 samples; 133 ms
    for a 48-edge star), no kernel operation. See the cost-model notes above
    and design §6.1.
    """
    direction = plane.z_dir * (-1.0 if reverse else 1.0)
    origin = plane_point_to_world(plane, center)
    rate = math.radians(abs(twist_angle_deg)) / distance_mm
    turns = abs(twist_angle_deg) / 360.0
    # A line flank the bounded mesher will take: helicoid_mesh_estimate's
    # (Tu / a) x (Tv / a), with Tv a full normal turn per twist turn.
    along_v = 2.0 * math.pi * turns / DEFAULT_ANGULAR_DEFLECTION
    linear = quadratic = 0.0
    for edge in face.edges():
        kind = edge.geom_type
        quadratic += _COST_TURN2_EDGE_S
        if kind == GeomType.LINE:
            linear += _COST_TURN_LINE_S
            turning = _edge_normal_turning(edge, origin, direction, rate)
            start, end = _axis_offsets(edge, origin, direction)
            if turning / DEFAULT_ANGULAR_DEFLECTION * along_v >= (
                HELICOID_MESH_ESTIMATE_MIN
            ):
                subtended = math.atan2(start.cross(end).length, start.dot(end))
                quadratic += _COST_TURN2_WIDE_LINE_S + _COST_TURN2_SPAN_S * subtended
            else:
                # A real edge has an end off the axis; the test only spares a
                # division by zero on a degenerate one.
                farthest = max(start.length, end.length)
                if farthest > 0.0:
                    quadratic += _COST_TURN2_NARROW_EXTENT_S * edge.length / farthest
        elif kind == GeomType.CIRCLE:
            linear += _COST_TURN_CIRCLE_S
            turning = _edge_normal_turning(edge, origin, direction, rate)
            scale = min(
                1.0,
                max(_COST_CIRCLE_MIN_SCALE, edge.radius / _COST_CIRCLE_FULL_RADIUS_MM),
            )
            quadratic += _COST_TURN2_CIRCLE_TURNING_S * turning * scale
        else:
            linear += _COST_TURN_OTHER_S
    return turns * linear + turns * turns * quadratic
