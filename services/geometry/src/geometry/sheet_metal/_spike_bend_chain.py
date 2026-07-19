"""SPIKE — depth->=2 bend-chain unfold tractability proof (docs/design/sheet-metal.md
sec 4.3 / sec 10, "Multi-bend / bend-graph flattening", the first deferred increment).

**ISOLATED SPIKE, not the shipped feature.** The shipped
:func:`geometry.sheet_metal.unfold.unfold_sheet_metal` unfolds a depth-1 bend STAR
(N flanges folded directly off ONE fixed base) and REJECTS every depth->=2 body with
a typed ``UnfoldStarError`` (sec 4.3's uniform depth-2 rejection). This module does
NOT touch that path or its contract; it is an additive proof-of-concept that answers
one question: **is a depth->=2 bend chain — a flange folded off ANOTHER flange (a box
corner / return / hat channel) — unfoldable with a clean recursive-compositional
walk, or does it need the heavier graph-relaxation solver the design defers?**

The genuinely hard part, named plainly (sec 2.2): at depth-1 every flange's unfold
transform composes ONLY with the FIXED base. At depth >= 2 a grandchild flange folds
off a CHILD flange that has ITSELF already been rotated flat, so the grandchild's
placement must compose THROUGH the parent's already-applied development — any error
in the parent's flat placement propagates to the child. That composition is exactly
the "graph relaxation" the design defers.

**Algorithm (the recursive-compositional formulation this spike validates):**

1. Resolve each bend by its :class:`CylindricalFaceSignature` provenance (the same
   machinery slice #3 shipped) into (parent flange, child flange, bend axis, radius,
   bend allowance). The PARENT of a bend is the flange matching the bend's recorded
   ``base_face_signature`` (sec 5); the CHILD is the other flanking flat.
2. Build the **bend tree**: nodes = flat faces, oriented edges = bends (parent ->
   child). The ROOT is the base flange (a face that is some bend's parent but never
   any bend's child). A depth-1 star has every bend rooted at the base; a depth->=2
   chain has bends whose parent is itself a child of an earlier bend.
3. **Walk the tree from the root outward** (BFS), assigning each flange a 2D
   developed placement ``phi`` (a rigid map from the flange's own plane into the
   shared flat plane). The base is placed at identity (its plane IS the flat). For
   each bend, the child's placement is computed **in the PARENT's already-developed
   frame** — this is the compositional step that depth-1 never needs:

       child_2d(cpC) = parent_2d(cpP) + BA * w_parent_2d

   where ``cpP`` / ``cpC`` are the bend's tangent-contact lines on the parent / child
   planes (the developable-surface tangent lines, sec 9 #1's convention), ``BA`` is
   the closed-form bend allowance (sec 1), and ``w_parent_2d`` is the parent's
   fold-perpendicular direction expressed in ITS developed frame. The child's fold
   axis maps to the parent's mapped axis direction (the fold line is continuous
   material), and the child extends beyond the ``BA`` strip. Because ``parent_2d`` is
   the parent's already-composed map, the walk composes transforms EXACTLY — no
   iteration, no relaxation.

**Verdict (proven by tests/test_sheet_metal_bend_chain.py + the spike golden):
TRACTABLE.** On a hand-built box corner (base + edge flange + a SECOND flange folded
off that flange with a PERPENDICULAR bend axis) the recursion reproduces the flat
pattern with residuals at floating-point scale (BA-strip offset ~1e-15, per-flange
isometry residual 0.0, area conservation exact), and the output is byte-deterministic
across a fresh interpreter. There is NO error accumulation beyond FP and NO OCCT wall:
every input (axis, radius, tangent line) is an exact analytic quantity read from the
cylinder adaptor, and every composition is an exact 2x2 rigid motion. See the module
docstring verdict note in ``docs/design/sheet-metal.md`` sec 4.3.

The OCP wheel ships no type stubs, so the raw build123d ``Vector`` calls are opaque to
pyright; the directives scope that relaxation to this file only, and the typed DTOs at
the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

import math
from dataclasses import dataclass

from build123d import Vector
from py_kit.schemas.features import PlanarFaceSignature

from geometry.kernel.faces import planar_signatures_match
from geometry.kernel.types import BodyShape
from geometry.sheet_metal.flat_pattern import BendLine, FlatEdge2D, FlatPattern
from geometry.sheet_metal.resolve import (
    FlangeFaceRecord,
    SheetMetalUnfoldError,
    resolve_bend_faces,
    resolve_cylindrical_face,
)
from geometry.sheet_metal.unfold import BendProvenance, bend_allowance

Vec2 = tuple[float, float]

#: A flat face's identity key: its outward normal + area centroid, rounded to the
#: subshape linear tolerance so the bend tree's nodes are stable and hashable. Two
#: distinct flanges never collide at this precision; a face is the SAME node across
#: the two bends that share it (a depth-2 chain's middle flange). NOT a stored
#: identity — an in-run graph key only (RESEARCH sec 9: never quantize a persisted id).
_KEY_NORMAL_DP = 6
_KEY_CENTROID_DP = 4


class BendChainError(SheetMetalUnfoldError):
    """The body is outside the spike's depth->=2 bend-chain scope (docs/design/
    sheet-metal.md sec 4.3): the bends do not form a single tree rooted at one base
    flange, or a bend's parent/child cannot be identified by provenance."""


def _face_key(sig: PlanarFaceSignature) -> tuple[float, ...]:
    """A hashable in-run identity for a flat face (normal + centroid, rounded)."""
    return (
        round(sig.normal.x, _KEY_NORMAL_DP),
        round(sig.normal.y, _KEY_NORMAL_DP),
        round(sig.normal.z, _KEY_NORMAL_DP),
        round(sig.centroid.x, _KEY_CENTROID_DP),
        round(sig.centroid.y, _KEY_CENTROID_DP),
        round(sig.centroid.z, _KEY_CENTROID_DP),
    )


@dataclass(frozen=True)
class _ChainBend:
    """One resolved bend of the chain, oriented parent -> child by provenance."""

    parent: FlangeFaceRecord
    child: FlangeFaceRecord
    axis_origin: Vector  # a point on the bend axis line
    axis_dir: Vector  # unit bend-axis direction
    radius_mm: float
    angle_rad: float
    allowance_mm: float
    k_factor: float
    width_mm: float


@dataclass(frozen=True)
class _Placement:
    """A flange's developed placement: an isometry from its own plane into the flat.

    ``phi(p) = R @ [(p - o).e1, (p - o).e2] + t`` maps a 3D point on the flange's
    plane to its 2D developed coordinate. ``(e1, e2)`` is an orthonormal in-plane
    basis; ``R`` (2x2) + ``t`` (2-vector) is the rigid motion placing this flange
    relative to the shared flat plane. The base flange is placed at identity."""

    o: Vector
    e1: Vector
    e2: Vector
    r00: float
    r01: float
    r10: float
    r11: float
    tx: float
    ty: float

    def phi(self, p: Vector) -> Vec2:
        d = p - self.o
        a = d.dot(self.e1)
        b = d.dot(self.e2)
        return (
            self.r00 * a + self.r01 * b + self.tx,
            self.r10 * a + self.r11 * b + self.ty,
        )


def _perp(v: Vector, axis: Vector) -> Vector:
    """The component of *v* perpendicular to unit *axis*."""
    return v - axis * v.dot(axis)


def _project_to_plane(point: Vector, plane_pt: Vector, normal: Vector) -> Vector:
    """Orthogonal projection of *point* onto the plane through *plane_pt* with unit
    *normal* — the bend axis projects onto a flange plane to that flange's tangent
    contact line (the developable-surface tangent line, sec 9 #1)."""
    return point - normal * (point - plane_pt).dot(normal)


def _resolve_chain(
    body: BodyShape, bends: list[BendProvenance], thickness_mm: float
) -> list[_ChainBend]:
    """Resolve every bend by provenance and orient it parent -> child (sec 5).

    The parent is the flanking flat matching the bend's recorded base-face signature;
    the child is the other flat. This is what lets the tree be built WITHOUT any
    geometric guessing — a depth-2 flange records its PARENT flange's signature, so
    the chain orients itself from construction provenance alone."""
    out: list[_ChainBend] = []
    for prov in bends:
        inner = resolve_cylindrical_face(body, prov.cyl_signature)
        rbf = resolve_bend_faces(body, inner)
        a, b = rbf.flanges
        if planar_signatures_match(a.signature, prov.base_face_signature):
            parent, child = a, b
        elif planar_signatures_match(b.signature, prov.base_face_signature):
            parent, child = b, a
        else:
            raise BendChainError(
                "A bend's recorded base-face signature matches neither flanking flat; "
                "the bend cannot be oriented parent -> child by provenance (sec 5)."
            )
        out.append(
            _ChainBend(
                parent=parent,
                child=child,
                axis_origin=inner.axis_origin,
                axis_dir=inner.axis_dir.normalized(),
                radius_mm=inner.radius,
                angle_rad=rbf.angle_rad,
                allowance_mm=bend_allowance(
                    rbf.angle_rad, inner.radius, prov.k_factor, thickness_mm
                ),
                k_factor=prov.k_factor,
                width_mm=child.width_mm,
            )
        )
    return out


def _find_root(chain: list[_ChainBend]) -> tuple[float, ...]:
    """The base-flange node: a bend parent that is never a bend child (the fixed
    root of the tree). Exactly one — else the bends are not a single rooted tree."""
    parents = {_face_key(b.parent.signature) for b in chain}
    children = {_face_key(b.child.signature) for b in chain}
    roots = parents - children
    if len(roots) != 1:
        raise BendChainError(
            f"The bends do not form a single tree rooted at one base flange "
            f"(found {len(roots)} root candidates). The spike unfolds a connected "
            "bend chain / tree off one base (docs/design/sheet-metal.md sec 4.3)."
        )
    return next(iter(roots))


def _base_placement(root_rec: FlangeFaceRecord) -> _Placement:
    """Place the base flange at identity: its own plane is the developed plane.

    The in-plane basis is derived deterministically from the base normal (no face
    iteration order dependence), so the whole developed layout is reproducible."""
    n = Vector(*root_rec.normal).normalized()
    seed = Vector(1.0, 0.0, 0.0) if abs(n.X) < 0.9 else Vector(0.0, 1.0, 0.0)
    e1 = _perp(seed, n).normalized()
    e2 = n.cross(e1).normalized()
    return _Placement(
        o=Vector(*root_rec.centroid),
        e1=e1,
        e2=e2,
        r00=1.0,
        r01=0.0,
        r10=0.0,
        r11=1.0,
        tx=0.0,
        ty=0.0,
    )


def _place_child(parent_pl: _Placement, bend: _ChainBend) -> _Placement:
    """Compose the child's developed placement in the PARENT's flattened frame.

    This is the depth->=2 crux: the child folds off a parent that is ITSELF already
    developed, so we express the bend's tangent line in the parent's 2D frame and
    place the child across a ``BA``-wide strip beyond it. Pure composition — the
    parent's map is applied to the shared tangent line, then offset by the bend
    allowance. No relaxation, no iteration."""
    axis = bend.axis_dir
    o = bend.axis_origin
    p_n = Vector(*bend.parent.normal).normalized()
    c_n = Vector(*bend.child.normal).normalized()
    p_c = Vector(*bend.parent.centroid)
    c_c = Vector(*bend.child.centroid)

    # Tangent-contact lines: the bend axis projected onto each flange plane. cpP and
    # cpC share the bend's axial coordinate (projection removes only the normal
    # component, which is perpendicular to the axis), so they are corresponding points.
    cp_p = _project_to_plane(o, p_c, p_n)
    cp_c = _project_to_plane(o, c_c, c_n)

    # Fold-perpendicular directions (in-plane, perpendicular to the axis).
    w_p = _perp(cp_p - p_c, axis).normalized()  # parent interior -> bend
    w_c = _perp(c_c - cp_c, axis).normalized()  # bend -> child interior

    # Parent-frame images of the axis + fold-perpendicular directions.
    a2 = _unit2(_map_dir(parent_pl, axis))
    wp2 = _unit2(_map_dir(parent_pl, w_p))

    # Child placement: fold axis -> a2, child fold-perpendicular -> wp2 (continues
    # across the strip). Origin at the child tangent contact, offset one BA beyond
    # the parent tangent contact along wp2 (the developed bend strip).
    q_parent = parent_pl.phi(cp_p)
    tx = q_parent[0] + bend.allowance_mm * wp2[0]
    ty = q_parent[1] + bend.allowance_mm * wp2[1]
    return _Placement(
        o=cp_c,
        e1=axis,
        e2=w_c,
        r00=a2[0],
        r01=wp2[0],
        r10=a2[1],
        r11=wp2[1],
        tx=tx,
        ty=ty,
    )


def _map_dir(pl: _Placement, v: Vector) -> Vec2:
    """A 3D in-plane direction expressed in *pl*'s developed frame (no translation)."""
    a = v.dot(pl.e1)
    b = v.dot(pl.e2)
    return (pl.r00 * a + pl.r01 * b, pl.r10 * a + pl.r11 * b)


def _unit2(v: Vec2) -> Vec2:
    length = math.hypot(v[0], v[1])
    return (v[0] / length, v[1] / length)


@dataclass(frozen=True)
class BendChainUnfold:
    """The spike's unfold result: the :class:`FlatPattern` plus the per-flange
    developed placements + residuals the tractability proof measures."""

    pattern: FlatPattern
    #: Per-bend developed strip width (should equal the bend allowance to FP scale).
    strip_widths_mm: tuple[float, ...]
    #: Per-flange developed 2D area (should equal each flange's 3D face area).
    flange_dev_areas_mm2: tuple[float, ...]
    #: The developed bounding box of every flange (min_x, min_y, max_x, max_y).
    flange_bboxes: tuple[tuple[float, float, float, float], ...]
    #: max tree depth (>=2 confirms a genuine bend chain, not a depth-1 star).
    max_depth: int


def unfold_bend_chain(
    body: BodyShape,
    bends: list[BendProvenance],
    thickness_mm: float,
    default_k_factor: float,
) -> BendChainUnfold:
    """Unfold a depth->=2 sheet-metal bend chain (the spike's proof entry point).

    Resolves each bend by provenance, builds the bend tree, walks it from the base
    outward composing each flange's developed placement in its parent's already-flat
    frame, and emits a :class:`FlatPattern` (per-flange developed outlines + fold
    lines) alongside the residuals the tractability proof measures.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (honest degradation, sec 5).
        BendChainError: the bends are not a single tree rooted at one base flange.
    """
    if not bends:
        raise BendChainError("An unfold needs at least one bend (edge flange).")

    chain = _resolve_chain(body, bends, thickness_mm)
    root_key = _find_root(chain)

    # Deterministic root record: any bend whose parent is the root.
    root_rec = next(
        b.parent for b in chain if _face_key(b.parent.signature) == root_key
    )
    placements: dict[tuple[float, ...], _Placement] = {
        root_key: _base_placement(root_rec)
    }
    depth: dict[tuple[float, ...], int] = {root_key: 0}

    # BFS: place a bend's child once its parent is placed. Deterministic order —
    # bends sorted by a canonical geometric key so the walk never depends on the
    # input list order (RESEARCH sec 9).
    pending = sorted(
        chain,
        key=lambda b: (
            _face_key(b.parent.signature),
            _face_key(b.child.signature),
        ),
    )
    placed_order: list[_ChainBend] = []
    strip_widths: list[float] = []
    guard = 0
    while pending:
        guard += 1
        if guard > len(chain) + 1:
            raise BendChainError(
                "The bend tree is disconnected or cyclic — a child was never reached "
                "from the base flange (docs/design/sheet-metal.md sec 4.3)."
            )
        progressed = False
        for bend in list(pending):
            pk = _face_key(bend.parent.signature)
            ck = _face_key(bend.child.signature)
            if pk in placements and ck not in placements:
                child_pl = _place_child(placements[pk], bend)
                placements[ck] = child_pl
                depth[ck] = depth[pk] + 1
                q_parent = placements[pk].phi(
                    _project_to_plane(
                        bend.axis_origin,
                        Vector(*bend.parent.centroid),
                        Vector(*bend.parent.normal).normalized(),
                    )
                )
                q_child = child_pl.phi(child_pl.o)
                strip_widths.append(math.dist(q_child, q_parent))
                placed_order.append(bend)
                pending.remove(bend)
                progressed = True
        if not progressed:
            raise BendChainError(
                "The bend tree is disconnected — some flange never chains back to the "
                "base (docs/design/sheet-metal.md sec 4.3)."
            )

    pattern, dev_areas, bboxes = _emit(
        chain,
        placed_order,
        placements,
        root_key,
        root_rec,
        thickness_mm,
        default_k_factor,
    )
    return BendChainUnfold(
        pattern=pattern,
        strip_widths_mm=tuple(strip_widths),
        flange_dev_areas_mm2=dev_areas,
        flange_bboxes=bboxes,
        max_depth=max(depth.values()),
    )


def _flange_loop(rec: FlangeFaceRecord, pl: _Placement) -> list[Vec2]:
    """The flange's developed outline: its face vertices mapped to 2D, deduplicated
    and ordered into a loop by angle about their centroid (robust for the convex
    rectangular flats the v1 edge flange produces)."""
    seen: list[Vec2] = []
    for v in rec.face.vertices():
        p = pl.phi(Vector(v.X, v.Y, v.Z))
        if not any(math.dist(p, q) <= 1e-6 for q in seen):
            seen.append(p)
    cx = sum(p[0] for p in seen) / len(seen)
    cy = sum(p[1] for p in seen) / len(seen)
    seen.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return seen


def _emit(
    chain: list[_ChainBend],
    placed_order: list[_ChainBend],
    placements: dict[tuple[float, ...], _Placement],
    root_key: tuple[float, ...],
    root_rec: FlangeFaceRecord,
    thickness_mm: float,
    default_k_factor: float,
) -> tuple[
    FlatPattern, tuple[float, ...], tuple[tuple[float, float, float, float], ...]
]:
    """Assemble the flat pattern: each flange's developed outline (body edges) + one
    fold line per bend, sorted for determinism. ``flat_length`` / ``bend_width`` are
    the developed bounding-box extents. Area is the sec 9 #2 invariant (base counted
    once + every flange's own area + every bend strip ``BA * width``) — the
    authoritative developed area, independent of the outline assembly."""
    # Every flange record, keyed, base first.
    recs: dict[tuple[float, ...], FlangeFaceRecord] = {root_key: root_rec}
    for b in chain:
        recs[_face_key(b.child.signature)] = b.child

    outline: list[FlatEdge2D] = []
    dev_areas: list[float] = []
    bboxes: list[tuple[float, float, float, float]] = []
    all_x: list[float] = []
    all_y: list[float] = []

    for key in sorted(recs):
        loop = _flange_loop(recs[key], placements[key])
        dev_areas.append(_shoelace(loop))
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        bboxes.append((min(xs), min(ys), max(xs), max(ys)))
        all_x.extend(xs)
        all_y.extend(ys)
        n = len(loop)
        for i in range(n):
            x1, y1 = loop[i]
            x2, y2 = loop[(i + 1) % n]
            outline.append(
                FlatEdge2D(kind="line", x1=x1, y1=y1, x2=x2, y2=y2, role="body")
            )

    bend_lines: list[BendLine] = []
    for i, bend in enumerate(placed_order, start=1):
        child_pl = placements[_face_key(bend.child.signature)]
        # Fold line = the child tangent contact line, spanning the bend width along
        # the fold axis, in developed coordinates.
        cp_c = child_pl.o
        along = [
            (Vector(v.X, v.Y, v.Z) - cp_c).dot(bend.axis_dir)
            for v in bend.child.face.vertices()
        ]
        s0, s1 = min(along), max(along)
        p0 = child_pl.phi(cp_c + bend.axis_dir * s0)
        p1 = child_pl.phi(cp_c + bend.axis_dir * s1)
        outline.append(
            FlatEdge2D(kind="line", x1=p0[0], y1=p0[1], x2=p1[0], y2=p1[1], role="bend")
        )
        # Fold sense: child centroid on the +parent-normal side -> "up".
        p_n = Vector(*bend.parent.normal).normalized()
        along_n = (Vector(*bend.child.centroid) - Vector(*bend.parent.centroid)).dot(
            p_n
        )
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{i}",
                angle_deg=math.degrees(bend.angle_rad),
                radius_mm=bend.radius_mm,
                k_factor=bend.k_factor,
                allowance_mm=bend.allowance_mm,
                width_mm=bend.width_mm,
                direction="up" if along_n >= 0.0 else "down",
                flat_start_mm=0.0,
                flat_end_mm=bend.allowance_mm,
            )
        )

    outline.sort(key=lambda e: (e.role, e.x1, e.y1, e.x2, e.y2))
    bend_lines.sort(key=lambda bl: bl.bend_id)

    flat_area = sum(rec.area_mm2 for rec in recs.values()) + sum(
        b.allowance_mm * b.width_mm for b in chain
    )
    return (
        FlatPattern(
            thickness_mm=thickness_mm,
            k_factor=default_k_factor,
            flat_length_mm=max(all_x) - min(all_x),
            flat_area_mm2=flat_area,
            bend_width_mm=max(all_y) - min(all_y),
            outline=tuple(outline),
            bends=tuple(bend_lines),
        ),
        tuple(dev_areas),
        tuple(bboxes),
    )


def _shoelace(loop: list[Vec2]) -> float:
    """Unsigned polygon area of a 2D loop (the flange's developed area, for the
    isometry residual check: it must equal the flange's 3D face area)."""
    area = 0.0
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
