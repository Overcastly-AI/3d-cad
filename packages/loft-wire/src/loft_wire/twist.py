"""The twist-angle field shared by the sweep and the legacy extrude twist.

Moved out of :mod:`loft_wire.features` unchanged (FILE-SIZE-RATCHET); that
module re-exports every name, so ``from loft_wire.features import
MAX_TWIST_ANGLE_DEG`` keeps working.
"""

from typing import Any

from pydantic import Field

#: Largest |twist| a twisted extrude accepts (degrees over the whole distance):
#: ten full turns. A request-validation sanity bound, not the geometric limit —
#: how tight a twist the kernel can sweep depends on the profile's radius from
#: the axis and on the distance, so a twist that is inside this bound and still
#: too tight for its profile is refused at rebuild as ``twist_failed``
#: (docs/design/twisted-extrude.md §4). So is a twist with too many turns for
#: its profile to build within the kernel's cost budget, a limit that depends
#: on the profile's edges (design §6.1).
MAX_TWIST_ANGLE_DEG = 3600.0

#: Smallest |twist| that IS a twist (degrees over the whole distance); anything
#: smaller is normalised to "no twist" (absent). 1e-9 deg is 1.75e-11 rad, which
#: moves a point 5.7 m from the axis by 1e-7 mm — the kernel's own linear
#: tolerance — so no modelled part can tell it from zero. It also keeps the
#: kernel's auxiliary helix pitch (360 / twist x distance) finite and sane: a
#: sub-normal twist (5e-324 deg) made that pitch infinite and hung the worker.
MIN_TWIST_ANGLE_DEG = 1e-9


def is_none(value: object) -> bool:
    """``exclude_if`` predicate: an absent optional field is not serialized.

    Used by additive fields whose absence must leave a dumped envelope EXACTLY
    as it was before the field existed — the stored row, the response bytes and
    the rebuild-cache key of every untwisted extrude or sweep
    (:attr:`ExtrudeParamsV1.twist_angle_deg`, :attr:`SweepParamsV1.twist_angle_deg`).
    """
    return value is None


def twist_angle_field(description: str) -> Any:
    """The ``twist_angle_deg`` field shared by sweep and the legacy extrude twist.

    One definition of the bounds and the serialization (CLAUDE.md DRY rule):
    optional, omitted from a dump while null, finite, and at most
    :data:`MAX_TWIST_ANGLE_DEG` either way. The "too small to be a twist"
    normalisation is :func:`normalised_twist`, run by each model's validator.
    """
    return Field(
        default=None,
        exclude_if=is_none,
        ge=-MAX_TWIST_ANGLE_DEG,
        le=MAX_TWIST_ANGLE_DEG,
        allow_inf_nan=False,
        description=description,
    )


def normalised_twist(twist: float | None) -> float | None:
    """``None`` for every spelling of "no twist" (``None``, ``0``, ``-0``, and
    any ``|twist| < MIN_TWIST_ANGLE_DEG``); the twist itself otherwise."""
    if twist is not None and abs(twist) < MIN_TWIST_ANGLE_DEG:
        return None
    return twist
