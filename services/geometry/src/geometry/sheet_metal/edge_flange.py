"""Sheet-metal edge flange (bend) — build a flange folded off a base-flange edge.

The kernel half of the edge-flange feature (docs/design/sheet-metal.md §4.2): a
new flange added off a STRAIGHT edge of the sheet body, at a chosen inner
``bend_radius`` and ``bend_angle``, connected to the base by a cylindrical BEND
region. Geometrically it is a sweep of the sheet's thickness cross-section along
an arc (the bend) + a straight segment (the flange length) — §4.2's "reuse, don't
reinvent" finding. This module builds the exact developed cross-section (a
quarter/partial annulus + the flange rectangle) in the plane perpendicular to the
picked edge and sweeps it along the edge (``Solid.extrude`` along the straight
bend axis — the same primitive :mod:`geometry.kernel.sweep` /
:mod:`geometry.kernel.extrude` use), giving EXACT analytic cylindrical bend faces
the :class:`~py_kit.schemas.features.CylindricalFaceSignature` matches to ulp
scale. Sweeping the (thickness x width) profile along a curved OCCT spine was
considered and rejected: build123d's relative-path sweep orientation is fragile
and unnecessary when the exact cross-section is known in closed form, and a clean
analytic cylinder is precisely what bend provenance needs (§2.2's flagged
MakeFace-robustness risk is sidestepped — the cross-section is a fixed simple
polygon+arcs, not a reconstructed outline).

Provenance (§5): on success the feature emits the bend's inner cylindrical
:class:`CylindricalFaceSignature` and the base reference face's
:class:`PlanarFaceSignature`, so the unfold pass finds the bend + its base by
provenance, never blind detection.

Determinism (RESEARCH §9): every value is a closed-form function of the resolved
edge geometry + the named parameters — no unordered iteration, no RNG.

The OCP wheel ships no type stubs, so the raw build123d calls are opaque to
pyright; the directives scope that relaxation to this file only, and the typed
DTOs at the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

import math
from dataclasses import dataclass

from build123d import CenterOf, Edge, Face, GeomType, Solid, Vector, Wire
from py_kit.schemas.features import CylindricalFaceSignature, PlanarFaceSignature

from geometry.kernel.edges import edge_signature_dto
from geometry.kernel.faces import face_signature_dto
from geometry.kernel.types import BodyShape
from geometry.sheet_metal.resolve import (
    SheetMetalUnfoldError,
    cylindrical_face_signature,
    find_cylindrical_face,
)


class EdgeFlangeError(SheetMetalUnfoldError):
    """The edge flange could not be built off the picked edge (per-feature error)."""


class EdgeFlangeEdgeError(EdgeFlangeError):
    """The picked edge is unsuitable for an edge flange — not a straight edge, or
    not a clean plate-edge with a large reference face to fold from."""


@dataclass(frozen=True)
class EdgeFlangeResult:
    """A built edge flange: the fused sheet body + the bend's provenance (§5)."""

    body: Solid
    cyl_signature: CylindricalFaceSignature
    base_face_signature: PlanarFaceSignature


def _adjacent_faces(body: BodyShape, edge: Edge) -> list[Face]:
    """Every planar face of *body* incident to *edge* (matched by signature)."""
    target = edge_signature_dto(edge)
    out: list[Face] = []
    for face in body.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        for candidate in face.edges():
            sig = edge_signature_dto(candidate)
            if (
                sig.curve == target.curve
                and _close(sig.end_a, target.end_a)
                and _close(sig.end_b, target.end_b)
                and abs(sig.length_mm - target.length_mm)
                <= 1e-6 * max(target.length_mm, 1.0)
            ):
                out.append(face)
                break
    return out


def _close(a: object, b: object) -> bool:
    """Two boundary ``Vec3`` within the linear subshape tolerance (mm)."""
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) <= 1e-6  # type: ignore[attr-defined]


def build_edge_flange(
    body: BodyShape,
    edge: Edge,
    flange_length_mm: float,
    bend_angle_deg: float,
    bend_radius_mm: float,
    thickness_mm: float,
) -> EdgeFlangeResult:
    """Fold a flange off *edge* of the sheet *body* and fuse it across a bend.

    *edge* is a resolved STRAIGHT edge of *body* (the picked base-flange edge).
    The flange extends outward from the edge's larger adjacent flat (plate) face
    and folds by ``bend_angle_deg`` about a bend of inner radius ``bend_radius_mm``,
    developing a leg of ``flange_length_mm`` (to the bend tangent line). The gauge
    ``thickness_mm`` is the part's sheet thickness. Returns the fused single sheet
    body + the bend provenance signatures (§5).

    Raises:
        EdgeFlangeEdgeError: *edge* is not a straight edge, or lacks a clean plate
            reference face to fold from.
        EdgeFlangeError: the fold geometry is degenerate or the fuse produced other
            than one solid (e.g. a radius/length that self-intersects the sheet).
    """
    if edge.geom_type != GeomType.LINE:
        raise EdgeFlangeEdgeError(
            "An edge flange folds off a STRAIGHT edge; the picked edge is curved."
        )

    p0 = edge @ 0.0
    p1 = edge @ 1.0
    width = float(edge.length)
    v = (p1 - p0).normalized()  # bend axis direction (along the edge)

    faces = _adjacent_faces(body, edge)
    if len(faces) < 1:
        raise EdgeFlangeEdgeError(
            "The picked edge is not incident to a planar face of the sheet body."
        )
    # Reference face = the larger adjacent flat (the plate face the flange extends
    # from); the smaller is the thickness face. Deterministic: max area, tie-broken
    # by the face's signature centroid so the pick never depends on face order.
    reference = max(
        faces,
        key=lambda f: (float(f.area), _sig_key(f)),
    )
    n = reference.normal_at(reference.center(CenterOf.MASS)).normalized()
    ref_centroid = reference.center(CenterOf.MASS)

    # Extension direction d: in the reference plane, perpendicular to the edge,
    # pointing AWAY from the plate body. d = ±(v x n); pick the sign that leads
    # away from the reference face centroid.
    d = v.cross(n).normalized()
    edge_mid = (p0 + p1) * 0.5
    away = Vector(
        edge_mid.X - ref_centroid.X,
        edge_mid.Y - ref_centroid.Y,
        edge_mid.Z - ref_centroid.Z,
    )
    if away.dot(d) < 0.0:
        d = -d

    theta = math.radians(bend_angle_deg)
    r = bend_radius_mm
    t = thickness_mm
    leg = flange_length_mm
    outer = r + t

    # Developed cross-section in (a, b) = (along d, along n), origin at p0 (on the
    # reference plane at the edge). The bend axis sits at (0, r); the inner cylinder
    # is tangent to the reference plane (b=0) at the edge foot A=(0,0).
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    dir_a, dir_b = math.cos(theta), math.sin(theta)  # flange axis after the fold
    off_a, off_b = t * math.sin(theta), -t * math.cos(theta)  # inner -> outer offset

    A = (0.0, 0.0)
    B = (0.0, -t)
    C = (r * sin_t, r - r * cos_t)  # inner arc end
    D = (C[0] + leg * dir_a, C[1] + leg * dir_b)
    Fp = (C[0] + off_a, C[1] + off_b)  # outer arc end (outer at the fold)
    E2 = (D[0] + off_a, D[1] + off_b)  # flange outer end
    half = theta / 2.0
    inner_mid = (r * math.sin(half), r - r * math.cos(half))
    outer_mid = (outer * math.sin(half), r - outer * math.cos(half))

    def to3d(ab: tuple[float, float]) -> Vector:
        return p0 + d * ab[0] + n * ab[1]

    try:
        edges = [
            Edge.make_three_point_arc(to3d(A), to3d(inner_mid), to3d(C)),
            Edge.make_line(to3d(C), to3d(D)),
            Edge.make_line(to3d(D), to3d(E2)),
            Edge.make_line(to3d(E2), to3d(Fp)),
            Edge.make_three_point_arc(to3d(Fp), to3d(outer_mid), to3d(B)),
            Edge.make_line(to3d(B), to3d(A)),
        ]
        wires = Wire.combine(edges)
        if len(wires) != 1 or not wires[0].is_closed:
            raise EdgeFlangeError(
                "The edge-flange cross-section did not close into one wire "
                "(check the bend radius / flange length for this gauge)."
            )
        flange = Solid.extrude(Face(wires[0]), v * width)
        fused = body.fuse(flange).clean()
    except EdgeFlangeError:
        raise
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise EdgeFlangeError(
            f"Edge-flange geometry failed in the kernel ({type(exc).__name__}); "
            "the bend radius / flange length may self-intersect the sheet."
        ) from exc

    solids = fused.solids()
    if len(solids) != 1:
        raise EdgeFlangeError(
            f"Edge flange produced {len(solids)} solids; a sheet-metal part is one "
            "connected body in v1 (the flange must fold off an edge of the sheet)."
        )
    result_body = solids[0]

    # Provenance (§5): the bend axis is the edge line lifted r along n; the inner
    # cylindrical face carries the bend signature. The base reference face is the
    # flat the flange folded from (its plane is intact — the arc starts at the
    # tangent edge and curves away, never covering it).
    axis_origin = (p0.X + n.X * r, p0.Y + n.Y * r, p0.Z + n.Z * r)
    axis_dir = (v.X, v.Y, v.Z)
    # Resolving the bend face is part of the kernel fold: a physically-degenerate
    # bend (e.g. a radius far below gauge, ~<1e-6 mm) can fuse into one solid yet
    # leave no findable cylindrical arc, so `find_cylindrical_face` raises
    # `NoBendFoundError` (a `SheetMetalUnfoldError`, NOT an `EdgeFlangeError`). Map
    # it — and any other resolution failure — to the typed `EdgeFlangeError` so the
    # feature degrades to `edge_flange_failed`, never the generic `evaluation_failed`
    # bucket (the honest-degradation contract; the try/except above only covers
    # construction+fuse, this covers provenance resolution).
    try:
        inner_face = find_cylindrical_face(result_body, axis_origin, axis_dir, r)
        cyl_signature = cylindrical_face_signature(inner_face)
    except EdgeFlangeError:
        raise
    except Exception as exc:
        raise EdgeFlangeError(
            f"Edge-flange bend face could not be resolved ({type(exc).__name__}); "
            "the bend radius may be too small to form a valid bend arc for this gauge."
        ) from exc
    base_sig = face_signature_dto(reference)
    assert base_sig is not None, "reference face is planar"
    return EdgeFlangeResult(
        body=result_body,
        cyl_signature=cyl_signature,
        base_face_signature=base_sig,
    )


def _sig_key(face: Face) -> tuple[float, float, float]:
    """A deterministic tie-break key for a planar face (its centroid)."""
    c = face.center(CenterOf.MASS)
    return (float(c.X), float(c.Y), float(c.Z))
