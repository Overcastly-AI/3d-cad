"""The sheet-metal unfold (SPIKE 0) — folded body → :class:`FlatPattern`.

This is the pillar's genuine kernel risk (docs/design/sheet-metal.md §2): OCCT
ships no turnkey unfold, so we build it. SPIKE 0 proves the simplest real case
end-to-end — an **L-bracket** (a base flange + ONE edge flange folded 90°) —
before the feature schema is committed.

Algorithm (§6, scoped to a depth-1 bend star — every bend folds directly off
the fixed base flange, so no graph relaxation is needed, §4.3):

1. Resolve each bend region (:mod:`geometry.sheet_metal.resolve`): its inner
   cylindrical face (radius, axis) + the two flat flanges it connects, each
   flange's developed length measured to the bend **tangent line** (§9 #1).
2. Compute the **bend allowance** ``BA = angle_rad * (radius + K * thickness)``
   (§1) — the flat length that replaces the two setback segments a sharp-corner
   unfold would use (the neutral-axis math is precisely why the flat blank is
   dimensionally different from a naive projection).
3. Lay the developed flanges + BA strips out flat and emit the outline + tagged
   bend lines as a :class:`FlatPattern`.

**Spike scope:** SPIKE 0 targets the single-bend L-bracket, where the developed
blank is a rectangle and ``flat_length = leg1_dev + BA + leg2_dev`` is a single
scalar along the fold-perpendicular axis. A general depth-1 star with N ≥ 2
edge flanges develops into a 2D outline with N legs radiating from the base;
that layout is the feature slice's work — this spike proves the bend math + the
OCCT resolution the star reuses per-bend. :func:`unfold_l_bracket` raises if the
body is not a single-bend bracket, keeping the spike honest about its scope.

The provenance star layout uses build123d ``Vector`` (the OCP wheel ships no type
stubs), opaque to pyright; the directives scope that relaxation to this file only,
and the typed DTOs at the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

import math
from dataclasses import dataclass
from typing import Literal, cast

from build123d import Vector
from py_kit.schemas.features import CylindricalFaceSignature, PlanarFaceSignature

from geometry.kernel.faces import planar_signatures_match
from geometry.kernel.types import BodyShape
from geometry.sheet_metal.flat_pattern import BendLine, FlatEdge2D, FlatPattern
from geometry.sheet_metal.resolve import (
    FlangeFaceRecord,
    SheetMetalUnfoldError,
    resolve_bend_faces,
    resolve_bends,
    resolve_cylindrical_face,
)

#: Star-layout tolerance (documented, not ad-hoc — §9). Faces of an authored
#: sheet are axis-aligned, so residuals are ulp-scale. Cylinder-axis-specific
#: (not in faces.py); the planar-face match tolerances live once in
#: :mod:`geometry.kernel.faces` and are applied via :func:`planar_signatures_match`.
_PARALLEL_TOL = 1e-9  # 1 - |dot| between unit axis directions
#: Axis-alignment tolerance for the non-parallel (2D) layout: a bend axis or a
#: base edge must be parallel/perpendicular to the base rectangle frame to within
#: this |dot| residual. Authored sheets are axis-aligned, so residuals are
#: ulp-scale; loose enough to absorb kernel jitter, tight enough that an angled
#: flange is an honest out-of-scope raise, never a silently mislaid arm.
_ALIGN_TOL = 1e-7


class UnfoldScopeError(SheetMetalUnfoldError):
    """The body is outside SPIKE 0's single-bend L-bracket scope."""


class UnfoldStarError(SheetMetalUnfoldError):
    """The body is outside the v1 depth-1 bend-star unfold scope
    (docs/design/sheet-metal.md §4.3). v1 unfolds a depth-1 star of edge flanges
    folded directly off ONE fixed base flange, either all-parallel (L-bracket /
    U-channel — a 1D strip) or non-parallel off a **rectangular** base (a tray /
    pan — a 2D plus/cross). Still outside scope and raised here: a non-rectangular
    or angled base, a bend axis not aligned to the base rectangle, or depth >= 2
    (a flange folded off ANOTHER flange — a box corner, the real graph-relaxation
    problem, deferred)."""


def bend_allowance(
    angle_rad: float, radius_mm: float, k_factor: float, thickness_mm: float
) -> float:
    """The bend allowance ``BA = angle_rad * (radius + K * thickness)`` (§1).

    The neutral axis sits ``K * thickness`` from the INNER bend face (§9's pinned
    convention); ``BA`` is the developed length of the bent arc measured along
    that neutral surface. Four-term closed form, no numeric dependency (§7).
    """
    return angle_rad * (radius_mm + k_factor * thickness_mm)


def unfold_l_bracket(
    body: BodyShape, thickness_mm: float, k_factor: float
) -> FlatPattern:
    """Unfold a single-bend L-bracket into its :class:`FlatPattern` (SPIKE 0).

    Resolves the one bend geometrically (:func:`resolve_bends`), computes its
    bend allowance, and develops the base + edge flanges flat with the bend
    region replaced by a ``BA``-length strip. The output is byte-deterministic
    (§9 #4): every value flows from a deterministic OCCT measurement + the
    closed-form allowance.

    Raises:
        NoBendFoundError / BendFlankingFacesError: the body is not a folded sheet
            at *thickness_mm* (from :func:`resolve_bends`).
        UnfoldScopeError: the body has other than exactly one bend (SPIKE 0 is
            the L-bracket; multi-bend stars are the feature slice).
    """
    bends = resolve_bends(body, thickness_mm)
    if len(bends) != 1:
        raise UnfoldScopeError(
            f"SPIKE 0 unfolds a single-bend L-bracket; found {len(bends)} bends. "
            "Multi-bend depth-1 stars are the feature slice (§4.3)."
        )
    bend = bends[0]
    base, edge = bend.flanges  # base = longer developed leg (deterministic, §resolve)

    ba = bend_allowance(bend.angle_rad, bend.radius_mm, k_factor, thickness_mm)
    width = bend.bend_width_mm
    leg1 = base.developed_length_mm
    leg2 = edge.developed_length_mm

    flat_length = leg1 + ba + leg2
    # §9 golden #2: developed area conserves the neutral surface — flange flats
    # unchanged + the bend strip is BA * width. Equivalently flat_length * width
    # for this rectangular blank; written as the sum to mirror the invariant.
    flat_area = (leg1 * width) + (leg2 * width) + (ba * width)

    # Developed (u, v) frame: u along the fold-perpendicular axis, v the width.
    # Bend strip occupies u ∈ [leg1, leg1 + BA]; fold centerline at its midpoint.
    bend_u0 = leg1
    bend_u1 = leg1 + ba
    cu = leg1 + ba / 2.0  # fold centerline in the developed frame

    fl = flat_length
    outline: tuple[FlatEdge2D, ...] = (
        FlatEdge2D(kind="line", x1=0.0, y1=0.0, x2=fl, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=0.0, x2=fl, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=width, x2=0.0, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=0.0, y1=width, x2=0.0, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=cu, y1=0.0, x2=cu, y2=width, role="bend"),
    )

    bend_line = BendLine(
        bend_id="bend-1",
        angle_deg=math.degrees(bend.angle_rad),
        radius_mm=bend.radius_mm,
        k_factor=k_factor,
        allowance_mm=ba,
        width_mm=width,
        # SPIKE 0: a single 90° up-fold; up/down inference from face orientation
        # is a feature-slice detail (needs the base-flange provenance to know
        # which side is "material up"). Pinned "up" here, noted in the report.
        direction="up",
        flat_start_mm=bend_u0,
        flat_end_mm=bend_u1,
    )

    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=k_factor,
        flat_length_mm=flat_length,
        flat_area_mm2=flat_area,
        bend_width_mm=width,
        outline=outline,
        bends=(bend_line,),
    )


# --- Provenance-driven unfold of an AUTHORED body (slice #3) ----------------------
#
# The spike's :func:`unfold_l_bracket` blind-resolves ONE bend. Slice #3 wires the
# proven unfold to REAL user-authored geometry (docs/design/sheet-metal.md §6): a
# base flange + N edge flanges, each bend tagged with a CylindricalFaceSignature at
# construction (§5), unfolded by PROVENANCE (find each bend face by its signature),
# not blind detection. v1 scope is a depth-1 PARALLEL bend star (§4.3) — every
# bend folds directly off the fixed base along a parallel axis, covering the
# L-bracket (N=1) and U-channel (N=2). A bend whose signature no longer resolves is
# an honest ``subshape_unresolved`` (via :func:`resolve_cylindrical_face`), never a
# wrong flat pattern.


@dataclass(frozen=True)
class BendProvenance:
    """One bend's construction-time provenance (§5): the cylindrical bend face's
    signature, the base flange face's signature (to separate base from the moving
    flange), and the bend's K-factor (inherited or overridden per-feature)."""

    cyl_signature: CylindricalFaceSignature
    base_face_signature: PlanarFaceSignature
    k_factor: float


@dataclass(frozen=True)
class _StarBend:
    """A resolved star bend, ready to lay out flat."""

    radius_mm: float
    angle_rad: float
    width_mm: float
    k_factor: float
    allowance_mm: float
    moving_leg_mm: float
    moving_area_mm2: float
    u_position: float  # moving flange centroid, projected on the layout u-axis
    side: int  # +1 extends +u beyond the base, -1 extends -u
    direction: Literal["up", "down"]  # fold sense relative to the base normal


def unfold_sheet_metal(
    body: BodyShape,
    bends: list[BendProvenance],
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Unfold an authored depth-1 parallel bend star into its :class:`FlatPattern`.

    Resolves each bend by its :class:`CylindricalFaceSignature` (§5), separates the
    shared base flange from each moving flange by the base face signature, and lays
    the developed blank out flat: the base flange in the middle, each flange folded
    down onto its side with the cylindrical bend region replaced by a bend-allowance
    strip (``BA = angle_rad * (radius + K * thickness)``, §1). Byte-deterministic
    (§9 #4): every value flows from a deterministic OCCT measurement + closed form.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (a dangling bend — §5 honest degradation).
        UnfoldStarError: the bends do not form a depth-1 PARALLEL star, or share no
            single base flange face (outside v1 scope).
    """
    if not bends:
        raise UnfoldStarError("An unfold needs at least one bend (edge flange).")

    # Resolve each bend ONCE by provenance: cylindrical face → geometry + flanges,
    # then separate the shared base from the moving flange by the base signature.
    # Each entry: (base_face, moving_face, axis_dir Vector, angle_rad, provenance).
    resolved = []
    for prov in bends:
        inner = resolve_cylindrical_face(body, prov.cyl_signature)
        rbf = resolve_bend_faces(body, inner)
        base_rec, moving_rec = _split_base_moving(rbf.flanges, prov.base_face_signature)
        axis_dir = Vector(*rbf.axis_dir).normalized()
        resolved.append((base_rec, moving_rec, axis_dir, rbf.angle_rad, prov))

    # The base flange is SHARED across every bend; take it from the first.
    base_rec = resolved[0][0]
    base_normal = Vector(*base_rec.normal).normalized()

    # A depth-1 star is PARALLEL (all bend axes share one direction → a 1D strip,
    # the L-bracket / U-channel) or NON-PARALLEL (flanges off perpendicular edges
    # of a rectangular base → a 2D plus/cross, a tray / pan). Both flatten each
    # flange independently against the fixed base (no graph relaxation, §4.3); they
    # differ only in the layout dimensionality. The parallel path is kept verbatim
    # so its committed goldens stay byte-identical.
    v0 = resolved[0][2]
    all_parallel = all(
        1.0 - abs(v0.dot(axis_dir)) <= _PARALLEL_TOL
        for _b, _m, axis_dir, _a, _p in resolved[1:]
    )
    if all_parallel:
        return _unfold_parallel(
            resolved, base_rec, base_normal, thickness_mm, default_k_factor
        )
    return _unfold_nonparallel(
        resolved, base_rec, base_normal, thickness_mm, default_k_factor
    )


#: Type alias for a resolved bend: (base_rec, moving_rec, axis_dir, angle_rad, prov).
_Resolved = tuple[FlangeFaceRecord, FlangeFaceRecord, Vector, float, BendProvenance]
#: A 2D outline segment in frame coords: (x1, y1, x2, y2, role).
_Seg = tuple[float, float, float, float, str]


def _unfold_parallel(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    base_normal: Vector,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Lay out an all-parallel depth-1 star as a 1D strip (L-bracket / U-channel).

    Kept verbatim from the v1 parallel implementation so its committed goldens
    stay byte-identical: v = the common bend axis, u ⟂ v in the base plane, and
    every flange projects onto u to a side of the fixed base."""
    v0 = resolved[0][2]
    u_axis = v0.cross(base_normal).normalized()

    def proj_u(centroid: tuple[float, float, float]) -> float:
        return centroid[0] * u_axis.X + centroid[1] * u_axis.Y + centroid[2] * u_axis.Z

    base_center_u = proj_u(base_rec.centroid)
    base_len = base_rec.developed_length_mm

    star_bends: list[_StarBend] = []
    for _base_rec, moving_rec, _axis, angle_rad, prov in resolved:
        radius = prov.cyl_signature.radius_mm
        ba = bend_allowance(angle_rad, radius, prov.k_factor, thickness_mm)
        um = proj_u(moving_rec.centroid)
        # Fold sense: the moving flange centroid on the +normal side is "up".
        along_n = (
            (moving_rec.centroid[0] - base_rec.centroid[0]) * base_normal.X
            + (moving_rec.centroid[1] - base_rec.centroid[1]) * base_normal.Y
            + (moving_rec.centroid[2] - base_rec.centroid[2]) * base_normal.Z
        )
        star_bends.append(
            _StarBend(
                radius_mm=radius,
                angle_rad=angle_rad,
                width_mm=moving_rec.width_mm,
                k_factor=prov.k_factor,
                allowance_mm=ba,
                moving_leg_mm=moving_rec.developed_length_mm,
                moving_area_mm2=moving_rec.area_mm2,
                u_position=um,
                side=1 if um > base_center_u else -1,
                direction="up" if along_n >= 0.0 else "down",
            )
        )

    return _lay_out_star(
        star_bends,
        base_len=base_len,
        base_area=base_rec.area_mm2,
        base_width=base_rec.width_mm,
        thickness_mm=thickness_mm,
        default_k_factor=default_k_factor,
    )


def _split_base_moving(
    flanges: tuple[FlangeFaceRecord, FlangeFaceRecord],
    base_sig: PlanarFaceSignature,
) -> tuple[FlangeFaceRecord, FlangeFaceRecord]:
    """(base, moving) — the flange matching *base_sig* is the base, the other moves."""
    a, b = flanges
    if planar_signatures_match(a.signature, base_sig):
        return a, b
    if planar_signatures_match(b.signature, base_sig):
        return b, a
    raise UnfoldStarError(
        "Neither flanking face of a bend matches the stored base-flange face "
        "signature; the bend is not a depth-1 flange off the recorded base (§4.3)."
    )


def _lay_out_star(
    star_bends: list[_StarBend],
    *,
    base_len: float,
    base_area: float,
    base_width: float,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Develop the base + flanges into a flat rectangular blank + tagged bend lines.

    Deterministic order: left (-u) bends outermost-first, then the base, then right
    (+u) bends nearest-first -- a pure function of each bend's u-position (RESEARCH
    §9). For the v1 parallel star with full-width flanges the blank is a rectangle
    (flat_length by base_width); each bend contributes one fold line."""
    left = sorted((b for b in star_bends if b.side < 0), key=lambda b: b.u_position)
    right = sorted((b for b in star_bends if b.side > 0), key=lambda b: b.u_position)

    width = base_width
    bend_lines: list[BendLine] = []
    fold_centers: list[float] = []
    u = 0.0
    index = 0

    def add_bend(b: _StarBend, strip_start: float) -> None:
        nonlocal index
        index += 1
        strip_end = strip_start + b.allowance_mm
        fold_centers.append(strip_start + b.allowance_mm / 2.0)
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{index}",
                angle_deg=math.degrees(b.angle_rad),
                radius_mm=b.radius_mm,
                k_factor=b.k_factor,
                allowance_mm=b.allowance_mm,
                width_mm=b.width_mm,
                direction=b.direction,
                flat_start_mm=strip_start,
                flat_end_mm=strip_end,
            )
        )

    # Left flanges: [flange leg][BA strip] then the base.
    for b in left:
        u += b.moving_leg_mm
        add_bend(b, u)
        u += b.allowance_mm
    # Base flange.
    u += base_len
    # Right flanges: [BA strip][flange leg].
    for b in right:
        add_bend(b, u)
        u += b.allowance_mm + b.moving_leg_mm

    flat_length = u
    flat_area = base_area + sum(
        b.moving_area_mm2 + b.allowance_mm * b.width_mm for b in star_bends
    )

    fl = flat_length
    outline: list[FlatEdge2D] = [
        FlatEdge2D(kind="line", x1=0.0, y1=0.0, x2=fl, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=0.0, x2=fl, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=width, x2=0.0, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=0.0, y1=width, x2=0.0, y2=0.0, role="body"),
    ]
    for cu in fold_centers:
        outline.append(
            FlatEdge2D(kind="line", x1=cu, y1=0.0, x2=cu, y2=width, role="bend")
        )

    # Deterministic bend-table order: by fold-line position along u.
    ordered = sorted(
        bend_lines, key=lambda bl: (bl.flat_start_mm + bl.flat_end_mm) / 2.0
    )

    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=flat_length,
        flat_area_mm2=flat_area,
        bend_width_mm=width,
        outline=tuple(outline),
        bends=tuple(ordered),
    )


# --- Non-parallel depth-1 star (sheet-metal v2 #1) — a 2D plus/cross layout ------
#
# A depth-1 star whose bend axes are NOT all parallel (a tray / pan: a base + N
# edge flanges off perpendicular edges) lays out in 2D, not along a single strip:
# each flange swings flat about its OWN bend axis into the base plane, extending
# OUTWARD along its own edge's direction. Because every flange folds independently
# off the FIXED base (depth 1, §4.3), each arm is placed analytically against the
# base rectangle with no graph relaxation — the same closed-form bend allowance,
# now positioned in the plane instead of on a line. The blank is a plus/cross with
# reentrant corners where perpendicular arms meet; those corners are disjoint in
# 2D (each arm occupies its own cardinal quadrant of the plane) and the built 3D
# body has exactly-additive volume (verified), so shared-corner flanges are IN
# scope — corner reliefs stay a documented deferral (§7). v1 scopes the base to a
# RECTANGLE with axis-aligned bends (a tray); a non-rectangular / angled base is
# an honest UnfoldStarError.


def _canonical_dir(v: Vector) -> Vector:
    """A sign-canonical unit direction: flip so the largest-magnitude component is
    positive (deterministic frame axis, independent of edge/vertex orientation)."""
    comps = sorted(((abs(v.X), 0), (abs(v.Y), 1), (abs(v.Z), 2)))
    idx = comps[-1][1]
    comp = (v.X, v.Y, v.Z)[idx]
    return v if comp >= 0.0 else v * -1.0


@dataclass(frozen=True)
class _BaseFrame:
    """A rectangular base flange's in-plane 2D frame: two perpendicular unit axes
    (world) + the min-corner offsets so any base point projects into ``[0, wx] x
    [0, wy]``. The layout origin never depends on face iteration order."""

    x2: Vector
    y2: Vector
    normal: Vector
    x_min: float
    y_min: float
    wx: float
    wy: float

    def to2d(self, p: tuple[float, float, float]) -> tuple[float, float]:
        v = Vector(*p)
        return (v.dot(self.x2) - self.x_min, v.dot(self.y2) - self.y_min)


def _base_frame(base_rec: FlangeFaceRecord) -> _BaseFrame:
    """Deterministic 2D frame of a RECTANGULAR base face (v1 non-parallel scope).

    Raises UnfoldStarError if the base has other than two perpendicular edge
    directions (a non-rectangular or angled base is out of scope)."""
    normal = _canonical_dir(Vector(*base_rec.normal).normalized())
    dirs: list[Vector] = []
    for edge in base_rec.face.edges():
        delta = (edge @ 1.0) - (edge @ 0.0)
        if delta.length < 1e-9:
            continue
        d = _canonical_dir(delta.normalized())
        if not any(1.0 - abs(d.dot(x)) <= _ALIGN_TOL for x in dirs):
            dirs.append(d)
    if len(dirs) != 2:
        raise UnfoldStarError(
            f"The non-parallel unfold requires a RECTANGULAR base flange; its face "
            f"has {len(dirs)} distinct edge directions. A non-rectangular / angled "
            "base is a documented next increment (§4.3)."
        )
    dirs.sort(key=lambda d: (round(d.X, 9), round(d.Y, 9), round(d.Z, 9)))
    x2, y2 = dirs[0], dirs[1]
    if abs(x2.dot(y2)) > _ALIGN_TOL:
        raise UnfoldStarError(
            "The base flange's edge directions are not perpendicular; v1's "
            "non-parallel unfold scopes to a rectangular base (§4.3)."
        )
    verts = [Vector(v.X, v.Y, v.Z) for v in base_rec.face.vertices()]
    px = [v.dot(x2) for v in verts]
    py = [v.dot(y2) for v in verts]
    return _BaseFrame(
        x2=x2,
        y2=y2,
        normal=normal,
        x_min=min(px),
        y_min=min(py),
        wx=max(px) - min(px),
        wy=max(py) - min(py),
    )


@dataclass(frozen=True)
class _Arm:
    """One flange laid out flat as an axis-aligned arm off a base-rectangle side.

    ``axis`` 0 = the arm extends along the frame X axis, 1 = along Y; ``sign`` is
    its outward direction. ``span`` is the arm's extent along the fold edge (the
    base-edge direction). ``fold`` is the fold-edge coordinate (0 or wx/wy)."""

    axis: int
    sign: int
    fold: float
    span0: float
    span1: float
    allowance_mm: float
    leg_mm: float
    area_mm2: float
    width_mm: float
    radius_mm: float
    angle_rad: float
    k_factor: float
    direction: Literal["up", "down"]


def _unfold_nonparallel(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    base_normal: Vector,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Lay out a NON-PARALLEL depth-1 star (a tray / pan) as a 2D plus/cross.

    Each flange is placed as an axis-aligned arm off its base-rectangle side, the
    cylindrical bend replaced by a ``BA``-length strip (§1). Area is the §9
    invariant (base counted once + Σ flange areas + Σ bend-strip areas); the
    outline is the union boundary (base free edges + each arm's three outer edges +
    one fold line per bend). Byte-deterministic: arms are sorted by a canonical
    (axis, sign, span) key, independent of the input bend order."""
    frame = _base_frame(base_rec)
    base_c = Vector(*base_rec.centroid)

    arms: list[_Arm] = []
    for _brec, moving_rec, axis_dir, angle_rad, prov in resolved:
        e = axis_dir.normalized()
        radius = prov.cyl_signature.radius_mm
        ba = bend_allowance(angle_rad, radius, prov.k_factor, thickness_mm)
        # Outward direction in the base plane, pointing away from the base interior.
        outward = e.cross(frame.normal).normalized()
        if (Vector(*moving_rec.centroid) - base_c).dot(outward) < 0.0:
            outward = outward * -1.0
        ox, oy = outward.dot(frame.x2), outward.dot(frame.y2)
        if abs(abs(ox) - 1.0) <= _ALIGN_TOL and abs(oy) <= _ALIGN_TOL:
            axis, sign = 0, 1 if ox > 0 else -1
            edge_dir = frame.y2
        elif abs(abs(oy) - 1.0) <= _ALIGN_TOL and abs(ox) <= _ALIGN_TOL:
            axis, sign = 1, 1 if oy > 0 else -1
            edge_dir = frame.x2
        else:
            raise UnfoldStarError(
                "A bend axis is not aligned to the base rectangle (an angled "
                "flange); v1's non-parallel unfold scopes to axis-aligned bends "
                "off a rectangular base (§4.3)."
            )
        # The arm's extent along the fold edge, from the moving flange's own
        # vertices (fold about the bend axis preserves the along-axis coordinate).
        edge_min = frame.x_min if axis == 1 else frame.y_min
        proj = [
            Vector(v.X, v.Y, v.Z).dot(edge_dir) - edge_min
            for v in moving_rec.face.vertices()
        ]
        along_n = (Vector(*moving_rec.centroid) - base_c).dot(frame.normal)
        arms.append(
            _Arm(
                axis=axis,
                sign=sign,
                fold=(frame.wx if axis == 0 else frame.wy) if sign > 0 else 0.0,
                span0=min(proj),
                span1=max(proj),
                allowance_mm=ba,
                leg_mm=moving_rec.developed_length_mm,
                area_mm2=moving_rec.area_mm2,
                width_mm=max(proj) - min(proj),
                radius_mm=radius,
                angle_rad=angle_rad,
                k_factor=prov.k_factor,
                direction="up" if along_n >= 0.0 else "down",
            )
        )

    # Deterministic order: by (axis, outward sign, position along the fold edge).
    arms.sort(key=lambda a: (a.axis, a.sign, a.span0, a.span1))

    return _emit_plus_pattern(
        arms,
        frame,
        thickness_mm=thickness_mm,
        default_k_factor=default_k_factor,
        base_area=base_rec.area_mm2,
    )


def _emit_plus_pattern(
    arms: list[_Arm],
    frame: _BaseFrame,
    *,
    thickness_mm: float,
    default_k_factor: float,
    base_area: float,
) -> FlatPattern:
    """Assemble the plus/cross outline + bend table from the placed arms.

    Coordinates are shifted so the whole blank sits in the positive quadrant with
    its bounding box at the origin — ``flat_length_mm`` / ``bend_width_mm`` are the
    bbox extents (for a rectangular parallel blank these equal the strip length /
    width, but that path never reaches here)."""
    # Collect every arm's outer geometry in frame coords, then shift to origin.
    raw: list[_Seg] = []
    fold_sides: set[tuple[int, int]] = set()

    for a in arms:
        fold_sides.add((a.axis, a.sign))
        near = a.fold
        far = near + a.sign * (a.allowance_mm + a.leg_mm)
        fold_c = near + a.sign * (a.allowance_mm / 2.0)
        if a.axis == 0:  # arm along X; spans [span0, span1] in Y
            raw.append((near, a.span0, far, a.span0, "body"))  # side
            raw.append((near, a.span1, far, a.span1, "body"))  # side
            raw.append((far, a.span0, far, a.span1, "body"))  # far edge
            raw.append((fold_c, a.span0, fold_c, a.span1, "bend"))
        else:  # arm along Y; spans [span0, span1] in X
            raw.append((a.span0, near, a.span0, far, "body"))
            raw.append((a.span1, near, a.span1, far, "body"))
            raw.append((a.span0, far, a.span1, far, "body"))
            raw.append((a.span0, fold_c, a.span1, fold_c, "bend"))

    # Base rectangle's four sides; a side with a flange is a fold (skipped as a
    # body edge — the arm continues the material there), else a real cut edge.
    # (axis, sign) -> the side: X/+ = right (x=wx), X/- = left (x=0), Y/+ = top,
    # Y/- = bottom.
    wx, wy = frame.wx, frame.wy
    base_sides: dict[tuple[int, int], _Seg] = {
        (0, 1): (wx, 0.0, wx, wy, "body"),
        (0, -1): (0.0, 0.0, 0.0, wy, "body"),
        (1, 1): (0.0, wy, wx, wy, "body"),
        (1, -1): (0.0, 0.0, wx, 0.0, "body"),
    }
    for side, seg in base_sides.items():
        if side not in fold_sides:
            raw.append(seg)

    # Shift so the bounding box's min corner is the origin (all coords >= 0).
    xs = [c for s in raw for c in (s[0], s[2])]
    ys = [c for s in raw for c in (s[1], s[3])]
    dx, dy = min(xs), min(ys)
    outline: list[FlatEdge2D] = [
        FlatEdge2D(
            kind="line",
            x1=s[0] - dx,
            y1=s[1] - dy,
            x2=s[2] - dx,
            y2=s[3] - dy,
            role=cast(Literal["body", "bend"], s[4]),
        )
        for s in raw
    ]
    # Deterministic outline order: body edges then bend edges, each by endpoints.
    outline.sort(key=lambda e: (e.role, e.x1, e.y1, e.x2, e.y2))

    bend_lines: list[BendLine] = []
    for i, a in enumerate(arms, start=1):
        near = a.fold
        s0 = near + a.sign * 0.0
        s1 = near + a.sign * a.allowance_mm
        lo, hi = sorted((s0, s1))
        shift = dx if a.axis == 0 else dy
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{i}",
                angle_deg=math.degrees(a.angle_rad),
                radius_mm=a.radius_mm,
                k_factor=a.k_factor,
                allowance_mm=a.allowance_mm,
                width_mm=a.width_mm,
                direction=a.direction,
                flat_start_mm=lo - shift,
                flat_end_mm=hi - shift,
            )
        )

    flat_area = base_area + sum(a.area_mm2 + a.allowance_mm * a.width_mm for a in arms)
    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=max(xs) - min(xs),
        flat_area_mm2=flat_area,
        bend_width_mm=max(ys) - min(ys),
        outline=tuple(outline),
        bends=tuple(bend_lines),
    )
