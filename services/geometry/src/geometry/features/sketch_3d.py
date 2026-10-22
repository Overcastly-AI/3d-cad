"""Evaluate a 3D sketch (SKETCH-3D, RESEARCH §28).

Resolves every snapped point to the geometry it follows (the origin, a point
of an earlier solved 2D or 3D sketch, or an end of a model edge), holds those
and the ``fixed`` points constant, and solves the rest
(:mod:`geometry.sketch.solver3d`). The solved points and lines go into
``state.solved_sketches_3d``, where a Pipe or a Plane Along Path reads a line
as a world edge, and onto the feature's ``solved_sketch_3d`` payload. Every
failure is a typed :class:`FeatureError`; a 3D sketch never touches a body.
"""

# pyright: reportPrivateUsage=false

from build123d import Vector
from loft_wire.features import EvaluatedFeatureInput, FeatureError, Sketch3DFeature
from loft_wire.geometry import Vec3
from loft_wire.sketch import Point2D, SketchPoint
from loft_wire.sketch_3d import (
    Sketch3DFixed,
    Sketch3DLine,
    Sketch3DPoint,
    Sketch3DSketchPointSnap,
    Sketch3DSnap,
    Sketch3DVertexSnap,
    SolvedPoint3D,
    SolvedSketch3DData,
)

from geometry.features.state import EvaluationState, Solved3DSketch
from geometry.kernel.edges import resolve_edge_durable
from geometry.kernel.extrude import plane_point_to_world
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.sketch.solver3d import (
    Point,
    Sketch3DConflictError,
    Sketch3DTooLargeError,
    solve_sketch_3d,
)


def _sketch_point(
    snap: Sketch3DSketchPointSnap, state: EvaluationState, point_id: str
) -> Point | FeatureError:
    sketch_id = snap.sketch.feature_id
    unresolved = FeatureError(
        code="reference_unresolved",
        message=(
            f"3D sketch point '{point_id}' is attached to point '{snap.point}' of "
            f"'{snap.entity}' in an earlier sketch, which is missing, later, "
            "suppressed or failed. Attach it again."
        ),
        upstream_feature_id=sketch_id,
    )
    solved_3d = state.solved_sketches_3d.get(sketch_id)
    if solved_3d is not None:
        found = solved_3d.points.get(snap.entity)
        if found is None or snap.point != "position":
            return unresolved
        return found
    solved = state.solved_sketches.get(sketch_id)
    plane = state.sketch_planes.get(sketch_id)
    if solved is None or plane is None:
        return unresolved
    entity = next((e for e in solved.entities if e.id == snap.entity), None)
    if entity is None:
        return unresolved
    name = "position" if isinstance(entity, SketchPoint) else snap.point
    if name == "position" and not isinstance(entity, SketchPoint):
        return unresolved
    local = getattr(entity, name, None)
    if not isinstance(local, Point2D):
        return unresolved
    world = plane_point_to_world(plane, local)
    return (world.X, world.Y, world.Z)


def _vertex(
    snap: Sketch3DVertexSnap, state: EvaluationState, point_id: str
) -> Point | FeatureError:
    active = state.active_body
    if active is None:
        return FeatureError(
            code="subshape_unresolved",
            message=(
                f"3D sketch point '{point_id}' is attached to a model vertex, but "
                "no body precedes this sketch."
            ),
            upstream_feature_id=snap.edge.feature_id,
        )
    signature = snap.edge.selector.signature
    try:
        resolved = resolve_edge_durable(
            active, signature, tally=state.subshape_tally, face_names=state.face_names()
        )
    except (SubshapeUnresolvedError, SubshapeAmbiguousError) as exc:
        code = (
            "subshape_ambiguous"
            if isinstance(exc, SubshapeAmbiguousError)
            else "subshape_unresolved"
        )
        return FeatureError(
            code=code,
            message=f"3D sketch point '{point_id}': {exc}",
            upstream_feature_id=snap.edge.feature_id,
        )
    # The end AS PICKED: whichever end of the edge today is nearer the
    # signature's end_a is ``a`` (the pipe's sense rule), the other is ``b``.
    a = Vector(signature.end_a.x, signature.end_a.y, signature.end_a.z)
    ends = [resolved.edge.position_at(0), resolved.edge.position_at(1)]
    if (ends[1] - a).length < (ends[0] - a).length:
        ends.reverse()
    at = ends[0] if snap.end == "a" else ends[1]
    return (at.X, at.Y, at.Z)


def _snap(
    snap: Sketch3DSnap, state: EvaluationState, point_id: str
) -> Point | FeatureError:
    if isinstance(snap, Sketch3DSketchPointSnap):
        return _sketch_point(snap, state, point_id)
    if isinstance(snap, Sketch3DVertexSnap):
        return _vertex(snap, state, point_id)
    return (0.0, 0.0, 0.0)


def _evaluate_sketch_3d(
    item: EvaluatedFeatureInput, state: EvaluationState
) -> FeatureError | None:
    """Solve the 3D sketch and record it for later features."""
    feature = item.feature
    assert isinstance(feature, Sketch3DFeature), "registry dispatches 'sketch_3d'"
    params = feature.params
    positions: dict[str, Point] = {}
    fixed: dict[str, Point] = {}
    lines: dict[str, tuple[str, str]] = {}
    for entity in params.entities:
        if isinstance(entity, Sketch3DLine):
            lines[entity.id] = (entity.start, entity.end)
            continue
        assert isinstance(entity, Sketch3DPoint)
        p = entity.position
        positions[entity.id] = (p.x, p.y, p.z)
        if entity.snap is not None:
            at = _snap(entity.snap, state, entity.id)
            if isinstance(at, FeatureError):
                return at
            fixed[entity.id] = at
    for constraint in params.constraints:
        if isinstance(constraint, Sketch3DFixed) and constraint.point not in fixed:
            fixed[constraint.point] = positions[constraint.point]
    try:
        solved = solve_sketch_3d(positions, fixed, lines, params.constraints)
    except Sketch3DConflictError as exc:
        return FeatureError(code="sketch_conflicting", message=str(exc))
    except Sketch3DTooLargeError as exc:
        return FeatureError(code="sketch_too_large", message=str(exc))
    for line, (a, b) in lines.items():
        pa, pb = Vector(*solved.points[a]), Vector(*solved.points[b])
        if (pb - pa).length <= 1e-9:
            return FeatureError(
                code="sketch_conflicting",
                message=f"3D sketch line '{line}' has zero length after the solve.",
            )
    data = SolvedSketch3DData(
        points=[
            SolvedPoint3D(id=key, position=Vec3(x=p[0], y=p[1], z=p[2]))
            for key, p in solved.points.items()
        ],
        dof=solved.dof,
        redundant_constraints=solved.redundant,
    )
    state.solved_sketches_3d[item.id] = Solved3DSketch(solved.points, lines, data)
    return None
