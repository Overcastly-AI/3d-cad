"""Analytic 2D sketch editing — trim & extend (BACKLOG #2, backend).

Trim and extend are **server-side geometry operations** (RESEARCH §3 +
CLAUDE.md): 2D curve intersection/trimming is kernel-owned and must never be
reimplemented in the frontend. This module implements them with **exact
analytic geometry** for the entity kinds the sketch model supports today —
line, arc, circle (and free points, which are not trimmable/extendable). The
analytic path is chosen over OCCT ``Geom2d`` deliberately: line/arc/circle
intersection has closed-form solutions, so the results are exact and
**bitwise deterministic** (RESEARCH §9) with no solver iteration, no kernel
handle crossing the boundary, and no nondeterministic exploration order.

Supported in v1 (honest scope — deferred kinds are stated so callers aren't
surprised):

* **Trim** — target line / arc / circle; cutters line / arc / circle. The
  target is cut at its nearest intersection on each side of the pick and the
  picked segment removed (Onshape/Fusion "cut at intersection"); no
  intersection on a side runs to the curve end; no intersection at all
  deletes the whole target.
* **Extend** — target line / arc; the picked end grows along the target's
  supporting line/circle to the nearest neighbor it meets. Circles (no ends)
  and points are rejected ``sketch_unsupported_entity``.
* **Deferred** — splines/bezier are not yet a sketch entity kind, so nothing
  to do here; when they land they extend this module (intersection +
  parameter helpers), not the DTO contract.

Everything below operates on pure floats/dataclasses; the only imported types
are the pydantic DTOs from :mod:`geometry.sketch.schemas` (the boundary
models). ``SketchEditError`` carries a legible ``code`` the endpoint maps to a
422 envelope — malformed edits are diagnosed, never 500s.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from geometry.sketch.schemas import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
    SketchPoint,
)

#: Geometric classification epsilon (mm). Used only to CLASSIFY — detect
#: parallel/collinear lines, dedup coincident intersections, test whether a
#: point lies within a curve's drawn extent, and reject zero-length results.
#: It never rounds a returned coordinate: trim/extend endpoints are the exact
#: analytic intersection values. 1e-9 mm is far below any meaningful sketch
#: feature size yet safely above double-precision noise at sketch magnitudes.
_TOL = 1e-9

_TWO_PI = 2.0 * math.pi


class SketchEditError(ValueError):
    """A trim/extend/offset edit cannot be performed as asked.

    ``code`` is the legible envelope code the endpoint surfaces as a 422
    (never a 500): ``sketch_target_not_found``, ``sketch_unsupported_entity``,
    ``sketch_pick_not_on_target``, ``sketch_extend_no_target``,
    ``sketch_offset_zero_distance``, ``sketch_degenerate_result``.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Internal vector + curve helpers (analytic, exact)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _V:
    """A 2D point/vector in sketch-plane mm."""

    x: float
    y: float


def _pt(p: Point2D) -> _V:
    return _V(p.x, p.y)


def _sub(a: _V, b: _V) -> _V:
    return _V(a.x - b.x, a.y - b.y)


def _dot(a: _V, b: _V) -> float:
    return a.x * b.x + a.y * b.y


def _cross(a: _V, b: _V) -> float:
    return a.x * b.y - a.y * b.x


def _dist(a: _V, b: _V) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _point2d(v: _V) -> Point2D:
    return Point2D(x=v.x, y=v.y)


@dataclass(frozen=True)
class _Support:
    """The infinite supporting curve of a target/cutter entity.

    ``kind`` is ``"line"`` (through ``a``/``b``) or ``"circle"`` (centre ``a``,
    radius ``r``). Arcs support a circle; segments support a line.
    """

    kind: str
    a: _V
    b: _V  # second line point; ignored for circles
    r: float  # radius; ignored for lines


def _support(entity: SketchEntity) -> _Support:
    if isinstance(entity, SketchLine):
        return _Support("line", _pt(entity.start), _pt(entity.end), 0.0)
    if isinstance(entity, SketchCircle):
        return _Support("circle", _pt(entity.center), _V(0.0, 0.0), entity.radius)
    if isinstance(entity, SketchArc):
        c = _pt(entity.center)
        return _Support("circle", c, _V(0.0, 0.0), _dist(c, _pt(entity.start)))
    raise SketchEditError(
        f"entity {entity.id!r} of kind {entity.kind!r} has no supporting curve",
        code="sketch_unsupported_entity",
    )


def _isect_line_line(s1: _Support, s2: _Support) -> list[_V]:
    """Intersection of two infinite lines (empty if parallel/collinear)."""
    d1 = _sub(s1.b, s1.a)
    d2 = _sub(s2.b, s2.a)
    denom = _cross(d1, d2)
    if abs(denom) < _TOL:
        return []  # parallel or collinear — no isolated crossing
    t = _cross(_sub(s2.a, s1.a), d2) / denom
    return [_V(s1.a.x + t * d1.x, s1.a.y + t * d1.y)]


def _isect_line_circle(line: _Support, circ: _Support) -> list[_V]:
    """Intersections of an infinite line with a full circle (0, 1 or 2)."""
    d = _sub(line.b, line.a)
    f = _sub(line.a, circ.a)
    a = _dot(d, d)
    b = 2.0 * _dot(f, d)
    c = _dot(f, f) - circ.r * circ.r
    disc = b * b - 4.0 * a * c
    if disc < -_TOL or a < _TOL:
        return []
    if disc < _TOL:  # tangent — single point
        t = -b / (2.0 * a)
        return [_V(line.a.x + t * d.x, line.a.y + t * d.y)]
    root = math.sqrt(disc)
    out: list[_V] = []
    for t in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a)):
        out.append(_V(line.a.x + t * d.x, line.a.y + t * d.y))
    return out


def _isect_circle_circle(c1: _Support, c2: _Support) -> list[_V]:
    """Intersections of two full circles (0, 1 or 2)."""
    d = _dist(c1.a, c2.a)
    if d < _TOL:
        return []  # concentric (or identical) — no isolated crossing
    if d > c1.r + c2.r + _TOL or d < abs(c1.r - c2.r) - _TOL:
        return []
    a = (c1.r * c1.r - c2.r * c2.r + d * d) / (2.0 * d)
    h2 = c1.r * c1.r - a * a
    ux = (c2.a.x - c1.a.x) / d
    uy = (c2.a.y - c1.a.y) / d
    mid = _V(c1.a.x + a * ux, c1.a.y + a * uy)
    if h2 <= _TOL:  # tangent — single point
        return [mid]
    h = math.sqrt(h2)
    return [
        _V(mid.x - h * uy, mid.y + h * ux),
        _V(mid.x + h * uy, mid.y - h * ux),
    ]


def _support_intersections(s1: _Support, s2: _Support) -> list[_V]:
    """All intersection points of two supporting curves."""
    if s1.kind == "line" and s2.kind == "line":
        return _isect_line_line(s1, s2)
    if s1.kind == "line" and s2.kind == "circle":
        return _isect_line_circle(s1, s2)
    if s1.kind == "circle" and s2.kind == "line":
        return _isect_line_circle(s2, s1)
    return _isect_circle_circle(s1, s2)


# --- parametrisation & containment on the ACTUAL (drawn) extent -------------


def _line_param(entity: SketchLine, p: _V) -> float:
    """Parameter of ``p`` along the segment (0 at start, 1 at end)."""
    a = _pt(entity.start)
    d = _sub(_pt(entity.end), a)
    denom = _dot(d, d)
    if denom < _TOL:
        return 0.0
    return _dot(_sub(p, a), d) / denom


def _angle_at(center: _V, p: _V) -> float:
    """Absolute angle of ``p`` about ``center`` in [0, 2π)."""
    ang = math.atan2(p.y - center.y, p.x - center.x)
    return ang % _TWO_PI


def _arc_geometry(entity: SketchArc) -> tuple[_V, float, float, float]:
    """(centre, radius, start-angle, sweep) of an arc — CCW start→end."""
    c = _pt(entity.center)
    r = _dist(c, _pt(entity.start))
    a0 = _angle_at(c, _pt(entity.start))
    a1 = _angle_at(c, _pt(entity.end))
    sweep = (a1 - a0) % _TWO_PI
    return c, r, a0, sweep


def _arc_offset(entity: SketchArc, p: _V) -> float:
    """Offset of ``p`` along the arc from its start (CCW), in [0, 2π)."""
    c, _r, a0, _sweep = _arc_geometry(entity)
    return (_angle_at(c, p) - a0) % _TWO_PI


def _contains(entity: SketchEntity, p: _V) -> bool:
    """True if ``p`` (already on the entity's support) lies on its drawn extent."""
    if isinstance(entity, SketchLine):
        t = _line_param(entity, p)
        return -_TOL <= t <= 1.0 + _TOL
    if isinstance(entity, SketchCircle):
        return True  # a full circle contains every point of its support
    if isinstance(entity, SketchArc):
        _c, _r, _a0, sweep = _arc_geometry(entity)
        off = _arc_offset(entity, p)
        # wrap the [sweep, 2π) tail back to a small negative so the endpoint
        # (off ≈ 0 or ≈ 2π) reads as on-extent, not just past the far end.
        if off > sweep + _TOL:
            off -= _TWO_PI
        return -_TOL <= off <= sweep + _TOL
    return False


def _point_on_line(entity: SketchLine, t: float) -> _V:
    a = _pt(entity.start)
    d = _sub(_pt(entity.end), a)
    return _V(a.x + t * d.x, a.y + t * d.y)


def _point_on_circle(center: _V, r: float, angle: float) -> _V:
    return _V(center.x + r * math.cos(angle), center.y + r * math.sin(angle))


# ---------------------------------------------------------------------------
# Cutter gathering
# ---------------------------------------------------------------------------


def _cutter_intersections(
    target: SketchEntity, cutters: list[SketchEntity]
) -> list[_V]:
    """Points where the target's support actually meets a cutter's drawn extent.

    Filtered to points on BOTH the target's drawn extent and the cutter's —
    only where the geometry really crosses, exactly as a user sees it (no
    infinite extensions). Deterministic order: cutters in input list order.
    """
    ts = _support(target)
    out: list[_V] = []
    for cutter in cutters:
        cs = _support(cutter)
        for p in _support_intersections(ts, cs):
            if _contains(target, p) and _contains(cutter, p):
                out.append(p)
    return out


def _dedup_sorted(values: list[float]) -> list[float]:
    """Sort ascending and drop near-duplicates (within ``_TOL``)."""
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > _TOL:
            out.append(v)
    return out


def _fresh_id(base: str, used: set[str]) -> str:
    """Lowest ``f"{base}.{n}"`` (n>=2) not already taken — deterministic."""
    n = 2
    while f"{base}.{n}" in used:
        n += 1
    return f"{base}.{n}"


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------


def _neighbors(
    pick: float, bounds: list[float], lo: float, hi: float
) -> tuple[float, float]:
    """Nearest bound below/above ``pick`` within (lo, hi), clamped to lo/hi."""
    left = lo
    right = hi
    for b in bounds:
        if b < pick - _TOL and b > left:
            left = b
        if b > pick + _TOL and b < right:
            right = b
    return left, right


def _trim_line(
    entity: SketchLine, pick: _V, cutters: list[SketchEntity]
) -> list[SketchEntity]:
    p = _line_param(entity, pick)
    if p < -_TOL or p > 1.0 + _TOL:
        raise SketchEditError(
            "pick does not project onto the target line's extent",
            code="sketch_pick_not_on_target",
        )
    params = _dedup_sorted(
        [
            t
            for x in _cutter_intersections(entity, cutters)
            if _TOL < (t := _line_param(entity, x)) < 1.0 - _TOL
        ]
    )
    left, right = _neighbors(p, params, 0.0, 1.0)
    pieces: list[tuple[float, float]] = []
    if left > _TOL:  # an intersection bounds the pick on the low side
        pieces.append((0.0, left))
    if right < 1.0 - _TOL:  # ...and/or on the high side
        pieces.append((right, 1.0))

    def make(t0: float, t1: float, ident: str) -> SketchLine:
        return SketchLine(
            id=ident,
            construction=entity.construction,
            kind="line",
            start=_point2d(_point_on_line(entity, t0)),
            end=_point2d(_point_on_line(entity, t1)),
        )

    return _rebuild(entity, pieces, lambda seg, ident: make(seg[0], seg[1], ident))


def _trim_arc(
    entity: SketchArc, pick: _V, cutters: list[SketchEntity]
) -> list[SketchEntity]:
    c, r, a0, sweep = _arc_geometry(entity)
    p = _arc_offset(entity, pick)
    if p > sweep + _TOL:
        p -= _TWO_PI
    if p < -_TOL or p > sweep + _TOL:
        raise SketchEditError(
            "pick does not project onto the target arc's extent",
            code="sketch_pick_not_on_target",
        )
    offs = _dedup_sorted(
        [
            o
            for x in _cutter_intersections(entity, cutters)
            if _TOL < (o := _arc_offset(entity, x)) < sweep - _TOL
        ]
    )
    left, right = _neighbors(p, offs, 0.0, sweep)
    pieces: list[tuple[float, float]] = []
    if left > _TOL:
        pieces.append((0.0, left))
    if right < sweep - _TOL:
        pieces.append((right, sweep))

    def make(off0: float, off1: float, ident: str) -> SketchArc:
        return SketchArc(
            id=ident,
            construction=entity.construction,
            kind="arc",
            center=_point2d(c),
            start=_point2d(_point_on_circle(c, r, a0 + off0)),
            end=_point2d(_point_on_circle(c, r, a0 + off1)),
        )

    return _rebuild(entity, pieces, lambda seg, ident: make(seg[0], seg[1], ident))


def _trim_circle(
    entity: SketchCircle, pick: _V, cutters: list[SketchEntity]
) -> list[SketchEntity]:
    c = _pt(entity.center)
    r = entity.radius
    pick_ang = _angle_at(c, pick)  # a circle contains every projected pick
    angles = _dedup_sorted(
        [_angle_at(c, x) for x in _cutter_intersections(entity, cutters)]
    )
    if len(angles) < 2:
        # Fewer than two distinct bounding intersections: nothing bounds the
        # picked arc, so the whole circle is deleted (documented Onshape
        # behaviour: "no intersection ⇒ delete the whole curve").
        return []
    # Cyclic neighbours of the pick angle bound the removed arc; the remainder
    # is the single complementary arc, CCW from the upper bound to the lower.
    lower = max((a for a in angles if a < pick_ang - _TOL), default=None)
    upper = min((a for a in angles if a > pick_ang + _TOL), default=None)
    if lower is None:
        lower = angles[-1]  # wrap: nearest below is the largest angle
    if upper is None:
        upper = angles[0]  # wrap: nearest above is the smallest angle
    arc = SketchArc(
        id=entity.id,
        construction=entity.construction,
        kind="arc",
        center=entity.center,
        start=_point2d(_point_on_circle(c, r, upper)),
        end=_point2d(_point_on_circle(c, r, lower)),
    )
    return [arc]


def _rebuild(
    target: SketchEntity,
    pieces: list[tuple[float, float]],
    build: Callable[[tuple[float, float], str], SketchEntity],
) -> list[SketchEntity]:
    """Turn parameter-segments into entities: first keeps the target id."""
    used = {target.id}
    out: list[SketchEntity] = []
    for seg in pieces:
        if seg[1] - seg[0] <= _TOL:
            continue  # drop a degenerate (zero-length) piece
        ident = target.id if not out else _fresh_id(target.id, used)
        used.add(ident)
        out.append(build(seg, ident))
    return out


def trim_sketch(
    entities: list[SketchEntity], target_id: str, pick: Point2D
) -> list[SketchEntity]:
    """Trim ``target_id`` at the pick, returning the rewritten entity list.

    The target is cut at its nearest intersection with the other entities on
    each side of the pick and the picked segment removed; the result replaces
    the target in place (see :class:`py_kit.schemas.sketch.SketchEditResult`).
    """
    target = _find_target(entities, target_id)
    cutters: list[SketchEntity] = [
        e for e in entities if e.id != target_id and not isinstance(e, SketchPoint)
    ]
    pv = _pt(pick)
    if isinstance(target, SketchLine):
        replacement = _trim_line(target, pv, cutters)
    elif isinstance(target, SketchArc):
        replacement = _trim_arc(target, pv, cutters)
    elif isinstance(target, SketchCircle):
        replacement = _trim_circle(target, pv, cutters)
    else:
        raise SketchEditError(
            f"trim does not support a {target.kind!r} entity",
            code="sketch_unsupported_entity",
        )
    return _splice(entities, target_id, replacement)


# ---------------------------------------------------------------------------
# Extend
# ---------------------------------------------------------------------------


def _extend_line(
    entity: SketchLine, which: str, cutters: list[SketchEntity]
) -> SketchLine:
    support = _support(entity)
    # Candidate params on the infinite line, kept only where a cutter really is
    # AND strictly beyond the picked endpoint (t>1 for the end, t<0 for start).
    candidates: list[float] = []
    for cutter in cutters:
        cs = _support(cutter)
        for x in _support_intersections(support, cs):
            if not _contains(cutter, x):
                continue
            t = _line_param(entity, x)
            beyond_end = which == "end" and t > 1.0 + _TOL
            beyond_start = which == "start" and t < -_TOL
            if beyond_end or beyond_start:
                candidates.append(t)
    if not candidates:
        raise SketchEditError(
            "no neighbouring entity found to extend the line to",
            code="sketch_extend_no_target",
        )
    best_t = min(candidates) if which == "end" else max(candidates)  # nearest
    new_pt = _point2d(_point_on_line(entity, best_t))
    if which == "end":
        return entity.model_copy(update={"end": new_pt})
    return entity.model_copy(update={"start": new_pt})


def _extend_arc(
    entity: SketchArc, which: str, cutters: list[SketchEntity]
) -> SketchArc:
    c, r, a0, sweep = _arc_geometry(entity)
    support = _support(entity)
    # Candidate continuation offsets (relative to the arc start a0): extending
    # the END grows the sweep just past `sweep` CCW; extending the START grows
    # it before 0 CW, carried as a negative offset. Both stay before the wrap
    # that would collide with the opposite endpoint.
    candidates: list[float] = []
    for cutter in cutters:
        cs = _support(cutter)
        for x in _support_intersections(support, cs):
            if not _contains(cutter, x):
                continue
            off = _arc_offset(entity, x)  # in [0, 2π)
            if which == "end" and sweep + _TOL < off < _TWO_PI - _TOL:
                candidates.append(off)
            elif which == "start":
                cand = off - _TWO_PI  # in (-2π, 0)
                if cand < -_TOL and sweep - cand < _TWO_PI - _TOL:
                    candidates.append(cand)
    if not candidates:
        raise SketchEditError(
            "no neighbouring entity found to extend the arc to",
            code="sketch_extend_no_target",
        )
    best = min(candidates) if which == "end" else max(candidates)  # nearest
    new_pt = _point2d(_point_on_circle(c, r, a0 + best))
    if which == "end":
        return entity.model_copy(update={"end": new_pt})
    return entity.model_copy(update={"start": new_pt})


def _nearest_end(entity: SketchLine | SketchArc, pick: _V) -> str:
    """Which endpoint ('start'/'end') the pick is nearer to (tie → 'start')."""
    ds = _dist(_pt(entity.start), pick)
    de = _dist(_pt(entity.end), pick)
    return "end" if de < ds - _TOL else "start"


def extend_sketch(
    entities: list[SketchEntity], target_id: str, pick: Point2D
) -> list[SketchEntity]:
    """Extend ``target_id``'s picked end to the nearest neighbor it meets.

    The pick selects the nearer endpoint; the curve grows along its own
    supporting line/circle until it reaches the closest entity in that
    direction. Circles and points have no free end and are rejected.
    """
    target = _find_target(entities, target_id)
    cutters: list[SketchEntity] = [
        e for e in entities if e.id != target_id and not isinstance(e, SketchPoint)
    ]
    pv = _pt(pick)
    replacement: SketchLine | SketchArc
    if isinstance(target, SketchLine):
        replacement = _extend_line(target, _nearest_end(target, pv), cutters)
    elif isinstance(target, SketchArc):
        replacement = _extend_arc(target, _nearest_end(target, pv), cutters)
    else:
        raise SketchEditError(
            f"extend does not support a {target.kind!r} entity "
            "(only line and arc have a free end to lengthen)",
            code="sketch_unsupported_entity",
        )
    if _dist(_pt(replacement.start), _pt(replacement.end)) < _TOL:
        raise SketchEditError(
            "extend produced a degenerate (zero-length) curve",
            code="sketch_degenerate_result",
        )
    return _splice(entities, target_id, [replacement])


# ---------------------------------------------------------------------------
# Offset (BACKLOG #3)
# ---------------------------------------------------------------------------
#
# A parallel copy of the target curve, displaced by a SIGNED distance along its
# **left-hand normal** — the curve's forward direction rotated +90° (CCW).
# +distance = left of the directed curve; -distance = right. For a line this is
# the familiar perpendicular offset. A circle/arc is traversed CCW, so its
# left-hand normal points INWARD (toward the centre): +distance shrinks the
# radius (radius - distance, same centre/angular span), -distance grows it.
#
# Exact closed-form for every kind (RESEARCH §9): the line case is one rational
# unit-normal displacement; the arc/circle case is a rational radial RESCALE
# (new_r / r), so the arc's angular span is preserved with NO trig at all.
# Offset ADDS geometry — the source is untouched; the new entity carries a
# fresh deterministic id and inherits the source's construction flag.
#
# v1 = single-entity offset; chain offset (connected runs + miter/arc joins) is
# deferred (see py_kit.schemas.sketch module comment).


def _offset_line(entity: SketchLine, distance: float, ident: str) -> SketchLine:
    a = _pt(entity.start)
    b = _pt(entity.end)
    d = _sub(b, a)
    length = math.hypot(d.x, d.y)
    if length < _TOL:
        raise SketchEditError(
            "cannot offset a zero-length line",
            code="sketch_degenerate_result",
        )
    # Left-hand unit normal: rotate the unit direction +90° CCW, (x,y)->(-y,x).
    ox = distance * (-d.y / length)
    oy = distance * (d.x / length)
    return SketchLine(
        id=ident,
        construction=entity.construction,
        kind="line",
        start=_point2d(_V(a.x + ox, a.y + oy)),
        end=_point2d(_V(b.x + ox, b.y + oy)),
    )


def _offset_circle(entity: SketchCircle, distance: float, ident: str) -> SketchCircle:
    new_r = entity.radius - distance  # +distance = inward (CCW left normal)
    if new_r <= _TOL:
        raise SketchEditError(
            "inward offset collapses the circle (radius <= 0)",
            code="sketch_degenerate_result",
        )
    return SketchCircle(
        id=ident,
        construction=entity.construction,
        kind="circle",
        center=entity.center,
        radius=new_r,
    )


def _offset_arc(entity: SketchArc, distance: float, ident: str) -> SketchArc:
    c = _pt(entity.center)
    s = _pt(entity.start)
    e = _pt(entity.end)
    r = _dist(c, s)
    if r < _TOL:
        raise SketchEditError(
            "cannot offset a degenerate (zero-radius) arc",
            code="sketch_degenerate_result",
        )
    new_r = r - distance  # +distance = inward (CCW left normal)
    if new_r <= _TOL:
        raise SketchEditError(
            "inward offset collapses the arc (radius <= 0)",
            code="sketch_degenerate_result",
        )
    scale = new_r / r  # exact radial rescale — preserves the angular span
    return SketchArc(
        id=ident,
        construction=entity.construction,
        kind="arc",
        center=entity.center,
        start=_point2d(_V(c.x + (s.x - c.x) * scale, c.y + (s.y - c.y) * scale)),
        end=_point2d(_V(c.x + (e.x - c.x) * scale, c.y + (e.y - c.y) * scale)),
    )


def offset_sketch(
    entities: list[SketchEntity], target_id: str, distance: float
) -> list[SketchEntity]:
    """Return the NEW offset entity/entities (the source is left unchanged).

    Offset ADDS a parallel copy of ``target_id`` at the signed ``distance``
    (see this module's Offset section for the left-hand-normal sign
    convention). The result is the newly created entity only, with a fresh
    deterministic id ``f"{target}.{n}"`` and the source's construction flag
    inherited; the caller appends it to its own entity list.
    """
    target = _find_target(entities, target_id)
    if not math.isfinite(distance) or abs(distance) < _TOL:
        raise SketchEditError(
            "offset distance must be a nonzero, finite value",
            code="sketch_offset_zero_distance",
        )
    ident = _fresh_id(target_id, {e.id for e in entities})
    new: SketchEntity
    if isinstance(target, SketchLine):
        new = _offset_line(target, distance, ident)
    elif isinstance(target, SketchCircle):
        new = _offset_circle(target, distance, ident)
    elif isinstance(target, SketchArc):
        new = _offset_arc(target, distance, ident)
    else:
        raise SketchEditError(
            f"offset does not support a {target.kind!r} entity "
            "(only line, arc and circle have a parallel offset)",
            code="sketch_unsupported_entity",
        )
    return [new]


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------


def _find_target(entities: list[SketchEntity], target_id: str) -> SketchEntity:
    for e in entities:
        if e.id == target_id:
            return e
    raise SketchEditError(
        f"target entity {target_id!r} is not in the sketch",
        code="sketch_target_not_found",
    )


def _splice(
    entities: list[SketchEntity], target_id: str, replacement: list[SketchEntity]
) -> list[SketchEntity]:
    """Replace the target in place with ``replacement`` (may be 0, 1 or 2)."""
    out: list[SketchEntity] = []
    for e in entities:
        if e.id == target_id:
            out.extend(replacement)
        else:
            out.append(e)
    return out
