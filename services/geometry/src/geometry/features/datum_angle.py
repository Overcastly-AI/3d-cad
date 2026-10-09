"""The plane-at-an-angle datum: resolve its line, then turn the reference about it.

:func:`resolve_angle_plane` is the ``kind: "angle"`` branch of the datum
evaluator (``datum_sketch._evaluate_datum``). The REFERENCE plane arrives
already resolved, through the same funnel a midplane side uses (origin datum,
earlier datum, picked planar face), so this module adds exactly one new kind of
reference, the LINE, and resolves each of its three forms through machinery
that already exists:

* a sketch line: the SOLVED sketch of this pass (``state.solved_sketches``),
  mapped to world through that sketch's resolved plane, so an edited or
  re-dimensioned line moves the datum;
* a model edge: :func:`~geometry.kernel.edges.resolve_edge_durable` against the
  active body with its face names, the strict/named/durable tiers every picked
  edge (fillet, flange, projection) resolves through;
* an origin axis: the world axis through the origin.

Every failure is a typed :class:`FeatureError` on the datum (it goes sick, a
sketch on it then fails ``reference_unresolved``), never an exception out of the
rebuild.
"""

from dataclasses import dataclass

from build123d import Plane, Vector
from loft_wire.features import (
    DatumAngleLine,
    DatumAngleParams,
    DatumOriginAxisRef,
    DatumSketchLineRef,
    EdgeSubshapeRef,
    FeatureError,
)
from loft_wire.sketch import SketchLine

from geometry.features.state import EvaluationState
from geometry.kernel.datum_angle import (
    DATUM_LINE_MIN_LENGTH_MM,
    DatumLineNotParallelError,
    plane_at_angle,
)
from geometry.kernel.edges import resolve_edge_durable
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError

#: World direction of each origin axis.
_ORIGIN_AXES: dict[str, Vector] = {
    "X": Vector(1.0, 0.0, 0.0),
    "Y": Vector(0.0, 1.0, 0.0),
    "Z": Vector(0.0, 0.0, 1.0),
}


@dataclass(frozen=True)
class _Line:
    """A resolved line: a point on it and its (not necessarily unit) direction."""

    point: Vector
    direction: Vector


def _line_error(message: str) -> FeatureError:
    return FeatureError(code="datum_line_invalid", message=message)


def _sketch_line(
    ref: DatumSketchLineRef, state: EvaluationState
) -> _Line | FeatureError:
    sketch_id = ref.sketch.feature_id
    solved = state.solved_sketches.get(sketch_id)
    plane = state.sketch_planes.get(sketch_id)
    if solved is None or plane is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                "The plane's line must be in an earlier, successfully solved "
                "sketch of this tree; that sketch is missing, later, suppressed "
                "or failed."
            ),
            upstream_feature_id=sketch_id,
        )
    entity = next((e for e in solved.entities if e.id == ref.entity), None)
    if entity is None:
        return FeatureError(
            code="reference_unresolved",
            message=(
                f"The plane's line '{ref.entity}' is no longer in its sketch "
                "(deleted or renamed). Pick the line again."
            ),
            upstream_feature_id=sketch_id,
        )
    if not isinstance(entity, SketchLine):
        return _line_error(
            f"The plane's line '{ref.entity}' is a '{entity.kind}', not a "
            "straight line; a plane at an angle turns about a line."
        )
    start = plane.origin + plane.x_dir * entity.start.x + plane.y_dir * entity.start.y
    end = plane.origin + plane.x_dir * entity.end.x + plane.y_dir * entity.end.y
    return _Line(point=start, direction=end - start)


def _edge_line(ref: EdgeSubshapeRef, state: EvaluationState) -> _Line | FeatureError:
    active = state.active_body
    if active is None:
        return FeatureError(
            code="subshape_unresolved",
            message=(
                "The plane's line is a model edge, but no body precedes this "
                "datum; add a feature that creates a body first."
            ),
            upstream_feature_id=ref.feature_id,
        )
    try:
        resolved = resolve_edge_durable(
            active,
            ref.selector.signature,
            tally=state.subshape_tally,
            face_names=state.face_names(),
        )
    except SubshapeUnresolvedError as exc:
        return FeatureError(
            code="subshape_unresolved",
            message=str(exc),
            upstream_feature_id=ref.feature_id,
        )
    except SubshapeAmbiguousError as exc:
        return FeatureError(
            code="subshape_ambiguous",
            message=str(exc),
            upstream_feature_id=ref.feature_id,
        )
    signature = resolved.signature
    if signature.curve != "line":
        return _line_error(
            f"The plane's edge is a '{signature.curve}' edge, not a straight "
            "one; a plane at an angle turns about a straight edge."
        )
    a, b = signature.end_a, signature.end_b
    start = Vector(a.x, a.y, a.z)
    direction = Vector(b.x, b.y, b.z) - start
    # The SENSE is the user's pick, never the current canonical order: the
    # canonical ends are sorted by raw coordinates, so on an axis-aligned edge
    # ulp noise decides which end is end_a, and an upstream edit that moves
    # that noise across zero would mirror +30 deg into -30 deg. Turn the
    # resolved direction to agree with the stored pick's end_a -> end_b.
    pa, pb = ref.selector.signature.end_a, ref.selector.signature.end_b
    picked = Vector(pb.x - pa.x, pb.y - pa.y, pb.z - pa.z)
    if direction.dot(picked) < 0:
        direction = -direction
    return _Line(point=start, direction=direction)


def _resolve_line(line: DatumAngleLine, state: EvaluationState) -> _Line | FeatureError:
    if isinstance(line, DatumOriginAxisRef):
        return _Line(point=Vector(0.0, 0.0, 0.0), direction=_ORIGIN_AXES[line.axis])
    if isinstance(line, DatumSketchLineRef):
        return _sketch_line(line, state)
    return _edge_line(line, state)


def resolve_angle_plane(
    params: DatumAngleParams, reference: Plane, state: EvaluationState
) -> Plane | FeatureError:
    """The ``angle`` datum's plane, or the typed error that makes it sick."""
    line = _resolve_line(params.line, state)
    if isinstance(line, FeatureError):
        return line
    if line.direction.length <= DATUM_LINE_MIN_LENGTH_MM:
        return _line_error(
            "The plane's line has no length (its ends coincide), so it has no "
            "direction to turn about."
        )
    try:
        return plane_at_angle(
            line.point, line.direction, reference, params.angle_deg, params.flip
        )
    except DatumLineNotParallelError as exc:
        return FeatureError(code="datum_line_not_parallel", message=str(exc))
