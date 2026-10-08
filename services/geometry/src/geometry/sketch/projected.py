"""Projected sketch entities in the solver: fixed geometry (SKETCH-PROJECT-EDGES).

A projected entity is a body edge seen from the sketch plane (Fusion 360's
Project, SolidWorks' Convert Entities). The body decides where it is, so the
solver may not move it: every one of its parameters is declared FIXED, the
circle radius included, and it adds no degrees of freedom. FreeCAD's sketcher
treats external geometry the same way. Constraints still reach it through its
ordinary ``start``/``end``/``center`` points, so coincident, collinear,
tangent, concentric and the point dimensions need no new kinds.

A projected ARC carries no arc rules. planegcs adds them to every arc, and
over parameters that are all fixed they are a constraint with no unknowns,
which the diagnosis reports as redundant and the sketch would read
over-constrained. :func:`add_fixed_arc` removes them again.

Also home to :func:`entity_point_names`, the one enumeration of an entity's
points that the solver's settle and its targets share.
"""

from typing import assert_never

from planegcs import ArcId, PointId
from planegcs import ConstraintTag as GcsConstraintTag
from planegcs import Sketch as GcsSystem

from geometry.sketch.schemas import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSpline,
)


def projected_ids(entities: list[SketchEntity]) -> frozenset[str]:
    """Ids of the entities linked to a body edge: fixed, and never settled."""
    return frozenset(entity.id for entity in entities if entity.projection)


def add_fixed_point(gcs: GcsSystem, point: Point2D) -> PointId:
    """A point no solve can move: x then y, as ``add_point`` declares them."""
    return gcs.add_point_from_params(
        gcs.add_param(point.x, fixed=True), gcs.add_param(point.y, fixed=True)
    )


def add_fixed_arc(
    gcs: GcsSystem,
    points: tuple[PointId, PointId, PointId],
    shape: tuple[float, float, float],
    rules_tag: int,
) -> ArcId:
    """An arc over fixed ``(center, start, end)`` points and a fixed
    ``(radius, start angle, end angle)``, without its arc rules.

    ``rules_tag`` is the tag planegcs is about to give the arc rules. The
    binding numbers constraint tags from 1 in creation order and only an arc
    creates one while entities are added, so the caller passes one more than
    the arcs it has added (``test_sketch_projection`` pins this: a wrong tag
    leaves a projected arc redundant or frees an arc before it).
    """
    radius, start_angle, end_angle = shape
    arc = gcs.add_arc(
        *points,
        gcs.add_param(radius, fixed=True),
        gcs.add_param(start_angle, fixed=True),
        gcs.add_param(end_angle, fixed=True),
    )
    gcs.clear_by_tag(GcsConstraintTag(rules_tag))
    return arc


def entity_point_names(entity: SketchEntity) -> list[tuple[str, Point2D]]:
    """``(point name, submitted coordinate)`` for every point an entity owns.

    The one enumeration of "which points does this kind of entity have", in the
    order the solver registers them, shared by the placement targets
    (:meth:`_GcsBuild._input_points`) and the shape pins
    (:meth:`_GcsBuild._shape_pins`) — the two must agree about the point set or
    a settle would hold one view of the entity against another.

    A circle contributes only its centre: its radius is a shape parameter, not
    a point, and is pinned separately.
    """
    match entity:
        case SketchPoint():
            return [("position", entity.position)]
        case SketchLine():
            return [("start", entity.start), ("end", entity.end)]
        case SketchCircle():
            return [("center", entity.center)]
        case SketchArc():
            return [
                ("center", entity.center),
                ("start", entity.start),
                ("end", entity.end),
            ]
        case SketchSpline():
            return [(f"fit{index}", point) for index, point in enumerate(entity.points)]
        case _:  # pragma: no cover — the entity union is closed
            assert_never(entity)
