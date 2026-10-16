"""Sheet-metal params: base flange, edge flange, hem and corner relief.

Moved out of :mod:`loft_wire.features` unchanged (FILE-SIZE-RATCHET), with
the bend-provenance :class:`CylindricalFaceSignature` they record. That module
re-exports every name, so ``from loft_wire.features import
SheetMetalHemParamsV1`` keeps working and the generated contracts are
unchanged (pydantic names schemas by class, not module).
"""

from typing import Literal

from pydantic import BaseModel, Field

from loft_wire.geometry import Vec3
from loft_wire.merge_field import MERGE_FIELD
from loft_wire.refs import FeatureRef
from loft_wire.signatures import EdgeSubshapeRef


class CylindricalFaceSignature(BaseModel):
    """§5 stage-1 geometric fingerprint of a CYLINDRICAL face — typed, kernel-free.

    The bend-provenance sibling of :class:`PlanarFaceSignature`
    (docs/design/sheet-metal.md §5): a sheet-metal **bend region** is a cylindrical
    face, and the planar signature cannot name one — an outward *normal* and an
    in-plane *centroid* are meaningless for a curved surface, so reusing it would
    be a type error, not a DRY win. This additive schema pins the bend's exact
    B-rep geometry to full precision (§7.2 forbids quantizing the stored identity):
    a point on the bend ``axis_origin`` + the unit ``axis_dir`` + the ``radius_mm``
    + the area ``centroid`` (all world mm). The geometry service EMITS it off a
    cylindrical face at edge-flange construction time
    (:func:`geometry.sheet_metal.resolve.cylindrical_face_signature`) and MATCHES
    it back to the bend face on a rebuilt body
    (:func:`geometry.sheet_metal.resolve.resolve_cylindrical_face`,
    nearest-within-tolerance, exactly one or an honest ``subshape_unresolved`` —
    the same best-effort stage-1 posture as the planar/edge signatures) so the
    unfold pass finds the bend by PROVENANCE, never blind geometric detection
    (§2.2 recognition-vs-provenance).

    ``surface`` is the ``"cylinder"`` discriminator mirroring
    :class:`PlanarFaceSignature`'s structurally-inert ``surface: "plane"`` — the
    seam §5 anticipates for a future ``SelectorV1.signature`` widening to a
    ``Field(discriminator="surface")`` union. v1 keeps the shared planar
    ``SubshapeRef``/``Selector`` machinery unchanged (no feature persists a
    cylindrical SubshapeRef yet — the signature is geometry-internal unfold
    provenance), so this schema is a pure additive sibling: it destabilises no
    persisted planar face reference (DRY — extract the union member on the second
    real consumer, not the first imagined one).
    """

    subshape_type: Literal["face"] = "face"
    surface: Literal["cylinder"] = "cylinder"
    axis_origin: Vec3 = Field(
        description="A point on the bend axis line, world mm (full precision)"
    )
    axis_dir: Vec3 = Field(
        description="Unit vector along the bend axis (full precision)"
    )
    radius_mm: float = Field(
        gt=0,
        description="Cylinder radius (mm) — the bend's inner radius, full precision",
    )
    centroid: Vec3 = Field(
        description="Area centroid of the cylindrical face, world mm (full precision)"
    )


# --- Sheet-metal base flange — an extrude by a fixed gauge, semantically tagged --
#
# The first body of a sheet-metal part (docs/design/sheet-metal.md §4.1): a
# profile sketch thickened by a FIXED gauge thickness — mechanically identical to
# an additive `extrude`, which is exactly why the geometry side reuses
# `extrude.py`'s `build_profile_face` + `extrude_face` thicken path VERBATIM (no
# new kernel geometry code, §4.1). It is a DISTINCT feature type, not a reuse of
# plain `extrude`, for ONE reason (design DECISION §4.1, mirroring how
# `ShellParamsV1` is its own type even though its boolean plumbing reuses
# `extrude.py`'s `combine_body`): it must persist the part's sheet-metal
# parameters (`thickness_mm`, a default `k_factor`, a default `bend_radius_mm`)
# somewhere, and the base flange is the natural anchor — later edge-flange /
# unfold slices READ the gauge + defaults off the base flange body (§5/§9).


#: v1 default K-factor (docs/design/sheet-metal.md §1/§9): the neutral-axis
#: fraction (K ∈ [0, 1]) that locates the bend's neutral surface as a fraction of
#: thickness from the INNER bend face. 0.44 is a common industry-baseline for
#: air-bent mild steel — a DOCUMENTED v1 default, not a universal material
#: constant. Stored on the base flange as the part's sheet-metal default and
#: inherited by every later edge flange (a full gauge/material rule TABLE is
#: deferred, §7/§10). Pinned here so the schema default and the golden's
#: hand-derivation share ONE source (CLAUDE.md DRY rule).
SHEET_METAL_DEFAULT_K_FACTOR = 0.44


class SheetMetalBaseFlangeParamsV1(BaseModel):
    """The first body of a sheet-metal part — a profile thickened to gauge (§4.1).

    A base flange is a profile sketch extruded by a FIXED gauge ``thickness_mm``
    — mechanically an additive extrude, so it shares :class:`ExtrudeParamsV1`'s
    ``profile`` FeatureRef (an EARLIER sketch, design §2.2), ``direction``
    (which side of the sketch plane the gauge grows), and ``merge`` (the
    multi-body ADD flag — a base flange is a body-CREATING base feature, so it
    starts the first body, or a second with ``merge=False``). Kernel-side it
    calls the SAME ``build_profile_face`` + ``extrude_face`` path extrude uses —
    no new geometry code (§4.1).

    Unlike a plain extrude it carries the part's SHEET-METAL DEFAULTS
    (``k_factor``, ``bend_radius_mm``) — the parameters a later edge-flange /
    unfold reads to compute a bend allowance (``BA = angle * (radius + K *
    thickness)``, §1). ``k_factor`` defaults to the v1 pinned
    :data:`SHEET_METAL_DEFAULT_K_FACTOR` (0.44); ``bend_radius_mm`` is REQUIRED
    (no universal default — it is tooling/material dependent) and names the
    part-default inner bend radius edge flanges inherit. Neither default affects
    the base flange's own geometry (a flat plate) — they ride ON the body for the
    downstream slices, exactly as the design's "base flange is the natural anchor
    for the sheet-metal parameters" decision intends.

    There is NO ``operation`` field: a base flange always CREATES material (it is
    the sheet's first body), never a cut. v1 scopes to a single per-part gauge +
    K + default radius (§7); a gauge/material rule table is deferred (§10).
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature whose entities form "
        "the single closed profile wire (design §2.2), thickened to the gauge"
    )
    thickness_mm: float = Field(
        gt=0,
        description="Gauge — the uniform sheet thickness (mm); the fixed distance "
        "the profile is thickened by. The part's one material thickness (§1).",
    )
    k_factor: float = Field(
        default=SHEET_METAL_DEFAULT_K_FACTOR,
        ge=0.0,
        le=1.0,
        description="Neutral-axis fraction K ∈ [0, 1] from the INNER bend face "
        "(§1); the part-default a later edge flange inherits for its bend "
        f"allowance. Defaults to the v1 baseline {SHEET_METAL_DEFAULT_K_FACTOR} "
        "(air-bent mild steel — a documented default, not a universal constant).",
    )
    bend_radius_mm: float = Field(
        gt=0,
        description="Part-default INNER bend radius (mm) a later edge flange "
        "inherits (§4.2). Required — no universal default (tooling/material "
        "dependent). Does not affect the base flange's own flat-plate geometry.",
    )
    direction: Literal["normal", "reverse"] = Field(
        default="normal",
        description="Which side of the sketch plane the gauge grows: 'normal' "
        "along the plane normal, 'reverse' opposite (the extrude `direction` "
        "idiom). Additive-optional; absent reads 'normal'.",
    )
    merge: bool = MERGE_FIELD


# --- Sheet-metal edge flange (bend) — a flange folded off a base-flange edge -----
#
# The headline sheet-metal feature (docs/design/sheet-metal.md §4.2): a new flange
# added off a STRAIGHT EDGE of the base flange, at a chosen bend radius + angle,
# connected to the base by a cylindrical BEND REGION. Geometrically it is a sweep
# of the sheet's thickness cross-section along an arc (the bend) + a straight
# segment (the flange length) — the geometry side reuses `sweep.py`'s
# profile-along-path primitives, driven by named parameters rather than a sketch
# (§4.2 decision: parameter-driven, the incumbent edge-flange gesture, not a raw
# sweep authoring flow). It is a DISTINCT feature type for two reasons (§4.2):
# named parameters instead of a sketch, and BEND PROVENANCE — the feature tags the
# cylindrical bend face with a `CylindricalFaceSignature` (§5) at construction, so
# the unfold pass finds the bend by provenance, never blind detection.
#
# v1 SCOPE (§4.3 depth-1 bend star): each edge flange folds DIRECTLY off the fixed
# base flange (never off another edge flange — depth >= 2 is deferred). N edge
# flanges radiating from one base cover the L-bracket (N=1) and U-channel (N=2)
# without the graph-relaxation a flange-off-a-flange would need.


class SheetMetalEdgeFlangeParamsV1(BaseModel):
    """A flange folded off a straight edge of the base flange (§4.2).

    ``edge`` is an :class:`EdgeSubshapeRef` naming the base-flange edge to fold off
    — the SAME stage-1 :class:`EdgeSignature` machinery a fillet/chamfer pick uses
    (topological-naming §10), resolved against the current sheet body; its
    ``feature_id`` materialises the dependency on the base-flange feature exactly
    like a picked fillet edge. The flange extends outward from that edge in the
    plane of its adjacent flat (plate) face and folds by ``bend_angle_deg`` about a
    bend of ``bend_radius_mm`` (inner radius), producing ONE fused sheet body (the
    base + flange joined across the cylindrical bend region).

    INHERITED DEFAULTS (§4.2): ``bend_radius_mm`` and ``k_factor`` default from the
    part's base flange (:class:`SheetMetalBaseFlangeParamsV1` — the gauge/K/radius
    anchored on the sheet body) when omitted (``None``), and may be OVERRIDDEN
    per-bend. ``flange_length_mm`` is the developed flat length of the flange leg
    (to the bend tangent line, §9 golden #1's convention); ``bend_angle_deg`` is
    the fold angle (90 deg for a right-angle flange).

    Like a fillet/shell it MODIFIES the implicit single body chain (design §7.6) —
    it carries no ``merge`` (it always fuses into the sheet body the edge belongs
    to) — so its only whole-feature dependency is the named-edge ref + tree order.
    """

    edge: EdgeSubshapeRef = Field(
        description="The base-flange STRAIGHT edge to fold off (a stage-1 "
        "EdgeSignature reference resolved against the current sheet body). The "
        "flange extends from this edge's adjacent flat face and folds about it."
    )
    flange_length_mm: float = Field(
        gt=0,
        description="Developed flat length of the flange leg (mm), measured to the "
        "bend tangent line (§9 golden #1 convention).",
    )
    bend_angle_deg: float = Field(
        gt=0.0,
        le=180.0,
        allow_inf_nan=False,
        description="Fold angle (degrees); 90 = a right-angle flange. In (0, 180].",
    )
    bend_radius_mm: float | None = Field(
        default=None,
        gt=0,
        description="INNER bend radius (mm). Omitted (None) inherits the part's "
        "base-flange default `bend_radius_mm` (§4.2); a value overrides it per-bend.",
    )
    k_factor: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Neutral-axis fraction K in [0, 1] for this bend's allowance "
        "(§1). Omitted (None) inherits the part's base-flange default `k_factor` "
        "(0.44 v1 baseline); a value overrides it per-bend.",
    )
    # WIDTH EXTENTS (design §4.5, WF-1 layer 2) — additive, no param_version bump.
    # Absent (None width, 0 offset) = full edge width, byte-identical legacy build.
    width_mm: float | None = Field(
        default=None,
        gt=0,
        description="Flange WIDTH (mm) along the picked edge (design §4.5.1). "
        "Omitted (None) spans the full edge (or the remainder past `offset_mm`). "
        "The span [offset, offset + width] is measured from the edge's CANONICAL "
        "start (the lexicographically smaller endpoint — the stored EdgeSignature's "
        "`end_a`). `offset + width` must fit the resolved edge length (a typed "
        "feature error otherwise). Each span end INTERIOR to the edge gets an "
        "automatic rectangular bend-end relief notch, size = 1 x gauge (§4.5.2).",
    )
    offset_mm: float | None = Field(
        default=None,
        ge=0.0,
        description="Span OFFSET (mm) from the picked edge's canonical start "
        "(its EdgeSignature `end_a`, design §4.5.1). Omitted (None) reads 0 — "
        "the span starts at `end_a`. With `width_mm` omitted the flange spans "
        "[offset, edge_length]. Nullable-optional (like `width_mm`) so existing "
        "clients that never send it stay valid — the additive-field rule.",
    )


# --- Sheet-metal hem — a ~180 deg fold-back of an edge (CLOSED / OPEN) ------------
#
# A HEM folds the sheet's edge ~180 deg back onto itself, forming a doubled, safe
# edge (the incumbents' Hem tool — SolidWorks/Fusion). It is the near-trivial win
# of the parity roadmap (docs/design/sheet-metal-parity.md §2 Hem row / Parity
# roadmap #3): a hem is mechanically a SPECIALIZATION of the shipped edge flange —
# a fixed 180 deg fold, folding the return back over the parent face. Verified
# geometrically (kernel-architect, 2026-07-19): `build_edge_flange` at
# `bend_angle_deg = 180` produces ONE clean valid solid, and the shipped
# `unfold_sheet_metal` develops it correctly as a bend at pi (BA = pi * (radius +
# K * thickness)). So a hem REUSES `build_edge_flange`'s bend machinery verbatim
# (bend_angle fixed at 180) — no new kernel geometry code, no new unfold.
#
# It is a DISTINCT feature type (not a `hem_type` flag on the edge flange) for the
# same reasons the edge flange is distinct from a raw sweep (§4.2), plus one more:
# a hem's authoring gesture NEVER sets a fold angle (it is always ~180) — the user
# picks an edge + a return length, exactly the incumbent Hem tool.
#
# --- THE HEM RADIUS RULE (HEM-1, 2026-08-28) --------------------------------------
#
# **A hem's inner bend radius is a function of its TYPE and the part's GAUGE — never
# of the part's general base-flange bend radius.** The base-flange radius describes
# a FREE-STANDING bend formed in a die; a hem is a fold-back whose radius IS its
# defining dimension, because the fold's cross-section makes the air gap between the
# two layers exactly `2 * bend_radius` (measured, `edge_flange.build_edge_flange`'s
# cross-section at theta = pi: the return's inner face lands at `b = 2r`).
#
# Inheriting the general radius is what shipped HEM-1: a `hem_type="closed"` hem on
# 2 mm sheet with a 3 mm part radius built a **6.00 mm air gap** — three gauges of
# air — under a label, a help text and a readout that all said "closed". Every gate
# passed: the feature built, the status was `ok`, the label was right. That is wrong
# geometry asserted to be correct, which this repo ranks above any missing feature.
#
# The rule, which follows from parity §2's own cited definitions of the four
# incumbent hem shapes (a CLOSED hem is "bent 180 deg flat against the parent, ZERO
# inside radius"; an OPEN hem is the one with the deliberate "air gap"):
#
#   | hem_type   | definition (parity §2)              | inner radius R   | gap=2R |
#   |------------|-------------------------------------|------------------|--------|
#   | `closed`   | pressed flat against the parent     | 0.05 * thickness | 0.1 t  |
#   | `open`     | folded back, deliberate air gap     | 0.50 * thickness | 1.0 t  |
#   | `teardrop` | >180 deg wrap, mouth narrower than ID| not representable|   -    |
#   | `rolled`   | full curl                           | not representable|   -    |
#
# CLOSED — why not zero, and why 0.05 * t. Zero is the physical ideal and is NOT
# buildable, measured three ways on the 50x20x2 plate:
#   * `r = 0` exactly -> OCCT `StdFail_NotDone` (the inner arc's three points
#     coincide), surfacing as the typed `edge_flange_failed`;
#   * `r <= 1e-7` -> `NoBendFoundError`: the fold fuses to one valid solid but
#     leaves no findable bend cylinder, so there is no bend provenance and the part
#     has no flat pattern — a sheet-metal part that cannot be unfolded is not a
#     sheet-metal part;
#   * `r = 1e-6` / `1e-5` (gap 2e-6 / 2e-5 mm) -> the body BUILDS and
#     `geometry.kernel.degenerate.find_zero_width_slits` reports **1 slit**: below
#     the kernel's own linear tolerance (`KERNEL_LINEAR_TOL_MM = 1e-4` mm) the two
#     layers are the SAME PLACE as far as this kernel is concerned, i.e. exactly the
#     degeneracy RESEARCH §9 says to REFUSE rather than ship. The slit disappears at
#     gap 1e-4 mm, the tolerance itself.
# So a closed hem is modelled at the RESIDUAL opening a flattening press leaves, not
# at zero. Hem practice sizes every hem feature in multiples of gauge (an open hem's
# inside diameter >= 1 t; a teardrop's mouth >= 0.25 t), so gauge is the unit:
# `0.05 * t` gives a gap of a TENTH of a gauge — 0.15 mm at our thinnest shipped
# gauge (1.5 mm), which is 1500x the kernel tolerance and 3 orders clear of the slit
# floor, while being 0.05 % of the 300 mm panel it sits on. It is the tightest gap
# that is unambiguously material-in-contact to a reader and unambiguously NOT a
# degeneracy to the kernel.
#
# OPEN — the shape the defect was actually building. `0.5 * t` puts the inside
# DIAMETER at exactly one gauge, the standard minimum opening for an open hem, so
# the previously-shipped hems (a 1.0 mm radius on 1.5-2.0 mm gauge) are honest OPEN
# hems and keep byte-identical geometry under the right name.
#
# TEARDROP / ROLLED are deliberately NOT `hem_type` members: both need a fold that
# wraps PAST 180 deg (a mouth narrower than the bore), which the exact-cross-section
# extrude does not build. Naming them in the Literal would be the same defect this
# rule exists to remove — a label the geometry cannot honour. A request naming them
# fails schema validation, which is the honest refusal.
#
# `bend_radius_mm` is HONOURED WHEN SET, NEVER INHERITED, AND REFUSED WHEN IT
# CONTRADICTS THE TYPE (`resolve_hem_bend_radius_mm`). Silently ignoring it would be
# the `extra="ignore"` defect class (CLAUDE.md: a payload that misspells a field
# validates, evaluates and gives the old reading); silently clamping it would be the
# same lie in the other direction. Refusal is the only option under which the label,
# the number and the solid can never disagree, and the API says so with a typed
# feature error naming the fix. The guard is SYMMETRIC — a "closed" hem with an
# open-hem radius and an "open" hem with a closed-hem radius are both refused —
# because CLAUDE.md's own lesson from the staging tool is that a guard written
# against one failure tends to encode that failure's DIRECTION.
#
# Additive: a new `hem_type` Literal member lands with NO param_version bump.

#: Inner bend radius of a CLOSED hem as a multiple of gauge (air gap = 2x this, so
#: a tenth of a gauge). A closed hem's physical ideal is ZERO inside radius (parity
#: §2); zero is unbuildable and any gap below the kernel's 1e-4 mm linear tolerance
#: is a zero-width slit RESEARCH §9 refuses, so this is the RESIDUAL opening of a
#: flattened fold. Derivation + the three measurements that bound it: the block
#: comment above. Pinned here so the schema, the evaluator and the goldens' hand
#: derivation share ONE source (CLAUDE.md DRY rule).
HEM_CLOSED_RADIUS_RATIO = 0.05

#: The closed/open BOUNDARY, as a multiple of gauge. A `closed` hem refuses a
#: `bend_radius_mm` ABOVE this (gap > 0.25 t is a deliberate opening, not a
#: flattened fold — 0.25 t is the smallest opening hem practice names anywhere, the
#: teardrop mouth minimum); an `open` hem refuses one BELOW it. The boundary belongs
#: to both, so the two ranges partition the line with no gap and no overlap.
HEM_CLOSED_MAX_RADIUS_RATIO = 0.125

#: Inner bend radius of an OPEN hem as a multiple of gauge: 0.5 t puts the inside
#: DIAMETER at one gauge — the standard minimum opening for an open hem — so the
#: gap reads one full gauge, plainly an opening.
HEM_OPEN_RADIUS_RATIO = 0.5


class HemRadiusError(ValueError):
    """A hem's ``bend_radius_mm`` contradicts its declared ``hem_type``.

    Raised by :func:`resolve_hem_bend_radius_mm`. The geometry service maps it to a
    typed ``hem_type_radius_conflict`` feature error; the message names the fix
    (which ``hem_type`` the requested radius actually describes).
    """


def resolve_hem_bend_radius_mm(
    hem_type: str, thickness_mm: float, override_mm: float | None = None
) -> float:
    """The inner bend radius a hem folds at — from its TYPE and the part's GAUGE.

    This is the whole of the HEM-1 rule (block comment above), in one place so the
    schema default, the evaluator and any later authoring UI cannot drift apart.

    *override_mm* (the user's ``bend_radius_mm``) is HONOURED when it is consistent
    with *hem_type* and REFUSED when it is not — never inherited from the part's
    base flange, and never silently ignored or clamped. Omitted, the radius is
    ``HEM_CLOSED_RADIUS_RATIO * thickness`` for a closed hem and
    ``HEM_OPEN_RADIUS_RATIO * thickness`` for an open one.

    Raises:
        HemRadiusError: *override_mm* describes the other hem type (its message
            names which), or *hem_type* is not a value this rule covers.
    """
    boundary = HEM_CLOSED_MAX_RADIUS_RATIO * thickness_mm
    if hem_type == "closed":
        if override_mm is None:
            return HEM_CLOSED_RADIUS_RATIO * thickness_mm
        if override_mm > boundary:
            raise HemRadiusError(
                f"A closed hem is pressed flat against the parent face, so its "
                f"layers must very nearly touch; a {override_mm:g} mm inner radius "
                f"leaves a {2 * override_mm:g} mm air gap on {thickness_mm:g} mm "
                f"sheet, which is an OPEN hem. Use hem_type='open' to keep that "
                f"gap, or a radius of at most {boundary:g} mm (the default is "
                f"{HEM_CLOSED_RADIUS_RATIO * thickness_mm:g} mm) for a closed hem."
            )
        return override_mm
    if hem_type == "open":
        if override_mm is None:
            return HEM_OPEN_RADIUS_RATIO * thickness_mm
        if override_mm < boundary:
            raise HemRadiusError(
                f"An open hem folds back leaving a deliberate air gap; a "
                f"{override_mm:g} mm inner radius leaves only "
                f"{2 * override_mm:g} mm on {thickness_mm:g} mm sheet, which is a "
                f"CLOSED hem. Use hem_type='closed' for a flattened fold, or a "
                f"radius of at least {boundary:g} mm (the default is "
                f"{HEM_OPEN_RADIUS_RATIO * thickness_mm:g} mm) for an open hem."
            )
        return override_mm
    raise HemRadiusError(  # pragma: no cover - the Literal admits no other value
        f"Unknown hem_type {hem_type!r}; this build folds 'closed' and 'open' hems."
    )


class SheetMetalHemParamsV1(BaseModel):
    """A hem folded off a straight edge of the sheet — closed or open (parity §2).

    A hem folds the picked edge ~180 deg back over the parent face. It is a
    specialization of the edge flange: the geometry side reuses ``build_edge_flange``
    with the fold angle FIXED at 180 deg, so the fused body is one clean solid and
    the flat pattern develops it as any bend (``BA = pi * (radius + K * thickness)``,
    §1) — its bend-table row reads angle 180 deg.

    ``edge`` is an :class:`EdgeSubshapeRef` naming the base-flange edge to hem — the
    SAME stage-1 :class:`EdgeSignature` machinery a fillet/chamfer or edge-flange
    pick uses (topological-naming §10); its ``feature_id`` materialises the
    dependency on the base-flange feature. ``length_mm`` is the developed flat
    length of the folded-back return (to the bend tangent line, §9 golden #1's
    convention).

    **THE RADIUS COMES FROM THE HEM TYPE AND THE GAUGE, NOT FROM THE PART'S GENERAL
    BEND RADIUS** (HEM-1; :func:`resolve_hem_bend_radius_mm` and the block comment
    above are the rule and its derivation). The fold's cross-section makes the air
    gap between the two layers exactly ``2 * bend_radius``, so the radius IS the
    hem's defining dimension: a ``closed`` hem is pressed flat (gap 0.1 * gauge —
    the residual of a flattening press; true zero is not buildable) and an ``open``
    hem leaves a deliberate opening (gap one gauge — inside diameter = gauge, the
    standard minimum). ``bend_radius_mm`` overrides that per-hem, but a value that
    describes the OTHER hem type is REFUSED with a typed error naming the fix,
    rather than silently building a hem the label misdescribes.

    ``k_factor`` still defaults from the part's base flange when omitted (``None``):
    K is a MATERIAL property (where the neutral surface sits), so unlike the radius
    it is genuinely a part-level default the hem inherits.

    A ZERO ``bend_radius_mm`` is a degenerate fold; the ``gt=0`` bound rejects it as
    a typed validation error rather than admitting a degenerate solid (honest
    degradation — parity §3).

    Like a fillet/shell it MODIFIES the implicit single body chain (design §7.6) —
    it carries no ``merge`` (it always fuses into the sheet body the edge belongs
    to) — so its only whole-feature dependency is the named-edge ref + tree order.
    """

    edge: EdgeSubshapeRef = Field(
        description="The base-flange STRAIGHT edge to hem (a stage-1 EdgeSignature "
        "reference resolved against the current sheet body). The return folds ~180 "
        "deg back over this edge's adjacent flat face."
    )
    hem_type: Literal["closed", "open"] = Field(
        default="closed",
        description="Hem shape, which DETERMINES the fold's inner radius from the "
        "part's gauge (the air gap between the two layers is exactly 2 x that "
        "radius). 'closed' presses the return flat against the parent (gap 0.1 x "
        "gauge — the residual of a flattening press; a true zero radius is not "
        "buildable); 'open' leaves a deliberate opening (gap 1 x gauge, i.e. inside "
        "diameter = gauge, the standard minimum). Teardrop and rolled hems wrap PAST "
        "180 deg and are not representable by this fold, so they are deliberately "
        "not values here (additive Literal members if that changes, no "
        "param_version bump). Absent reads 'closed'.",
    )
    length_mm: float = Field(
        gt=0,
        description="Developed flat length of the folded-back return (mm), measured "
        "to the bend tangent line (§9 golden #1 convention).",
    )
    bend_radius_mm: float | None = Field(
        default=None,
        gt=0,
        description="INNER bend radius (mm) of the hem fold; the layers' air gap is "
        "exactly 2 x this. Omitted (None) is derived from `hem_type` and the part's "
        "gauge — 0.05 x gauge closed, 0.5 x gauge open. It is NOT inherited from the "
        "part's base-flange `bend_radius_mm` (that describes a free-standing die "
        "bend, and inheriting it put a 6 mm gap inside a 'closed' hem on 2 mm "
        "sheet — HEM-1). A value overrides the derived radius, but one that "
        "describes the OTHER hem type is REFUSED (`hem_type_radius_conflict`) "
        "rather than silently building a mislabelled hem: at most 0.125 x gauge for "
        "'closed', at least 0.125 x gauge for 'open'. A zero radius (zero-gap "
        "degenerate fold) is rejected by the `gt=0` bound.",
    )
    k_factor: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Neutral-axis fraction K in [0, 1] for the hem's bend allowance "
        "(§1). Omitted (None) inherits the part's base-flange default `k_factor` "
        "(0.44 v1 baseline) — K is a material property, so unlike the radius it IS "
        "a part-level default; a value overrides it per-hem.",
    )


# --- Sheet-metal corner relief — a RECTANGULAR notch at a bend intersection -------
#
# A CORNER RELIEF cuts a small material notch at the shared corner of two adjacent
# edge flanges so the folded sheet does not tear/interfere and — the point for the
# flat pattern — so the corner develops into a single non-overlapping blank
# (docs/design/sheet-metal.md §4.4). The 3D notch geometry + the relieved flat-
# pattern unfold already ship (`geometry.sheet_metal.apply_corner_relief` /
# `unfold_sheet_metal(reliefs=...)`); this is the FEATURE that lets a user AUTHOR
# one so both halves fire end-to-end.
#
# AUTO vs EXPLICIT — v1 is EXPLICIT (sheet-metal.md §4.4.2). A relief is an explicit
# per-corner feature: the user names the two bends whose intersection it relieves
# and a size. Auto relief (a part-level default applied at every corner that needs
# it) is the incumbent default and the natural follow-on, but it is a POLICY LAYER
# over this primitive (walk the bend graph, synthesise an explicit relief per
# colliding corner) — no new geometry, so it is a clean fast-follow. Shipping the
# explicit primitive first keeps the determinism/golden story tight (the relief set
# is an explicit input, not a graph-walk output that could drift, §4.4.2).
#
# The two bends are named by `FeatureRef` — each points at the earlier
# `sheet_metal_edge_flange` feature that CREATED that bend. The evaluator maps each
# ref to that feature's recorded bend provenance (its `CylindricalFaceSignature`,
# §5) and builds the geometry-side `CornerRelief` from the two signatures, so the
# feature never has to persist a kernel cylindrical signature on the wire — the
# provenance lives where it is computed (the edge flange), exactly like a fillet's
# picked edge materialises the base-flange dependency. This is why corner relief is
# a BODY-AFFECTING feature that MODIFIES the sheet body (it cuts the notch) yet its
# only whole-feature dependencies are the two edge-flange features + tree order.


class SheetMetalCornerReliefParamsV1(BaseModel):
    """An explicit RECTANGULAR corner relief at two adjacent flanges' corner (§4.4).

    Names the two bends whose shared corner it relieves — ``bend_a`` / ``bend_b``,
    each a :class:`FeatureRef` at the earlier ``sheet_metal_edge_flange`` feature
    that created that bend. The evaluator resolves each ref to that feature's
    recorded :class:`CylindricalFaceSignature` (§5) and drives BOTH halves of the
    relief from the two signatures: the 3D notch boolean
    (:func:`geometry.sheet_metal.apply_corner_relief`) and the relieved flat-pattern
    unfold (:func:`unfold_sheet_metal` with ``reliefs=...``) — consistent by
    construction (the fold-back guarantee, §4.4.4).

    SIZING (§4.4.3): the notch is ``size = relief_ratio * thickness`` by default
    (``relief_ratio = 1.0`` — one gauge thickness, the tear-safe SolidWorks Relief
    Ratio default), with the part's gauge taken from the base flange. An absolute
    ``size_mm`` OVERRIDES the ratio when set (the authoring/UI convenience the golden
    pins to an exact number). The manufacturing floor ``size >= bend_radius`` (the
    notch should clear the bend arc) is a recommendation, not a hard bound — an
    undersized relief is a manufacturing warning, still a fold-back-consistent body.

    v1 ships ``relief_type = "rectangular"`` only (the sole purely-rectilinear
    developable notch; obround / round / tear are §4.4.1 follow-ons). It MODIFIES the
    implicit single sheet body chain (design §7.6) — it carries no ``merge`` — so its
    only whole-feature dependencies are the two edge-flange refs + tree order.
    """

    bend_a: FeatureRef = Field(
        description="The FIRST bend of the relieved corner — a FeatureRef at the "
        "earlier sheet_metal_edge_flange feature that created it. Resolved to that "
        "feature's recorded CylindricalFaceSignature (§5)."
    )
    bend_b: FeatureRef = Field(
        description="The SECOND bend of the relieved corner — a FeatureRef at the "
        "other sheet_metal_edge_flange feature. Its shared corner with bend_a is the "
        "corner the notch relieves; the two bends must be PERPENDICULAR (a real "
        "tray corner) or the relief is a typed error (§4.4)."
    )
    relief_type: Literal["rectangular"] = Field(
        default="rectangular",
        description="Relief geometry. v1 ships 'rectangular' only (the sole purely-"
        "rectilinear developable notch — §4.4.1). Obround / round / tear each need a "
        "curved / degenerate cut and are deferred (additive Literal members, no "
        "param_version bump). Absent reads 'rectangular'.",
    )
    relief_ratio: float = Field(
        default=1.0,
        gt=0.0,
        allow_inf_nan=False,
        description="Notch size as a multiple of gauge thickness (size = "
        "relief_ratio * thickness) — the SolidWorks Relief Ratio family. Default 1.0 "
        "(one thickness, tear-safe). IGNORED when size_mm is set.",
    )
    size_mm: float | None = Field(
        default=None,
        gt=0.0,
        allow_inf_nan=False,
        description="Absolute notch size (mm). When set, OVERRIDES relief_ratio (the "
        "authoring/UI convenience that resolves the ratio to an exact value the "
        "golden pins). Omitted (None) uses relief_ratio * the part's gauge thickness.",
    )
