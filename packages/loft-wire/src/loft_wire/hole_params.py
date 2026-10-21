"""Hole params: a face-placed drill (through-all or blind, plain or recessed,
optionally tapped), split out of :mod:`loft_wire.features` (FILE-SIZE-RATCHET).

:mod:`loft_wire.features` re-exports every name here, so ``from
loft_wire.features import HoleParamsV1`` keeps working and the generated
contracts are unchanged (pydantic names schemas by class, not module).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from loft_wire.geometry import Vec3
from loft_wire.hole_placement import FACE_X_FIELD, FACE_Y_FIELD, derive_hole_position
from loft_wire.refs import FeatureRef, SubshapeRef

# --- Hole params — a first-class face-placed drill (slice 1: the simple hole) ----
#
# A dedicated HOLE feature, NOT a hand-sketched circle cut: pick a planar face,
# a point on it, a diameter, and a depth (through-all or blind), and the geometry
# service drills a cylinder INTO the material (opposite the face's outward normal
# — the correct cut direction, automatically). This erases the highest-frequency
# everyday-modeling friction (sketch a circle → constrain → extrude-cut, every
# time) and later seeds drawing hole callouts.
#
# The placement REUSES the existing face-reference grammar, not a new taxonomy:
# `face` is the SAME stage-1 planar-face :class:`SubshapeRef` the `on_face` datum,
# the shell openings, and the sketch-on-a-face path already resolve (topo-naming
# §4) — a pick UI echoes a `/overlay` face signature straight in. So a hole is
# body-MODIFYING off the implicit single body chain (design §7.6, like fillet/
# shell/draft) AND names a face reference that materialises into
# feature_dependencies (deleting the placement-face's feature is a write-time
# 409-with-dependents; a reorder re-checks strict-backward).
#
# SCOPE: a SIMPLE straight drilled hole — through-all OR a blind depth (slice 1)
# — PLUS an optional coaxial RECESS at the placement face (slice 2): a larger
# cylindrical `counterbore` (seats a socket-head cap screw) or a `countersink`
# cone (seats a flat-head screw). The recess is a `HoleType`-discriminated member
# (:data:`HoleType`) added to `HoleParamsV1` ADDITIVELY — the base bore is
# unchanged and a legacy hole with no `type` reads `simple`, so NO `param_version`
# bump (the RevolveAxis / DatumParams / PatternGeometry idiom).
#
# SLICE 2 TAIL — TAPPED holes (2026-07-25): a tapped hole is the tap-drill bore
# PLUS a typed thread callout (`thread`), NOT modelled helical geometry (the
# COSMETIC representation every incumbent defaults to; the decision, its
# trade-off, and what would have to change to model threads later are recorded in
# `geometry.kernel.threads`). Two shape decisions worth stating, because both
# could reasonably have gone the other way:
#
#   * `thread` is its OWN optional field, NOT a fourth `HoleType` member.
#     Threading is ORTHOGONAL to the recess — a counterbored tapped hole (cap
#     screw head sunk over a tapped bore) is an everyday feature, and a `tapped`
#     member of the `type` union would have made those mutually exclusive. It
#     also keeps the `HoleType` union (and every consumer narrowing on its
#     `kind`) unchanged.
#   * The bore stays AUTHORED (`diameter_mm`), and the callout is checked against
#     it: the drilled hole must lie in `[minor diameter, nominal diameter)` for
#     the designation (the ISO tap drill `D - P` sits strictly inside), so a shop
#     table's rounded stock drill is accepted while an M6 callout on a Ø20 bore
#     is a typed `hole_thread_mismatch`. An unknown (nominal, pitch) pair is a
#     typed `hole_thread_unsupported`. Neither EVER degrades to a plain hole
#     carrying a thread callout nobody can cut.
#
# Standard drill-size tables remain a future additive member.


class HoleThroughAll(BaseModel):
    """A hole that cuts fully THROUGH the body (``kind: "through_all"``).

    No depth to specify — the drill clears the body on both sides regardless of
    the local wall thickness (the geometry service spans the bounding box). The
    default ``kind`` makes ``{"kind": "through_all"}`` explicit while a future
    additive depth mode joins the discriminated union without a bump.
    """

    kind: Literal["through_all"] = "through_all"


class HoleBlindDepth(BaseModel):
    """A blind hole drilled ``depth_mm`` into the material (``kind: "blind"``).

    ``depth_mm`` is measured from the placement face INTO the solid along the
    (inward) drill axis. A depth that exceeds the available material — the drill
    would break through the far side — is a per-feature ``hole_too_deep`` rebuild
    error (use a through-all hole instead), never a silently wrong body.
    """

    kind: Literal["blind"]
    depth_mm: float = Field(
        gt=0,
        description="Depth of the blind hole from the face into the material (mm)",
    )


#: A hole's depth mode — cut fully through, or a blind pocket — discriminated on
#: ``kind``. The ``counterbore`` / ``countersink`` shape is a SEPARATE param
#: (the hole TYPE — :data:`HoleType`), not a depth mode; this union stays
#: through-all|blind (a recess is measured from the face independently of it).
HoleDepth = Annotated[HoleThroughAll | HoleBlindDepth, Field(discriminator="kind")]


class HoleSimple(BaseModel):
    """A plain straight drilled hole — no recess (``kind: "simple"``, the default).

    The slice-1 shape: the bore alone (``diameter_mm`` + the through-all|blind
    ``depth``), with no counterbore/countersink recess at the face. ``kind``
    DEFAULTS to ``"simple"`` so a legacy :class:`HoleParamsV1` that carries NO
    ``type`` validates unchanged — the discriminated :data:`HoleType` is a purely
    ADDITIVE member (NO ``param_version`` bump; the RevolveAxis / DatumParams
    idiom).
    """

    kind: Literal["simple"] = "simple"


class HoleCounterbore(BaseModel):
    """A larger coaxial CYLINDRICAL recess at the face (``kind: "counterbore"``).

    Seats a socket-head cap screw: a flat-bottomed cylinder of
    ``cbore_diameter_mm`` sunk ``cbore_depth_mm`` from the placement face, coaxial
    with the bore, subtracted ALONGSIDE the bore. The recess diameter must exceed
    the bore ``diameter_mm`` and its depth must fit within the body's thickness —
    an invalid recess degrades to a typed ``hole_cbore_invalid`` (diameter) /
    ``hole_too_deep`` (depth) rebuild error, never a raise or a silently wrong
    body (the never-500 posture the simple hole already holds).
    """

    kind: Literal["counterbore"]
    cbore_diameter_mm: float = Field(
        gt=0,
        description="Counterbore recess diameter (mm); must EXCEED the bore "
        "`diameter_mm` (a `hole_cbore_invalid` rebuild error otherwise)",
    )
    cbore_depth_mm: float = Field(
        gt=0,
        description="Depth of the counterbore recess from the face into the "
        "material (mm); must fit the body thickness (a `hole_too_deep` otherwise)",
    )


class HoleCountersink(BaseModel):
    """A coaxial CONICAL recess at the face (``kind: "countersink"``).

    Seats a flat-head screw: a truncated cone — ``csink_diameter_mm`` wide at the
    surface, tapering at the ``csink_angle_deg`` INCLUDED angle (82° and 90° are
    the fastener standards) down to the bore diameter — subtracted alongside the
    bore. The mouth diameter must exceed the bore ``diameter_mm`` and the cone
    depth the angle implies must fit the body — an invalid recess degrades to a
    typed ``hole_csink_invalid`` (diameter) / ``hole_too_deep`` (depth) rebuild
    error, never a raise.
    """

    kind: Literal["countersink"]
    csink_diameter_mm: float = Field(
        gt=0,
        description="Countersink mouth diameter at the face surface (mm); must "
        "EXCEED the bore `diameter_mm` (a `hole_csink_invalid` otherwise)",
    )
    csink_angle_deg: float = Field(
        gt=0.0,
        lt=180.0,
        description="INCLUDED cone angle (degrees); 82 and 90 are the flat-head "
        "fastener standards. The cone tapers from the mouth diameter down to the "
        "bore diameter over a depth the angle implies.",
    )


#: A hole's TYPE — a plain bore, or a bore PLUS a coaxial recess at the face —
#: discriminated on ``kind``. ADDITIVE to :class:`HoleParamsV1` (the base bore is
#: unchanged; the type only ADDS the recess): a legacy hole with no ``type`` reads
#: ``simple``, so NO ``param_version`` bump (the RevolveAxis / DatumParams /
#: PatternGeometry idiom). A tapped hole is NOT a member here — threading is
#: orthogonal to the recess (a counterbored tapped hole is an everyday feature),
#: so it rides on its own :class:`IsoMetricThread` field (see the section comment).
HoleType = Annotated[
    HoleSimple | HoleCounterbore | HoleCountersink, Field(discriminator="kind")
]


class IsoMetricThread(BaseModel):
    """An ISO 261 metric thread callout on a hole (``standard: "iso_metric"``).

    The COSMETIC thread representation: the kernel cuts the tap-drill bore only
    (``diameter_mm``) and carries this designation as metadata for drawing/BOM/
    export callouts — it does NOT model helical geometry (decision + rationale +
    the upgrade path in ``geometry.kernel.threads``). ``standard`` is required so
    a future thread standard (UNC/UNF, NPT) joins as a discriminated union member
    without a ``param_version`` bump.

    The pair (``nominal_diameter_mm``, ``pitch_mm``) must be a real ISO 261
    combination — M10 x 1.5 (coarse) or M10 x 1.25/1/0.75 (fine), say — and the
    hole's ``diameter_mm`` must be a hole the tap can actually cut, i.e. within
    ``[D - 1.0825*P, D)``. The ISO recommended tap drill is ``D - P`` (5.0 mm for
    M6 x 1, 8.5 mm for M10 x 1.5 — the published tables' values). Violations are
    the typed rebuild errors ``hole_thread_unsupported`` / ``hole_thread_mismatch``
    — never a silent fallback to an untapped hole.
    """

    standard: Literal["iso_metric"]
    nominal_diameter_mm: float = Field(
        gt=0,
        description="Nominal (major) thread diameter — the `M` number, mm: 10.0 "
        "for M10x1.5. Must be an ISO 261 size (a `hole_thread_unsupported` "
        "rebuild error otherwise)",
    )
    pitch_mm: float = Field(
        gt=0,
        description="Thread pitch (mm): 1.5 for M10x1.5. Must be a standard pitch "
        "for that nominal diameter (a `hole_thread_unsupported` otherwise)",
    )


class HoleParamsV1(BaseModel):
    """A face-placed cylindrical hole — through-all or blind, plain or recessed.

    The dedicated Hole feature (BACKLOG P2): drill a straight cylinder of
    ``diameter_mm`` into the body that OWNS the planar ``face`` (in a multi-body
    part, the body whose face was picked — not the last one built), at ``position``,
    cutting INTO the material (opposite the face's outward normal — the correct
    direction, chosen automatically, no direction knob to get wrong). Like a
    fillet/shell/draft it modifies the implicit single body chain (design §7.6),
    so it carries no whole-feature ``FeatureRef`` — its dependency on the prior
    body-affecting feature is tree order. The placement face IS a named reference,
    though: ``face`` is the SAME stage-1 planar-face :class:`SubshapeRef` the
    ``on_face`` datum / shell openings resolve, so it materialises into
    ``feature_dependencies`` (deleting that body feature is a 409-with-dependents;
    a reorder re-checks strict-backward).

    ``position`` is a WORLD point, projected onto the resolved face plane to fix
    the drill axis; with ``face_x_mm``/``face_y_mm`` it is derived from them
    (:mod:`loft_wire.hole_placement`). Off the body is ``hole_off_body``.

    ``depth`` is a :data:`HoleDepth`: ``through_all`` cuts fully through;
    ``blind`` drills a ``depth_mm`` pocket. A blind depth that exceeds the
    available material is ``hole_too_deep``. A non-planar / missing / congruent
    face reference degrades exactly as the ``on_face`` datum does
    (``subshape_unresolved`` / ``subshape_ambiguous``) — planar faces only carry a
    signature, so a non-planar pick cannot be authored.

    ``type`` is a :data:`HoleType`: ``simple`` (the default when omitted — the
    slice-1 plain bore) or a bore PLUS a coaxial recess at the face —
    ``counterbore`` (a larger cylinder) or ``countersink`` (a cone). A recess
    whose diameter does not exceed the bore is ``hole_cbore_invalid`` /
    ``hole_csink_invalid``; a recess deeper than the material is ``hole_too_deep``.

    ``thread`` (optional, ``None`` = an untapped hole) makes the hole TAPPED: a
    cosmetic :class:`IsoMetricThread` callout over the tap-drill bore, ORTHOGONAL
    to ``type`` (a counterbored tapped hole sets both). It adds NO geometry, so a
    tapped hole mirrors, patterns, shells and exports exactly as its bore does.
    ``hole_thread_unsupported`` / ``hole_thread_mismatch`` refuse a bad callout.
    """

    face: SubshapeRef = Field(
        description="Planar face of an earlier body-affecting feature to drill "
        "into (the SAME stage-1 signature reference the on_face datum uses)"
    )
    position: Vec3 = Field(
        description="World-space placement point, projected onto the face plane "
        "to fix the drill axis (mm)"
    )
    diameter_mm: float = Field(gt=0, description="Hole diameter (mm)")
    depth: HoleDepth = Field(
        description="Through-all, or a blind pocket depth (:data:`HoleDepth`)"
    )
    type: HoleType = Field(
        default_factory=HoleSimple,
        description="Hole type: a plain bore (`simple`, the default when omitted "
        "— slice-1 behaviour) or a bore plus a coaxial counterbore / countersink "
        "recess at the face (:data:`HoleType`)",
    )
    thread: IsoMetricThread | None = Field(
        default=None,
        description="Optional COSMETIC thread callout making this a TAPPED hole "
        "(`null`/omitted = untapped). Carries the designation for drawing/BOM "
        "callouts; adds no geometry — `diameter_mm` is the tap-drill bore "
        "(:class:`IsoMetricThread`)",
    )
    face_x_mm: float | None = FACE_X_FIELD
    face_y_mm: float | None = FACE_Y_FIELD
    scope_bodies: list[FeatureRef] | None = Field(
        default=None,
        description="Feature Scope (SolidWorks): further bodies a THROUGH-ALL "
        "bore also cuts, each named by its base (body-creating) feature. "
        "`null`/omitted cuts only the body that owns `face` (the Fusion 360 / "
        "SolidWorks default). The bore cuts each listed body coaxially; a "
        "counterbore / countersink recess seats in the owner only. A listed "
        "body the bore cannot reach is `hole_off_body`",
    )
    _derive_position = model_validator(mode="after")(derive_hole_position)

    @model_validator(mode="after")
    def _scope_is_through_all_and_distinct(self) -> "HoleParamsV1":
        """A scope needs a through-all bore (a blind depth is measured on one
        body) and names each body at most once."""
        if not self.scope_bodies:
            return self
        if not isinstance(self.depth, HoleThroughAll):
            raise ValueError(
                "scope_bodies requires a through_all depth: a blind hole's depth "
                "is measured in the body that owns its face"
            )
        ids = [ref.feature_id for ref in self.scope_bodies]
        if len(set(ids)) != len(ids):
            raise ValueError("scope_bodies names the same body more than once")
        return self
