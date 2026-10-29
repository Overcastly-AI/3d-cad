"""House drawings: the plan's horizontal section and the elevations (HOUSE-DRAWINGS).

Revit cuts a floor plan 4'-0" above its level; Chief Architect dimensions the
exterior walls to the opening centres on its own. Given an evaluated part (its
bodies, each keyed by the base feature that built it) and its plugin members
(which body is a subfloor, a header, a top plate), this module produces:

* the ``plan``: every body the plane 48 in above the lowest floor passes
  through, cut, as canonical 2D loops (the outline drawn, the loops hatched)
  plus the exterior dimension strings: the overall framing on every side, and
  on a side with openings a string from corner to each opening's centre to
  corner;
* an ``elevation_*``: the part seen from outside one wall (visible lines only,
  as a builder's elevation has no hidden lines), dimensioning each distinct
  opening head and the wall plate above the floor.

The house is a building on a rectangular footprint, and a side is the side of
the framing's plan extent. A part with no plugin members still cuts (48 in
above its lowest point) and still elevates; it simply has no strings.

Performance: a house is ~450 bodies. The plan does not boolean the whole
compound: it cuts only the bodies whose box straddles the plane, and a body
that is its own box (a stud, a plate, every dimensioned lumber member) is cut
analytically, with no boolean at all. The elevations reuse the shipped exact
HLR (``project_view``) on the part's compound once per view.

Kernel-only (CLAUDE.md): the results are the neutral DTOs of
:mod:`loft_wire.drawings`; deterministic (RESEARCH §9): loops and edges are
emitted in a canonical order that is a pure function of the geometry.
"""
# The OCP wheel ships no stubs; scope the relaxation to this file (section.py's).
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportPrivateUsage=false

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from build123d import Face, Plane, Vector
from loft_wire.drawing_house import (
    PLAN_CUT_HEIGHT_MM,
    AutoDimensionPoint,
    DimensionSide,
    DrawingMember,
    ViewAutoDimension,
)
from loft_wire.drawings import (
    DrawingViewResult,
    ProjectedPoint,
    ProjectedViewEdge,
    SectionFaceLoop,
    ViewProjection,
    ViewScale,
)
from loft_wire.features import FeatureError
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from geometry.drawings.project import Point2D, ViewDirection, project_point
from geometry.drawings.section import _canonical_loop, _signed_area
from geometry.kernel.types import BodyShape

#: The plan view kind, and the elevations by the wall they look at.
PLAN_VIEW: ViewProjection = "plan"
MATERIALS_VIEW: ViewProjection = "materials"
ELEVATION_DIRECTIONS: dict[ViewProjection, ViewDirection] = {
    "elevation_front": "front",
    "elevation_back": "back",
    "elevation_left": "left",
    "elevation_right": "right",
}

#: The side of the plan each elevation's wall is on (front is -Y, below).
_ELEVATION_SIDE: dict[ViewProjection, DimensionSide] = {
    "elevation_front": "below",
    "elevation_back": "above",
    "elevation_left": "left",
    "elevation_right": "right",
}

#: A floor's walking surface: the subfloor (any plugin) or a slab-on-grade
#: (``loft.slab``; a door's ``slab`` is its leaf, not a floor).
_FLOOR_ROLES = frozenset({"subfloor"})
_SLAB_PLUGIN = "loft.slab"

#: The wall framing (the plan's overall dimensions are its extent): every
#: lumber member of a wall, but no sheathing, finish or unit.
FRAMING_ROLES = frozenset(
    {
        "stud",
        "king",
        "jack",
        "header",
        "cripple",
        "sill",
        "sill_cripple",
        "top_plate",
        "bottom_plate",
        "block",
        "backing_stud",
    }
)
#: A floor's sill plate is a ``sill`` too, but under the walls, not in them.
_NOT_FRAMING_PLUGINS = frozenset({"loft.floor", "loft.deck", "loft.foundation"})

#: The members under the cut a plan draws beyond it (seen from above).
_BEYOND_ROLES = frozenset({"bottom_plate", "sill"})

#: A header within this of a side of the framing is in that side's wall (mm);
#: a header further in is an interior opening and gets no exterior string.
_WALL_BAND_MM = 12 * 25.4

#: Opening centres closer than this are one opening (a header's plies, mm).
_SAME_OPENING_MM = 0.5 * 25.4

#: Heights within this are one dimension (1/32 in, under the print's 1/16).
_SAME_HEIGHT_MM = 25.4 / 32

#: A body is its own box when its volume is the box's to this relative
#: tolerance (the cut list's prism test): it is cut analytically.
_BOX_TOLERANCE = 1e-9


@dataclass(frozen=True)
class _Box:
    """A body's world bounding box (mm)."""

    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float


def _box(body: BodyShape) -> _Box:
    bb = body.bounding_box()
    return _Box(bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


@dataclass(frozen=True)
class HouseFacts:
    """What the strings measure, read from the bodies by their roles (mm)."""

    floor_z: float
    framing: _Box | None
    #: Opening centres per side: along X for below/above, along Y for left/right.
    openings: Mapping[DimensionSide, tuple[float, ...]]
    #: Distinct opening head heights per side (header undersides, world Z).
    heads: Mapping[DimensionSide, tuple[float, ...]]
    plate_z: float | None
    #: The plates and rough sills under the cut, which a plan draws beyond it
    #: (the wall's inside line between the studs, the window sills).
    beyond: tuple[_Box, ...] = ()


def _roles(members: Sequence[DrawingMember]) -> dict[uuid.UUID, DrawingMember]:
    return {m.feature_id: m for m in members}


def _is_floor(member: DrawingMember) -> bool:
    return member.role in _FLOOR_ROLES or (
        member.role == "slab" and member.plugin_id == _SLAB_PLUGIN
    )


def _is_framing(member: DrawingMember) -> bool:
    return member.role in FRAMING_ROLES and member.plugin_id not in _NOT_FRAMING_PLUGINS


def _distinct(values: Iterable[float], tol: float) -> tuple[float, ...]:
    """*values* sorted, each run of near-equal values kept once (its first)."""
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return tuple(out)


def _side_of(box: _Box, framing: _Box) -> DimensionSide | None:
    """The exterior wall a header is in, or None for an interior one."""
    cx = (box.x0 + box.x1) / 2
    cy = (box.y0 + box.y1) / 2
    along_x = (box.x1 - box.x0) >= (box.y1 - box.y0)
    if along_x:
        if cy - framing.y0 <= _WALL_BAND_MM:
            return "below"
        if framing.y1 - cy <= _WALL_BAND_MM:
            return "above"
        return None
    if cx - framing.x0 <= _WALL_BAND_MM:
        return "left"
    if framing.x1 - cx <= _WALL_BAND_MM:
        return "right"
    return None


def house_facts(
    bodies: Mapping[uuid.UUID, BodyShape], members: Sequence[DrawingMember]
) -> HouseFacts:
    """Read the floor level, the framing extent, the openings and the plate."""
    by_id = _roles(members)
    boxes = {bid: _box(body) for bid, body in bodies.items()}
    floors = [boxes[b].z1 for b in boxes if b in by_id and _is_floor(by_id[b])]
    lowest = min((box.z0 for box in boxes.values()), default=0.0)
    floor_z = min(floors) if floors else lowest
    framing_boxes = [boxes[b] for b in boxes if b in by_id and _is_framing(by_id[b])]
    framing = (
        _Box(
            min(b.x0 for b in framing_boxes),
            min(b.y0 for b in framing_boxes),
            min(b.z0 for b in framing_boxes),
            max(b.x1 for b in framing_boxes),
            max(b.y1 for b in framing_boxes),
            max(b.z1 for b in framing_boxes),
        )
        if framing_boxes
        else None
    )
    centres: dict[DimensionSide, list[float]] = {}
    heads: dict[DimensionSide, list[float]] = {}
    plates = [boxes[b].z1 for b in boxes if b in by_id and by_id[b].role == "top_plate"]
    if framing is not None:
        for bid, box in boxes.items():
            member = by_id.get(bid)
            if member is None or member.role != "header":
                continue
            side = _side_of(box, framing)
            if side is None:
                continue
            along = (
                (box.x0 + box.x1) / 2
                if side in ("below", "above")
                else (box.y0 + box.y1) / 2
            )
            centres.setdefault(side, []).append(along)
            heads.setdefault(side, []).append(box.z0)
    cut_z = floor_z + PLAN_CUT_HEIGHT_MM
    beyond = tuple(
        sorted(
            (
                boxes[b]
                for b in boxes
                if b in by_id
                and _is_framing(by_id[b])
                and by_id[b].role in _BEYOND_ROLES
                and boxes[b].z1 < cut_z
            ),
            key=lambda bx: (bx.x0, bx.y0, bx.z0),
        )
    )
    return HouseFacts(
        beyond=beyond,
        floor_z=floor_z,
        framing=framing,
        openings={s: _distinct(v, _SAME_OPENING_MM) for s, v in centres.items()},
        heads={s: _distinct(v, _SAME_HEIGHT_MM) for s, v in heads.items()},
        plate_z=max(plates) if plates else None,
    )


# --- the plan's cut ------------------------------------------------------------


def _box_loop(box: _Box, scale: float) -> tuple[Point2D, ...]:
    """A box's cut: its plan rectangle, CCW from its lowest-left corner."""
    pts = [
        project_point("top", (box.x0, box.y0, 0.0), scale),
        project_point("top", (box.x1, box.y0, 0.0), scale),
        project_point("top", (box.x1, box.y1, 0.0), scale),
        project_point("top", (box.x0, box.y1, 0.0), scale),
    ]
    if _signed_area(pts) < 0:
        pts.reverse()
    k = min(range(4), key=lambda i: (pts[i].x, pts[i].y))
    return tuple(pts[k:] + pts[:k])


def _is_own_box(body: BodyShape, box: _Box) -> bool:
    volume = (box.x1 - box.x0) * (box.y1 - box.y0) * (box.z1 - box.z0)
    return volume > 0 and abs(body.volume - volume) <= _BOX_TOLERANCE * volume


def _cut_faces(body: BodyShape, box: _Box, z: float) -> list[Face]:
    """The faces of *body* on the plane Z = *z* (a boolean common with a face)."""
    pad = 1.0 + (box.x1 - box.x0) + (box.y1 - box.y0)
    plane = Plane(origin=Vector((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, z))
    face = Face.make_rect(box.x1 - box.x0 + pad, box.y1 - box.y0 + pad, plane)
    op = BRepAlgoAPI_Common(body.wrapped, face.wrapped)
    op.Build()
    out: list[Face] = []
    if not op.IsDone():
        return out
    explorer = TopExp_Explorer(op.Shape(), TopAbs_FACE)
    while explorer.More():
        out.append(Face(TopoDS.Face_s(explorer.Current())))
        explorer.Next()
    return out


@dataclass(frozen=True)
class PlanCut:
    """The plan's section: its height and its canonical loops (view mm)."""

    z: float
    loops: tuple[tuple[tuple[Point2D, ...], tuple[tuple[Point2D, ...], ...]], ...]
    bodies_cut: int


def plan_cut(bodies: Mapping[uuid.UUID, BodyShape], z: float, scale: float) -> PlanCut:
    """Cut every body the plane Z = *z* passes through; canonical loops."""
    loops: list[tuple[tuple[Point2D, ...], tuple[tuple[Point2D, ...], ...]]] = []
    cut = 0
    for body in bodies.values():
        box = _box(body)
        if not box.z0 < z < box.z1:
            continue
        cut += 1
        if _is_own_box(body, box):
            loops.append((_box_loop(box, scale), ()))
            continue
        for face in _cut_faces(body, box, z):
            outer = _canonical_loop(face.outer_wire(), "top", scale, outer=True)
            holes = tuple(
                _canonical_loop(w, "top", scale, outer=False)
                for w in face.inner_wires()
            )
            loops.append((outer, holes))
    loops.sort(key=lambda lp: (lp[0][0].x, lp[0][0].y, len(lp[0])))
    return PlanCut(z=z, loops=tuple(loops), bodies_cut=cut)


def _point(p: Point2D) -> ProjectedPoint:
    return ProjectedPoint(x_mm=p.x, y_mm=p.y)


def _loop_edges(loop: Sequence[Point2D]) -> list[ProjectedViewEdge]:
    edges: list[ProjectedViewEdge] = []
    for i, a in enumerate(loop):
        b = loop[(i + 1) % len(loop)]
        if a == b:
            continue
        start, end = (a, b) if (a.x, a.y) <= (b.x, b.y) else (b, a)
        mid = Point2D((a.x + b.x) / 2, (a.y + b.y) / 2)
        edges.append(
            ProjectedViewEdge(
                primitive="line",
                visible=True,
                start=_point(start),
                end=_point(end),
                midpoint=_point(mid),
            )
        )
    return edges


# --- the automatic dimensions ----------------------------------------------------


def _auto(x: float, y: float, scale: float) -> AutoDimensionPoint:
    return AutoDimensionPoint(x_mm=x * scale, y_mm=y * scale)


def _string(
    side: DimensionSide,
    stations: Sequence[float],
    across: float,
    scale: float,
    tier: int,
) -> list[ViewAutoDimension]:
    """A chained string through *stations* (model mm along the side's axis) on
    the line *across* (model mm), each link one dimension."""
    horizontal = side in ("below", "above")
    out: list[ViewAutoDimension] = []
    for a, b in pairwise(stations):
        if b - a <= 0:
            continue
        start = _auto(a, across, scale) if horizontal else _auto(across, a, scale)
        end = _auto(b, across, scale) if horizontal else _auto(across, b, scale)
        out.append(
            ViewAutoDimension(
                start=start,
                end=end,
                axis="x" if horizontal else "y",
                side=side,
                tier=tier,
                value_mm=b - a,
            )
        )
    return out


def plan_dimensions(facts: HouseFacts, scale: float) -> list[ViewAutoDimension]:
    """The plan's exterior strings: to the opening centres, then overall."""
    f = facts.framing
    if f is None:
        return []
    out: list[ViewAutoDimension] = []
    sides: tuple[tuple[DimensionSide, float, float, float], ...] = (
        ("below", f.y0, f.x0, f.x1),
        ("above", f.y1, f.x0, f.x1),
        ("left", f.x0, f.y0, f.y1),
        ("right", f.x1, f.y0, f.y1),
    )
    for side, across, lo, hi in sides:
        centres = [c for c in facts.openings.get(side, ()) if lo < c < hi]
        if centres:
            out += _string(side, [lo, *centres, hi], across, scale, 0)
        out += _string(side, [lo, hi], across, scale, 1 if centres else 0)
    return out


def elevation_dimensions(
    facts: HouseFacts, view: ViewProjection, scale: float
) -> list[ViewAutoDimension]:
    """An elevation's heights above the floor: each opening head, then the plate."""
    f = facts.framing
    direction = ELEVATION_DIRECTIONS[view]
    if f is None:
        return []
    corners = [
        project_point(direction, (x, y, 0.0), 1.0)
        for x in (f.x0, f.x1)
        for y in (f.y0, f.y1)
    ]
    left = min(c.x for c in corners)
    heights = list(facts.heads.get(_ELEVATION_SIDE[view], ()))
    if facts.plate_z is not None:
        heights.append(facts.plate_z)
    out: list[ViewAutoDimension] = []
    for tier, z in enumerate(h for h in heights if h > facts.floor_z):
        out.append(
            ViewAutoDimension(
                start=_auto(left, facts.floor_z, scale),
                end=_auto(left, z, scale),
                axis="y",
                side="left",
                tier=tier,
                value_mm=z - facts.floor_z,
            )
        )
    return out


# --- the view results -----------------------------------------------------------


def plan_view_result(
    bodies: Mapping[uuid.UUID, BodyShape],
    facts: HouseFacts,
    scale: ViewScale,
    scale_value: float,
) -> DrawingViewResult:
    """The ``plan`` view: the cut 48 in above the lowest floor, hatched, with
    its exterior strings."""
    cut = plan_cut(bodies, facts.floor_z + PLAN_CUT_HEIGHT_MM, scale_value)
    if not cut.loops:
        return DrawingViewResult(
            view=PLAN_VIEW,
            scale=scale,
            error=FeatureError(
                code="section_plane_misses_body",
                message="Nothing stands 48 in above the lowest floor, so the plan "
                "cuts no walls; model the walls first.",
            ),
        )
    edges = (
        [e for outer, _ in cut.loops for e in _loop_edges(outer)]
        + [e for _, holes in cut.loops for hole in holes for e in _loop_edges(hole)]
        + [e for box in facts.beyond for e in _loop_edges(_box_loop(box, scale_value))]
    )
    return DrawingViewResult(
        view=PLAN_VIEW,
        scale=scale,
        edges=edges,
        section_faces=[
            SectionFaceLoop(
                outer=[_point(p) for p in outer],
                holes=[[_point(p) for p in hole] for hole in holes],
            )
            for outer, holes in cut.loops
        ],
        auto_dimensions=plan_dimensions(facts, scale_value),
    )


HouseViewKind = Literal["plan", "elevation", "materials"]


def house_view_kind(view: ViewProjection) -> HouseViewKind | None:
    """Which house branch evaluates *view*, or None for a standard view."""
    if view == PLAN_VIEW:
        return "plan"
    if view in ELEVATION_DIRECTIONS:
        return "elevation"
    if view == MATERIALS_VIEW:
        return "materials"
    return None


def standard_direction(view: ViewProjection) -> ViewDirection:
    """A standard (front / top / right / iso) view's HLR direction."""
    if view == "front" or view == "top" or view == "right" or view == "iso":
        return view
    raise ValueError(f"{view!r} is not a standard view direction")
