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
    shares_edge_with,
)

#: Span-extent tolerance class (documented, not ad-hoc — §9): relative linear
#: tolerance against the resolved edge length, the same ``1e-6 * max(L, 1)`` rule
#: :func:`_adjacent_faces` already applies to edge-length matching. Used to (a)
#: accept ``offset + width == edge_length`` up to FP, and (b) classify a span end
#: as INTERIOR (needing an auto bend-end relief, design §4.5.2) vs. a blank-corner
#: end at the edge's own endpoint (no relief).
_SPAN_TOL_REL = 1e-6
#: Post-notch base-face relocation tolerances (design §4.5.2): the notched base
#: flat is found on the FINAL body by (same-orientation normal, in-plane seam,
#: tangent-seam adjacency). Normal dot within 1e-9 (the resolve module's
#: ``_PERP_TOL`` class) and plane distance within 1e-7 mm (its
#: ``_TANGENT_DIST_TOL_MM`` class) — authored sheets are axis-aligned, residuals
#: are ulp-scale.
_BASE_NORMAL_TOL = 1e-9
_BASE_PLANE_TOL_MM = 1e-7


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
    width_mm: float | None = None,
    offset_mm: float = 0.0,
) -> EdgeFlangeResult:
    """Fold a flange off *edge* of the sheet *body* and fuse it across a bend.

    *edge* is a resolved STRAIGHT edge of *body* (the picked base-flange edge).
    The flange extends outward from the edge's larger adjacent flat (plate) face
    and folds by ``bend_angle_deg`` about a bend of inner radius ``bend_radius_mm``,
    developing a leg of ``flange_length_mm`` (to the bend tangent line). The gauge
    ``thickness_mm`` is the part's sheet thickness. Returns the fused single sheet
    body + the bend provenance signatures (§5).

    WIDTH EXTENTS (design §4.5): ``width_mm``/``offset_mm`` restrict the flange to
    the span ``[offset, offset + width]`` of the edge, measured from its CANONICAL
    start (the lexicographically smaller endpoint — the stored ``EdgeSignature``'s
    ``end_a``, so the offset's meaning never depends on kernel edge orientation).
    ``width_mm = None`` spans to the edge's end. Both absent (``None``/``0``) is
    the verbatim legacy full-width build — byte-identical geometry. Each span end
    INTERIOR to the edge gets an automatic rectangular bend-end relief notch cut
    into the base flat (size = 1 x gauge along the edge, 1 x gauge deep beyond the
    bend tangent line, through-thickness — §4.5.2); a blank-corner end gets none.

    Raises:
        EdgeFlangeEdgeError: *edge* is not a straight edge, or lacks a clean plate
            reference face to fold from.
        EdgeFlangeError: the width/offset span exceeds the resolved edge, the fold
            geometry is degenerate, or the fuse/relief produced other than one
            solid (e.g. a radius/length that self-intersects the sheet).
    """
    if edge.geom_type != GeomType.LINE:
        raise EdgeFlangeEdgeError(
            "An edge flange folds off a STRAIGHT edge; the picked edge is curved."
        )

    p0 = edge @ 0.0
    p1 = edge @ 1.0
    edge_len = float(edge.length)
    v = (p1 - p0).normalized()  # bend axis direction (along the edge)

    # Resolve the span [span0, span1] in the edge's NATIVE parameterisation. The
    # legacy full-width call keeps the exact legacy values (span0 = 0.0, width =
    # edge.length) so absent width params produce bitwise-identical geometry.
    span_tol = _SPAN_TOL_REL * max(edge_len, 1.0)
    if width_mm is None and offset_mm == 0.0:
        span0, span1 = 0.0, edge_len
    else:
        span_width = width_mm if width_mm is not None else edge_len - offset_mm
        if span_width <= span_tol or offset_mm + span_width > edge_len + span_tol:
            raise EdgeFlangeError(
                f"The flange width extents do not fit the picked edge: offset "
                f"{offset_mm:g} mm + width {span_width:g} mm exceeds the edge "
                f"length {edge_len:g} mm (design §4.5.1)."
            )
        # Canonical start = lexicographically smaller endpoint (EdgeSignature's
        # end_a convention); convert to native coordinates if the edge runs the
        # other way.
        if (p0.X, p0.Y, p0.Z) <= (p1.X, p1.Y, p1.Z):
            span0, span1 = offset_mm, offset_mm + span_width
        else:
            span0, span1 = edge_len - (offset_mm + span_width), edge_len - offset_mm
        span0 = max(span0, 0.0)
        span1 = min(span1, edge_len)
    width = span1 - span0

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

    # Cross-section origin: the span's native start on the edge line. The legacy
    # full-width path keeps `p0` itself (no `+ v * 0.0` arithmetic — byte-identity
    # of the committed goldens, §4.5.1).
    origin = p0 if span0 == 0.0 else p0 + v * span0

    def to3d(ab: tuple[float, float]) -> Vector:
        return origin + d * ab[0] + n * ab[1]

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

    # AUTO BEND-END RELIEF (design §4.5.2): a span end INTERIOR to the edge tears
    # the adjacent base flat when the fold is formed, so each interior end gets a
    # rectangular notch cut into the BASE beside the bend end — `size` wide along
    # the edge on the blank side of the end, `size` deep into the base beyond the
    # bend tangent line, through the full gauge, with size = 1 x thickness (the
    # corner-relief §4.4.3 gauge-multiple family at its tear-safe default ratio
    # 1.0). The notch never crosses the bend, so the live bend width stays the
    # authored span (fold-back invariant trivially intact) and the flat notch IS
    # the 3D notch. A blank-corner end (at the edge's own endpoint) needs none.
    relief_spans: list[tuple[float, float]] = []
    size = thickness_mm
    if span0 > span_tol:
        relief_spans.append((span0 - size, span0))
    if span1 < edge_len - span_tol:
        relief_spans.append((span1, span1 + size))
    if relief_spans:
        result_body = _cut_end_reliefs(result_body, relief_spans, p0, v, d, n, t)

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
    if relief_spans:
        # The end-relief notches changed the base flat's area/centroid, so the
        # legacy pre-fuse signature would no longer match at unfold time (§4.5.2).
        # Emit the signature from the FINAL body's base face, located by the bend's
        # tangent-seam adjacency + the reference plane (same orientation normal,
        # in-plane with the fold line) — never a guess.
        base_sig = _post_relief_base_signature(result_body, inner_face, n, p0)
    else:
        base_sig = face_signature_dto(reference)
        assert base_sig is not None, "reference face is planar"
    return EdgeFlangeResult(
        body=result_body,
        cyl_signature=cyl_signature,
        base_face_signature=base_sig,
    )


def _cut_end_reliefs(
    body: Solid,
    relief_spans: list[tuple[float, float]],
    p0: Vector,
    v: Vector,
    d: Vector,
    n: Vector,
    t: float,
) -> Solid:
    """Cut the auto bend-end relief notches into the base flat (design §4.5.2).

    Each *relief_spans* entry ``(s0, s1)`` is a native along-edge range (already
    ``size`` wide, on the blank side of an interior span end). The tool is the
    exact box spanning ``[s0, s1]`` along the edge axis *v*, ``[-size, 0]`` along
    the outward direction *d* (i.e. ``size`` INTO the base beyond the bend tangent
    line at the edge), and the full gauge ``[-t, 0]`` along the reference normal
    *n* — built as a rectangle in the (d, n) cross-section plane extruded along
    *v*, the same primitive the flange itself uses (no new kernel geometry). Exact
    (not oversized) so it can only ever remove base material: the flange/bend live
    at ``d > 0`` over the flange span, disjoint from the notch's along-edge range.

    Raises:
        EdgeFlangeError: the boolean failed, or a notch severed the sheet (other
            than exactly one solid — honest degradation, §5).
    """
    size = relief_spans[0][1] - relief_spans[0][0]
    try:
        cut = body
        for s0, _s1 in relief_spans:
            base_pt = p0 + v * s0
            corners = [
                base_pt,
                base_pt + d * -size,
                base_pt + d * -size + n * -t,
                base_pt + n * -t,
            ]
            tool_edges = [
                Edge.make_line(corners[0], corners[1]),
                Edge.make_line(corners[1], corners[2]),
                Edge.make_line(corners[2], corners[3]),
                Edge.make_line(corners[3], corners[0]),
            ]
            tool_wires = Wire.combine(tool_edges)
            if len(tool_wires) != 1 or not tool_wires[0].is_closed:
                raise EdgeFlangeError(
                    "The bend-end relief tool section did not close into one wire."
                )
            tool = Solid.extrude(Face(tool_wires[0]), v * size)
            cut = cut - tool
        cleaned = cut.clean()
    except EdgeFlangeError:
        raise
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise EdgeFlangeError(
            f"Bend-end relief boolean failed in the kernel ({type(exc).__name__})."
        ) from exc
    solids = cleaned.solids()
    if len(solids) != 1:
        raise EdgeFlangeError(
            f"Bend-end relief produced {len(solids)} solids; the notch must not "
            "sever the sheet (design §4.5.2)."
        )
    return solids[0]


def _post_relief_base_signature(
    body: Solid, inner_face: Face, n: Vector, p0: Vector
) -> PlanarFaceSignature:
    """The NOTCHED base flat's signature, located on the final body (§4.5.2).

    The base face is the unique planar face that (a) has the reference orientation
    (normal within ``_BASE_NORMAL_TOL`` of *n*, same sign), (b) lies in the
    reference plane (the plane through *p0* with normal *n* — the bend tangent
    plane, within ``_BASE_PLANE_TOL_MM``), and (c) shares a topological edge with
    the bend's inner cylindrical face (the tangent seam,
    :func:`geometry.sheet_metal.resolve.shares_edge_with`). Exactly one match or a
    typed error — the refuse-to-guess rule (§5)."""
    bend_edges = inner_face.edges()
    matches: list[Face] = []
    for face in body.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        centroid = face.center(CenterOf.MASS)
        normal = face.normal_at(centroid)
        if normal.dot(n) < 1.0 - _BASE_NORMAL_TOL:
            continue
        point = Vector(centroid.X, centroid.Y, centroid.Z)
        if abs((point - p0).dot(n)) > _BASE_PLANE_TOL_MM:
            continue
        if not shares_edge_with(face, bend_edges):
            continue
        matches.append(face)
    if len(matches) != 1:
        raise EdgeFlangeError(
            f"Expected exactly one notched base flat adjacent to the bend, found "
            f"{len(matches)}; the bend-end relief left an unresolvable base face."
        )
    sig = face_signature_dto(matches[0])
    assert sig is not None, "the notched base flat is planar"
    return sig


def _sig_key(face: Face) -> tuple[float, float, float]:
    """A deterministic tie-break key for a planar face (its centroid)."""
    c = face.center(CenterOf.MASS)
    return (float(c.X), float(c.Y), float(c.Z))
