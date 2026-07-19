"""Geometric bend resolution for the sheet-metal unfold (SPIKE 0).

Given an evaluated folded body, find each **bend region** — a cylindrical face
pair (inner + outer sheet surface, concentric, radii differing by the gauge
thickness) — and the **two flanking planar faces** the bend connects, plus the
developed length of each flange (measured to the bend **tangent line**, §9
golden #1's pinned convention).

**Resolution posture — geometric, not by provenance signature (a spike call,
documented):** the design doc (§5) specifies the *shipped* edge-flange feature
tags its bend faces at construction time with a NEW ``CylindricalFaceSignature``
(``axis_origin`` + ``axis_dir`` + ``radius_mm`` + ``centroid``, a py-kit schema)
so the unfold pass never re-detects geometry. This spike resolves the bend
**geometrically** instead, for two reasons: (1) SPIKE 0's brief forbids touching
py-kit schemas (``CylindricalFaceSignature`` lives there), and (2) the spike's
job is the unfold *math* + OCCT robustness, not rebuild-survival provenance.
Every value the signature must carry is nonetheless extracted here from
``BRepAdaptor_Surface.Cylinder()`` (``axis_origin``/``axis_dir``/``radius_mm``/
``centroid`` on :class:`ResolvedBend`) — proving the signature's payload is
cheaply available at construction time, so the feature slice is a persistence +
matching wrapper, not new geometry work.

The OCP wheel ships no type stubs, so the raw BRepAdaptor/GProp calls are opaque
to pyright; the directives scope that relaxation to this file only, and the
fully-typed dataclasses below keep the boundary honest.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

import math
from dataclasses import dataclass

from build123d import CenterOf, Face, GeomType, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from geometry.kernel.types import BodyShape

Vec3f = tuple[float, float, float]

#: Documented resolution tolerances (NOT ad-hoc epsilons — CLAUDE.md / §9). The
#: L-bracket's faces are axis-aligned and its radii exact, so residuals are
#: ulp-scale; these bounds are tight enough that unrelated geometry never ties a
#: bend, loose enough to absorb kernel jitter.
_PARALLEL_TOL = 1e-9  # 1 - |dot| between unit axis directions (concentric test)
_AXIS_COINCIDENT_TOL_MM = 1e-7  # distance between two cylinder axis lines (mm)
_TANGENT_DIST_TOL_MM = 1e-7  # |plane-to-axis distance - radius| for a flanking face
_PERP_TOL = 1e-9  # |normal · axis_dir| for a plane parallel to the bend axis
_THICKNESS_REL_TOL = 1e-6  # (outer - inner radius) vs. gauge thickness


class SheetMetalUnfoldError(ValueError):
    """Base: the body could not be resolved as a depth-1 sheet-metal bend star."""


class NoBendFoundError(SheetMetalUnfoldError):
    """No cylindrical bend region (a concentric inner/outer face pair whose radii
    differ by the gauge thickness) was found — the body is not a folded sheet, or
    the thickness argument does not match its gauge."""


class BendFlankingFacesError(SheetMetalUnfoldError):
    """A bend cylinder was found but not exactly two planar faces tangent to its
    inner surface (the two flat flanges) — the bend geometry is unexpected for a
    v1 depth-1 edge flange."""


@dataclass(frozen=True)
class ResolvedFlange:
    """One flat flange flanking a bend: its developed length (to the tangent
    line), bend width, and outward normal."""

    developed_length_mm: float
    width_mm: float
    normal: Vec3f


@dataclass(frozen=True)
class ResolvedBend:
    """A resolved bend region: the closed-form inputs the unfold needs, plus the
    exact geometry the shipped ``CylindricalFaceSignature`` (§5) will carry
    (``axis_origin``/``axis_dir``/``radius_mm``/``centroid``)."""

    radius_mm: float  # inner bend radius (the CAD "bend radius")
    angle_rad: float  # fold angle: angle between the two flanking flange normals
    bend_width_mm: float
    axis_origin: Vec3f  # point on the bend axis (signature payload)
    axis_dir: Vec3f  # unit vector along the bend axis (signature payload)
    centroid: Vec3f  # inner cylindrical face area centroid (signature payload)
    flanges: tuple[ResolvedFlange, ResolvedFlange]


@dataclass(frozen=True)
class _CylFace:
    """Internal: a cylindrical face's resolved geometry."""

    face: Face
    radius: float
    axis_origin: Vector
    axis_dir: Vector
    centroid: Vector


def _cylindrical_faces(body: BodyShape) -> list[_CylFace]:
    """Every cylindrical face of *body*, with axis + radius from the B-rep."""
    out: list[_CylFace] = []
    for face in body.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        surf = BRepAdaptor_Surface(face.wrapped)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        cyl = surf.Cylinder()
        axis = cyl.Axis()
        loc = axis.Location()
        direction = axis.Direction()
        centroid = face.center(CenterOf.MASS)
        axis_dir = Vector(direction.X(), direction.Y(), direction.Z()).normalized()
        out.append(
            _CylFace(
                face=face,
                radius=float(cyl.Radius()),
                axis_origin=Vector(loc.X(), loc.Y(), loc.Z()),
                axis_dir=axis_dir,
                centroid=Vector(centroid.X, centroid.Y, centroid.Z),
            )
        )
    return out


def _axes_coincident(a: _CylFace, b: _CylFace) -> bool:
    """True if two cylindrical faces share the same axis LINE (concentric)."""
    if 1.0 - abs(a.axis_dir.dot(b.axis_dir)) > _PARALLEL_TOL:
        return False
    delta = b.axis_origin - a.axis_origin
    # Distance from b's origin to a's axis line = |delta - (delta·dir) dir|.
    along = a.axis_dir * delta.dot(a.axis_dir)
    perp = delta - along
    return perp.length <= _AXIS_COINCIDENT_TOL_MM


def _flanking_flanges(
    body: BodyShape, inner: _CylFace
) -> tuple[ResolvedFlange, ResolvedFlange]:
    """The two flat flanges tangent to the bend's INNER surface.

    A flange face is planar, parallel to the bend axis (``normal ⟂ axis_dir``),
    and tangent to the inner cylinder (its plane sits ``radius`` from the axis).
    Its **developed length** is its extent perpendicular to the axis — which runs
    exactly from the bend tangent line to the flange's free edge (§9 golden #1's
    tangent-line convention: the flat portion of a flange ends where it meets the
    arc, so the planar face's own length IS the leg developed to the tangent).
    """
    axis_dir = inner.axis_dir
    origin = inner.axis_origin
    flanges: list[ResolvedFlange] = []
    for face in body.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        centroid = face.center(CenterOf.MASS)
        normal = face.normal_at(centroid)
        if abs(normal.dot(axis_dir)) > _PERP_TOL:
            continue  # plane not parallel to the bend axis
        point = Vector(centroid.X, centroid.Y, centroid.Z)
        dist = abs((point - origin).dot(normal))
        if abs(dist - inner.radius) > _TANGENT_DIST_TOL_MM:
            continue  # not tangent to the INNER surface (skips outer flange faces)
        # In-plane direction perpendicular to the axis: developed-length axis.
        u = axis_dir.cross(normal).normalized()
        verts = [Vector(v.X, v.Y, v.Z) for v in face.vertices()]
        u_proj = [v.dot(u) for v in verts]
        w_proj = [v.dot(axis_dir) for v in verts]
        flanges.append(
            ResolvedFlange(
                developed_length_mm=max(u_proj) - min(u_proj),
                width_mm=max(w_proj) - min(w_proj),
                normal=(normal.X, normal.Y, normal.Z),
            )
        )
    if len(flanges) != 2:
        raise BendFlankingFacesError(
            f"Bend (radius {inner.radius:.4g} mm) is flanked by {len(flanges)} "
            "planar faces tangent to its inner surface; a v1 edge flange has "
            "exactly two flat flanges."
        )
    # Deterministic order: base flange (longer developed length) first, tie-broken
    # by outward normal so the layout origin never depends on face iteration order.
    flanges.sort(key=lambda f: (-f.developed_length_mm, f.normal))
    return flanges[0], flanges[1]


def _fold_angle(n1: Vec3f, n2: Vec3f) -> float:
    """Fold angle from the two flange outward normals.

    Flat (coplanar flanges) → parallel normals → 0; folded by θ → the edge
    flange's normal rotates θ off the base's → angle θ. This is the ``angle_rad``
    the bend allowance (§1) integrates. For axis-aligned faces the dot is exact
    (0.0 for a 90° fold → ``acos`` returns π/2 to full float precision).
    """
    dot = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
    return math.acos(max(-1.0, min(1.0, dot)))


def resolve_bends(body: BodyShape, thickness_mm: float) -> list[ResolvedBend]:
    """Resolve every bend region of a depth-1 sheet-metal bend star.

    Pairs concentric cylindrical faces whose radii differ by *thickness_mm* (the
    inner + outer surfaces of one bent sheet), takes the smaller radius as the
    **bend radius**, and resolves the two flat flanges the bend connects. The
    fold angle is the angle between the two flange normals (0 when flat, θ when
    folded by θ) — exact for axis-aligned faces.

    Raises:
        NoBendFoundError: no concentric cylinder pair with a thickness-matched
            radius gap (not a folded sheet, or a wrong *thickness_mm*).
        BendFlankingFacesError: a bend lacks exactly two tangent flat flanges.
    """
    cyls = _cylindrical_faces(body)
    bends: list[ResolvedBend] = []
    consumed: set[int] = set()
    for i, a in enumerate(cyls):
        if i in consumed:
            continue
        for j in range(i + 1, len(cyls)):
            if j in consumed:
                continue
            b = cyls[j]
            if not _axes_coincident(a, b):
                continue
            gap = abs(a.radius - b.radius)
            if abs(gap - thickness_mm) > _THICKNESS_REL_TOL * max(thickness_mm, 1.0):
                continue
            inner = a if a.radius < b.radius else b
            flanges = _flanking_flanges(body, inner)
            angle = _fold_angle(flanges[0].normal, flanges[1].normal)
            bends.append(
                ResolvedBend(
                    radius_mm=inner.radius,
                    angle_rad=angle,
                    bend_width_mm=flanges[0].width_mm,
                    axis_origin=(
                        inner.axis_origin.X,
                        inner.axis_origin.Y,
                        inner.axis_origin.Z,
                    ),
                    axis_dir=(inner.axis_dir.X, inner.axis_dir.Y, inner.axis_dir.Z),
                    centroid=(inner.centroid.X, inner.centroid.Y, inner.centroid.Z),
                    flanges=flanges,
                )
            )
            consumed.add(i)
            consumed.add(j)
            break
    if not bends:
        raise NoBendFoundError(
            "No sheet-metal bend region found: expected a concentric inner/outer "
            f"cylindrical face pair whose radii differ by the gauge thickness "
            f"({thickness_mm:.4g} mm). The body is not a folded sheet at this gauge."
        )
    return bends
