"""Roof members through wall sheathing: the exact overlap, and the notches
(ROOF-HIP-SHEATHING-NOTCH, ROOF-THROUGH-SHEATHING-UPDATE, RESEARCH §23).

A roof's heel sits on the framing's outside face, so each tail, and each
hip's tail over a corner, passes through the wall's sheathing below the
plate's top. Framers notch the sheathing round them, as a Revit wall
attached to a roof is cut by it. This module reads both sides from their
EXPANDED members (never the plugins' layouts), so it measures any roof
release on any wall release the same way:

* a roof BODY is an extrude of a side profile, either on an axis plane
  (``YZ``/``XZ`` or an offset of one; a rafter, common, jack) or on a
  midplane datum extruded symmetric (a hip or valley), and the booleans
  that trim it (an intersect with a plan prism: a jack's cheek, a hip's
  double cheeks; a subtract: a hip's seat);
* a wall's sheathing PANEL is an extrude of a rectilinear outline on an
  axis plane: a box in the world with its openings cut out.

:func:`overlap` is the shared volume of one body and one panel, exactly:
the body's profile is clipped to the panel's height, and its area across the
panel's plan is integrated over the body's thickness. That area is
quadratic between the thickness stations where a bound passes a profile
corner, so Simpson's rule on each piece is exact. A trim that cuts the body
INSIDE the panel's plan (partly) is not modelled: the overlap says so
(:class:`Partial`) rather than guess.

:func:`notches` is what roof 1.5.0 adds: for each body, one cut of the
body's own section by the body's own extrude, from exactly the panels it
overlaps (Objects To Cut). The cut equals the body wherever it meets those
panels when no trim acts there, which is checked per pair; the panel then
meets the member face to face, with no shared volume and nothing more
removed.
"""

import itertools
import math
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from loft_wire.expr import Quantity
from loft_wire.features import (
    AuthoredEnvelope,
    BooleanFeature,
    CustomFeature,
    DatumFeature,
    DatumMidplaneParams,
    DatumOffsetParams,
    DatumPlaneRef,
    ExpandedMember,
    ExtrudeFeature,
    ExtrudeParamsV1,
    FeatureRef,
    SketchFeature,
)
from loft_wire.lumber import MM_PER_INCH
from loft_wire.plugins import member_id
from loft_wire.sketch import SketchLine

from loft_plugins.api import ExpandInputs, Member, PluginError
from loft_plugins.builtin.house import stored_inputs, wall_outline

Vec2 = tuple[float, float]
Loop = tuple[Vec2, ...]

#: The roles whose extrudes are roof bodies (every roof release's).
BODY_ROLES = frozenset(
    {"rafter", "common", "jack", "valley_jack", "cripple", "hip", "valley"}
)
#: A shared volume below this (in^3) is none: float noise at a face.
MIN_OVERLAP_IN3 = 1e-6
#: Relative slack when a trim's plan is compared with a region's.
_AREA_TOL = 1e-9
_R2 = math.sqrt(2.0)


class Partial(Exception):
    """A trim (or an opening in the panel) cuts the body inside the panel's
    plan only partly: the overlap there is not a clipped prism."""


# --- Plane geometry ----------------------------------------------------------------


def _area(poly: Sequence[Vec2]) -> float:
    total = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return total / 2


def _clip(poly: Sequence[Vec2], a: float, b: float, c: float) -> list[Vec2]:
    """*poly* less the part where ``a x + b y > c`` (Sutherland-Hodgman: a
    non-convex polygon may come back with zero-width bridges, whose area is
    nil, so its area is still exact)."""
    out: list[Vec2] = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp = a * p[0] + b * p[1] - c
        fq = a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _clip_box(poly: Sequence[Vec2], lo: Vec2, hi: Vec2) -> list[Vec2]:
    out = list(poly)
    for a, b, c in ((-1, 0, -lo[0]), (1, 0, hi[0]), (0, -1, -lo[1]), (0, 1, hi[1])):
        if not out:
            return out
        out = _clip(out, a, b, c)
    return out


def _clip_convex(poly: Sequence[Vec2], window: Sequence[Vec2]) -> list[Vec2]:
    """*poly* (any simple polygon) within the convex *window*."""
    w = list(window) if _area(window) > 0 else list(reversed(window))
    out = list(poly)
    for i in range(len(w)):
        if not out:
            return out
        (x0, y0), (x1, y1) = w[i], w[(i + 1) % len(w)]
        # Inside is the left of each counter-clockwise edge.
        a, b = y1 - y0, -(x1 - x0)
        out = _clip(out, a, b, a * x0 + b * y0)
    return out


# --- Bodies and panels ------------------------------------------------------------


@dataclass(frozen=True)
class Trim:
    """A boolean on a body with a plan prism: its outline and its Z span."""

    operation: Literal["intersect", "subtract"]
    outline: Loop
    z0: float
    z1: float


@dataclass(frozen=True)
class Body:
    """A side profile ``(s, z)`` swept across ``w0..w1``: plan point
    ``origin + s e_s + w e_w`` (inches), and the trims on it."""

    id: uuid.UUID
    role: str
    name: str | None
    feature: ExtrudeFeature
    origin: Vec2
    e_s: Vec2
    e_w: Vec2
    w0: float
    w1: float
    profile: Loop
    trims: tuple[Trim, ...]

    def point(self, s: float, w: float) -> Vec2:
        return (
            self.origin[0] + s * self.e_s[0] + w * self.e_w[0],
            self.origin[1] + s * self.e_s[1] + w * self.e_w[1],
        )

    def bounds(self) -> tuple[Vec2, Vec2, float, float]:
        ss = [s for s, _ in self.profile]
        zs = [z for _, z in self.profile]
        pts = [self.point(s, w) for s in (min(ss), max(ss)) for w in (self.w0, self.w1)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys)), (max(xs), max(ys)), min(zs), max(zs)


@dataclass(frozen=True)
class Panel:
    """A sheathing panel: its plan box and Z span (inches), the plan axis
    its sketch runs along, and its outline loops in ``(along, z)``."""

    id: uuid.UUID
    lo: Vec2
    hi: Vec2
    z0: float
    z1: float
    along: int
    loops: tuple[Loop, ...]


Features = Mapping[uuid.UUID, AuthoredEnvelope]


def _loops(sketch: SketchFeature) -> list[Loop]:
    """A sketch's closed loops of lines, in inches."""
    loops: list[Loop] = []
    current: list[Vec2] = []
    first: Vec2 | None = None
    for entity in sketch.params.entities:
        if not isinstance(entity, SketchLine):
            continue
        start = (entity.start.x / MM_PER_INCH, entity.start.y / MM_PER_INCH)
        end = (entity.end.x / MM_PER_INCH, entity.end.y / MM_PER_INCH)
        if first is None:
            first = start
        current.append(start)
        if math.dist(end, first) < 1e-9:
            loops.append(tuple(current))
            current, first = [], None
    return loops


def _axis_plane(
    ref: DatumPlaneRef | FeatureRef, features: Features
) -> tuple[str, float] | None:
    """An origin plane or an unflipped offset of one: (base, offset in)."""
    if isinstance(ref, DatumPlaneRef):
        return ref.plane, 0.0
    datum = features.get(ref.feature_id)
    if not isinstance(datum, DatumFeature):
        return None
    params = datum.params
    if not isinstance(params, DatumOffsetParams) or params.flip:
        return None
    return params.base, params.offset_mm / MM_PER_INCH


def _plane_of(ref: object, features: Features) -> tuple[str, float, bool] | None:
    """An origin plane or an offset of one (flip kept): (base, in, flip)."""
    if isinstance(ref, DatumPlaneRef):
        return ref.plane, 0.0, False
    if not isinstance(ref, FeatureRef):
        return None
    datum = features.get(ref.feature_id)
    if not isinstance(datum, DatumFeature) or not isinstance(
        datum.params, DatumOffsetParams
    ):
        return None
    p = datum.params
    return p.base, p.offset_mm / MM_PER_INCH, p.flip


def _sketch(ref: FeatureRef, features: Features) -> SketchFeature | None:
    sketch = features.get(ref.feature_id)
    return sketch if isinstance(sketch, SketchFeature) else None


def _span(off: float, distance: float, direction: str) -> tuple[float, float]:
    d = -distance if direction == "reverse" else distance
    return (min(off, off + d), max(off, off + d))


def _body(
    member_id_: uuid.UUID,
    role: str,
    name: str | None,
    feature: ExtrudeFeature,
    features: Features,
    trims: tuple[Trim, ...],
) -> Body | None:
    params = feature.params
    sketch = _sketch(params.profile, features)
    if sketch is None:
        return None
    loops = _loops(sketch)
    if len(loops) != 1:
        return None
    pts = loops[0]
    distance = params.distance_mm / MM_PER_INCH
    plane = sketch.params.plane
    if isinstance(plane, FeatureRef):
        datum = features.get(plane.feature_id)
        if isinstance(datum, DatumFeature) and isinstance(
            datum.params, DatumMidplaneParams
        ):
            if params.extent != "symmetric":
                return None
            a = _plane_of(datum.params.a, features)
            b = _plane_of(datum.params.b, features)
            if a is None or b is None or a[0] != "YZ" or b[0] != "XZ" or a[2]:
                return None
            # Geometry's bisector of YZ at X a (normal +X) and XZ at Y -b
            # (normal -Y, +Y flipped): normal (1, ny)/sqrt 2, origin on both,
            # x_dir +Z, y_dir normal x Z = (ny, -1)/sqrt 2 (roof._hip_outline).
            ny = 1.0 if b[2] else -1.0
            return Body(
                member_id_,
                role,
                name,
                feature,
                (a[1], -b[1]),
                (ny / _R2, -1.0 / _R2),
                (1.0 / _R2, ny / _R2),
                -distance / 2,
                distance / 2,
                tuple((y, x) for x, y in pts),
                trims,
            )
    axis = _axis_plane(plane, features)
    if axis is None or params.extent != "one_side":
        return None
    base, off = axis
    if base == "YZ":  # sketch x is world Y; extruded along +X
        w0, w1 = _span(off, distance, params.direction)
        return Body(
            member_id_,
            role,
            name,
            feature,
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 0.0),
            w0,
            w1,
            pts,
            trims,
        )
    if base == "XZ":  # sketch x is world X; the normal is -Y
        w0, w1 = _span(-off, -distance, params.direction)
        return Body(
            member_id_,
            role,
            name,
            feature,
            (0.0, 0.0),
            (1.0, 0.0),
            (0.0, 1.0),
            w0,
            w1,
            pts,
            trims,
        )
    return None


def _trim(tool: FeatureRef, operation: str, features: Features) -> Trim | None:
    prism = features.get(tool.feature_id)
    if not isinstance(prism, ExtrudeFeature) or operation not in (
        "intersect",
        "subtract",
    ):
        return None
    sketch = _sketch(prism.params.profile, features)
    if sketch is None:
        return None
    level = _axis_plane(sketch.params.plane, features)
    loops = _loops(sketch)
    if level is None or level[0] != "XY" or len(loops) != 1:
        return None
    if prism.params.extent != "one_side":
        return None
    z0, z1 = _span(
        level[1], prism.params.distance_mm / MM_PER_INCH, prism.params.direction
    )
    return Trim(
        "intersect" if operation == "intersect" else "subtract", loops[0], z0, z1
    )


@dataclass(frozen=True)
class RoofMember:
    """One member of a roof's expansion: its id, role, name and feature."""

    id: uuid.UUID
    role: str
    name: str | None
    feature: AuthoredEnvelope


def roof_bodies(members: Sequence[RoofMember], earlier: Features) -> list[Body]:
    """Every body of a roof's expansion, with its trims (module docstring).
    A body this cannot read (another plane, a profile of several loops) is
    left out: the overlap then under-counts, never invents."""
    own: dict[uuid.UUID, AuthoredEnvelope] = {m.id: m.feature for m in members}
    features: Mapping[uuid.UUID, AuthoredEnvelope] = _Chain(own, earlier)
    trims: dict[uuid.UUID, list[Trim]] = {}
    for m in members:
        f = m.feature
        if isinstance(f, BooleanFeature):
            trim = _trim(f.params.tool, f.params.operation, features)
            if trim is not None:
                trims.setdefault(f.params.target.feature_id, []).append(trim)
    out: list[Body] = []
    for m in members:
        f = m.feature
        if m.role not in BODY_ROLES or not isinstance(f, ExtrudeFeature):
            continue
        if f.params.operation != "add":
            continue
        body = _body(m.id, m.role, m.name, f, features, tuple(trims.get(m.id, ())))
        if body is not None:
            out.append(body)
    return out


class _Chain(Mapping[uuid.UUID, AuthoredEnvelope]):
    def __init__(self, *maps: Mapping[uuid.UUID, AuthoredEnvelope]) -> None:
        self._maps = maps

    def __getitem__(self, key: uuid.UUID) -> AuthoredEnvelope:
        for m in self._maps:
            if key in m:
                return m[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[uuid.UUID]:
        seen: set[uuid.UUID] = set()
        for m in self._maps:
            for key in m:
                if key not in seen:
                    seen.add(key)
                    yield key

    def __len__(self) -> int:
        return len(set(self))


def _panel(panel_id: uuid.UUID, features: Features) -> Panel | None:
    body = features.get(panel_id)
    if not isinstance(body, ExtrudeFeature) or body.params.extent != "one_side":
        return None
    sketch = _sketch(body.params.profile, features)
    if sketch is None:
        return None
    axis = _axis_plane(sketch.params.plane, features)
    loops = _loops(sketch)
    if axis is None or not loops:
        return None
    base, off = axis
    xs = [x for loop in loops for x, _ in loop]
    zs = [z for loop in loops for _, z in loop]
    distance = body.params.distance_mm / MM_PER_INCH
    if base == "YZ":
        x0, x1 = _span(off, distance, body.params.direction)
        lo, hi, along = (x0, min(xs)), (x1, max(xs)), 1
    elif base == "XZ":
        y0, y1 = _span(-off, -distance, body.params.direction)
        lo, hi, along = (min(xs), y0), (max(xs), y1), 0
    else:
        return None
    return Panel(panel_id, lo, hi, min(zs), max(zs), along, tuple(loops))


def _names(prefix: str, features: Features, wall_id: uuid.UUID) -> Iterator[uuid.UUID]:
    """Every sheathing panel a wall emitted under *prefix*: its columns and
    rows from 0 while they exist, its corner rips and returns."""
    col = 0
    while True:
        row = 0
        while True:
            pid = member_id(wall_id, "sheathing", 0, f"{prefix}exterior/{col}/{row}")
            if pid not in features:
                break
            yield pid
            row += 1
        if row == 0:
            break
        col += 1
    for kind in ("corner", "return"):
        for end in ("start", "end"):
            pid = member_id(wall_id, "sheathing", 0, f"{prefix}{kind}/{end}")
            if pid in features:
                yield pid


def wall_panels(
    wall_ids: Iterable[uuid.UUID],
    earlier: Features,
    parameters: Mapping[str, Quantity] | None = None,
) -> list[Panel]:
    """The sheathing panels of the ``loft.wall`` features *wall_ids* (any
    release; a line wall's or each outline line's), read from their members
    in *earlier*."""
    out: list[Panel] = []
    for wall_id in wall_ids:
        envelope = earlier.get(wall_id)
        if (
            not isinstance(envelope, CustomFeature)
            or envelope.params.plugin_id != "loft.wall"
        ):
            continue
        prefixes = [""]
        if envelope.params.inputs.get("outline") is not None:
            try:
                outline = wall_outline(
                    stored_inputs(
                        wall_id,
                        envelope,
                        earlier,
                        parameters,
                    )
                )
            except PluginError:
                outline = None
            if outline is not None:
                prefixes = [f"{s.line_id}/" for s in outline.segments]
        for prefix in prefixes:
            for pid in _names(prefix, earlier, wall_id):
                panel = _panel(pid, earlier)
                if panel is not None:
                    out.append(panel)
    return out


# --- The overlap -------------------------------------------------------------------


@dataclass(frozen=True)
class Overlap:
    """One body's shared volume with one panel (in^3), and whether the
    body's untrimmed sweep is the body throughout the panel (a cut by it
    then removes exactly the overlap)."""

    volume: float
    untrimmed: bool


def _intrudes(panel: Panel, a: float, b: float, z0: float, z1: float) -> bool:
    """Whether an edge of the panel's outline (an opening) enters the open
    box ``(a, b) x (z0, z1)`` of its ``(along, z)``, the outer top excluded."""
    for loop in panel.loops:
        n = len(loop)
        for i in range(n):
            (x0, y0), (x1, y1) = loop[i], loop[(i + 1) % n]
            if y0 == y1:
                if (
                    z0 + 1e-9 < y0 < z1 - 1e-9
                    and min(b, max(x0, x1)) - max(a, min(x0, x1)) > 1e-9
                ):
                    return True
            elif (
                a + 1e-9 < x0 < b - 1e-9
                and min(z1, max(y0, y1)) - max(z0, min(y0, y1)) > 1e-9
            ):
                return True
    return False


def overlap(body: Body, panel: Panel) -> Overlap:
    """The exact shared volume of *body* and *panel* (module docstring).
    Raises :class:`Partial` where a trim or an opening cuts the body inside
    the panel's plan only partly."""
    z0, z1 = panel.z0, panel.z1
    untrimmed = True
    for _ in range(2):  # a seat that removes the body's bottom: once more
        q = _clip(_clip(list(body.profile), 0, -1, -z0), 0, 1, z1)
        if not q or abs(_area(q)) < 1e-12:
            return Overlap(0.0, untrimmed)
        ss = [s for s, _ in q]
        zq0, zq1 = min(z for _, z in q), max(z for _, z in q)
        rect = [
            body.point(min(ss), body.w0),
            body.point(max(ss), body.w0),
            body.point(max(ss), body.w1),
            body.point(min(ss), body.w1),
        ]
        region = _clip_box(rect, panel.lo, panel.hi)
        whole = abs(_area(region)) if len(region) >= 3 else 0.0
        if whole < 1e-12:
            return Overlap(0.0, untrimmed)
        raised = z0
        for trim in body.trims:
            met = _clip_convex(trim.outline, region)
            part = abs(_area(met)) if len(met) >= 3 else 0.0
            none = part <= _AREA_TOL * whole + 1e-12
            full = part >= whole * (1 - _AREA_TOL) - 1e-12
            if trim.operation == "intersect":
                if none:
                    return Overlap(0.0, untrimmed)
                if not full or trim.z0 > zq0 + 1e-9 or trim.z1 < zq1 - 1e-9:
                    raise Partial(f"an intersect trims body {body.id} in the panel")
                continue
            if none or trim.z1 <= zq0 + 1e-9 or trim.z0 >= zq1 - 1e-9:
                continue
            if not full or trim.z0 > zq0 + 1e-9:
                raise Partial(f"a subtract trims body {body.id} in the panel")
            untrimmed = False
            raised = max(raised, trim.z1)
        if raised == z0:
            break
        z0 = raised
    else:  # pragma: no cover - two seats stacked
        raise Partial(f"body {body.id}: stacked subtracts")
    along = [p[panel.along] for p in region]
    if _intrudes(panel, min(along), max(along), zq0, z1):
        raise Partial(f"an opening in panel {panel.id} meets body {body.id}")
    return Overlap(_integrate(body, q, panel.lo, panel.hi), untrimmed)


def _integrate(body: Body, q: list[Vec2], lo: Vec2, hi: Vec2) -> float:
    """``int A(w) dw`` over the body's thickness: ``A(w)`` the area of the
    profile *q* (already clipped to the panel's Z) between the s-bounds the
    panel's plan box sets at *w*. Exact: Simpson on each piece between the
    stations where ``A`` may bend."""
    o, es, ew = body.origin, body.e_s, body.e_w
    wlo, whi = body.w0, body.w1
    lowers: list[tuple[float, float]] = []  # s = p + k w
    uppers: list[tuple[float, float]] = []
    for k in (0, 1):
        if abs(es[k]) > 1e-12:
            a = ((lo[k] - o[k]) / es[k], -ew[k] / es[k])
            b = ((hi[k] - o[k]) / es[k], -ew[k] / es[k])
            (lowers if es[k] > 0 else uppers).append(a)
            (uppers if es[k] > 0 else lowers).append(b)
        elif abs(ew[k]) > 1e-12:
            ta, tb = (lo[k] - o[k]) / ew[k], (hi[k] - o[k]) / ew[k]
            wlo, whi = max(wlo, min(ta, tb)), min(whi, max(ta, tb))
        elif not lo[k] <= o[k] <= hi[k]:
            return 0.0
    if whi - wlo <= 1e-12:
        return 0.0
    stations = {wlo, whi}
    lines = lowers + uppers
    corners = {s for s, _ in q}
    for p, k in lines:
        if abs(k) > 1e-15:
            for s in corners:
                w = (s - p) / k
                if wlo < w < whi:
                    stations.add(w)
    for i, (p1, k1) in enumerate(lines):
        for p2, k2 in lines[i + 1 :]:
            if abs(k1 - k2) > 1e-15:
                w = (p2 - p1) / (k1 - k2)
                if wlo < w < whi:
                    stations.add(w)

    def area(w: float) -> float:
        cut = list(q)
        if lowers:
            cut = _clip(cut, -1, 0, -max(p + k * w for p, k in lowers))
        if uppers and cut:
            cut = _clip(cut, 1, 0, min(p + k * w for p, k in uppers))
        return abs(_area(cut)) if len(cut) >= 3 else 0.0

    ws = sorted(stations)
    total = 0.0
    for a, b in itertools.pairwise(ws):
        if b - a > 1e-15:
            total += (b - a) / 6 * (area(a) + 4 * area((a + b) / 2) + area(b))
    return total


def _boxes_meet(body: Body, panel: Panel) -> bool:
    lo, hi, z0, z1 = body.bounds()
    return (
        min(hi[0], panel.hi[0]) - max(lo[0], panel.lo[0]) > 1e-9
        and min(hi[1], panel.hi[1]) - max(lo[1], panel.lo[1]) > 1e-9
        and min(z1, panel.z1) - max(z0, panel.z0) > 1e-9
    )


@dataclass(frozen=True)
class Pair:
    body: Body
    panel: Panel
    overlap: Overlap


def pairs(bodies: Sequence[Body], panels: Sequence[Panel]) -> list[Pair]:
    """Every (body, panel) that share more than :data:`MIN_OVERLAP_IN3`.
    Raises :class:`Partial` as :func:`overlap` does."""
    out: list[Pair] = []
    for body in bodies:
        for panel in panels:
            if not _boxes_meet(body, panel):
                continue
            found = overlap(body, panel)
            if found.volume > MIN_OVERLAP_IN3:
                out.append(Pair(body, panel, found))
    return out


# --- Roof 1.5.0's notches ----------------------------------------------------------


def notches(
    inputs: ExpandInputs,
    members: Sequence[Member],
    wall_ids: Sequence[uuid.UUID],
    refuse: str,
) -> list[Member]:
    """Roof 1.5.0's cuts: each body's own section, extruded as the body is,
    cut from exactly the picked walls' panels it overlaps (module
    docstring), named ``tail/<role>/<body name>``. Where a body's trim acts
    inside a panel it overlaps, the cut would not be the body there, so the
    roof is refused (*refuse* names the input), never notched wrong."""
    if not wall_ids:
        return []
    panels = wall_panels(wall_ids, inputs.earlier, inputs.parameters)
    if not panels:
        return []
    own = [
        RoofMember(
            inputs.ref(m.role, m.index, m.name).feature_id, m.role, m.name, m.feature
        )
        for m in members
    ]
    bodies = roof_bodies(own, inputs.earlier)
    try:
        found = pairs(bodies, panels)
    except Partial as exc:
        raise PluginError(
            "plugin_input_unsupported",
            "The roof meets the wall sheathing where a member is cheek-cut or "
            "seated; notching it there is a later rung (ROOF-VALLEY-SHEATHING-"
            f"NOTCH). ({exc})",
            input=refuse,
        ) from exc
    by_body: dict[uuid.UUID, list[Pair]] = {}
    for pair in found:
        if not pair.overlap.untrimmed:
            raise PluginError(
                "plugin_input_unsupported",
                "A seated member meets the wall sheathing; notching it is a later "
                "rung (ROOF-VALLEY-SHEATHING-NOTCH).",
                input=refuse,
            )
        by_body.setdefault(pair.body.id, []).append(pair)
    used = sum(1 for m in members if m.role == "cutter")
    out: list[Member] = []
    for body in bodies:
        hits = by_body.get(body.id)
        if not hits:
            continue
        params = body.feature.params
        out.append(
            Member(
                "cutter",
                used + len(out),
                ExtrudeFeature(
                    type="extrude",
                    version=1,
                    params=ExtrudeParamsV1(
                        profile=params.profile,
                        distance_mm=params.distance_mm,
                        operation="cut",
                        direction=params.direction,
                        extent=params.extent,
                        cut_bodies=[
                            FeatureRef(kind="feature", feature_id=p.panel.id)
                            for p in hits
                        ],
                    ),
                ),
                name=f"tail/{body.role}/{body.name}",
            )
        )
    return out


# --- The warning on a stored roof --------------------------------------------------


@dataclass(frozen=True)
class Through:
    """What a stored roof shares with the wall sheathing: the volume (in^3),
    the (member, panel) pairs, and whether a trim made a pair approximate."""

    volume: float
    pairs: int
    approximate: bool


def _notched(members: Sequence[ExpandedMember]) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """(section, panel) pairs the roof's own cuts already notch."""
    out: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for m in members:
        f = m.feature
        if isinstance(f, ExtrudeFeature) and f.params.operation == "cut":
            scope = f.params.cut_bodies
            if isinstance(scope, list):
                for target in scope:
                    out.add((f.params.profile.feature_id, target.feature_id))
    return out


def through_sheathing(
    members: Sequence[ExpandedMember],
    earlier: Features,
    parameters: Mapping[str, Quantity] | None = None,
) -> Through:
    """The overlap of a stored roof's members with every earlier wall's
    sheathing, less what its own cuts notch (any roof release: 1.0-1.3 run
    their tails through the OSB; 1.4.0 on an outline notches a gable's)."""
    walls = [
        fid
        for fid, env in earlier.items()
        if isinstance(env, CustomFeature) and env.params.plugin_id == "loft.wall"
    ]
    panels = wall_panels(walls, earlier, parameters)
    if not panels:
        return Through(0.0, 0, False)
    own = [RoofMember(m.id, m.role, m.name, m.feature) for m in members]
    bodies = roof_bodies(own, earlier)
    done = _notched(members)
    volume, count, approximate = 0.0, 0, False
    for body in bodies:
        for panel in panels:
            if not _boxes_meet(body, panel):
                continue
            if (body.feature.params.profile.feature_id, panel.id) in done:
                continue
            try:
                found = overlap(body, panel).volume
            except Partial:
                approximate = True
                # The sweep and the box, untrimmed: an upper bound.
                found = overlap(
                    replace(body, trims=()), replace(panel, loops=())
                ).volume
            if found > MIN_OVERLAP_IN3:
                volume += found
                count += 1
    return Through(volume, count, approximate)
