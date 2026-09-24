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

from build123d import Edge, Face, Plane, Solid, Vector, Wire
from loft_wire.sketch import Point2D
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.GeomAdaptor import GeomAdaptor_Curve
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.GeomConvert import GeomConvert_CurveToAnaCurve
from OCP.GProp import GProp_GProps
from OCP.ShapeBuild import ShapeBuild_Edge
from OCP.ShapeFix import ShapeFix_Edge
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.extrude import plane_point_to_world
from geometry.kernel.properties import VOLUME_EPS

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
#: The failure it exists for — a twist so tight that OCCT returns an INVERTED
#: solid, volume ~ -A*d, which ``BRepCheck`` still calls valid (that square at
#: 3600 deg) — misses by 2.0.
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
    holes does not leave one solid, or when the swept tool fails the Cavalieri
    invariant (:data:`TWIST_VOLUME_REL_TOL`) — in practice a twist too tight for
    the profile's distance from the axis. The feature layer reports it as
    ``twist_failed``; the fix is a smaller twist or a longer extrusion.
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
    return Solid(builder.Shape())


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
    """Volume of *solid* by the adaptive GProp the inspector itself uses
    (:data:`~geometry.kernel.properties.VOLUME_EPS`), so the guard and the
    reported mass properties read a twisted body identically."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid.wrapped, props, VOLUME_EPS, False, False)
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

    Works on a copy and returns the ORIGINAL tool if the result fails
    ``BRepCheck`` or moves the volume by more than the fit allows, so this can
    only ever improve a body, never break one. Deterministic: edges are visited
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
    before, after = _adaptive_volume(tool), _adaptive_volume(copy)
    if abs(after - before) > TWIST_VOLUME_REL_TOL * abs(before):
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
            (:data:`MAX_AUX_HELIX_PITCH_MM`), the sweep failed, did not leave
            one solid, or failed the invariant (a twist too tight for the
            profile).
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

    tool = _restore_cap_edges(tool, origin, direction, distance_mm)
    expected = _adaptive_area(face) * distance_mm
    swept = _adaptive_volume(tool)
    if not abs(swept - expected) <= TWIST_VOLUME_REL_TOL * expected:
        raise TwistError(
            f"A {twist_angle_deg:g} deg twist over {distance_mm:g} mm is too tight "
            f"for this profile to sweep cleanly; {_TOO_TIGHT}."
        )
    return tool
