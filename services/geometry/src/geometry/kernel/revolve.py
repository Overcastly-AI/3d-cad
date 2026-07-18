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

Axis contract (design decision, v1): the axis of revolution is a LINE entity of
the *same* sketch the profile comes from, named by its sketch-local id. A
construction centerline is the natural axis (reference-only, excluded from the
profile, exactly what an axis is), but any line resolves. The axis is defined
by the line's two solved endpoints mapped to world space through the profile's
datum plane — sharing :func:`plane_point_to_world`, so the axis and profile can
never disagree on where the sketch plane sits.

Validity (design §4.3): revolving a profile the axis *crosses* sweeps material
through itself — an invalid, self-intersecting body. That is detected up front,
in the 2D sketch plane, as :class:`AxisIntersectsProfileError`; a profile that
merely *touches* the axis (a solid of revolution against its own centerline) is
valid and passes. A profile strictly on one side of the axis is the annulus /
shaft / disc case.

Determinism (RESEARCH §9): the profile is built in entity list order, the axis
is a pure function of two solved points, and the OCCT revolve + boolean are
pure algorithms on identical inputs — no unordered iteration participates.
"""

import math
from collections.abc import Sequence

from build123d import Axis, Face, Plane, Solid
from py_kit.schemas.sketch import (
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
)

from geometry.kernel.extrude import plane_point_to_world

#: Clearance tolerance (mm) for the axis-vs-profile side test, aligned with the
#: kernel linear tolerance (1e-7 m; model units are mm). A profile point within
#: this band of the axis line counts as ON the axis (touching, allowed), not
#: across it — so a solid of revolution built against its own centerline passes
#: while a genuinely straddling profile fails.
AXIS_CLEARANCE_TOL = 1e-7

#: Arc sampling density for the side test. Lines and circles get exact extreme
#: signed distances; an arc's extremum need not fall at an endpoint, so it is
#: sampled at this many points across its span (a smooth circular arc, so a
#: dense uniform sample cannot miss a side change of meaningful extent).
_ARC_SAMPLES = 64


class NoAxisError(ValueError):
    """The revolve axis reference does not resolve to a usable sketch line
    (unknown entity id, the entity is not a line, or the line is degenerate)."""


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
    length = math.hypot(dx, dy)  # > 0: resolve_axis_line rejected degenerate
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
    axis: SketchLine, entities: Sequence[SketchEntity]
) -> None:
    """Reject an axis that crosses the profile interior (design §4.3).

    Raises:
        AxisIntersectsProfileError: the profile has geometry strictly on BOTH
            sides of the axis line. Touching the axis (one bound at 0 within
            :data:`AXIS_CLEARANCE_TOL`) is valid — a solid of revolution built
            against its own centerline.
    """
    lo, hi = _axis_side_bounds(axis, entities)
    if lo < -AXIS_CLEARANCE_TOL and hi > AXIS_CLEARANCE_TOL:
        raise AxisIntersectsProfileError(
            "The axis of revolution crosses the profile: revolving it would "
            "sweep material through itself. Move the axis so the whole profile "
            "lies on one side of it (touching is allowed)."
        )


def revolve_face(
    face: Face,
    axis: SketchLine,
    plane: Plane,
    angle_deg: float,
    reverse: bool,
) -> Solid:
    """Revolve *face* about the sketch-plane *axis* line by *angle_deg*.

    The axis is built from the line's two endpoints mapped to world space
    through the profile's resolved sketch *plane* (shared mapping — the axis and
    profile agree on plane placement, including on an offset ``datum`` plane).
    ``reverse`` sweeps the opposite way about the axis (visible only for a
    partial angle; a full 360° is handed either way).

    Raises:
        RevolveError: the OCCT revolve failed or left other than exactly one
            solid (single body chain per part in v1, design §7.6).
    """
    if not 0.0 < angle_deg <= 360.0:
        raise ValueError(f"angle_deg must be in (0, 360], got {angle_deg}")

    origin = plane_point_to_world(plane, axis.start)
    direction = plane_point_to_world(plane, axis.end) - origin
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
    return solids[0].clean()
