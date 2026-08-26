"""Sketch profile → face → revolution about a sketch-line axis → boolean.

The kernel half of the revolve feature (feature-tree design §4.3, the second
core body-affecting feature): the feature layer hands in the *solved* sketch
entities (pydantic DTOs from :mod:`py_kit.schemas.sketch`) plus the datum
plane, the axis line's sketch-local id, and the sweep angle; this module owns
every OCCT/build123d call. Failures raise the typed exceptions below with
**sanitized messages** (no kernel internals) — the feature layer maps them 1:1
onto ``FeatureError`` codes so geometry outcomes stay values at the boundary.

The profile is built by the SHARED :func:`geometry.kernel.extrude.build_profile_face`
(construction geometry excluded there, the single profile-exclusion point) and
the ``add``/``cut`` boolean is the SHARED
:func:`geometry.kernel.extrude.combine_body` — revolve only owns the
sweep-and-axis step (CLAUDE.md DRY rule).

Axis contract (design decision; ``sketch_line`` is v1, ``origin_axis`` joined
additively for REVOLVE-1). Two references resolve, and BOTH end up as the same
thing — a straight line **in the sketch plane**, expressed in sketch-local 2D:

* ``sketch_line`` — a LINE entity of the *same* sketch the profile comes from,
  named by its sketch-local id. A construction centerline is the natural axis
  (reference-only, excluded from the profile, exactly what an axis is), but any
  line resolves. Being a sketch entity, it is in the sketch plane by
  construction, and it is the ONLY reference that can also close a half-profile
  (:func:`build_revolve_profile_face`).
* ``origin_axis`` — the world X, Y or Z axis through the origin. A pure enum:
  nothing upstream can move, rename or delete it, so it is the most
  rebuild-stable axis there is, and it is what makes a plain closed profile
  turnable without first drawing a centerline (the REVOLVE-1 gap: with no
  construction geometry the axis list had nothing correct to offer).

An ``origin_axis`` must LIE IN the profile's sketch plane —
:class:`AxisNotInSketchPlaneError` otherwise. This is not a conservatism: a
planar profile revolved about an axis that leaves its plane does not sweep its
own cross-section. If the axis merely *misses* the plane while staying parallel
to it (an origin axis under an offset datum) the swept body is a ring whose
section is nothing the user drew; if the axis *pierces* the plane (Z for a
sketch on XY) every point of the profile orbits at its own distance from the
piercing point and the result self-intersects. Both are wrong bodies that look
plausible in a viewport, so both are refused by name. The check is the exact
inverse mapping of the one the profile is built with
(:func:`plane_point_to_local` / :func:`plane_point_to_world`), so the axis and
the profile can never disagree on where the sketch plane sits.

Validity (design §4.3): revolving a profile the axis *crosses* sweeps material
through itself — an invalid, self-intersecting body. That is detected up front,
in the 2D sketch plane, as :class:`AxisIntersectsProfileError`; a profile that
merely *touches* the axis (a solid of revolution against its own centerline) is
valid and passes. A profile strictly on one side of the axis is the annulus /
shaft / disc case. Because every axis reference resolves to a sketch-local 2D
line first, that guard is written ONCE and applies to every axis kind.

Partial angle: ``angle_deg`` in (0, 360] sweeps the profile through that arc,
capping the result with two planar faces on the profile's own plane;
``reverse`` negates the axis direction so the sweep goes the other way about
it. At a full 360° the two caps coincide and vanish, and ``reverse`` is a
no-op — the same solid either way.

Determinism (RESEARCH §9): the profile is built in entity list order, the axis
is a pure function of two solved points, and the OCCT revolve + boolean are
pure algorithms on identical inputs — no unordered iteration participates.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Axis, Face, Plane, Solid, Vector
from py_kit.schemas.features import OriginAxis, RevolveAxis, SketchLineAxis
from py_kit.schemas.sketch import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
)

from geometry.kernel.extrude import (
    ProfileNotClosedError,
    ProfileUnsupportedError,
    build_profile_face,
    plane_point_to_local,
    plane_point_to_world,
)
from geometry.kernel.healing import clean_shape

#: Clearance tolerance (mm) for the axis-vs-profile side test, aligned with the
#: kernel linear tolerance (1e-7 m; model units are mm). A profile point within
#: this band of the axis line counts as ON the axis (touching, allowed), not
#: across it — so a solid of revolution built against its own centerline passes
#: while a genuinely straddling profile fails.
#:
#: The SAME band answers "does this world axis lie in the sketch plane?"
#: (:func:`resolve_revolve_axis`) — one documented tolerance for "on the axis /
#: in the plane", never a second ad-hoc epsilon. It is generous for the shipped
#: cases and deliberately so: an origin axis against an origin datum plane is
#: exactly 0.0 out of plane (both frames are axis-aligned unit vectors through
#: the world origin), and an offset datum is out of plane by its whole
#: ``offset_mm``, so nothing real lands anywhere near the boundary.
AXIS_CLEARANCE_TOL = 1e-7

#: World direction of each origin axis, keyed by the ``OriginAxis.axis`` enum.
#: The axes pass through the world origin, so a point and a direction fully
#: determine each line. Materialized once as a module constant rather than
#: reached for through ``build123d.Axis.X`` at call time, so the mapping the
#: DTO promises is readable in one place.
ORIGIN_AXIS_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}

#: Arc sampling density for the side test. Lines and circles get exact extreme
#: signed distances; an arc's extremum need not fall at an endpoint, so it is
#: sampled at this many points across its span (a smooth circular arc, so a
#: dense uniform sample cannot miss a side change of meaningful extent).
_ARC_SAMPLES = 64


class NoAxisError(ValueError):
    """The revolve axis reference does not resolve to a usable sketch line
    (unknown entity id, the entity is not a line, or the line is degenerate)."""


class AxisNotInSketchPlaneError(ValueError):
    """The axis of revolution does not lie in the profile's sketch plane, so
    revolving the profile would not sweep its own cross-section."""


class AxisIntersectsProfileError(ValueError):
    """The axis of revolution crosses the profile interior — revolving it would
    sweep material through itself (an invalid, self-intersecting body)."""


class RevolveError(RuntimeError):
    """The OCCT revolve failed or produced an unsupported result."""


def resolve_axis_line(
    entities: Sequence[SketchEntity], axis_entity_id: str
) -> SketchLine:
    """Find the axis LINE entity by its sketch-local id among *entities*.

    Raises:
        NoAxisError: no entity has that id, or it is not a line entity, or the
            line is degenerate (zero length — no direction to revolve about).
    """
    match = next((e for e in entities if e.id == axis_entity_id), None)
    if match is None:
        raise NoAxisError(
            f"Revolve axis references sketch entity '{axis_entity_id}', which "
            "is not in the profile's sketch."
        )
    if not isinstance(match, SketchLine):
        raise NoAxisError(
            f"Revolve axis '{axis_entity_id}' is a '{match.kind}' entity; the "
            "axis of revolution must be a line."
        )
    if math.hypot(match.end.x - match.start.x, match.end.y - match.start.y) <= (
        AXIS_CLEARANCE_TOL
    ):
        raise NoAxisError(
            f"Revolve axis '{axis_entity_id}' is degenerate (its endpoints "
            "coincide); it has no direction to revolve about."
        )
    return match


@dataclass(frozen=True)
class ResolvedRevolveAxis:
    """An axis reference of any kind, reduced to the sketch plane.

    ``line`` is the axis as a 2D segment in SKETCH coordinates — the single
    representation every downstream step consumes, so the side test
    (:func:`check_axis_clears_profile`) and the sweep (:func:`revolve_face`) are
    written once and cannot disagree about which axis they were given. Consumers
    treat it as the INFINITE line through its two points; its length carries no
    meaning (an ``origin_axis`` is reduced to a unit-length representative).

    ``entity`` is the sketch entity the axis IS, or ``None`` when the axis is
    not sketch geometry. Only a real entity can be promoted to a closing profile
    edge (:func:`build_revolve_profile_face`), so this is what keeps that
    fallback honest instead of inventing an edge the user never drew.
    """

    line: SketchLine
    entity: SketchLine | None


def resolve_revolve_axis(
    axis: RevolveAxis, plane: Plane, entities: Sequence[SketchEntity]
) -> ResolvedRevolveAxis:
    """Reduce any :data:`~py_kit.schemas.features.RevolveAxis` to the sketch plane.

    THE single axis-resolution point (CLAUDE.md DRY rule): every axis kind lands
    on one 2D sketch-plane line, so the profile-clearance guard and the sweep
    below take one shape of input regardless of how the user named the axis.

    Raises:
        NoAxisError: a ``sketch_line`` reference that is not a usable line.
        AxisNotInSketchPlaneError: a world axis that does not lie in the
            profile's sketch plane (see the module docstring for why that is a
            refusal and not a body).
    """
    match axis:
        case SketchLineAxis():
            line = resolve_axis_line(entities, axis.entity)
            return ResolvedRevolveAxis(line=line, entity=line)
        case OriginAxis():
            direction = ORIGIN_AXIS_DIRECTIONS[axis.axis]
            return ResolvedRevolveAxis(
                line=_world_axis_to_sketch_line(
                    plane,
                    origin=Vector(0.0, 0.0, 0.0),
                    direction=Vector(*direction),
                    subject=f"The {axis.axis} origin axis",
                ),
                entity=None,
            )


def _world_axis_to_sketch_line(
    plane: Plane, *, origin: Vector, direction: Vector, subject: str
) -> SketchLine:
    """Express the world line ``origin + t * direction`` in sketch coordinates.

    Both halves of "lies in the plane" are checked, because they fail for
    different reasons and a caller deserves to be told which: the axis POINT
    must be in the plane (otherwise the axis is parallel to the plane but offset
    from it — the offset-datum case, whose swept body has a section nobody
    drew), and the axis DIRECTION must have no component along the plane normal
    (otherwise the axis pierces the plane and the revolution self-intersects).

    Both use :data:`AXIS_CLEARANCE_TOL`: the point test in mm, the direction
    test on a UNIT vector's normal component, which is the sine of the angle
    between the axis and the plane and so is already dimensionless.
    """
    length = direction.length
    if length <= AXIS_CLEARANCE_TOL:
        raise NoAxisError(
            f"{subject} is degenerate (zero direction); it has no direction to "
            "revolve about."
        )
    unit = direction / length

    _, _, point_out_of_plane = plane_point_to_local(plane, origin)
    if abs(point_out_of_plane) > AXIS_CLEARANCE_TOL:
        raise AxisNotInSketchPlaneError(
            f"{subject} is {abs(point_out_of_plane):.6g} mm away from the "
            "profile's sketch plane, so revolving about it would not sweep the "
            "profile's own cross-section. Revolve about an axis that lies in "
            "the sketch plane, or draw a construction centerline in the sketch."
        )

    tip_u, tip_v, direction_out_of_plane = plane_point_to_local(plane, origin + unit)
    if abs(direction_out_of_plane) > AXIS_CLEARANCE_TOL:
        raise AxisNotInSketchPlaneError(
            f"{subject} points out of the profile's sketch plane, so revolving "
            "about it would sweep the profile through itself. Choose an axis "
            "that lies in the sketch plane (a plane's own normal is never one), "
            "or draw a construction centerline in the sketch."
        )

    base_u, base_v, _ = plane_point_to_local(plane, origin)
    return SketchLine(
        id="__axis__",
        kind="line",
        construction=True,
        start=Point2D(x=base_u, y=base_v),
        end=Point2D(x=tip_u, y=tip_v),
    )


def build_revolve_profile_face(
    plane: Plane, entities: Sequence[SketchEntity], axis: ResolvedRevolveAxis
) -> Face:
    """Build the revolve profile face, closing a half-profile along the axis.

    First the SHARED :func:`geometry.kernel.extrude.build_profile_face`
    (construction geometry excluded there) — the existing real-edge and
    offset-profile paths return here **byte-identical**: a profile already
    closed by real edges (a shaft with a real on-axis edge, a washer offset
    from the axis) never touches the fallback below.

    A half-profile whose only open side lies ON the axis is the natural
    SolidWorks/Fusion idiom: draw three real edges of an L / rectangle plus a
    **construction centerline** on the axis, and revolve about that centerline.
    Marking the on-axis edge ``construction`` correctly excludes it from the
    profile wire, so the first attempt raises
    :class:`~geometry.kernel.extrude.ProfileNotClosedError`. The fallback then
    retries with the AXIS line promoted to a real closing edge: the profile
    closes into exactly the face a real on-axis edge would give, and revolving
    it fills the solid of revolution.

    A profile open somewhere OTHER than the axis stays open even with the axis
    edge added (its free endpoints are not the axis endpoints), so the ORIGINAL
    ``ProfileNotClosedError`` re-raises — a genuinely open profile is never
    masked (design §4.3; the axis is the only edge the fallback will supply).

    The fallback needs a real drawn ENTITY to promote, so it applies to a
    ``sketch_line`` axis only. An ``origin_axis`` is not sketch geometry
    (``ResolvedRevolveAxis.entity is None``) and the fallback is skipped
    outright: closing the loop would mean inventing an edge along a world axis
    the user never drew — a bigger assumption than the honest
    ``profile_not_closed`` the caller gets instead, whose fix (draw the fourth
    side, or a centerline) is one edge of work.
    """
    entity = axis.entity
    try:
        return build_profile_face(plane, entities)
    except ProfileNotClosedError as original:
        if entity is None:
            # Not sketch geometry — there is no drawn edge to promote, and
            # synthesizing one would close a loop the user did not draw.
            raise
        # Retry with the construction axis promoted to a real profile edge: it
        # closes a half-profile open ONLY along the axis, and nothing else.
        closed_axis = entity.model_copy(update={"construction": False})
        entities_with_axis = [closed_axis if e is entity else e for e in entities]
        try:
            return build_profile_face(plane, entities_with_axis)
        except (ProfileNotClosedError, ProfileUnsupportedError):
            # Still open (or malformed) even with the axis edge → the profile is
            # open away from the axis. Report the honest original diagnosis.
            raise original from None


def _axis_side_bounds(
    axis: SketchLine, entities: Sequence[SketchEntity]
) -> tuple[float, float]:
    """Min and max signed distance of the profile to the axis line (2D).

    Signed distance is measured in the sketch plane from the infinite line
    through the axis segment. Construction geometry and points never bound the
    profile (they are excluded from the wire), so they are skipped here too —
    the test is against exactly the geometry that becomes the swept face.
    """
    ax0x, ax0y = axis.start.x, axis.start.y
    dx, dy = axis.end.x - ax0x, axis.end.y - ax0y
    length = math.hypot(dx, dy)  # > 0: resolve_revolve_axis rejected degenerate
    ux, uy = dx / length, dy / length

    def signed(px: float, py: float) -> float:
        # Left-normal projection: >0 on one side of the directed line, <0 on
        # the other, 0 exactly on it.
        return ux * (py - ax0y) - uy * (px - ax0x)

    lo = math.inf
    hi = -math.inf
    for entity in entities:
        if entity.construction:
            continue
        samples: list[float] = []
        match entity:
            case SketchLine():
                samples = [
                    signed(entity.start.x, entity.start.y),
                    signed(entity.end.x, entity.end.y),
                ]
            case SketchCircle():
                # A full circle reaches its own radius to either side of its
                # centre in every direction, so the perpendicular extent to the
                # axis is exactly centre ± radius (exact, no sampling).
                centre = signed(entity.center.x, entity.center.y)
                samples = [centre - entity.radius, centre + entity.radius]
            case SketchArc():
                radius = math.hypot(
                    entity.start.x - entity.center.x,
                    entity.start.y - entity.center.y,
                )
                start_ang = math.atan2(
                    entity.start.y - entity.center.y,
                    entity.start.x - entity.center.x,
                )
                end_ang = math.atan2(
                    entity.end.y - entity.center.y,
                    entity.end.x - entity.center.x,
                )
                # Arc is traversed CCW start→end (sketch DTO contract).
                span = (end_ang - start_ang) % (2.0 * math.pi)
                for i in range(_ARC_SAMPLES + 1):
                    ang = start_ang + span * (i / _ARC_SAMPLES)
                    samples.append(
                        signed(
                            entity.center.x + radius * math.cos(ang),
                            entity.center.y + radius * math.sin(ang),
                        )
                    )
            case _:  # SketchPoint — never part of the profile
                continue
        if samples:
            lo = min(lo, *samples)
            hi = max(hi, *samples)
    return lo, hi


def check_axis_clears_profile(
    axis: ResolvedRevolveAxis, entities: Sequence[SketchEntity]
) -> None:
    """Reject an axis that crosses the profile interior (design §4.3).

    Written against the RESOLVED axis, so it guards every axis kind identically
    — a world origin axis through the middle of a profile is refused for exactly
    the reason, and with exactly the message, that a badly-placed centerline is.

    Raises:
        AxisIntersectsProfileError: the profile has geometry strictly on BOTH
            sides of the axis line. Touching the axis (one bound at 0 within
            :data:`AXIS_CLEARANCE_TOL`) is valid — a solid of revolution built
            against its own centerline.
    """
    lo, hi = _axis_side_bounds(axis.line, entities)
    if lo < -AXIS_CLEARANCE_TOL and hi > AXIS_CLEARANCE_TOL:
        raise AxisIntersectsProfileError(
            "The axis of revolution crosses the profile: revolving it would "
            "sweep material through itself. Move the axis so the whole profile "
            "lies on one side of it (touching is allowed)."
        )


def revolve_face(
    face: Face,
    axis: ResolvedRevolveAxis,
    plane: Plane,
    angle_deg: float,
    reverse: bool,
) -> Solid:
    """Revolve *face* about the resolved sketch-plane *axis* by *angle_deg*.

    The axis is built from the resolved line's two endpoints mapped back to
    world space through the profile's resolved sketch *plane* (shared mapping —
    the axis and profile agree on plane placement, including on an offset
    ``datum`` plane). An ``origin_axis`` therefore makes the same world-space
    round trip a sketch-line axis does, so the two cannot diverge.

    ``reverse`` sweeps the opposite way about the axis (visible only for a
    partial angle; a full 360° is handed either way).

    Raises:
        RevolveError: the OCCT revolve failed or left other than exactly one
            solid (single body chain per part in v1, design §7.6).
    """
    if not 0.0 < angle_deg <= 360.0:
        raise ValueError(f"angle_deg must be in (0, 360], got {angle_deg}")

    origin = plane_point_to_world(plane, axis.line.start)
    direction = plane_point_to_world(plane, axis.line.end) - origin
    if reverse:
        direction = -direction
    revolution_axis = Axis(origin, direction)

    try:
        result = Solid.revolve(face, angle_deg, revolution_axis)
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise RevolveError(
            f"Revolve failed in the kernel ({type(exc).__name__}); the profile "
            "or axis may be degenerate for a revolution."
        ) from exc

    if len(solids) != 1:
        raise RevolveError(
            f"Revolve produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    # clean() removes redundant seam faces/edges the operation can leave
    # behind, keeping topology counts meaningful (and golden-assertable).
    return clean_shape(solids[0])
