"""Linear/circular pattern — replicate a source solid; union it or cut it.

The kernel half of the pattern feature (feature-tree design §4.3; BACKLOG #7,
BACKLOG #3 pattern-a-cut / showcase F1).

v1 DESIGN DECISION (recorded in docs/GEOMETRY-QA.md 2026-07-12/2026-07-13): a
pattern places rigid copies of a source solid at a linear row / circular ring
of placements about world-space direction/axis vectors — never picked
sub-geometry, so (like revolve's axis) it is independent of topological naming
(#1). Placement 0 is the seed (already in the body); placements ``1..count-1``
are transformed copies. TWO combine modes, both exact rigid transforms with no
solid-delta extraction:

* ADD (the original, BACKLOG #7): the source solid IS the current evaluated
  body, and the copies are BOOLEAN-UNIONED into the single body chain (design
  §7.6) — the boss/prism array. :func:`linear_pattern` / :func:`circular_pattern`.
* CUT (BACKLOG #3 / showcase F1): the source solid is the removal TOOL of the
  immediately-preceding cut feature (a bolt-circle hole, a lightening hole), and
  the copies are BOOLEAN-CUT from the current body — so one hole-cut + a circular
  pattern removes N holes, not N bodies. :func:`linear_pattern_cut` /
  :func:`circular_pattern_cut`. The feature layer reconstructs the tool from the
  source feature's already-solved profile (evaluate.py), so this kernel is
  mode-agnostic: it is handed the solid(s) to replicate and the placements.

Documented limitations (GEOMETRY-QA): the ADD mode arrays the WHOLE body-so-far
(feature-scoped ADD patterning of one boss's tool is future work); the CUT mode
arrays the immediately-preceding cut feature's tool (an intervening
fillet/etc. falls back to ADD — the source is inferred from tree order, not a
picked reference). Either way the result must be ONE connected solid (§7.6): a
disjoint union or a cut that severs the body raises :class:`PatternDisjointError`
until multi-body parts land.

All pattern value validation lives here (not as pydantic Field constraints —
see the DTO note in :mod:`py_kit.schemas.features`): the typed exceptions below
carry **sanitized messages**, which the feature layer maps 1:1 onto per-feature
``pattern_*`` error codes so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): placements are a pure function of the params in
ascending instance order; the OCCT transform + fuse/cut are pure algorithms on
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
    """The OCCT union/cut of an instance failed or produced an unsupported
    result (e.g. a patterned cut consumed the whole body)."""


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


def _cut_and_finalize(body: Solid, tools: Sequence[Solid], count: int) -> Solid:
    """Boolean-CUT every *tool* copy from *body* and require one connected solid.

    The subtractive twin of :func:`_fuse_and_finalize` (BACKLOG #3 / showcase
    F1): a single variadic ``cut`` (as :func:`geometry.kernel.extrude.combine_body`
    does its boolean) removes every patterned tool copy in one operation, then
    ``clean()`` collapses the redundant seams the cut leaves behind — keeping
    topology counts meaningful (and golden-assertable). A cut that consumes the
    whole body or severs it into disjoint lumps is the §7.6 single-body-chain
    violation.

    Raises:
        PatternError: the OCCT cut failed or removed the entire body.
        PatternDisjointError: the cut severed the body into >1 solid.
    """
    try:
        # cut carries Shape[Unknown] type params upstream (same gap
        # tessellate.py documents for export_gltf) — scoped ignore only.
        cut = body.cut(*tools)  # pyright: ignore[reportUnknownMemberType]
        solids = cut.clean().solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise PatternError(
            f"Pattern cut failed in the kernel ({type(exc).__name__}); a tool "
            "copy may graze or self-intersect the body."
        ) from exc

    if len(solids) == 0:
        raise PatternError(
            f"The pattern's {count} cut instances removed the entire body — "
            "nothing remains. Reduce the count or the tool size."
        )
    if len(solids) > 1:
        raise PatternDisjointError(
            f"The pattern's {count} cut instances severed the body into "
            f"{len(solids)} disjoint lumps, but v1 parts are one body (design "
            "§7.6). Move the cuts so they do not slice the body apart, or await "
            "multi-body support."
        )
    return solids[0]


def _linear_unit(direction: tuple[float, float, float]) -> Vector:
    """Validate a linear direction to its unit vector (shared by add/cut)."""
    dx, dy, dz = direction
    magnitude = math.sqrt(dx * dx + dy * dy + dz * dz)
    if magnitude <= MIN_DIRECTION_MAGNITUDE:
        raise PatternDirectionError(
            "Linear pattern direction vector is zero-length; it has no "
            "direction to array along."
        )
    return Vector(dx / magnitude, dy / magnitude, dz / magnitude)


def _linear_copies(
    sources: Sequence[Solid],
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> list[Solid]:
    """Copies of every *source* at placements ``k = 1..count-1`` along a row.

    Validated once (spacing then direction) and enumerated placement-outer,
    source-inner so a single source (the ADD body) reproduces the original
    ``[body.translate(...) for k in ...]`` order byte-for-byte.

    Raises:
        PatternSpacingError: ``spacing_mm <= 0`` (with copies to place).
        PatternDirectionError: the direction vector is (near) zero-length.
    """
    if spacing_mm <= 0.0:
        raise PatternSpacingError(
            f"Linear pattern spacing must be > 0, got {spacing_mm} mm; "
            "instances would coincide."
        )
    unit = _linear_unit(direction)
    return [
        source.translate(unit * (spacing_mm * k))
        for k in range(1, count)
        for source in sources
    ]


def _circular_copies(
    sources: Sequence[Solid],
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> list[Solid]:
    """Copies of every *source* at placements ``k = 1..count-1`` about a ring.

    Validated once (axis then angle) and enumerated placement-outer,
    source-inner so a single source (the ADD body) reproduces the original
    ``[body.rotate(...) for k in ...]`` order byte-for-byte.

    Raises:
        PatternAxisError: the axis direction is (near) zero-length.
        PatternAngleError: ``angle_deg`` outside (0, 360] with copies to place.
    """
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
    return [
        source.rotate(axis, step * k)  # pyright: ignore[reportUnknownMemberType]
        for k in range(1, count)
        for source in sources
    ]


def linear_pattern(
    body: Solid,
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> Solid:
    """Array *body* into a row of *count* along the world *direction* (ADD).

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
    copies = _linear_copies([body], direction, spacing_mm, count)
    return _fuse_and_finalize(body, copies, count)


def circular_pattern(
    body: Solid,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> Solid:
    """Array *body* into a ring of *count* about the world axis (ADD).

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
    copies = _circular_copies([body], axis_point, axis_direction, angle_deg, count)
    return _fuse_and_finalize(body, copies, count)


def linear_pattern_cut(
    body: Solid,
    tools: Sequence[Solid],
    direction: tuple[float, float, float],
    spacing_mm: float,
    count: int,
) -> Solid:
    """Array the cut *tools* into a row of *count* and remove them from *body*.

    The subtractive twin of :func:`linear_pattern` (BACKLOG #3 / showcase F1):
    the seed cut (placement 0) is already in *body*; a copy of every tool is
    placed at ``spacing_mm * k`` for ``k = 1..count-1`` and cut from the body,
    so a single hole-cut + this pattern removes *count* holes. ``count == 1``
    returns *body* unchanged.

    Raises:
        PatternCountError: ``count < 1``.
        PatternSpacingError: ``spacing_mm <= 0`` (with copies to place).
        PatternDirectionError: the direction vector is (near) zero-length.
        PatternDisjointError: the cut severed the body into >1 solid.
        PatternError: the OCCT cut failed or removed the entire body.
    """
    _check_count(count)
    if count == 1:
        return body
    copies = _linear_copies(tools, direction, spacing_mm, count)
    return _cut_and_finalize(body, copies, count)


def circular_pattern_cut(
    body: Solid,
    tools: Sequence[Solid],
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
    count: int,
) -> Solid:
    """Array the cut *tools* into a ring of *count* and remove them from *body*.

    The subtractive twin of :func:`circular_pattern` (BACKLOG #3 / showcase F1
    — the bolt-circle / lightening-hole ring): the seed cut (placement 0) is
    already in *body*; a copy of every tool is rotated ``angle_deg / count * k``
    about the axis for ``k = 1..count-1`` and cut from the body, so the closing
    position at ``angle_deg`` is EXCLUSIVE and a 360° sweep is a clean full ring
    of holes. ``count == 1`` returns *body* unchanged.

    Raises:
        PatternCountError: ``count < 1``.
        PatternAxisError: the axis direction is (near) zero-length.
        PatternAngleError: ``angle_deg`` outside (0, 360] with copies to place.
        PatternDisjointError: the cut severed the body into >1 solid.
        PatternError: the OCCT cut failed or removed the entire body.
    """
    _check_count(count)
    if count == 1:
        return body
    copies = _circular_copies(tools, axis_point, axis_direction, angle_deg, count)
    return _cut_and_finalize(body, copies, count)
