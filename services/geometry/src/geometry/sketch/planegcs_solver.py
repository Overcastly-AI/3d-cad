"""``SketchSolver`` backed by planegcs (FreeCAD's PlaneGCS solver).

planegcs (PyPI, LGPL-2.1-or-later — allowed as a dynamically-loaded dep,
RESEARCH §8) wraps the planar geometric constraint solver extracted from
FreeCAD's Sketcher. Spike verdict + license evidence: RESEARCH §2.

planegcs types stay strictly inside this module — the interface speaks only
the pydantic DTOs of :mod:`geometry.sketch.schemas`.

Determinism: entities and constraints are translated in input list order,
the solve uses planegcs's default DogLeg algorithm from the input positions
as the starting guess, and PlaneGCS itself is deterministic (no random
restarts). Same definition in → bitwise-identical solution out (asserted by
the unit suite; RESEARCH §9 "solver determinism" gate).
"""

import math

from planegcs import ArcId, CircleId, LineId, PointId
from planegcs import Sketch as GcsSystem
from planegcs import SolveStatus as GcsSolveStatus

from geometry.sketch.schemas import (
    CoincidentConstraint,
    DistanceConstraint,
    EntityPointRef,
    FixedConstraint,
    HorizontalConstraint,
    Point2D,
    RadiusConstraint,
    SketchArc,
    SketchCircle,
    SketchDefinition,
    SketchEntity,
    SketchLine,
    SketchPoint,
    SketchSolveStatus,
    SolvedSketch,
    VerticalConstraint,
)
from geometry.sketch.solver import SketchDefinitionError


class PlanegcsSketchSolver:
    """Solve :class:`SketchDefinition` sketches with planegcs.

    Stateless: every :meth:`solve` builds a fresh planegcs system, so calls
    are independent and safe to repeat (the geometry service is stateless by
    contract).
    """

    def solve(self, sketch: SketchDefinition) -> SolvedSketch:
        system = _GcsBuild(sketch)
        raw_status = system.gcs.solve()  # default DogLeg — deterministic
        diagnosis = system.gcs.diagnose()
        solved = raw_status in (GcsSolveStatus.Success, GcsSolveStatus.Converged)

        status = _map_status(
            solved=solved,
            conflicting=bool(diagnosis.conflicting),
            redundant=bool(diagnosis.redundant),
            dof=diagnosis.dof,
        )
        # Internal tags (e.g. arc rules auto-added by planegcs) are not in
        # the map; report only indices of caller-supplied constraints.
        conflicting = sorted(
            {
                system.tag_to_index[tag]
                for tag in diagnosis.conflicting
                if tag in system.tag_to_index
            }
        )
        redundant = sorted(
            {
                system.tag_to_index[tag]
                for tag in diagnosis.redundant
                if tag in system.tag_to_index
            }
        )
        entities = (
            system.read_back()
            if solved
            else [entity.model_copy(deep=True) for entity in sketch.entities]
        )
        return SolvedSketch(
            status=status,
            entities=entities,
            dof=diagnosis.dof if diagnosis.dof >= 0 else None,
            conflicting_constraints=conflicting,
            redundant_constraints=redundant,
        )


def _map_status(
    *, solved: bool, conflicting: bool, redundant: bool, dof: int
) -> SketchSolveStatus:
    """Precedence documented on :data:`~geometry.sketch.schemas.SketchSolveStatus`."""
    if conflicting:
        return "conflicting"
    if redundant:
        return "overconstrained"
    if not solved:
        return "diverged"
    if dof > 0:
        return "underconstrained"
    return "converged"


class _GcsBuild:
    """Translation of one ``SketchDefinition`` into a planegcs system.

    Holds the DTO-id → planegcs-handle maps needed to apply constraints, map
    diagnosis tags back to constraint indices, and read solved geometry out.
    """

    def __init__(self, sketch: SketchDefinition) -> None:
        self.sketch = sketch
        self.gcs = GcsSystem()
        self._points: dict[tuple[str, str], PointId] = {}
        self._lines: dict[str, LineId] = {}
        self._circles: dict[str, CircleId] = {}
        self._arcs: dict[str, ArcId] = {}
        #: planegcs constraint tag → index into ``sketch.constraints``.
        self.tag_to_index: dict[int, int] = {}
        for entity in sketch.entities:  # input order — deterministic
            self._add_entity(entity)
        for index, constraint in enumerate(sketch.constraints):
            self._add_constraint(index, constraint)

    # -- entities -----------------------------------------------------------

    def _add_point(self, entity_id: str, name: str, point: Point2D) -> PointId:
        pid = self.gcs.add_point(point.x, point.y)
        self._points[(entity_id, name)] = pid
        return pid

    def _add_entity(self, entity: SketchEntity) -> None:
        match entity:
            case SketchPoint():
                self._add_point(entity.id, "position", entity.position)
            case SketchLine():
                p1 = self._add_point(entity.id, "start", entity.start)
                p2 = self._add_point(entity.id, "end", entity.end)
                self._lines[entity.id] = self.gcs.add_line(p1, p2)
            case SketchCircle():
                center = self._add_point(entity.id, "center", entity.center)
                radius = self.gcs.add_param(entity.radius, fixed=False)
                self._circles[entity.id] = self.gcs.add_circle(center, radius)
            case SketchArc():
                radius = math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
                if radius == 0.0:
                    raise SketchDefinitionError(
                        f"Arc {entity.id!r} is degenerate: start coincides with center"
                    )
                start_angle = math.atan2(
                    entity.start.y - entity.center.y,
                    entity.start.x - entity.center.x,
                )
                end_angle = math.atan2(
                    entity.end.y - entity.center.y,
                    entity.end.x - entity.center.x,
                )
                if end_angle <= start_angle:  # CCW convention (schemas)
                    end_angle += math.tau
                center = self._add_point(entity.id, "center", entity.center)
                start = self._add_point(entity.id, "start", entity.start)
                end = self._add_point(entity.id, "end", entity.end)
                # add_arc_cse -> add_arc auto-adds the arc-rules constraints
                # tying start/end to center/radius/angles; do NOT add them
                # again (that would be a redundant constraint).
                self._arcs[entity.id] = self.gcs.add_arc_cse(
                    center, start, end, radius, start_angle, end_angle
                )

    # -- constraints ---------------------------------------------------------

    def _resolve_point(self, ref: EntityPointRef) -> PointId:
        try:
            return self._points[(ref.entity, ref.point)]
        except KeyError:
            raise SketchDefinitionError(
                f"No point {ref.point!r} on entity {ref.entity!r} (unknown "
                "entity id, or a point name the entity kind does not have)"
            ) from None

    def _resolve_line(self, entity_id: str, constraint_kind: str) -> LineId:
        try:
            return self._lines[entity_id]
        except KeyError:
            raise SketchDefinitionError(
                f"Constraint {constraint_kind!r} requires a line entity; "
                f"{entity_id!r} is not a known line"
            ) from None

    def _add_constraint(self, index: int, constraint: object) -> None:
        gcs = self.gcs
        match constraint:
            case CoincidentConstraint():
                tag = gcs.coincident(
                    self._resolve_point(constraint.a),
                    self._resolve_point(constraint.b),
                )
            case HorizontalConstraint():
                line = self._resolve_line(constraint.entity, "horizontal")
                tag = gcs.horizontal(line)
            case VerticalConstraint():
                tag = gcs.vertical(self._resolve_line(constraint.entity, "vertical"))
            case DistanceConstraint():
                line_id = constraint.entity
                self._resolve_line(line_id, "distance")  # kind check
                tag = gcs.set_p2p_distance(
                    self._points[(line_id, "start")],
                    self._points[(line_id, "end")],
                    constraint.value_mm,
                )
            case RadiusConstraint():
                if constraint.entity in self._circles:
                    tag = gcs.set_circle_radius(
                        self._circles[constraint.entity], constraint.value_mm
                    )
                elif constraint.entity in self._arcs:
                    tag = gcs.set_arc_radius(
                        self._arcs[constraint.entity], constraint.value_mm
                    )
                else:
                    raise SketchDefinitionError(
                        "Constraint 'radius' requires a circle or arc entity; "
                        f"{constraint.entity!r} is neither"
                    )
            case FixedConstraint():
                point_id = self._resolve_point(constraint.point)
                x, y = gcs.get_point(point_id)  # pre-solve = input position
                fix_x, fix_y = gcs.fix_point(point_id, x, y)
                self.tag_to_index[fix_x] = index
                self.tag_to_index[fix_y] = index
                return
            case _:  # pragma: no cover — unreachable via the DTO union
                raise SketchDefinitionError(f"Unsupported constraint: {constraint!r}")
        self.tag_to_index[tag] = index

    # -- results -------------------------------------------------------------

    def read_back(self) -> list[SketchEntity]:
        """Solved entities, same ids/kinds/order/construction-flag as input.

        The ``construction`` flag is a property of the entity, not a solve
        result, so it is carried through unchanged: construction geometry
        solves like any other entity and stays flagged for the profile builder
        and the UI (dashed/muted rendering).
        """
        solved: list[SketchEntity] = []
        for entity in self.sketch.entities:
            match entity:
                case SketchPoint():
                    x, y = self.gcs.get_point(self._points[(entity.id, "position")])
                    solved.append(
                        SketchPoint(
                            id=entity.id,
                            kind="point",
                            construction=entity.construction,
                            position=Point2D(x=x, y=y),
                        )
                    )
                case SketchLine():
                    info = self.gcs.get_line(self._lines[entity.id])
                    solved.append(
                        SketchLine(
                            id=entity.id,
                            kind="line",
                            construction=entity.construction,
                            start=Point2D(x=info.p1[0], y=info.p1[1]),
                            end=Point2D(x=info.p2[0], y=info.p2[1]),
                        )
                    )
                case SketchCircle():
                    circle = self.gcs.get_circle(self._circles[entity.id])
                    solved.append(
                        SketchCircle(
                            id=entity.id,
                            kind="circle",
                            construction=entity.construction,
                            center=Point2D(x=circle.center[0], y=circle.center[1]),
                            radius=circle.radius,
                        )
                    )
                case SketchArc():
                    arc = self.gcs.get_arc(self._arcs[entity.id])
                    solved.append(
                        SketchArc(
                            id=entity.id,
                            kind="arc",
                            construction=entity.construction,
                            center=Point2D(x=arc.center[0], y=arc.center[1]),
                            start=Point2D(x=arc.start_point[0], y=arc.start_point[1]),
                            end=Point2D(x=arc.end_point[0], y=arc.end_point[1]),
                        )
                    )
        return solved
