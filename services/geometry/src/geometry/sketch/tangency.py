"""Sketch tangency: the planegcs encoding and the endpoint-tangent angle.

Two forms of one wire constraint (:class:`~loft_wire.sketch.TangentConstraint`):

* **Whole-curve** (no ``a_point``/``b_point``): planegcs's native
  ``tangent_line_arc`` and friends — centre-to-line distance equals ``r`` (or
  the circle-circle analogue), the contact point free. Unchanged since it
  shipped, so every stored sketch that uses it solves exactly as before.
* **Endpoint** (both set; SKETCH-ENDPOINT-TANGENT): the two named ends are one
  point AND the curves share a tangent direction there. FreeCAD's encoding of
  its endpoint-to-endpoint tangency, used here verbatim: a coincidence plus
  ``angle_via_point`` pinning the angle between the two tangent directions at
  that point to ``0`` or ``pi``.

Why the second form exists. After a sketch fillet the arc's ends are already
coincident with the trimmed legs, and the whole-curve equation is first-order
dependent on that coincidence at the solution, so planegcs flags it REDUNDANT
and the sketch reads over-constrained (measured: DOF 5 clean -> "redundant
[10, 11]"). Leaving tangency out instead let an R edit pull the arc off tangent
(R5 -> R10 on a 40 x 25 rectangle put the centre 9.114 mm from both legs, a
kink in the extrude with no warning). The angle-at-a-point equation is
independent of the coincidence, so the pair is three equations for three
removed degrees of freedom.

**Which of ``0`` / ``pi``** is decided SYMBOLICALLY from the two end names
(:func:`endpoint_target_rad`), never from coordinates, as the web's
``endpointTangent.ts`` reads every join from the constraints. The tangent
directions follow each curve's own parameterisation (a line ``start -> end``,
an arc counter-clockwise), so at a smooth join one curve runs INTO the point
and the other OUT of it: an ``end`` meeting a ``start`` gives the same
direction (``0``); two ``start`` ends or two ``end`` ends give opposite ones
(``pi``). The other target at the same join is a CUSP: the arc folded back
over the leg.

The first version read the target from the submitted geometry (``0`` when the
two tangents ran within a right angle). The review built two sketches where
that read a cusp as intended and held it: a leg dragged through straight
(submitted reversed) and an arc dragged to the outside of its corner, both
solved with the centre 5 mm OUTSIDE the rectangle and no warning. Read
symbolically, the only solutions are the smooth ones; a corner that cannot
reach one does not converge or fails the payload's residual gate, and reads
``conflicting`` naming this tangent. That is the warning: a silent cusp is no
longer an outcome. The angle conventions are planegcs's own, measured
(``calculate_angle_via_point``): the signed angle from ``a``'s tangent to
``b``'s, error ``wrap(actual - target)`` in radians.
"""

import math
from collections.abc import Callable, Mapping

from planegcs import ArcId, CircleId, LineId, PointId
from planegcs import ConstraintTag as GcsConstraintTag
from planegcs import Sketch as GcsSystem

from geometry.sketch.schemas import EntityPointRef, TangentConstraint
from geometry.sketch.solver import SketchDefinitionError

_Vec = tuple[float, float]
#: ``(entity id, point name)`` -> coordinate, the solver's point table shape.
PointTable = Mapping[tuple[str, str], _Vec]


def join_point(constraint: TangentConstraint, points: PointTable) -> tuple[str, str]:
    """The ``(entity, end)`` the angle is evaluated at: an ARC's named end.

    A line's tangent does not depend on the point, an arc's does, so the point
    handed to ``angle_via_point`` must lie on the arc — ``a``'s end when ``a``
    is an arc, else ``b``'s. The two are coincident at any solution.
    """
    assert constraint.a_point is not None and constraint.b_point is not None
    if (constraint.a, "center") in points:
        return (constraint.a, constraint.a_point)
    return (constraint.b, constraint.b_point)


def _tangent_at(entity_id: str, at: _Vec, points: PointTable) -> _Vec | None:
    """planegcs's tangent direction of a line or (CCW) arc at ``at``."""
    center = points.get((entity_id, "center"))
    start = points.get((entity_id, "start"))
    end = points.get((entity_id, "end"))
    if start is None or end is None:
        return None  # a circle or a spline: no ends to be tangent at
    if center is None:
        return (end[0] - start[0], end[1] - start[1])
    return (-(at[1] - center[1]), at[0] - center[0])


def endpoint_angle_rad(
    constraint: TangentConstraint, points: PointTable
) -> float | None:
    """Signed angle from ``a``'s tangent to ``b``'s at the join, if resolvable."""
    at = points.get(join_point(constraint, points))
    if at is None:
        return None
    ta = _tangent_at(constraint.a, at, points)
    tb = _tangent_at(constraint.b, at, points)
    if ta is None or tb is None:
        return None
    return math.atan2(ta[0] * tb[1] - ta[1] * tb[0], ta[0] * tb[0] + ta[1] * tb[1])


def endpoint_target_rad(constraint: TangentConstraint) -> float:
    """``0`` when one join end is a ``start`` and the other an ``end``, else ``pi``.

    The smooth branch, from the names alone (module note): the curve that ends
    at the join runs into it, the one that starts there runs out of it.
    """
    return 0.0 if constraint.a_point != constraint.b_point else math.pi


def endpoint_residual(
    constraint: TangentConstraint, solved: PointTable
) -> float | None:
    """``max(join gap mm, wrapped angle miss rad)``, planegcs's two errors."""
    a = solved.get((constraint.a, constraint.a_point or ""))
    b = solved.get((constraint.b, constraint.b_point or ""))
    angle = endpoint_angle_rad(constraint, solved)
    if a is None or b is None or angle is None:
        return None
    miss = angle - endpoint_target_rad(constraint)
    miss = (miss + math.pi) % math.tau - math.pi
    return max(math.hypot(b[0] - a[0], b[1] - a[1]), abs(miss))


def add_tangent(
    gcs: GcsSystem,
    constraint: TangentConstraint,
    curves: tuple[dict[str, LineId], dict[str, CircleId], dict[str, ArcId]],
    point: Callable[[EntityPointRef], PointId],
    submitted: PointTable,
) -> list[GcsConstraintTag]:
    """The planegcs tags for one ``tangent``, either form.

    Whole-curve: one native tag per curve-pair shape, ``a``/``b`` reordered to
    each variant's argument order (tangency is symmetric); fixed by input, so
    dispatch is deterministic. Endpoint: two coincidence tags and the angle tag.
    Two lines are never tangent; an endpoint form needs ends on both curves.
    """
    lines, circles, arcs = curves

    def kind(entity_id: str) -> str:
        for name, table in (("line", lines), ("circle", circles), ("arc", arcs)):
            if entity_id in table:
                return name
        raise SketchDefinitionError(
            f"Constraint 'tangent' references {entity_id!r}, which is not a known "
            "line, circle, or arc entity"
        )

    a_id, b_id = constraint.a, constraint.b
    pair = (kind(a_id), kind(b_id))
    if pair == ("line", "line"):
        raise SketchDefinitionError(
            "Constraint 'tangent' relates a line and a curve, or two curves; "
            f"{pair} is not a tangency-capable pair"
        )
    if constraint.a_point is not None and constraint.b_point is not None:
        if "circle" in pair:
            raise SketchDefinitionError(
                "An endpoint 'tangent' joins two curves with ends (a line or an "
                f"arc); {pair} has a circle"
            )
        handle: dict[str, LineId | ArcId] = {**lines, **arcs}
        entity, end = join_point(constraint, submitted)
        join = point(EntityPointRef(entity=entity, point=end))
        target = endpoint_target_rad(constraint)
        return [
            gcs.coincident(
                point(EntityPointRef(entity=a_id, point=constraint.a_point)),
                point(EntityPointRef(entity=b_id, point=constraint.b_point)),
            ),
            gcs.set_angle_via_point(handle[a_id], handle[b_id], join, target),
        ]
    match pair:
        case ("line", "arc"):
            return [gcs.tangent_line_arc(lines[a_id], arcs[b_id])]
        case ("arc", "line"):
            return [gcs.tangent_line_arc(lines[b_id], arcs[a_id])]
        case ("line", "circle"):
            return [gcs.tangent_line_circle(lines[a_id], circles[b_id])]
        case ("circle", "line"):
            return [gcs.tangent_line_circle(lines[b_id], circles[a_id])]
        case ("arc", "arc"):
            return [gcs.tangent_arc_arc(arcs[a_id], arcs[b_id])]
        case ("circle", "circle"):
            return [gcs.tangent_circle_circle(circles[a_id], circles[b_id])]
        case ("circle", "arc"):
            return [gcs.tangent_circle_arc(circles[a_id], arcs[b_id])]
        case _:  # ("arc", "circle")
            return [gcs.tangent_circle_arc(circles[b_id], arcs[a_id])]
