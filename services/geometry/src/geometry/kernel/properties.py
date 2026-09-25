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
# pyright: reportUnknownArgumentType=false

import math
from collections.abc import Sequence

from build123d import Face
from loft_wire.materials import mass_g
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopoDS import TopoDS_Compound

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
#: sweep a spline (:func:`_volume_integrand`). Found by geometry QA
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

#: Basis curves whose swept surface IS converted (:func:`_volume_integrand`).
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


def _volume_integrand(shape: BodyShape) -> object:
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
    """
    faces = shape.faces()
    if not any(_sweeps_a_spline(face) for face in faces):
        return shape.wrapped
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for face in faces:
        if _sweeps_a_spline(face):
            twin = BRepBuilderAPI_NurbsConvert(face.wrapped, True).Shape()
            builder.Add(compound, twin)
        else:
            builder.Add(compound, face.wrapped)
    return compound


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

    volume_props = GProp_GProps()
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
    # twins, which the adaptive rule does converge on (:func:`_volume_integrand`).
    BRepGProp.VolumeProperties_s(
        _volume_integrand(shape), volume_props, VOLUME_EPS, False, False
    )
    surface_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, surface_props)

    centroid = volume_props.CentreOfMass()
    bbox = shape.bounding_box(optimal=True)

    volume = float(volume_props.Mass())
    centre = Vec3(x=float(centroid.X()), y=float(centroid.Y()), z=float(centroid.Z()))
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
