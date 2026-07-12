"""Linear/circular pattern — replicate the current body and union the copies.

The kernel half of the pattern feature (feature-tree design §4.3; BACKLOG #7).

v1 DESIGN DECISION (option B, recorded in docs/GEOMETRY-QA.md 2026-07-12): a
pattern replicates the CURRENT evaluated body — everything modelled so far —
and BOOLEAN-UNIONS the copies into the single body chain (design §7.6).
Instance 0 is the existing body (never double-counted); instances ``1..count-1``
are rigid copies transformed to each placement and fused in. A pattern arrays
WHOLE features by tree position about world-space direction/axis vectors —
never picked sub-geometry — so, like revolve's axis, it is independent of
topological naming (#1).

Correct and EXACT for the common case where the body IS the thing to array (a
bare boss/prism): a pure rigid transform + fuse, no solid-delta extraction, no
hidden inaccuracy. Documented limitations (GEOMETRY-QA):

* it arrays the WHOLE body-so-far — any base is dragged to each placement;
  feature-scoped patterning of one feature's tool solid is future work;
* additive UNION only — no cut/hole arrays in v1;
* the copies must merge into ONE connected solid (§7.6) — a pattern whose
  instances are disjoint raises :class:`PatternDisjointError` until multi-body
  parts land.

All pattern value validation lives here (not as pydantic Field constraints —
see the DTO note in :mod:`py_kit.schemas.features`): the typed exceptions below
carry **sanitized messages**, which the feature layer maps 1:1 onto per-feature
``pattern_*`` error codes so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): placements are a pure function of the params in
ascending instance order; the OCCT transform + fuse are pure algorithms on
identical inputs; no unordered iteration participates.
"""

import math
from collections.abc import Sequence

from build123d import Axis, Solid, Vector

#: Minimum magnitude (mm-agnostic) for a direction/axis vector to define a
#: direction. Aligned with the kernel linear tolerance posture (1e-7 m); below
#: it the vector has no usable direction.
MIN_DIRECTION_MAGNITUDE = 1e-9


class PatternCountError(ValueError):
    """The instance count is below 1 (a pattern has at least the seed)."""


class PatternSpacingError(ValueError):
    """The linear spacing is zero or negative (instances would coincide)."""


class PatternDirectionError(ValueError):
    """The linear direction vector is (near) zero-length — no direction."""


class PatternAxisError(ValueError):
    """The circular axis direction is (near) zero-length — no axis to spin
    about."""


class PatternAngleError(ValueError):
    """The circular sweep angle is outside (0, 360] with more than one
    instance (a zero sweep collapses every copy onto the seed)."""


class PatternDisjointError(RuntimeError):
    """The pattern's instances do not merge into a single connected solid
    (§7.6 single body chain); v1 has no multi-body parts."""


class PatternError(RuntimeError):
    """The OCCT union of an instance failed or produced an unsupported
    result."""


def _check_count(count: int) -> None:
    if count < 1:
        raise PatternCountError(
            f"Pattern count must be at least 1 (the seed instance is instance "
            f"0), got {count}."
        )


def _fuse_and_finalize(body: Solid, copies: Sequence[Solid], count: int) -> Solid:
    """Boolean-union every *copy* onto *body* and require one connected solid.

    A single variadic ``fuse`` (as :func:`geometry.kernel.extrude.combine_body`
    does its boolean) so the result type stays a plain shape, then ``clean()``
    collapses the redundant seams a union leaves behind — keeping topology
    counts meaningful (and golden-assertable). A union that leaves more than one
    solid is the §7.6 single-body-chain violation.

    Raises:
        PatternError: the OCCT union failed.
        PatternDisjointError: the union left other than exactly one solid.
    """
    try:
        # fuse carries Shape[Unknown] type params upstream (same gap
        # tessellate.py documents for export_gltf) — scoped ignore only.
        fused = body.fuse(*copies)  # pyright: ignore[reportUnknownMemberType]
        solids = fused.clean().solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise PatternError(
            f"Pattern union failed in the kernel ({type(exc).__name__}); an "
            "instance may self-intersect the body."
        ) from exc

    if len(solids) != 1:
        raise PatternDisjointError(
            f"The pattern's {count} instances do not merge into a single "
            f"connected solid — the union left {len(solids)} disjoint lumps, "
            "but v1 parts are one body (design §7.6). Overlap or abut the "
            "instances (reduce the spacing/angle), or await multi-body support."
        )
    return solids[0]


def linear_pattern(
    body: Solid,
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> Solid:
    """Array *body* into a row of *count* along the world *direction*.

    Instance 0 is *body* itself; instances ``1..count-1`` are placed at
    ``spacing_mm * k`` along the unit direction and fused in. ``count == 1``
    returns *body* unchanged (a no-op pattern).

    Raises:
        PatternCountError: ``count < 1``.
        PatternSpacingError: ``spacing_mm <= 0`` (with copies to place).
        PatternDirectionError: the direction vector is (near) zero-length.
        PatternDisjointError: the instances do not merge into one solid.
        PatternError: the OCCT union failed.
    """
    _check_count(count)
    if count == 1:
        return body  # seed only — nothing to replicate
    if spacing_mm <= 0.0:
        raise PatternSpacingError(
            f"Linear pattern spacing must be > 0, got {spacing_mm} mm; "
            "instances would coincide."
        )
    dx, dy, dz = direction
    magnitude = math.sqrt(dx * dx + dy * dy + dz * dz)
    if magnitude <= MIN_DIRECTION_MAGNITUDE:
        raise PatternDirectionError(
            "Linear pattern direction vector is zero-length; it has no "
            "direction to array along."
        )
    unit = Vector(dx / magnitude, dy / magnitude, dz / magnitude)

    copies = [body.translate(unit * (spacing_mm * k)) for k in range(1, count)]
    return _fuse_and_finalize(body, copies, count)


def circular_pattern(
    body: Solid,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> Solid:
    """Array *body* into a ring of *count* about the world axis.

    Instance 0 is *body*; instances ``1..count-1`` are rotated ``angle_deg /
    count * k`` about the axis (through *axis_point* along *axis_direction*)
    and fused in — so the closing position at ``angle_deg`` is EXCLUSIVE and a
    360° sweep is a clean full ring. ``count == 1`` returns *body* unchanged.

    Raises:
        PatternCountError: ``count < 1``.
        PatternAxisError: the axis direction is (near) zero-length.
        PatternAngleError: ``angle_deg`` outside (0, 360] with copies to place.
        PatternDisjointError: the instances do not merge into one solid.
        PatternError: the OCCT union failed.
    """
    _check_count(count)
    if count == 1:
        return body
    dx, dy, dz = axis_direction
    magnitude = math.sqrt(dx * dx + dy * dy + dz * dz)
    if magnitude <= MIN_DIRECTION_MAGNITUDE:
        raise PatternAxisError(
            "Circular pattern axis direction is zero-length; it defines no "
            "axis to rotate about."
        )
    if not 0.0 < angle_deg <= 360.0:
        raise PatternAngleError(
            f"Circular pattern sweep must be in (0, 360] degrees with more "
            f"than one instance, got {angle_deg}; a zero sweep collapses every "
            "copy onto the seed."
        )
    axis = Axis(Vector(*axis_point), Vector(dx, dy, dz))
    step = angle_deg / count

    # rotate carries Shape[Unknown] type params upstream — scoped ignore.
    copies = [
        body.rotate(axis, step * k)  # pyright: ignore[reportUnknownMemberType]
        for k in range(1, count)
    ]
    return _fuse_and_finalize(body, copies, count)
