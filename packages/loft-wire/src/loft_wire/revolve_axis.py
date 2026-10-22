"""Revolve axes: a profile sketch's line or a world origin axis, split out of
:mod:`loft_wire.features` (FILE-SIZE-RATCHET).

:mod:`loft_wire.features` re-exports every name here, so ``from
loft_wire.features import RevolveAxis`` keeps working and the generated
contracts are unchanged (pydantic names schemas by class, not module).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from loft_wire.sketch import EntityId


class SketchLineAxis(BaseModel):
    """``kind: "sketch_line"`` — a LINE entity of the profile's own sketch.

    The v1 axis reference, and still the most direct one: a line entity named by
    its sketch-local id (design §2.4 entity ids) within the SAME sketch the
    profile comes from. A **construction** line is the natural choice — a
    centerline is reference-only (excluded from the closed-wire profile) and is
    exactly what an axis of revolution is — but any line entity resolves; the
    axis is defined by the line's two solved endpoints, mapped to world space
    through the profile's datum plane.

    This variant alone can also CLOSE a half-profile: a three-sided L or
    rectangle whose fourth side is the centerline builds the face the
    revolution needs (see :func:`geometry.kernel.revolve.build_revolve_profile_face`).
    An :class:`OriginAxis` is not a sketch entity, so it cannot close anything —
    a profile revolved about an origin axis must already be a closed loop.
    """

    kind: Literal["sketch_line"] = "sketch_line"
    entity: EntityId = Field(
        description="Sketch-local id of a LINE entity in the profile's sketch "
        "(a construction centerline is ideal) used as the axis of revolution"
    )


class OriginAxis(BaseModel):
    """``kind: "origin_axis"`` — one of the three WORLD origin axes (X, Y, Z).

    The always-available axis (REVOLVE-1): a part that has no construction
    centerline drawn still has X, Y and Z through the world origin, so a plain
    closed profile can be turned without first learning the centerline idiom.
    The reference is a pure enum — no sketch entity, no picked sub-geometry —
    so it is the most rebuild-stable axis there is: nothing upstream can move,
    rename or delete it, and it is wholly independent of topological naming (#1).

    The axis must LIE IN the profile's sketch plane, exactly as a sketch-line
    axis does by construction. Revolving a planar profile about an axis that
    leaves its plane sweeps material out of the profile's own cross-section, so
    an out-of-plane pick is the per-feature ``axis_not_in_sketch_plane`` error,
    never a silently wrong solid. Concretely: a sketch on the ``XY`` origin
    datum turns about ``X`` or ``Y`` and REFUSES ``Z`` (its normal); ``XZ``
    turns about ``X`` or ``Z`` and refuses ``Y``; ``YZ`` turns about ``Y`` or
    ``Z`` and refuses ``X``. A sketch on an OFFSET datum refuses every origin
    axis that its offset has lifted the plane away from (RESEARCH §12 — the
    plane slides along its own normal), which is honest: the origin axis is no
    longer in that plane.
    """

    kind: Literal["origin_axis"]
    axis: Literal["X", "Y", "Z"] = Field(
        description="World origin axis (through 0,0,0) to revolve about. It "
        "must lie in the profile's sketch plane — an out-of-plane choice (e.g. "
        "Z for a sketch on the XY datum) is an `axis_not_in_sketch_plane` "
        "rebuild error."
    )


#: Discriminated axis-of-revolution union (the :data:`DatumParams` /
#: :data:`PatternGeometry` idiom). ``origin_axis`` joined ADDITIVELY (REVOLVE-1)
#: with **no** ``param_version`` bump: every persisted axis is
#: ``{"kind": "sketch_line", "entity": ...}``, which still validates unchanged,
#: and :meth:`RevolveParamsV1._legacy_sketch_line_kind` supplies the
#: discriminator for the older rows that omit it entirely. A future
#: ``datum_axis`` or ``model_edge`` variant joins the same way.
RevolveAxis = Annotated[SketchLineAxis | OriginAxis, Field(discriminator="kind")]
