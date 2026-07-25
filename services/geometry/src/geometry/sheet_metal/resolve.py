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
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import CenterOf, Edge, Face, GeomType, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from py_kit.schemas.features import CylindricalFaceSignature, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

from geometry.kernel.faces import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    face_signature_dto,
)
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
    """A bend cylinder was found but not exactly two planar faces adjacent AND
    tangent to its inner surface (the two flat flanges) — the bend geometry is
    unexpected for a v1 edge flange."""


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


def cylindrical_face_widths(body: BodyShape, radius_mm: float) -> list[float]:
    """The along-axis extents (mm) of *body*'s cylindrical faces at ``radius_mm``,
    sorted. A geometry query used to WITNESS a bend region's developed width straight
    off the folded body — e.g. the fold-back cross-consistency check that a corner
    relief shortened the 3D bend face by the same amount the flat pattern did. Radius
    is matched within the relative tolerance the signature matchers use, so the inner
    bend surface is selected and its concentric outer twin (``radius + thickness``)
    is skipped."""
    ref = max(abs(radius_mm), 1.0)
    widths: list[float] = []
    for cf in _cylindrical_faces(body):
        if abs(cf.radius - radius_mm) / ref > _RADIUS_REL_TOL:
            continue
        proj = [Vector(v.X, v.Y, v.Z).dot(cf.axis_dir) for v in cf.face.vertices()]
        widths.append(max(proj) - min(proj))
    return sorted(widths)


def bend_radii_match(a_mm: float, b_mm: float) -> bool:
    """True if two bend radii agree within the cylindrical-signature relative radius
    tolerance (``_RADIUS_REL_TOL``) — the ONE radius-grouping rule shared by the
    signature matchers and the runtime fold-back cross-check
    (:func:`geometry.sheet_metal.unfold.unfold_sheet_metal`), so a developed fold
    line groups with its live bend face exactly when the matchers would pair them."""
    return abs(a_mm - b_mm) / max(abs(a_mm), abs(b_mm), 1.0) <= _RADIUS_REL_TOL


def _axis_extent(cf: _CylFace) -> float:
    """The along-axis extent (mm) of a cylindrical face — its vertex projections on
    its OWN axis direction, max minus min. The one width measurement shared by the
    coaxial measurers so a face is measured identically however it is reached."""
    proj = [Vector(v.X, v.Y, v.Z).dot(cf.axis_dir) for v in cf.face.vertices()]
    return max(proj) - min(proj)


def _on_signature_axis(cf: _CylFace, signature: CylindricalFaceSignature) -> bool:
    """True if *cf* lies on the signature's axis LINE at its radius — centroid
    deliberately IGNORED (unlike :func:`_cyl_matches`).

    The axis-line + radius selection shared by the coaxial fold-back measurers
    (:func:`coaxial_cylindrical_face_widths` / :func:`live_bend_face_widths`): a
    face that a LATER feature (an ordinary cut) shortened or shifted ALONG its axis
    still matches (its centroid moved but its axis line + radius did not), so the
    fold-back check can MEASURE the modified fold rather than lose it. The same
    ``_PARALLEL_TOL`` / ``_AXIS_COINCIDENT_TOL_MM`` / ``_RADIUS_REL_TOL`` rules the
    signature matchers use keep unrelated cylinders — a drilled hole whose radius
    happens to equal the bend radius sits on a DIFFERENT axis — out of the match."""
    target_dir = Vector(
        signature.axis_dir.x, signature.axis_dir.y, signature.axis_dir.z
    ).normalized()
    if 1.0 - abs(cf.axis_dir.dot(target_dir)) > _PARALLEL_TOL:
        return False
    target_origin = Vector(
        signature.axis_origin.x, signature.axis_origin.y, signature.axis_origin.z
    )
    delta = target_origin - cf.axis_origin
    if _perp_distance(delta, cf.axis_dir) > _AXIS_COINCIDENT_TOL_MM:
        return False
    return bend_radii_match(cf.radius, signature.radius_mm)


def coaxial_cylindrical_face_widths(
    body: BodyShape, signature: CylindricalFaceSignature
) -> list[float]:
    """The along-axis extents (mm), sorted, of *body*'s cylindrical faces on the
    signature's axis LINE at its radius — centroid deliberately IGNORED.

    The single-bend measurement helper (§4.4.4 fold-back witness): finds a bend
    face a later cut shortened/shifted along its axis so the check MEASURES the
    modified fold instead of losing it (contrast :func:`resolve_cylindrical_face`,
    whose centroid term drops a trimmed bend). Zero matches (the fold was cut away
    entirely) is an empty list; a MULTI-face return means TWO COAXIAL bends share
    this axis line + radius — so the runtime fold-back check across *several* bends
    must not sum these per-signature lists (each returns every coaxial face, N^2
    over N collinear folds); it uses :func:`live_bend_face_widths`, which measures
    each distinct face ONCE. Both a zero and a multi-face return are honest
    mismatches for the caller to surface, never a guess."""
    return sorted(
        _axis_extent(cf)
        for cf in _cylindrical_faces(body)
        if _on_signature_axis(cf, signature)
    )


def live_bend_face_widths(
    body: BodyShape, signatures: Sequence[CylindricalFaceSignature]
) -> list[tuple[float, float]]:
    """``(radius_mm, along-axis width_mm)`` for each DISTINCT cylindrical bend face
    of *body* lying on ANY signature's axis LINE at its radius, measured ONCE.

    The live-body measurement arm of the runtime fold-back cross-check
    (:func:`geometry.sheet_metal.unfold._check_live_fold_back`, WF-1 code-review
    2026-07-22). Two distinct bends that share the SAME axis line AND radius — two
    edge flanges on COLLINEAR segments of one base edge (a notch-split edge, PB-1;
    or two tabs off one edge) — each match BOTH faces under the centroid-ignoring
    axis-line+radius selection, so calling :func:`coaxial_cylindrical_face_widths`
    once per signature double-counts (``[wA, wB, wA, wB]`` for two folds, an N^2
    count mismatch that FALSE-REJECTS a correctly-developed body). Deduping by
    TopoDS identity (``TopoDS_Shape.IsSame`` — NOT by width value, so two genuinely
    equal-width folds still count as two) measures each face exactly once: N coaxial
    equal-radius folds yield N widths. Centroid stays IGNORED (unlike
    :func:`resolve_cylindrical_face`) so a TRIMMED bend whose centroid shifted is
    still MEASURED — the WF-1 cut-after-fold reject depends on it. The faces are
    enumerated ONCE (:func:`_cylindrical_faces`) so identity comparisons are over a
    single wrapper set; the result is sorted for a deterministic, order-free return."""
    faces = _cylindrical_faces(body)
    unique: list[_CylFace] = []
    for signature in signatures:
        for cf in faces:
            if not _on_signature_axis(cf, signature):
                continue
            if not any(cf.face.wrapped.IsSame(u.face.wrapped) for u in unique):
                unique.append(cf)
    return sorted((cf.radius, _axis_extent(cf)) for cf in unique)


def shares_edge_with(face: Face, bend_edges: list[Edge]) -> bool:
    """True if *face* shares a topological edge with the bend's inner face.

    The flank test that makes bend resolution TOPOLOGICAL, not merely metric: a
    bend's two flat flanges are its NEIGHBOURS across the tangent seam lines (the
    sheet is one shell, so the parent flat, the bend cylinder, and the moving flat
    share those exact edges — ``TopoDS_Shape.IsSame`` identity, no tolerance). A
    face that is merely COPLANAR with a tangent plane of the cylinder — e.g. a
    perpendicular wall's end face lying exactly in the plane a hem's return leg
    folds onto (the TB-1 hemmed-tray dogfooding failure, BACKLOG 2026-07-20) —
    passes the metric tangency test but never this adjacency test, so it can no
    longer masquerade as a flange and inflate the flank count past two."""
    for edge in face.edges():
        for bend_edge in bend_edges:
            if edge.wrapped.IsSame(bend_edge.wrapped):
                return True
    return False


def _perp_distance(delta: Vector, axis_dir: Vector) -> float:
    """Distance from a point at offset *delta* to a line through the origin along
    *axis_dir* — ``|delta - (delta·dir) dir|``. The one place the axis-line
    perpendicular distance is computed (shared by the concentric test and both
    cylinder-signature matchers), so the coincidence rule lives once."""
    return (delta - axis_dir * delta.dot(axis_dir)).length


def _axes_coincident(a: _CylFace, b: _CylFace) -> bool:
    """True if two cylindrical faces share the same axis LINE (concentric)."""
    if 1.0 - abs(a.axis_dir.dot(b.axis_dir)) > _PARALLEL_TOL:
        return False
    delta = b.axis_origin - a.axis_origin
    return _perp_distance(delta, a.axis_dir) <= _AXIS_COINCIDENT_TOL_MM


def _flanking_flanges(
    body: BodyShape, inner: _CylFace
) -> tuple[ResolvedFlange, ResolvedFlange]:
    """The two flat flanges adjacent + tangent to the bend's INNER surface.

    A flange face is planar, parallel to the bend axis (``normal ⟂ axis_dir``),
    tangent to the inner cylinder (its plane sits ``radius`` from the axis), and
    **topologically adjacent** to the bend face (:func:`shares_edge_with` — it
    meets the cylinder at a tangent seam line; a face merely coplanar with a
    tangent plane is a bystander, never a flange).
    Its **developed length** is its extent perpendicular to the axis — which runs
    exactly from the bend tangent line to the flange's free edge (§9 golden #1's
    tangent-line convention: the flat portion of a flange ends where it meets the
    arc, so the planar face's own length IS the leg developed to the tangent).
    """
    axis_dir = inner.axis_dir
    origin = inner.axis_origin
    bend_edges = inner.face.edges()
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
        if not shares_edge_with(face, bend_edges):
            continue  # coplanar bystander, not a flange across a tangent seam
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
            "planar faces adjacent and tangent to its inner surface; a v1 edge "
            "flange has exactly two flat flanges."
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


# --- Provenance side (slice #3): emit + match a CylindricalFaceSignature ----------
#
# The unfold of an AUTHORED body is driven by PROVENANCE, not blind detection
# (docs/design/sheet-metal.md §2.2/§5): the edge-flange feature tags the bend's
# INNER cylindrical face with a :class:`CylindricalFaceSignature` at construction,
# and the unfold matches that signature back to the bend face on the rebuilt body.
# The match degrades to a typed ``subshape_unresolved``/``subshape_ambiguous``
# under a topology-changing edit, the SAME best-effort stage-1 posture the planar
# (:mod:`geometry.kernel.faces`) and edge (:mod:`geometry.kernel.edges`) signatures
# ship — no new mechanism beyond the one new signature type (§5).

#: Cylindrical-signature match tolerances (documented, NOT ad-hoc — §9). A bend
#: face is bit-identical on a clean rebuild, so residuals are ulp-scale; these are
#: tight enough that two distinct cylinders never collide, loose enough for jitter.
_RADIUS_REL_TOL = 1e-6  # relative radius difference
_CENTROID_TOL_MM = 1e-6  # Euclidean centroid distance (mm)


@dataclass(frozen=True)
class FlangeFaceRecord:
    """A resolved flanking flat face of a bend: its Face + signature + metrics.

    Richer than :class:`ResolvedFlange` (which carries only scalars): the unfold
    of a depth-1 bend STAR needs the actual planar :class:`Face` (to identify the
    shared base face by its :class:`PlanarFaceSignature`) plus each face's world
    ``centroid``/``normal`` (to lay flanges out on the correct side and infer the
    fold direction up/down)."""

    face: Face
    signature: PlanarFaceSignature
    developed_length_mm: float
    width_mm: float
    area_mm2: float
    normal: Vec3f
    centroid: Vec3f


@dataclass(frozen=True)
class ResolvedBendFaces:
    """A bend resolved BY PROVENANCE: its geometry + both flanking face records.

    The provenance sibling of :class:`ResolvedBend` — the unfold-of-authored-body
    (slice #3) analogue that keeps the flanking :class:`Face`s so a depth-1 star
    can separate the shared base from each moving flange and lay them out flat."""

    radius_mm: float
    angle_rad: float
    bend_width_mm: float
    axis_origin: Vec3f
    axis_dir: Vec3f
    centroid: Vec3f
    flanges: tuple[FlangeFaceRecord, FlangeFaceRecord]


def cylindrical_face_signature(face: Face) -> CylindricalFaceSignature:
    """Emit the :class:`CylindricalFaceSignature` (§5) of a cylindrical *face*.

    The EMIT side of bend provenance: reads the same ``BRepAdaptor_Surface``
    axis/radius :func:`_cylindrical_faces` extracts, plus the face's area centroid,
    into the kernel-free boundary DTO. Raises if *face* is not cylindrical (a
    caller bug — the edge-flange feature only tags the bend faces it creates)."""
    surf = BRepAdaptor_Surface(face.wrapped)
    if surf.GetType() != GeomAbs_Cylinder:
        raise NoBendFoundError(
            "cylindrical_face_signature called on a non-cylindrical face; only a "
            "bend region's cylindrical face carries this provenance signature."
        )
    cyl = surf.Cylinder()
    axis = cyl.Axis()
    loc = axis.Location()
    direction = axis.Direction()
    axis_dir = Vector(direction.X(), direction.Y(), direction.Z()).normalized()
    centroid = face.center(CenterOf.MASS)
    return CylindricalFaceSignature(
        axis_origin=Vec3(x=loc.X(), y=loc.Y(), z=loc.Z()),
        axis_dir=Vec3(x=axis_dir.X, y=axis_dir.Y, z=axis_dir.Z),
        radius_mm=float(cyl.Radius()),
        centroid=Vec3(x=centroid.X, y=centroid.Y, z=centroid.Z),
    )


def _cyl_matches(candidate: _CylFace, target: CylindricalFaceSignature) -> bool:
    """Nearest-within-tolerance match of a cylindrical face to a stored signature.

    Same axis LINE (parallel direction + coincident line), radius within a
    relative tolerance, and centroid within the linear tolerance — field by field
    so a lone in-tolerance candidate is unique and two are an honest ambiguity."""
    target_dir = Vector(
        target.axis_dir.x, target.axis_dir.y, target.axis_dir.z
    ).normalized()
    if 1.0 - abs(candidate.axis_dir.dot(target_dir)) > _PARALLEL_TOL:
        return False
    target_origin = Vector(
        target.axis_origin.x, target.axis_origin.y, target.axis_origin.z
    )
    delta = target_origin - candidate.axis_origin
    if _perp_distance(delta, candidate.axis_dir) > _AXIS_COINCIDENT_TOL_MM:
        return False
    radius_ref = max(abs(target.radius_mm), 1.0)
    if abs(candidate.radius - target.radius_mm) / radius_ref > _RADIUS_REL_TOL:
        return False
    centroid_dist = math.dist(
        (candidate.centroid.X, candidate.centroid.Y, candidate.centroid.Z),
        (target.centroid.x, target.centroid.y, target.centroid.z),
    )
    return centroid_dist <= _CENTROID_TOL_MM


def resolve_cylindrical_face(
    body: BodyShape, signature: CylindricalFaceSignature
) -> _CylFace:
    """Match a stored :class:`CylindricalFaceSignature` to ONE cylindrical face.

    The MATCH side of bend provenance (§5): exactly one cylindrical face of *body*
    within tolerance, or an honest error — the same refuse-to-guess rule the
    planar/edge resolvers follow.

    Raises:
        SubshapeUnresolvedError: no cylindrical face matches (a topology-changing
            edit moved/removed the bend face — a dangling bend, surfaced).
        SubshapeAmbiguousError: two or more match (a congruent twin bend).
    """
    matches = [c for c in _cylindrical_faces(body) if _cyl_matches(c, signature)]
    if not matches:
        raise SubshapeUnresolvedError(
            "No cylindrical face of the current body matches the stored bend "
            "signature (axis / radius / centroid); the bend region no longer "
            "exists after the rebuild. The flat pattern cannot resolve this bend."
        )
    if len(matches) > 1:
        raise SubshapeAmbiguousError(
            f"{len(matches)} cylindrical faces match the stored bend signature "
            "within tolerance; the bend reference is ambiguous. Refusing to guess."
        )
    return matches[0]


def _flanking_face_records(
    body: BodyShape, inner: _CylFace
) -> tuple[FlangeFaceRecord, FlangeFaceRecord]:
    """The two flat flanges of a bend, as full :class:`FlangeFaceRecord`s.

    The provenance-unfold sibling of :func:`_flanking_flanges`: same adjacent +
    tangent-to-inner-surface selection (:func:`shares_edge_with` keeps coplanar
    bystanders — e.g. a perpendicular wall's end face in a hem's return plane —
    out of the flank count), but keeps each :class:`Face` + its
    :class:`PlanarFaceSignature` + world centroid so the star unfold can identify
    the shared base face and lay flanges out on the correct side."""
    axis_dir = inner.axis_dir
    origin = inner.axis_origin
    bend_edges = inner.face.edges()
    records: list[FlangeFaceRecord] = []
    for face in body.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        centroid = face.center(CenterOf.MASS)
        normal = face.normal_at(centroid)
        if abs(normal.dot(axis_dir)) > _PERP_TOL:
            continue
        point = Vector(centroid.X, centroid.Y, centroid.Z)
        dist = abs((point - origin).dot(normal))
        if abs(dist - inner.radius) > _TANGENT_DIST_TOL_MM:
            continue
        if not shares_edge_with(face, bend_edges):
            continue
        u = axis_dir.cross(normal).normalized()
        verts = [Vector(v.X, v.Y, v.Z) for v in face.vertices()]
        u_proj = [v.dot(u) for v in verts]
        w_proj = [v.dot(axis_dir) for v in verts]
        signature = face_signature_dto(face)
        assert signature is not None, "a planar face always has a signature"
        records.append(
            FlangeFaceRecord(
                face=face,
                signature=signature,
                developed_length_mm=max(u_proj) - min(u_proj),
                width_mm=max(w_proj) - min(w_proj),
                area_mm2=float(face.area),
                normal=(normal.X, normal.Y, normal.Z),
                centroid=(centroid.X, centroid.Y, centroid.Z),
            )
        )
    if len(records) != 2:
        raise BendFlankingFacesError(
            f"Bend (radius {inner.radius:.4g} mm) is flanked by {len(records)} "
            "planar faces adjacent and tangent to its inner surface; a v1 edge "
            "flange has exactly two flat flanges."
        )
    records.sort(key=lambda f: (-f.developed_length_mm, f.normal))
    return records[0], records[1]


#: Along-axis span-match tolerance (mm) — documented, NOT ad-hoc (§9). The
#: constructed bend face's along-axis extent is the flange's authored span to FP
#: (same ``p0``/``v``/``span`` the geometry was extruded from), so residuals are
#: ulp-scale; loose enough for fuse/clean vertex jitter, far tighter than the gap
#: between two collinear flanges' spans on one edge.
_SPAN_MATCH_TOL_MM = 1e-6


def find_cylindrical_face(
    body: BodyShape,
    axis_origin: Vec3f,
    axis_dir: Vec3f,
    radius_mm: float,
    axis_span: tuple[float, float] | None = None,
) -> Face:
    """The one cylindrical face of *body* on a KNOWN axis line at a known radius.

    Used at edge-flange construction time to locate the bend's inner cylindrical
    face (whose axis + radius the feature computed exactly) so its
    :class:`CylindricalFaceSignature` can be emitted. Exactly one or a raise (a
    construction invariant — the feature just created this face).

    *axis_span* — the constructed bend face's expected ``(min, max)`` projection on
    ``axis_dir`` (world mm) — disambiguates COAXIAL equal-radius bends: two edge
    flanges on collinear segments of one base edge (a notch-split edge, PB-1) share
    the SAME axis line AND radius, so axis+radius alone matches BOTH the earlier
    flange's bend and the one just built (WF-1 code-review 2026-07-22). The span
    (an exact closed form from the flange's ``[span0, span1]``) selects the face
    whose own along-axis extent matches, so the second collinear flange resolves to
    ITS bend, not the first's. Only applied when more than one candidate matches
    (single-bend construction is the verbatim legacy path — committed goldens
    byte-unchanged); omitted (``None``) keeps the strict exactly-one contract."""
    want_dir = Vector(*axis_dir).normalized()
    want_origin = Vector(*axis_origin)
    radius_ref = max(abs(radius_mm), 1.0)
    matches: list[_CylFace] = []
    for cand in _cylindrical_faces(body):
        if 1.0 - abs(cand.axis_dir.dot(want_dir)) > _PARALLEL_TOL:
            continue
        delta = want_origin - cand.axis_origin
        if _perp_distance(delta, cand.axis_dir) > _AXIS_COINCIDENT_TOL_MM:
            continue
        if abs(cand.radius - radius_mm) / radius_ref > _RADIUS_REL_TOL:
            continue
        matches.append(cand)
    if len(matches) > 1 and axis_span is not None:
        lo, hi = min(axis_span), max(axis_span)
        matches = [c for c in matches if _axis_span_matches(c, want_dir, lo, hi)]
    if len(matches) != 1:
        raise NoBendFoundError(
            f"Expected exactly one cylindrical face on the constructed bend axis "
            f"at radius {radius_mm:.4g} mm, found {len(matches)}."
        )
    return matches[0].face


def _axis_span_matches(cf: _CylFace, want_dir: Vector, lo: float, hi: float) -> bool:
    """True if *cf*'s vertex extent along *want_dir* matches ``[lo, hi]`` (mm).

    Projects onto the CALLER's ``want_dir`` (not ``cf.axis_dir``, which OCCT may
    orient oppositely) so the compared range is sign-consistent with the expected
    span the feature computed from ``p0``/``v``/``span``."""
    proj = [Vector(v.X, v.Y, v.Z).dot(want_dir) for v in cf.face.vertices()]
    return (
        abs(min(proj) - lo) <= _SPAN_MATCH_TOL_MM
        and abs(max(proj) - hi) <= _SPAN_MATCH_TOL_MM
    )


def resolve_bend_faces(body: BodyShape, inner: _CylFace) -> ResolvedBendFaces:
    """Resolve a bend's full geometry + flanking face records from its inner face."""
    flanges = _flanking_face_records(body, inner)
    angle = _fold_angle(flanges[0].normal, flanges[1].normal)
    return ResolvedBendFaces(
        radius_mm=inner.radius,
        angle_rad=angle,
        bend_width_mm=flanges[0].width_mm,
        axis_origin=(inner.axis_origin.X, inner.axis_origin.Y, inner.axis_origin.Z),
        axis_dir=(inner.axis_dir.X, inner.axis_dir.Y, inner.axis_dir.Z),
        centroid=(inner.centroid.X, inner.centroid.Y, inner.centroid.Z),
        flanges=flanges,
    )
