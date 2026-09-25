"""Mass properties and topology counts of a B-rep shape (OCCT GProp).

Measurements come from the exact B-rep (GProp integration + optimal AABB),
never from a tessellation — mesh quality cannot perturb them.

MASS lives here too (docs/design/materials.md): ``mass = volume x density`` is
computed from the very volume this module just measured, in the same function,
so the two cannot drift. A body whose caller passes no density reports
``mass_g=None`` — absent, never ``0.0``.

VOLUME IS INTEGRATED ADAPTIVELY (:data:`VOLUME_EPS`), not at OCCT's default
fixed Gauss order. That order is EXACT for planes and quadrics and biased on
trimmed NURBS, which made the defect structurally invisible to this repo's
own fixtures — see :data:`VOLUME_EPS` for the derivation and the numbers.

The OCP wheel ships no type stubs, so the raw GProp calls below are opaque
to pyright; the directives scope that relaxation to this file only, and the
fully-typed :class:`ShapeProperties` DTO keeps the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from build123d import Face
from loft_wire.materials import mass_g
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
from OCP.BRepGProp import (
    BRepGProp,
    BRepGProp_Domain,
    BRepGProp_Face,
    BRepGProp_Vinert,
)
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.gp import gp_Pnt, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator

from geometry.kernel.types import BodyShape
from geometry.schemas import BoundingBox, ShapeProperties, TopologyCounts, Vec3

#: Per-face relative bound handed to OCCT's ADAPTIVE volume integrator
#: (``BRepGProp::VolumeProperties(S, VProps, Eps, OnlyClosed, SkipShared)``).
#:
#: WHY NOT THE DEFAULT. The two-argument overload integrates at a FIXED Gauss
#: order chosen from each surface's degree. For a plane or a quadric that order
#: is EXACT — which is precisely why this was invisible here for so long: every
#: authored golden in this repo is planes, cylinders, cones, spheres and tori,
#: and 58 of the 59 agree with their hand-derived analytic volumes to <= 3e-11
#: under EITHER integrator (the 59th, `sketch-angle-gusset-45deg`, sits 2.1e-8
#: out under both — a constant sketch-solve offset, not an integration residual).
#: On trimmed NURBS the fixed order is NOT exact, and the error is not small:
#: measured on a KUKA KR600 STEP import (4 123 faces)
#: the fixed order reads 1 067 269 278.7 mm^3 where the adaptive integrator
#: converges to 1 065 685 171 mm^3 — **1.49e-3 relative, ~1.58 litres on a
#: 1.07 m^3 robot**, in the third significant figure of a number the inspector
#: shows a user and that ``mass_g`` is computed from. A CAD tool that reports a
#: plausible wrong mass is worse than a slow one, because nobody re-checks it.
#:
#: WHY 1e-10, AND WHY NOT LOOSER. Eps is a per-FACE RELATIVE bound, so it has no
#: closed-form relationship to the absolute mm^3 tolerances the goldens assert;
#: it was therefore DERIVED BY SWEEP over the whole 59-golden corpus rather than
#: reasoned about. The column that decides it is the corpus-wide SAFETY MARGIN —
#: the smallest ratio of a golden's documented tolerance to its actual deviation
#: from its hand-derived analytic volume — because "passes" and "passes with room
#: to spare" are different claims and only the second one survives an OCCT
#: upgrade (full table in docs/GEOMETRY-QA.md, 2026-09-15):
#:
#:   eps        goldens outside tolerance   min margin (tol/deviation)
#:   FIXED      0                           68.7
#:   1e-3       8                           FAILS
#:   1e-7       8                           FAILS
#:   1e-8       0                            3.4
#:   1e-9       0                            3.4
#:   1e-10      0                           68.7
#:   1e-12      0                           68.7
#:
#: The eight that fail are the FILLET, REVOLVED-GROOVE and SHELL-PINCH goldens —
#: bodies with blend faces — and they carry the corpus's tightest tolerances
#: (1e-9 and 1e-8 absolute). A LOOSE eps makes the analytically-exact cases WORSE
#: than the fixed order did, because adaptive subdivision stops as soon as two
#: successive refinements agree; it does not start from the exact answer.
#:
#: 1e-8 merely PASSES: `mirror-revolve-groove-tangent-wall` still carries a
#: 2.9e-10 integration residual against a 1e-9 bound, i.e. 3.4x margin, which is
#: a golden one OCCT release away from going red for a reason nobody would
#: recognise. **At 1e-10 that residual vanishes beneath float noise and the
#: corpus margin becomes 68.7x — numerically identical to the FIXED order's own
#: margin**, and the golden that bounds it stops being a blend part
#: (`mirror-revolve-groove-tangent-wall`) and becomes the same float-noise case
#: that bounds the exact integrator (`draft-frustum-box`). That equality is the
#: criterion: 1e-10 is where adaptive integration stops being measurably worse
#: than exact integration on the shapes where exact integration is available.
#: Nothing in the corpus improves between 1e-10 and 1e-16.
#:
#: COST, measured, because it is not free: ~5.2x on the volume integration.
#: Across all 59 goldens 29.6 ms -> 154.5 ms (0.5 -> 2.6 ms each, against
#: whole-tree benchmark ceilings of 1000/2000 ms); on the 4 123-face KUKA
#: import 1.9 s -> ~14 s, against an import+tessellate path already measured at
#: ~34 s. Bought knowingly: this is the difference between a right number and a
#: fast wrong one.
#:
#: SURFACE AREA IS DELIBERATELY LEFT ON THE FIXED ORDER. It has the same defect
#: class and two orders less of it (7.1e-6 on a lofted NURBS part, 1.7e-5 on the
#: KUKA), and — decisively — the adaptive area reading does not CONVERGE on that
#: part: it moves 1.7e-5 -> 2.9e-5 between eps 1e-8 and 1e-10, i.e. by the size
#: of the signal, while costing another ~11 s. Swapping a known small bias for an
#: unconverged reading at double the price is not an improvement. Recorded as a
#: known limit in docs/GEOMETRY-QA.md rather than fixed in passing.
VOLUME_EPS = 1e-10


#: Surface kinds the adaptive VOLUME integrator does not converge on when they
#: sweep a spline (:func:`volume_integrand`). Found by geometry QA
#: (docs/GEOMETRY-QA.md 2026-09-24, F1). The flanks of a PLAIN extrude of a
#: sketch-spline profile are ``Geom_SurfaceOfLinearExtrusion`` over a B-spline.
#: On the gear's spur twin (24 such gaps cut from a disc) the adaptive reading
#: WANDERS with eps: +5.35 / -0.34 mm^3 at 1e-10 / 1e-12 against the
#: section-area truth, and +8.52 / +21.97 / -24.62 at 1e-10 / 1e-12 / 1e-14 on
#: the spline-slot golden. A revolved spline is ``Geom_SurfaceOfRevolution``,
#: the same family, so it is routed the same way.
_SWEPT_SURFACE_KINDS = frozenset(
    {
        GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion,
        GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution,
    }
)

#: Basis curves whose swept surface IS converted (:func:`volume_integrand`).
#: Only a spline basis is: the extrusion or revolution of an ELLIPSE (or any
#: other analytic conic) converges unconverted and comes out WORSE as a NURBS
#: twin (review S3 of a0a70ec, measured: an ellipse prism 1.05e-5 -> 1.93e-5
#: mm^3, an elliptic torus 1.05e-5 -> 4.85e-5), so it stays as it is.
_SPLINE_CURVE_KINDS = frozenset(
    {
        GeomAbs_CurveType.GeomAbs_BSplineCurve,
        GeomAbs_CurveType.GeomAbs_BezierCurve,
    }
)


def _sweeps_a_spline(face: Face) -> bool:
    """Whether *face* is an extrusion or revolution of a B-spline/Bezier curve."""
    adaptor = BRepAdaptor_Surface(face.wrapped)
    if adaptor.GetType() not in _SWEPT_SURFACE_KINDS:
        return False
    return adaptor.BasisCurve().GetType() in _SPLINE_CURVE_KINDS


def _is_offset(face: Face) -> bool:
    """Whether *face* lies on a ``Geom_OffsetSurface`` (:func:`volume_properties`)."""
    return (
        BRepAdaptor_Surface(face.wrapped).GetType()
        == GeomAbs_SurfaceType.GeomAbs_OffsetSurface
    )


def volume_integrand(shape: BodyShape) -> object:
    """The ``TopoDS_Shape`` whose volume integral is the body's volume.

    With no face that sweeps a spline (:func:`_sweeps_a_spline`) this is the
    body itself, so every such body, an extruded or revolved ellipse included,
    is measured byte-for-byte as before. Otherwise it is a COMPOUND of the
    body's faces in which each spline-sweeping face is replaced by its
    ``BRepBuilderAPI_NurbsConvert`` twin, orientation kept. That conversion is
    exact (an extrusion or revolution of a B-spline IS a B-spline surface), and
    GProp sums a volume face by face (divergence theorem), so the compound
    integrates to the body's volume. Only the offending faces change
    representation.

    Measured on the spline-slot golden: -1.8e-12 mm^3 from its Green's-theorem
    truth, against +1.3e-4 when the WHOLE body is converted (planes and
    cylinders re-expressed as NURBS then integrate adaptively, less well) and
    +8.52 mm^3 with nothing converted. The body is never modified.

    COST (review S2, 2026-09-25, measured): building the integrand is about
    1.5 ms per converted face plus the face walk. A disc with 48 spline-slot
    walls of 99 faces: 71 ms to build, then 51-66 ms to integrate against 37 ms
    raw. The 4 123-face KUKA import (38 converted faces): 289-465 ms to build
    against an 11.1-11.7 s volume integral, about 3 %. Not cached: a per-body
    cache would save that 3 % at the price of a keyed store in the one
    measurement every rebuild trusts.
    """
    faces = shape.faces()
    # Classified ONCE per face (review N4): each check builds a surface adaptor.
    converts = [_sweeps_a_spline(face) for face in faces]
    if not any(converts):
        return shape.wrapped
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for face, convert in zip(faces, converts, strict=True):
        if convert:
            twin = BRepBuilderAPI_NurbsConvert(face.wrapped, True).Shape()
            builder.Add(compound, twin)
        else:
            builder.Add(compound, face.wrapped)
    return compound


@dataclass(frozen=True)
class VolumeReading:
    """A body's volume (mm^3) and volume centroid (mm), as reported."""

    volume: float
    centroid: tuple[float, float, float]


#: Gauss-Legendre order per knot span for an offset face
#: (:func:`_offset_face_moments`), and the higher order that checks it. Within a
#: span the offset of a polynomial patch is analytic, so the rule converges
#: fast: measured on the shelled spline-slot disc, order 8 is 1.8e-5 mm^3 off
#: order 16, and 16 and 24 agree to 1e-12 relative.
_OFFSET_GAUSS_ORDER = 16
_OFFSET_GAUSS_CHECK_ORDER = 24

#: Relative agreement demanded between the two orders; worse falls back.
_OFFSET_GAUSS_AGREEMENT = 1e-10

#: Relative spread (of the parameter value) within which a pcurve counts as an
#: isoline (:func:`isoline_rectangle`), and the points it is sampled at.
_ISOLINE_TOL = 1e-9
_ISOLINE_SAMPLES = 16


def isoline_rectangle(face: Face) -> tuple[float, float, float, float] | None:
    """``(u0, u1, v0, v1)`` when *face* is bounded by exactly two u-isolines and
    two v-isolines (its trimmed domain IS that parameter rectangle), else None.

    Every offset wall a shell of an extrude makes has this form: its ends are
    v-isolines and its sides, where it meets the neighbouring walls, u-isolines
    (measured on the golden, QA's case 2 and the shelled spline-slot disc).
    """
    us: list[float] = []
    vs: list[float] = []
    edges = 0
    explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
    while explorer.More():
        pcurve = BRepAdaptor_Curve2d(TopoDS.Edge_s(explorer.Current()), face.wrapped)
        first, last = pcurve.FirstParameter(), pcurve.LastParameter()
        points = [
            pcurve.Value(first + (last - first) * k / _ISOLINE_SAMPLES)
            for k in range(_ISOLINE_SAMPLES + 1)
        ]
        u = [p.X() for p in points]
        v = [p.Y() for p in points]
        if max(u) - min(u) <= _ISOLINE_TOL * max(1.0, abs(u[0])):
            us.append(u[0])
        elif max(v) - min(v) <= _ISOLINE_TOL * max(1.0, abs(v[0])):
            vs.append(v[0])
        else:
            return None
        edges += 1
        explorer.Next()
    if edges != 4 or len(us) != 2 or len(vs) != 2:
        return None
    return (min(us), max(us), min(vs), max(vs))


def _knot_breaks(knots: Sequence[float], low: float, high: float) -> list[float]:
    return sorted({low, high, *(k for k in knots if low < k < high)})


def _offset_face_moments(
    face: Face, location: gp_Pnt, order: int
) -> tuple[float, tuple[float, float, float]] | None:
    """This offset face's contribution to the body's volume and first moments.

    The field is the one OCCT's per-face volume integrator (``BRepGProp_Vinert``)
    uses, so the result adds to its per-face results: volume
    ``(1/3) (X - L) . n dA`` and first moments ``(X - L) ((X - L) . n) / 4 dA``,
    L = *location*. Measured against ``BRepGProp_Vinert`` on a box face by face,
    and against Gauss-Kronrod on the golden's offset face: 3e-12 mm^3, 6e-11 in
    the moments. Integrated by Gauss-Legendre of *order* on every knot span of
    the offset's B-spline basis, over the face's isoline rectangle. None when
    the face is not an isoline rectangle.
    """
    rectangle = isoline_rectangle(face)
    if rectangle is None:
        return None
    u0, u1, v0, v1 = rectangle
    adaptor = BRepAdaptor_Surface(face.wrapped)
    basis = adaptor.BasisSurface()
    u_knots: list[float] = []
    v_knots: list[float] = []
    if basis.GetType() == GeomAbs_SurfaceType.GeomAbs_BSplineSurface:
        spline = basis.BSpline()
        u_knots = [spline.UKnot(i) for i in range(1, spline.NbUKnots() + 1)]
        v_knots = [spline.VKnot(i) for i in range(1, spline.NbVKnots() + 1)]
    nodes, weights = np.polynomial.legendre.leggauss(order)
    sign = -1.0 if face.wrapped.Orientation() == TopAbs_REVERSED else 1.0
    lx, ly, lz = location.X(), location.Y(), location.Z()
    point, d_u, d_v = gp_Pnt(), gp_Vec(), gp_Vec()
    mass = mx = my = mz = 0.0
    for ua, ub in itertools.pairwise(_knot_breaks(u_knots, u0, u1)):
        for va, vb in itertools.pairwise(_knot_breaks(v_knots, v0, v1)):
            jacobian = (ub - ua) * (vb - va) / 4
            for node_u, weight_u in zip(nodes, weights, strict=True):
                u = (ua + ub) / 2 + (ub - ua) / 2 * float(node_u)
                for node_v, weight_v in zip(nodes, weights, strict=True):
                    v = (va + vb) / 2 + (vb - va) / 2 * float(node_v)
                    adaptor.D1(u, v, point, d_u, d_v)
                    nx = d_u.Y() * d_v.Z() - d_u.Z() * d_v.Y()
                    ny = d_u.Z() * d_v.X() - d_u.X() * d_v.Z()
                    nz = d_u.X() * d_v.Y() - d_u.Y() * d_v.X()
                    x, y, z = point.X() - lx, point.Y() - ly, point.Z() - lz
                    weight = float(weight_u) * float(weight_v) * jacobian
                    flux = sign * (x * nx + y * ny + z * nz) * weight
                    mass += flux / 3
                    mx += x * flux / 4
                    my += y * flux / 4
                    mz += z * flux / 4
    return mass, (mx, my, mz)


def _checked_offset_moments(
    face: Face, location: gp_Pnt
) -> tuple[float, tuple[float, float, float]] | None:
    """:func:`_offset_face_moments`, confirmed by a higher order, else None."""
    result = _offset_face_moments(face, location, _OFFSET_GAUSS_ORDER)
    if result is None:
        return None
    check = _offset_face_moments(face, location, _OFFSET_GAUSS_CHECK_ORDER)
    if check is None:
        return None
    scale = max(abs(result[0]), abs(check[0]), 1e-300)
    if abs(result[0] - check[0]) > _OFFSET_GAUSS_AGREEMENT * scale:
        return None
    return check


def _offset_body_reading(shape: BodyShape) -> VolumeReading:
    """Volume and centroid of a body with offset faces, face by face.

    Offset faces: :func:`_checked_offset_moments`. An offset face that is not an
    isoline rectangle, or does not converge, FALLS BACK to its
    ``BRepBuilderAPI_NurbsConvert`` twin: bounded time, but an approximation
    (1.7e-6 mm from the true surface on the golden, +6.45e-6 mm^3 there).
    Every other face goes through OCCT's adaptive per-face integrator at
    :data:`VOLUME_EPS`, a spline-swept one as its exact NURBS twin, as
    :func:`volume_integrand` routes them. All faces share one reference point,
    the bounding-box centre, so their contributions add.
    """
    centre = shape.bounding_box().center()
    location = gp_Pnt(centre.X, centre.Y, centre.Z)
    lx, ly, lz = location.X(), location.Y(), location.Z()
    mass = mx = my = mz = 0.0
    for face in shape.faces():
        if _is_offset(face):
            own = _checked_offset_moments(face, location)
            if own is not None:
                mass += own[0]
                mx, my, mz = mx + own[1][0], my + own[1][1], mz + own[1][2]
                continue
            target = TopoDS.Face_s(
                BRepBuilderAPI_NurbsConvert(face.wrapped, True).Shape()
            )
        elif _sweeps_a_spline(face):
            target = TopoDS.Face_s(
                BRepBuilderAPI_NurbsConvert(face.wrapped, True).Shape()
            )
        else:
            target = TopoDS.Face_s(face.wrapped)
        surface = BRepGProp_Face(target)
        if TopoDS_Iterator(target).More():
            part = BRepGProp_Vinert(
                surface, BRepGProp_Domain(target), location, VOLUME_EPS
            )
        else:
            part = BRepGProp_Vinert(surface, location, VOLUME_EPS)
        m = float(part.Mass())
        g = part.CentreOfMass()
        mass += m
        mx += m * (g.X() - lx)
        my += m * (g.Y() - ly)
        mz += m * (g.Z() - lz)
    return VolumeReading(
        volume=mass,
        centroid=(lx + mx / mass, ly + my / mass, lz + mz / mass),
    )


def volume_properties(shape: BodyShape) -> VolumeReading:
    """Volume and volume centroid of *shape*, as reported.

    THE one place a body's volume is integrated: :func:`measure_shape` and the
    twisted extrude's Cavalieri guard both read it, so they cannot disagree.
    The integrand is :func:`volume_integrand` (spline-swept faces as their
    exact NURBS twins) and the rule the adaptive one at :data:`VOLUME_EPS`,
    EXCEPT for a body with a face on a ``Geom_OffsetSurface``, which is
    integrated face by face (:func:`_offset_body_reading`;
    OFFSET-SURFACE-VOLUME-1, GEOMETRY-QA 2026-09-25 F2).

    Why offsets need their own route (a ``Geom_OffsetSurface`` is its own OCCT
    surface type, not a sweep): a Shell of a spline extrude offsets the spline
    wall, and OCCT's adaptive and fixed-order rules do not converge on that
    face. Measured on the golden ``shell-spline-prism-30x10-t1`` against its
    analytic truth: +1.61 / -8.31 / +5.90 mm^3 at eps 1e-10 / 1e-12 / 1e-14,
    and +97 mm^3 on QA's case 2. The F1 NURBS conversion does not carry over,
    because an offset of a polynomial surface is not polynomial:
    ``BRepBuilderAPI_NurbsConvert`` APPROXIMATES it. Gauss-Kronrod
    (``VolumePropertiesGK``, b29fa88) is accurate but took 43-196 s on ordinary
    shelled spline parts (QA F2). The per-face route integrates the TRUE
    offset surface by Gauss-Legendre per knot span: the golden -1.39e-8 mm^3
    (Gauss-Kronrod -9.0e-9; both read +1.8e-7 before the shell's rim edges were
    rebuilt, kernel.offset_edges) in 0.1 s; case 2 0.1 s (was 52 s); the shelled
    spline-slot disc 1.4 s (was 148 s). Every body WITHOUT an offset face reads
    byte-for-byte as before.
    """
    faces = shape.faces()
    if any(_is_offset(face) for face in faces):
        return _offset_body_reading(shape)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(
        volume_integrand(shape), props, VOLUME_EPS, False, False
    )
    centre = props.CentreOfMass()
    return VolumeReading(
        volume=float(props.Mass()),
        centroid=(float(centre.X()), float(centre.Y()), float(centre.Z())),
    )


def measure_shape(
    shape: BodyShape, *, density_kg_m3: float | None = None
) -> ShapeProperties:
    """Compute volume, surface area, centroid, exact AABB, topology counts.

    *shape* is any part body — a single :class:`~build123d.Solid` or a
    :class:`~build123d.Compound` of a multi-body part's disjoint solids (§MB-0).
    OCCT GProp integrates volume / surface / centroid over every subshape solid
    and ``.faces()`` / ``.edges()`` / ``.shells()`` count across them, so a
    compound measures to the same analytic roll-up :func:`combine_properties`
    produces per-body — the STEP round-trip re-measures a multi-solid part this
    way.

    *density_kg_m3* is the body's material density (``None`` = no material
    assigned, the default). With a density the result carries ``mass_g`` =
    volume x density and a ``center_of_mass``; the shape passed here is ONE
    body of ONE material, so its centre of mass IS its volume centroid — the
    mass weighting only becomes visible when bodies of different materials are
    combined (:func:`combine_properties`). Without a density both fields stay
    ``None``: absent, not zero (docs/design/materials.md).
    """
    if shape.wrapped is None:
        raise ValueError("Cannot measure an empty shape")

    # Adaptive integration (:data:`VOLUME_EPS`). ``OnlyClosed=False`` and
    # ``SkipShared=False`` reproduce the two-argument overload's defaults
    # EXACTLY, so the only behavioural change is the integration rule: passing
    # OnlyClosed=True would silently drop open shells, which is a different
    # answer to a different question and would confound an integration fix with
    # a change of subject. The return value is OCCT's estimate of the relative
    # error it reached; it is not consulted, because the sweep that chose
    # VOLUME_EPS measured the achieved accuracy against hand-derived analytic
    # values rather than against the integrator's opinion of itself.
    # Swept (extrusion/revolution) faces are integrated as their exact NURBS
    # twins, which the adaptive rule does converge on (:func:`volume_integrand`);
    # a body with offset faces is integrated by Gauss-Kronrod
    # (:func:`volume_properties`).
    reading = volume_properties(shape)
    surface_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, surface_props)

    bbox = shape.bounding_box(optimal=True)

    volume = reading.volume
    x, y, z = reading.centroid
    centre = Vec3(x=x, y=y, z=z)
    mass = mass_g(volume, density_kg_m3)

    return ShapeProperties(
        volume=volume,
        surface_area=float(surface_props.Mass()),
        centroid=centre,
        # One body, one material: the centre of mass coincides with the volume
        # centroid exactly. Reported only when a material says so.
        mass_g=mass,
        center_of_mass=centre if mass is not None else None,
        bounding_box=BoundingBox(
            min=Vec3(x=bbox.min.X, y=bbox.min.Y, z=bbox.min.Z),
            max=Vec3(x=bbox.max.X, y=bbox.max.Y, z=bbox.max.Z),
        ),
        topology=TopologyCounts(
            faces=len(shape.faces()),
            edges=len(shape.edges()),
            shells=len(shape.shells()),
        ),
    )


def combine_properties(parts: Sequence[ShapeProperties]) -> ShapeProperties:
    """Analytic roll-up of a part's multiple disjoint bodies (multi-body §MB-0).

    A part may now end with more than one body (design docs/design/multi-body.md
    §MB-0); its combined mass properties are composed ANALYTICALLY over the body
    set — NO re-mesh, NO boolean — reusing the assembly ``_combine_properties``
    pattern (``geometry.assembly.evaluate``) with identity placements, since a
    part's bodies already share one frame: total volume = Σ per-body volumes;
    combined centroid = volume-weighted Σ of each body's centroid; combined AABB
    = union of the per-body AABBs; surface area + topology counts (faces / edges /
    shells) are summed. Deterministic: a fixed-order float64 reduction over the
    tree-ordered body set (RESEARCH §9). Callers gate on a non-empty set (a part
    with a single body measures that solid directly — byte-identical to before).

    MASS composes the same way and is where the volume/mass distinction stops
    being academic (docs/design/materials.md §3): total mass = Σ per-body masses,
    and the combined ``center_of_mass`` is weighted by MASS, not volume — a steel
    body and an aluminium body of equal volume do not balance at their midpoint.
    Both are ``None`` unless EVERY body has a material: a partial sum would
    understate the mass of the part while looking like a complete answer, which
    is the lie this whole field exists to avoid. ``centroid`` stays
    volume-weighted and is always reported.
    """
    if not parts:
        raise ValueError("combine_properties requires at least one body's properties")
    total_volume = 0.0
    total_area = 0.0
    cx = cy = cz = 0.0
    # Mass roll-up: known only while every body so far has one (see docstring).
    total_mass: float | None = 0.0
    mx = my = mz = 0.0
    faces = edges = shells = 0
    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    for part in parts:
        total_volume += part.volume
        total_area += part.surface_area
        cx += part.volume * part.centroid.x
        cy += part.volume * part.centroid.y
        cz += part.volume * part.centroid.z
        if part.mass_g is None or part.center_of_mass is None:
            total_mass = None
        elif total_mass is not None:
            total_mass += part.mass_g
            mx += part.mass_g * part.center_of_mass.x
            my += part.mass_g * part.center_of_mass.y
            mz += part.mass_g * part.center_of_mass.z
        faces += part.topology.faces
        edges += part.topology.edges
        shells += part.topology.shells
        box = part.bounding_box
        min_x, min_y, min_z = (
            min(min_x, box.min.x),
            min(min_y, box.min.y),
            min(min_z, box.min.z),
        )
        max_x, max_y, max_z = (
            max(max_x, box.max.x),
            max(max_y, box.max.y),
            max(max_z, box.max.z),
        )
    if total_volume != 0.0:
        cx, cy, cz = cx / total_volume, cy / total_volume, cz / total_volume
    center_of_mass: Vec3 | None = None
    if total_mass is not None:
        # A zero total mass can only come from zero total volume (density > 0),
        # in which case the mass-weighted average is undefined; fall back to the
        # volume centroid rather than dividing by zero.
        center_of_mass = (
            Vec3(x=mx / total_mass, y=my / total_mass, z=mz / total_mass)
            if total_mass != 0.0
            else Vec3(x=cx, y=cy, z=cz)
        )
    return ShapeProperties(
        volume=total_volume,
        surface_area=total_area,
        centroid=Vec3(x=cx, y=cy, z=cz),
        mass_g=total_mass,
        center_of_mass=center_of_mass,
        bounding_box=BoundingBox(
            min=Vec3(x=min_x, y=min_y, z=min_z),
            max=Vec3(x=max_x, y=max_y, z=max_z),
        ),
        topology=TopologyCounts(faces=faces, edges=edges, shells=shells),
    )
