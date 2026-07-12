"""Feature-tree boundary DTOs — params, envelopes, refs, evaluation contract.

Implements docs/design/feature-tree.md §1.3-1.4 (versioned param envelopes +
upcast registry), §2.1-2.2 (GeomRef vocabulary + reference-validity helpers)
and §4 (the documents→geometry evaluation contract). Single source of truth
(CLAUDE.md DRY rule): the documents service validates writes and serves its
feature CRUD API with these models, the geometry service parses evaluation
requests with the SAME models, and ``just gen`` exports them to
``packages/contracts`` / ``packages/ts-client``. Pure pydantic only — kernel
types never appear here (CLAUDE.md service boundaries).

Units are fixed per field, never tagged per value (design §8.2): lengths are
millimetres, encoded in field names (``distance_mm``) exactly as
:mod:`py_kit.schemas.geometry` does.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Self, assert_never, cast, get_args

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from py_kit.schemas.geometry import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
    ExportFormat,
    ShapeProperties,
    Vec3,
)
from py_kit.schemas.sketch import EntityId, SketchDefinition, SolvedSketch

#: Upper bound for a user-facing feature name ("Sketch1", "Extrude1").
FEATURE_NAME_MAX_LENGTH = 200

#: Non-empty (post-strip), bounded feature name.
FeatureName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=FEATURE_NAME_MAX_LENGTH
    ),
]

#: A JSON object — the shape of a stored params payload before validation.
JsonObject = dict[str, Any]


# --- §2.1 GeomRef — the reference vocabulary -----------------------------------


class DatumPlaneRef(BaseModel):
    """One of the three origin datum planes."""

    kind: Literal["datum_plane"]
    plane: Literal["XY", "XZ", "YZ"]


class FeatureRef(BaseModel):
    """A whole earlier feature of the same part (e.g. a sketch)."""

    kind: Literal["feature"]
    feature_id: uuid.UUID


#: Discriminated reference union. A ``subshape`` variant remains reserved here
#: for a future DIRECT sketch-on-subshape reference; the shipped sketch-on-a-face
#: path does NOT need it — a sketch sits on an ``on_face`` datum by the existing
#: ``FeatureRef`` variant (datum-planes §7), and the :class:`SubshapeRef` lives
#: inside that datum's params, not in this union.
GeomRef = Annotated[DatumPlaneRef | FeatureRef, Field(discriminator="kind")]


# --- Stage-1 topological naming: SubshapeRef (docs/design/topological-naming.md) --
#
# A SubshapeRef names ONE planar face of an earlier body-affecting feature's
# result by a geometric SIGNATURE (§2b), NOT an enumeration index (§1.3 rejects
# indices — they silently retarget). v1 scope is PLANAR FACES only (the
# sketch-on-a-face / datum-from-face foundation); edge/vertex signatures and the
# stage-2 provenance half are future additive members (§3, §10). The signature is
# pure pydantic — no kernel type crosses the boundary (§7.4): the geometry
# service computes it from the recomputed body and resolves it back to a face,
# entirely service-internal.
#
# HONEST STABILITY LIMIT (§7.3 — stated plainly, NOT oversold): a stage-1
# signature is BEST-EFFORT, not a provably-stable structural reference. It
# resolves the same face across the common edits (parametric changes that do not
# move the face; upstream inserts that do not touch it) and FAILS HONESTLY
# (``subshape_unresolved`` / ``subshape_ambiguous``) for most others — but under
# a drastic model change it CAN retarget to a coincidentally-congruent face (same
# normal/centroid/area) without erroring. It does NOT "never silently retarget";
# only the stage-2 provenance half (coordinate-blind) makes that structural.


class PlanarFaceSignature(BaseModel):
    """§2b stage-1 geometric fingerprint of a PLANAR face — typed, kernel-free.

    Full-precision invariants (§7.2 forbids quantizing the stored identity): the
    outward unit ``normal``, the area ``centroid`` (world mm), and the
    ``area_mm2``. A planar face is uniquely fixed among a body's faces by
    (normal, centroid, area) in the common case; congruent twins of a symmetric
    part tie and resolve to an honest ``subshape_ambiguous`` (§5), never a guess.
    Matching is nearest-within-tolerance at the documented subshape tolerance
    (geometry.kernel.faces / docs/GEOMETRY-QA.md), never an ad-hoc epsilon.
    """

    subshape_type: Literal["face"] = "face"
    surface: Literal["plane"] = "plane"
    normal: Vec3 = Field(
        description="Outward unit normal of the planar face (full precision)"
    )
    centroid: Vec3 = Field(
        description="Area centroid of the face, world mm (full precision)"
    )
    area_mm2: float = Field(gt=0, description="Face area (mm^2), full precision")


class SelectorV1(BaseModel):
    """Stage-1 selector payload: the geometric signature alone (§3, §4).

    ``selector_version`` is the discriminator of the (currently single-member)
    ``Selector`` union — decoupled from feature ``param_version`` (§4). Stage 2
    adds a ``SelectorV2`` member (signature + provenance) additively, at which
    point ``Selector`` becomes ``Annotated[SelectorV1 | SelectorV2,
    Field(discriminator="selector_version")]`` with no change to persisted v1
    rows. pydantic forbids a discriminated single-member union, so ``Selector``
    is a plain alias until then (same idiom as :data:`FeatureData`).
    """

    selector_version: Literal[1] = 1
    signature: PlanarFaceSignature


#: Version-discriminated selector union (§4). One member (stage 1) today, so a
#: plain alias; stage 2 promotes it to a ``selector_version``-discriminated union.
Selector = SelectorV1


class SubshapeRef(BaseModel):
    """Stage-1 reference to ONE planar face of a body-affecting feature's result.

    (docs/design/topological-naming.md §4.) ``feature_id`` is the stage-1 anchor
    — "the prior body-affecting feature whose body I signature-match against"
    (§4), NOT necessarily the originating feature (stage 2 shifts it to the true
    originating feature). It materializes into ``feature_dependencies`` like a
    :class:`FeatureRef` (via the widened :func:`iter_feature_refs` /
    :func:`feature_references`), so deleting that feature is a write-time
    409-with-dependents. ``subshape_type`` is ``"face"`` only in v1 (edge/vertex
    reserved — §10).
    """

    kind: Literal["subshape"]
    feature_id: uuid.UUID
    subshape_type: Literal["face"]
    selector: Selector


# --- §2.4 EdgeSelector — deterministic edge selection (NOT topological naming) ---
#
# Body-modifying features (fillet, chamfer) must name edges of the CURRENT body
# chain. v1 topological naming (design §2.4 ``SubshapeRef``) is a Phase 2 item,
# so v1 selects edges by a DETERMINISTIC GEOMETRIC PREDICATE over the body,
# never by an opaque per-feature subshape id. Two honest, rebuild-stable
# consequences a UI can drive today:
#
#   * the predicate is evaluated against whatever body exists at the feature's
#     point in the tree, so it survives rebuilds without a name map; and
#   * it is a real limitation, not naming: "the edge I clicked" is Phase 2.
#     When ``SubshapeRef`` lands it becomes an additive ``kind: "subshape"``
#     variant of this union (design §2.4 — discriminated on ``kind``, so no
#     persisted selector changes shape and no ``param_version`` bump is forced).


class AllEdgesSelector(BaseModel):
    """Every edge of the target body (the whole-body round-over)."""

    kind: Literal["all_edges"]


class AxisParallelEdgesSelector(BaseModel):
    """Every straight edge parallel to a world axis (e.g. Z = the vertical
    edges of an upright prism). Curved edges never match — an arc has no
    single direction. Deterministic and rebuild-stable: a geometric predicate,
    not a stored edge id."""

    kind: Literal["axis_parallel"]
    axis: Literal["X", "Y", "Z"]


#: Discriminated edge-selection union for body-modifying features. A
#: ``subshape`` variant (Phase 2 topological naming, design §2.4) is additive.
EdgeSelector = Annotated[
    AllEdgesSelector | AxisParallelEdgesSelector, Field(discriminator="kind")
]


# --- §1.4 Per-type params (current versions) ------------------------------------


class DatumOffsetParams(BaseModel):
    """An origin datum slid ``offset_mm`` along its normal (``kind: "offset"``).

    The v1 face-free slice (docs/design/datum-planes.md §3): ``base`` is one of
    the three stable origin datums, ``offset_mm`` slides the plane along that
    datum's normal, and ``flip`` optionally reverses the normal. No picked
    geometry, no reference to another feature's output — so this is independent
    of topological naming (#1), exactly like revolve's world-axis or a pattern's
    world-vector. A datum is NOT body-affecting: it produces a plane, contributes
    no body, and is TOTAL — any finite ``offset_mm`` yields a valid plane, so an
    offset datum never carries an ``error`` status (§3b). A non-finite offset is
    a parse-time 422 (``allow_inf_nan=False``), never a rebuild error.

    ``kind`` defaults to ``"offset"`` so LEGACY params (persisted before the
    ``on_face`` variant, which carry no discriminator) validate here unchanged —
    :class:`DatumFeature`'s before-validator injects it (additive, NO
    ``param_version`` bump — datum-planes §4/§7).
    """

    kind: Literal["offset"] = "offset"
    base: Literal["XY", "XZ", "YZ"] = Field(
        description="Origin datum this plane is parallel to (its orientation)."
    )
    offset_mm: float = Field(
        allow_inf_nan=False,
        description="Signed distance along `base`'s normal (mm). 0 coincides "
        "with the origin datum; +/- selects side. Any finite value is valid.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir so "
        "sketch +u is unchanged and +v flips). Additive-optional; absent reads "
        "as False. Position is fully covered by signed `offset_mm`; `flip` only "
        "chooses which way 'normal' points for authoring/extrude-side.",
    )


class DatumOnFaceParams(BaseModel):
    """A datum plane adopted from a picked PLANAR face (``kind: "on_face"``).

    The v2 on-a-face slice (docs/design/datum-planes.md §7): the datum's plane
    resolves to the plane of a planar face of an EARLIER body-affecting feature's
    result, named by a stage-1 :class:`SubshapeRef` signature
    (docs/design/topological-naming.md), with an optional ``offset_mm`` along the
    face normal. This is the sketch-on-a-face foundation — a sketch sits on this
    datum by the SAME ``FeatureRef`` it uses for an offset datum, so on-face
    reuses the datum node rather than a new mechanism (datum-planes §2b/§7).

    The derived sketch basis is DETERMINISTIC (RESEARCH §9): origin at the face
    area centroid (plus ``offset_mm`` along the normal), ``z_dir`` the outward
    face normal, and an ``x_dir`` pinned from the normal
    (``geometry.kernel.faces._deterministic_x_dir``) so the 2D→3D mapping is
    stable across rebuilds, independent of OCCT's face parametrisation.

    HONEST v1 limits: the face reference is a stage-1 signature — best-effort,
    NOT structurally non-retargeting (see :class:`SubshapeRef`). A rebuild that
    removes the face is an honest ``subshape_unresolved`` on this datum; a
    congruent twin is ``subshape_ambiguous``; a drastic change can (rarely)
    retarget to a congruent face. Only PLANAR faces carry a signature, so a
    non-planar face cannot be referenced (the pick UI omits them from the
    sketchable set — a non-planar pick is rejected before a datum is authored).
    """

    kind: Literal["on_face"]
    face: SubshapeRef = Field(
        description="Planar face of an earlier body-affecting feature whose "
        "plane this datum adopts (stage-1 signature reference)"
    )
    offset_mm: float = Field(
        default=0.0,
        allow_inf_nan=False,
        description="Signed offset along the face normal (mm); 0 sits on the "
        "face. Optional (datum-planes §7).",
    )


#: Datum params: an offset-from-origin plane OR an on-a-face plane, discriminated
#: on ``kind``. LEGACY persisted params carry no ``kind`` (they predate on_face)
#: — :class:`DatumFeature`'s before-validator injects ``kind: "offset"`` so old
#: rows validate unchanged (additive, NO ``param_version`` bump — datum-planes
#: §4/§7).
DatumParams = Annotated[
    DatumOffsetParams | DatumOnFaceParams, Field(discriminator="kind")
]


class SketchParamsV1(SketchDefinition):
    """Sketch on a plane — an origin datum, or a ``datum`` feature (design §2.1).

    ``plane`` is a :data:`GeomRef`: a :class:`DatumPlaneRef` names one of the
    three origin datums (XY/XZ/YZ), or a :class:`FeatureRef` points at an earlier
    ``datum`` feature (an offset/parallel plane — docs/design/datum-planes.md).
    The ``FeatureRef`` variant is now accepted when it resolves to a ``datum``
    feature (widened in :func:`feature_references` from no acceptable target to
    ``{datum}``); the stored shape is unchanged, so this is purely additive — no
    ``param_version`` bump.

    Extends :class:`py_kit.schemas.sketch.SketchDefinition` (typed
    ``entities``/``constraints`` — the §1.4 placeholder finalized by the
    "Sketch model + solver API" item), so a persisted sketch's params ARE
    valid solver input: same validation (unique sketch-local entity ids per
    design §2.4) on the documents write path and the geometry request path.
    """

    plane: GeomRef


class ExtrudeParamsV1(BaseModel):
    """Linear extrusion of an earlier sketch feature's profile."""

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature (design §2.2)"
    )
    distance_mm: float = Field(gt=0, description="Extrusion depth (mm)")
    operation: Literal["add", "cut"]
    direction: Literal["normal", "reverse"] = "normal"


class RevolveAxis(BaseModel):
    """The axis of revolution: a straight LINE entity of the profile's sketch.

    v1 references a line entity by its sketch-local id (design §2.4 entity ids)
    within the SAME sketch the profile comes from. A **construction** line is
    the natural choice — a centerline is reference-only (excluded from the
    closed-wire profile) and is exactly what an axis of revolution is — but any
    line entity resolves; the axis is defined by the line's two solved
    endpoints, mapped to world space through the profile's datum plane.

    The ``kind`` discriminator seeds a future additive ``datum_axis`` variant
    (the §2.1 ``GeomRef`` pattern) without forcing a ``param_version`` bump: a
    persisted axis is always ``{"kind": "sketch_line", "entity": ...}`` today,
    and a later datum-axis reference joins as ``kind: "datum_axis"``.
    """

    kind: Literal["sketch_line"] = "sketch_line"
    entity: EntityId = Field(
        description="Sketch-local id of a LINE entity in the profile's sketch "
        "(a construction centerline is ideal) used as the axis of revolution"
    )


class RevolveParamsV1(BaseModel):
    """Revolution of an earlier sketch feature's profile about a sketch-line axis.

    The revolve sibling of :class:`ExtrudeParamsV1` (design §4.3, second core
    body-affecting feature): it consumes the SAME ``profile`` FeatureRef to an
    earlier sketch and the SAME ``add``/``cut`` boolean against the body chain,
    swapping the linear prism for a swept revolution. The ``axis`` is a
    :class:`RevolveAxis` (a line entity of that same sketch — no picked
    sub-geometry reference, so this is independent of topological naming), and
    ``angle_deg`` is the sweep (full 360° by default). The profile must clear
    the axis: a profile the axis crosses would revolve into self-intersecting
    material and is a per-feature ``axis_intersects_profile`` error (design
    §4.3), never a silent bad body.
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature (design §2.2)"
    )
    axis: RevolveAxis = Field(
        description="Axis of revolution — a line entity of the profile's sketch"
    )
    angle_deg: float = Field(
        default=360.0,
        gt=0.0,
        le=360.0,
        description="Sweep angle about the axis (degrees); 360 = full solid of "
        "revolution",
    )
    operation: Literal["add", "cut"]
    direction: Literal["normal", "reverse"] = Field(
        default="normal",
        description="Sweep sense about the axis for a partial revolution "
        "(irrelevant at a full 360°): 'reverse' sweeps the opposite way",
    )


class SweepParamsV1(BaseModel):
    """Sweep an earlier sketch's closed profile along an earlier sketch's open path.

    The first NON-PRISMATIC body-affecting feature (design §4.3): where extrude
    sweeps a profile along the plane normal and revolve about an axis, sweep
    follows an arbitrary open PATH wire — the shaft / pipe / rib primitive named
    in the Part-modeling scorecard notes. It consumes the SAME ``profile``
    FeatureRef to an earlier sketch (a single closed wire, built by the shared
    ``build_profile_face``) and the SAME ``add``/``cut`` boolean against the body
    chain as extrude/revolve; the new ingredient is ``path``, a SECOND
    FeatureRef to an earlier sketch whose entities form a single OPEN wire.

    Path representation (v1 DESIGN DECISION — docs/design/feature-tree.md
    §2.1/§2.2, docs/GEOMETRY-QA.md 2026-07-12): the path is a whole earlier
    SKETCH feature referenced by id (option A — the most general model, matching
    how production CAD names a sweep path, and reusing the tree's stable feature
    ids exactly as the ``profile`` slot does). This is NOT topological naming
    (#1): it references a whole feature's evaluated wire, never a picked
    sub-edge — the same mechanism extrude/revolve already use for their profile.

    v1 limits (stated plainly — documented scope, not bugs):

    * the path must resolve to a single **open** wire; a closed path is a
      ``sweep_path_closed`` rebuild error, disjoint path loops are
      ``sweep_path_not_connected``, and a path with no curve entities is
      ``sweep_path_empty`` (construction geometry is excluded from the path
      exactly as it is from the profile);
    * the sweep is **anchored at the profile** — build123d applies the path as a
      relative trajectory from the profile's own location, so the path's
      absolute position is not used. Author the path starting at the profile
      origin, with its first segment perpendicular to the profile plane, for a
      predictable result (as the golden's vertical path over an XY circle is);
    * NO twist, NO scale-along-path, NO multi-section, NO guide rails, NO
      per-segment transition control — one profile rigidly swept along one path
      (all later, additive params — no ``param_version`` bump);
    * a self-intersecting path, or a corner tighter than the profile can turn
      without sweeping through itself, is a kernel ``sweep_failed`` rebuild
      error, never a silently bad body.
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature whose entities "
        "form the single CLOSED profile wire (design §2.2)"
    )
    path: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature whose entities "
        "form a single OPEN wire — the sweep trajectory (design §2.2)"
    )
    operation: Literal["add", "cut"]


class LoftParamsV1(BaseModel):
    """Blend a solid THROUGH two or more ordered section sketches (design §4.3).

    The loft sibling of :class:`SweepParamsV1` and the second non-prismatic
    body-affecting feature: where sweep drives ONE profile along a path, a loft
    skins a solid through an ORDERED list of cross-section sketches (the
    transitional-solid / cone / adapter primitive named in the Part-modeling
    scorecard notes). It shares the SAME ``add``/``cut`` boolean against the body
    chain as extrude/revolve/sweep; the new ingredient is ``profiles``, a list
    of ``FeatureRef``s (min 2) to earlier sketch features, blended in list order.

    Section representation (v1 DESIGN DECISION — docs/GEOMETRY-QA.md
    2026-07-12): each ``profiles`` entry is a whole earlier SKETCH feature
    referenced by id — the same stable-feature-id mechanism the extrude/revolve
    ``profile`` and sweep ``profile``/``path`` slots use. This is NOT topological
    naming (#1): it references a whole feature's evaluated wire, never a picked
    sub-edge. A section's non-construction entities form either a single CLOSED
    profile wire (built by the shared ``build_profile_face``) OR a single POINT,
    interpreted as an APEX vertex (the standard loft-to-a-point tip); an apex may
    appear only as the FIRST or LAST section.

    Why apex support in v1 (honest limit, not gold-plating): datum planes are
    origin-only and mutually perpendicular (never parallel), so two parallel
    offset circular sections — a cylinder/frustum — are not authorable until
    offset datum planes land. A closed section lofted to an apex point IS
    authorable and gives an analytic solid (a pyramid/cone), which is the loft
    golden's mass-property anchor.

    v1 limits (stated plainly — documented scope, not bugs):

    * a RULED (straight) loft through the sections in list order — NO guide
      rails, NO tangency/normal end conditions, NO periodic (closed) loft, NO
      per-section twist/alignment control (all later, additive params — no
      ``param_version`` bump);
    * sections are coplanar-or-parallel profiles as authored (each sketch
      carries its own plane); an open/non-closed section is a
      ``profile_not_closed`` rebuild error, a multi-loop section is
      ``profile_unsupported``, and a section ref that is not an earlier ok
      sketch is ``reference_unresolved`` (exactly like extrude/sweep);
    * incompatible sections (crossed rails), an apex wedged between two wire
      sections, or a skin OCCT cannot reduce to exactly one solid is a kernel
      ``loft_failed`` rebuild error, never a silently bad body.
    """

    profiles: list[FeatureRef] = Field(
        min_length=2,
        description="Ordered earlier sketch features (>= 2) to blend through; "
        "each forms a single closed profile wire or a single apex point "
        "(design §2.2). Fewer than 2 is a request-validation 422.",
    )
    operation: Literal["add", "cut"]


class FilletParamsV1(BaseModel):
    """Round selected edges of the current body chain with a constant radius.

    ``edges`` is a geometric :class:`EdgeSelector` predicate over the body that
    exists at this feature's point in the tree — NOT a topological-naming
    reference (design §2.4; that is Phase 2). No feature reference: like an
    extrude ``cut``, a fillet operates on the implicit single body chain
    (design §7.6), so its dependency on the prior body-affecting feature is the
    tree order, not a ``FeatureRef``.
    """

    edges: EdgeSelector = Field(
        description="Which edges of the current body to round (geometric "
        "predicate, not topological naming — design §2.4)"
    )
    radius_mm: float = Field(gt=0, description="Fillet radius (mm)")


class ChamferParamsV1(BaseModel):
    """Bevel selected edges of the current body chain with a symmetric distance.

    The chamfer sibling of :class:`FilletParamsV1`: it reuses the SAME
    :class:`EdgeSelector` predicate (the shared edge-reference plumbing —
    design §2.4, NOT topological naming; Phase 2 is ``SubshapeRef``), so a UI
    or caller names chamfer edges exactly as it names fillet edges. Like a
    fillet it operates on the implicit single body chain (design §7.6), so it
    carries no ``FeatureRef``; its dependency on the prior body-affecting
    feature is the tree order.

    ``distance_mm`` is the symmetric setback measured along each of the edge's
    two adjacent faces (a 45° bevel): the flat chamfer face is the hypotenuse.
    """

    edges: EdgeSelector = Field(
        description="Which edges of the current body to bevel (geometric "
        "predicate, not topological naming — design §2.4; same selector union "
        "as fillet)"
    )
    distance_mm: float = Field(
        gt=0,
        description="Symmetric chamfer setback along each adjacent face (mm) — "
        "a 45° bevel",
    )


# --- Pattern params (linear / circular) -----------------------------------------
#
# DESIGN DECISION (v1, BACKLOG #7 — recorded in docs/GEOMETRY-QA.md 2026-07-12):
# a pattern replicates the CURRENT evaluated body — everything modelled so far —
# and BOOLEAN-UNIONS the copies into the single body chain (design §7.6). This is
# option (B): "pattern the current body", NOT (A) "replicate an isolated source
# feature's solid delta". Instance 0 is the existing body (never double-counted);
# instances 1..count-1 are rigid copies transformed to each placement and fused
# in. A pattern operates on WHOLE features by tree position, never on picked
# sub-geometry, so — like revolve's axis — it is independent of topological
# naming (#1).
#
# Why (B): for the common case where the body IS the thing to array (a bare
# boss/prism), option (B) is a pure rigid transform + fuse — EXACT, with zero
# hidden inaccuracy (no solid-delta subtraction, which (A) needs and which can
# leave slivers). Its honest limitations (stated plainly, GEOMETRY-QA):
#   * it arrays the WHOLE body-so-far — any base is dragged to each placement.
#     Feature-scoped patterning (replicating only one chosen feature's tool
#     solid onto a fixed base) needs per-feature tool tracking and is future
#     work (#7 follow-up), NOT this version.
#   * additive UNION only — v1 has no cut/hole arrays.
#   * the copies must merge into ONE connected solid (§7.6 single body chain);
#     a pattern whose instances are disjoint is a per-feature `pattern_disjoint`
#     rebuild error until multi-body parts land.
#
# All pattern VALUE validation (count, spacing, direction/axis magnitude, angle)
# lives at rebuild in geometry.kernel.pattern, surfacing as per-feature
# `pattern_*` errors under the strict-prefix rule — NOT as pydantic Field
# constraints. This is a deliberate departure from the extrude/revolve
# gt=0-at-parse idiom: pattern validity is partly CROSS-FIELD (a zero sweep is
# only wrong when count > 1; direction is a free vector whose magnitude no
# single-field bound can check), so v1 centralizes every check in one place for
# one uniform, legible per-feature error surface rather than splitting
# single-field checks to 422s and cross-field checks to rebuild errors. (A
# non-integer count is still a parse-time type error — `count` is typed ``int``.)


class LinearPatternParamsV1(BaseModel):
    """A linear (row/grid-line) pattern along a world-space direction.

    ``count`` INCLUDES the seed (instance 0 = the existing body), so a row of
    N total bodies is ``count = N``; ``count = 1`` is a no-op (seed only).
    Copies are placed at ``spacing_mm * k`` along the unit ``direction`` for
    ``k = 1..count-1``. See the module design note above for what "the body"
    means and the connected-solid requirement.
    """

    kind: Literal["linear"] = "linear"
    direction: Vec3 = Field(
        description="World-space direction of the row; only its DIRECTION is "
        "used (magnitude ignored; a zero-length vector is a `pattern_bad_"
        "direction` rebuild error)"
    )
    spacing_mm: float = Field(
        description="Centre-to-centre step between consecutive instances along "
        "`direction` (mm); must be > 0 (a `pattern_bad_spacing` rebuild error "
        "otherwise). Validated at rebuild, not at parse (see module note)."
    )
    count: int = Field(
        description="TOTAL instances INCLUDING the seed (instance 0); an "
        "integer >= 1. `count < 1` is a `pattern_bad_count` rebuild error; "
        "`count = 1` is a no-op (the body is unchanged)."
    )


class CircularPatternParamsV1(BaseModel):
    """A circular (ring) pattern about a world-space axis.

    ``count`` INCLUDES the seed. Instances are placed every ``angle_deg /
    count`` degrees about the axis for ``k = 1..count-1``, so the closing
    position at ``angle_deg`` is EXCLUSIVE (omitted): ``angle_deg = 360`` with
    ``count = 4`` yields a clean 4-up ring at 0/90/180/270° with no overlapping
    twin at 360° ≡ 0°. To place N instances INCLUSIVELY across a partial arc of
    ``a`` degrees (both ends occupied), set ``angle_deg = a * count / (count -
    1)``. See the module design note above for the connected-solid requirement.
    """

    kind: Literal["circular"] = "circular"
    axis_point: Vec3 = Field(
        description="A point on the world-space axis of rotation (mm)"
    )
    axis_direction: Vec3 = Field(
        description="Direction of the axis of rotation; only its DIRECTION is "
        "used (magnitude ignored; a zero-length vector is a `pattern_bad_axis` "
        "rebuild error)"
    )
    angle_deg: float = Field(
        description="TOTAL sweep about the axis (degrees). Instances are spaced "
        "`angle_deg / count`, so `angle_deg = 360` is a full ring; the closing "
        "instance at `angle_deg` is EXCLUSIVE. Must be in (0, 360] when count "
        "> 1 (a `pattern_bad_angle` rebuild error otherwise)."
    )
    count: int = Field(
        description="TOTAL instances INCLUDING the seed; an integer >= 1. "
        "`count < 1` is a `pattern_bad_count` rebuild error; `count = 1` is a "
        "no-op."
    )


#: Discriminated pattern-geometry union (linear vs circular), the RevolveAxis
#: `kind`-discriminator idiom: a future `path`/`mirror` variant joins additively
#: without a `param_version` bump.
PatternGeometry = Annotated[
    LinearPatternParamsV1 | CircularPatternParamsV1, Field(discriminator="kind")
]


class PatternParamsV1(BaseModel):
    """Repeat the current single body into a linear row or circular ring.

    Wraps the discriminated :data:`PatternGeometry` under ``pattern`` (the
    nested-discriminator idiom of :class:`RevolveParamsV1`'s ``axis``). Like a
    fillet/chamfer, a pattern carries NO ``FeatureRef``: it operates on the
    implicit single body chain that exists at its point in the tree (design
    §7.6), so its dependency on the prior body-affecting feature is tree order,
    not a reference. See the module-level DESIGN DECISION note for the v1
    "pattern the whole body + union" semantics and its stated limitations.
    """

    pattern: PatternGeometry = Field(
        description="Linear or circular pattern geometry (discriminated on `kind`)"
    )


# --- §1.3 Versioned envelopes ----------------------------------------------------


class DatumFeature(BaseModel):
    """``{"type": "datum", "version": 1, "params": {...}}`` envelope.

    A non-body-affecting feature that produces a plane a later sketch sits on
    (docs/design/datum-planes.md §2b). ``params`` is the discriminated
    :data:`DatumParams` union — an ``offset`` plane (§3) or an ``on_face`` plane
    (§7). Adding the ``on_face`` variant is ADDITIVE with NO ``param_version``
    bump: legacy offset params (persisted before ``on_face`` existed) carry no
    ``kind`` discriminator, so :meth:`_legacy_offset_kind` injects ``"offset"``
    before validation and every existing datum row/golden validates unchanged
    (datum-planes §4/§7).
    """

    type: Literal["datum"]
    version: Literal[1]
    params: DatumParams

    @model_validator(mode="before")
    @classmethod
    def _legacy_offset_kind(cls, data: Any) -> Any:
        """Read a kind-less datum params blob as an ``offset`` plane.

        The ``on_face`` variant introduced the ``kind`` discriminator; params
        persisted before it carry only ``{base, offset_mm, flip}``. Injecting
        ``kind: "offset"`` keeps them valid without a stored-shape change or a
        ``param_version`` bump — the additive migration datum-planes §4/§7
        promises. On_face params always carry ``kind: "on_face"`` explicitly, so
        they are untouched.
        """
        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, Any]", data)
        params = fields.get("params")
        if not isinstance(params, dict):
            return fields
        params_dict = cast("dict[str, Any]", params)
        if "kind" in params_dict:
            return fields
        new_params = dict(params_dict)
        new_params["kind"] = "offset"
        new_fields = dict(fields)
        new_fields["params"] = new_params
        return new_fields


class SketchFeature(BaseModel):
    """``{"type": "sketch", "version": 1, "params": {...}}`` envelope."""

    type: Literal["sketch"]
    version: Literal[1]
    params: SketchParamsV1


class ExtrudeFeature(BaseModel):
    """``{"type": "extrude", "version": 1, "params": {...}}`` envelope."""

    type: Literal["extrude"]
    version: Literal[1]
    params: ExtrudeParamsV1


class RevolveFeature(BaseModel):
    """``{"type": "revolve", "version": 1, "params": {...}}`` envelope."""

    type: Literal["revolve"]
    version: Literal[1]
    params: RevolveParamsV1


class SweepFeature(BaseModel):
    """``{"type": "sweep", "version": 1, "params": {...}}`` envelope."""

    type: Literal["sweep"]
    version: Literal[1]
    params: SweepParamsV1


class LoftFeature(BaseModel):
    """``{"type": "loft", "version": 1, "params": {...}}`` envelope."""

    type: Literal["loft"]
    version: Literal[1]
    params: LoftParamsV1


class FilletFeature(BaseModel):
    """``{"type": "fillet", "version": 1, "params": {...}}`` envelope."""

    type: Literal["fillet"]
    version: Literal[1]
    params: FilletParamsV1


class ChamferFeature(BaseModel):
    """``{"type": "chamfer", "version": 1, "params": {...}}`` envelope."""

    type: Literal["chamfer"]
    version: Literal[1]
    params: ChamferParamsV1


class PatternFeature(BaseModel):
    """``{"type": "pattern", "version": 1, "params": {...}}`` envelope."""

    type: Literal["pattern"]
    version: Literal[1]
    params: PatternParamsV1


#: Discriminated union of the CURRENT version of every feature type — this is
#: what the OpenAPI contract exports (design §1.4). Older stored versions are
#: upcast on read via :data:`FEATURE_REGISTRY`.
Feature = Annotated[
    DatumFeature
    | SketchFeature
    | ExtrudeFeature
    | RevolveFeature
    | SweepFeature
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | PatternFeature,
    Field(discriminator="type"),
]

#: Plain (non-annotated) union alias for type annotations of validated values.
FeatureEnvelope = (
    DatumFeature
    | SketchFeature
    | ExtrudeFeature
    | RevolveFeature
    | SweepFeature
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | PatternFeature
)


# --- §1.4 Registry + upcasts -----------------------------------------------------


class FeatureSchemaError(Exception):
    """Registry misconfiguration — raised at import time, never at runtime."""


class UnknownFeatureVersionError(LookupError):
    """A stored ``(type, param_version)`` has no upcast path to the current
    version — totality (design §1.4) is violated; the row cannot be loaded."""


#: A pure-Python upcast: params valid under version N → params valid under N+1.
#: Every upcast is TOTAL — it must succeed on any params blob that validated
#: under the old version (design §1.4).
UpcastFn = Callable[[JsonObject], JsonObject]


def _literal_field(model: type[BaseModel], field: str) -> Any:
    """The single literal value of an envelope's ``type``/``version`` field."""
    annotation = model.model_fields[field].annotation
    values = get_args(annotation)
    if len(values) != 1:
        raise FeatureSchemaError(
            f"{model.__name__}.{field} must be a single-value Literal, "
            f"got {annotation!r}"
        )
    return values[0]


class FeatureTypeRegistry[ModelT: BaseModel]:
    """``(type, version) → model class`` plus the upcast chains (design §1.4).

    Envelope models registered here always describe the CURRENT version of
    their type; older stored versions reach it through registered upcasts.
    :meth:`validate_chains` enforces complete chains (no gaps) at import time
    so lazily-read old rows can always reach the current shape.
    """

    def __init__(self) -> None:
        self._current: dict[str, int] = {}
        self._models: dict[str, type[ModelT]] = {}
        self._upcasts: dict[tuple[str, int], UpcastFn] = {}

    def register(self, model: type[ModelT]) -> None:
        """Register *model* as the current envelope of its ``type`` literal."""
        feature_type = str(_literal_field(model, "type"))
        version = int(_literal_field(model, "version"))
        if feature_type in self._current:
            raise FeatureSchemaError(f"feature type {feature_type!r} registered twice")
        self._current[feature_type] = version
        self._models[feature_type] = model

    def register_upcast(
        self, feature_type: str, from_version: int, upcast: UpcastFn
    ) -> None:
        """Register the total upcast ``from_version → from_version + 1``."""
        key = (feature_type, from_version)
        if key in self._upcasts:
            raise FeatureSchemaError(
                f"upcast {feature_type!r} v{from_version} registered twice"
            )
        self._upcasts[key] = upcast

    def validate_chains(self) -> None:
        """Enforce complete upcast chains (call at import time — design §1.4).

        For every type with upcasts: sources must be contiguous and end at
        ``current - 1`` (v_n → v_n+1 → ... → current, no gaps), and no upcast
        may start at or beyond the current version.
        """
        for feature_type, from_version in self._upcasts:
            if feature_type not in self._current:
                raise FeatureSchemaError(
                    f"upcast for unregistered feature type {feature_type!r}"
                )
            if from_version >= self._current[feature_type]:
                raise FeatureSchemaError(
                    f"upcast {feature_type!r} v{from_version} starts at/beyond "
                    f"the current version {self._current[feature_type]}"
                )
        for feature_type, current in self._current.items():
            sources = sorted(
                version
                for (registered_type, version) in self._upcasts
                if registered_type == feature_type
            )
            if sources and sources != list(range(sources[0], current)):
                raise FeatureSchemaError(
                    f"upcast chain for {feature_type!r} has gaps: "
                    f"{sources} does not reach v{current} contiguously"
                )

    def current_version(self, feature_type: str) -> int:
        """The current params version of *feature_type* (raises if unknown)."""
        try:
            return self._current[feature_type]
        except KeyError:
            raise UnknownFeatureVersionError(
                f"unknown feature type {feature_type!r}"
            ) from None

    def upcast_params(
        self, feature_type: str, version: int, params: JsonObject
    ) -> JsonObject:
        """Walk the upcast chain from *version* to the current version."""
        current = self.current_version(feature_type)
        if version > current:
            raise UnknownFeatureVersionError(
                f"{feature_type!r} params at v{version} are NEWER than the "
                f"current v{current} — refusing to guess"
            )
        while version < current:
            upcast = self._upcasts.get((feature_type, version))
            if upcast is None:
                raise UnknownFeatureVersionError(
                    f"no upcast registered from {feature_type!r} v{version} "
                    f"toward current v{current}"
                )
            params = upcast(params)
            version += 1
        return params

    def load(self, feature_type: str, version: int, params: JsonObject) -> ModelT:
        """Stored columns → current-version validated envelope (read path).

        Design §1.4 mapping-to-JSONB rule: columns → envelope dict → upcast if
        needed → validate. The rest of the system only ever sees
        current-version params.
        """
        current = self.current_version(feature_type)
        upcast = self.upcast_params(feature_type, version, params)
        return self._models[feature_type].model_validate(
            {"type": feature_type, "version": current, "params": upcast}
        )


#: The module-level registry — sketch + extrude, both at v1.
FEATURE_REGISTRY: FeatureTypeRegistry[FeatureEnvelope] = FeatureTypeRegistry()
FEATURE_REGISTRY.register(DatumFeature)
FEATURE_REGISTRY.register(SketchFeature)
FEATURE_REGISTRY.register(ExtrudeFeature)
FEATURE_REGISTRY.register(RevolveFeature)
FEATURE_REGISTRY.register(SweepFeature)
FEATURE_REGISTRY.register(LoftFeature)
FEATURE_REGISTRY.register(FilletFeature)
FEATURE_REGISTRY.register(ChamferFeature)
FEATURE_REGISTRY.register(PatternFeature)
FEATURE_REGISTRY.validate_chains()


# --- §2.2/§2.3 Reference helpers --------------------------------------------------


#: Feature types that produce/mutate the body chain — the acceptable targets of
#: a :class:`SubshapeRef` face reference (topo-naming §4: a face is named on a
#: body-affecting feature's result). ``datum``/``sketch`` are NOT body-affecting.
BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {"extrude", "revolve", "sweep", "loft", "fillet", "chamfer", "pattern"}
)


def iter_feature_refs(value: Any) -> Iterator[FeatureRef | SubshapeRef]:
    """Every :class:`FeatureRef` OR :class:`SubshapeRef` reachable in a model tree.

    Generic pydantic walk (models, lists, tuples, dict values) so extraction can
    never drift from the schema (design §2.3) — a new ref-bearing field is found
    without touching this function. Both ref kinds carry a ``feature_id`` that
    joins the dependency graph; topo-naming §4 widened this walk to also yield
    :class:`SubshapeRef` (a named face reference), which is yielded WHOLE and not
    descended into (its only graph-relevant field is ``feature_id`` — its
    signature payload carries no refs).
    """
    if isinstance(value, FeatureRef | SubshapeRef):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from iter_feature_refs(getattr(value, name))
    elif isinstance(value, list | tuple):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            yield from iter_feature_refs(item)
    elif isinstance(value, dict):
        for item in value.values():  # pyright: ignore[reportUnknownVariableType]
            yield from iter_feature_refs(item)


@dataclass(frozen=True)
class FeatureReference:
    """One reference slot of a feature + the target feature types it accepts.

    ``allowed_types`` empty means NO feature type is acceptable in that slot
    (e.g. a sketch plane in v1 accepts datum planes only — design §2.1). ``ref``
    is a :class:`FeatureRef` (a whole-feature reference) OR a :class:`SubshapeRef`
    (a named face of a body-affecting feature — topo-naming §4); both expose a
    ``feature_id`` that documents materializes into ``feature_dependencies``.
    """

    slot: str
    ref: FeatureRef | SubshapeRef
    allowed_types: frozenset[str]


def feature_references(feature: FeatureEnvelope) -> tuple[FeatureReference, ...]:
    """All feature references of *feature* with their slot type rules.

    This is the design §2.2 rule-3 helper: the slot→acceptable-types mapping
    lives next to the param models so documents and any future caller enforce
    identical rules. Self-checked against the generic :func:`iter_feature_refs`
    walk — if a schema gains a ref-bearing field this mapping misses, the
    mismatch raises instead of silently dropping an edge.
    """
    references: list[FeatureReference] = []
    match feature:
        case DatumFeature():
            # An OFFSET datum carries NO reference (design §5): `base` is an
            # origin-datum enum, `offset_mm`/`flip` are scalars. An ON_FACE datum
            # names a PLANAR FACE of an earlier body-affecting feature's result
            # (topo-naming §4): its SubshapeRef.feature_id materializes into
            # feature_dependencies exactly like a FeatureRef, so deleting that
            # body feature is a write-time 409-with-dependents and a reorder
            # re-checks strict-backward for the named ref too.
            if isinstance(feature.params, DatumOnFaceParams):
                references.append(
                    FeatureReference(
                        "face", feature.params.face, BODY_AFFECTING_FEATURE_TYPES
                    )
                )
        case SketchFeature():
            if isinstance(feature.params.plane, FeatureRef):
                # A sketch-plane FeatureRef is accepted iff it points at a
                # `datum` feature (design §4): the only feature type that
                # produces a sketchable plane. This widened `allowed_types`
                # (was empty) is the entire write-time acceptance change —
                # documents' §2.2 rule-3 check then permits it.
                references.append(
                    FeatureReference(
                        "plane", feature.params.plane, frozenset({"datum"})
                    )
                )
        case ExtrudeFeature() | RevolveFeature():
            # Both take a single sketch profile ref; revolve's axis is a
            # sketch-LOCAL entity id (a line within that same sketch), NOT a
            # FeatureRef, so it never appears in the FeatureRef walk below.
            references.append(
                FeatureReference(
                    "profile", feature.params.profile, frozenset({"sketch"})
                )
            )
        case SweepFeature():
            # Two sketch refs: the closed PROFILE and the open PATH wire (design
            # §4.3). Both resolve to earlier sketch features (the path is a whole
            # feature's wire, NOT a picked sub-edge — independent of #1).
            references.append(
                FeatureReference(
                    "profile", feature.params.profile, frozenset({"sketch"})
                )
            )
            references.append(
                FeatureReference("path", feature.params.path, frozenset({"sketch"}))
            )
        case LoftFeature():
            # One sketch ref per ordered section (design §4.3). Each resolves to
            # an earlier sketch feature (a whole feature's wire/apex, NOT a
            # picked sub-edge — independent of #1), so the slot rule is the same
            # `sketch`-only rule as extrude/sweep, emitted per section in order.
            for index, section in enumerate(feature.params.profiles):
                references.append(
                    FeatureReference(
                        f"profiles[{index}]", section, frozenset({"sketch"})
                    )
                )
        case FilletFeature() | ChamferFeature() | PatternFeature():
            # No FeatureRef: fillet/chamfer modify the implicit single body
            # chain (design §7.6) and select edges by a geometric predicate,
            # not by a per-feature subshape reference (design §2.4); a pattern
            # replicates that same implicit body about world-space direction/
            # axis vectors (no picked sub-geometry — independent of #1). Their
            # ordering dependency on the prior body-affecting feature is the
            # tree order.
            pass
        case _:
            assert_never(feature)  # exhaustive: new types must map their slots

    walked = sorted(ref.feature_id for ref in iter_feature_refs(feature))
    mapped = sorted(reference.ref.feature_id for reference in references)
    if walked != mapped:
        raise FeatureSchemaError(
            f"feature_references() slot map for {feature.type!r} is out of "
            f"sync with the schema walk: mapped {mapped}, walked {walked}"
        )
    return tuple(references)


# --- Feature CRUD DTOs (documents API + gateway aggregation) ----------------------


class FeatureCreate(BaseModel):
    """Create a feature. Appends at the tip; while rolled back, inserts
    immediately after the bar and moves the bar to the new feature (§3)."""

    name: FeatureName = Field(description='User-facing name ("Sketch1")')
    feature: Feature
    expected_tree_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the tree_version the client "
        "last saw; a stale value is rejected 422 (design §1.2)",
    )


class FeatureUpdate(BaseModel):
    """Rename and/or replace a feature's param envelope (both bump
    ``tree_version`` — any mutation bumps, design §1.2). The feature ``type``
    is immutable — replace the feature to change its kind."""

    expected_tree_version: int = Field(ge=0)
    name: FeatureName | None = None
    feature: Feature | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> Self:
        if self.name is None and self.feature is None:
            raise ValueError("provide at least one of 'name' or 'feature'")
        return self


class FeatureResponse(BaseModel):
    """A feature as stored, with the envelope reassembled (design §1.3) and
    params already upcast to the current version (design §1.4)."""

    id: uuid.UUID
    part_id: uuid.UUID
    order_index: int = Field(
        description="Dense 0..n-1 evaluation order; only relative position is "
        "meaningful to clients (design §1.2)"
    )
    name: str
    feature: Feature
    rolled_back: bool = Field(
        description="True when the feature sits after the rollback bar (§3)"
    )
    created_at: datetime
    updated_at: datetime


class FeatureTreeResponse(BaseModel):
    """The ordered feature tree of a part plus its concurrency token."""

    part_id: uuid.UUID
    tree_version: int
    rollback_feature_id: uuid.UUID | None = Field(
        description="Last INCLUDED feature; null = bar at the tip (§3)"
    )
    features: list[FeatureResponse]


class FeatureMutationResponse(BaseModel):
    """Result of a single-feature mutation: the affected feature + the new
    tree version (the client's next ``expected_tree_version``)."""

    feature: FeatureResponse
    tree_version: int


class FeatureReorderRequest(BaseModel):
    """Reorder the whole tree: the complete permutation of feature ids in the
    desired evaluation order. Backward-only references (design §2.2 rule 2)
    are re-checked under the new order."""

    expected_tree_version: int = Field(ge=0)
    order: list[uuid.UUID] = Field(
        description="ALL feature ids of the part, in the desired order"
    )


class RollbackBarMove(BaseModel):
    """Move the rollback bar (§3): the id of the last included feature, or
    null for the tip. Bumps ``tree_version`` (it changes what an evaluation
    of the part means)."""

    expected_tree_version: int = Field(ge=0)
    rollback_feature_id: uuid.UUID | None


# --- §4 Evaluation contract (documents → geometry) ---------------------------------


class EvaluatedFeatureInput(BaseModel):
    """One ordered entry of an evaluation request."""

    id: uuid.UUID = Field(description="Feature identity for refs + result keying")
    feature: Feature


class EvaluateTreeRequest(BaseModel):
    """Evaluate an ordered, validated, current-version feature list (§4.2).

    Documents applies the rollback bar BEFORE sending: geometry receives
    exactly the prefix to evaluate and never needs to know rollback exists.
    """

    part_id: uuid.UUID
    tree_version: int = Field(description="Echoed back; cache/correlation key")
    features: list[EvaluatedFeatureInput] = Field(
        description="Ordered prefix (rollback already applied)"
    )
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description="Presentation parameter (mm), NEVER persisted per feature "
        "(design §8.3)",
    )


class ExportTreeRequest(EvaluateTreeRequest):
    """Evaluate a feature tree and export its LAST-GOOD body as a CAD file.

    Extends :class:`EvaluateTreeRequest` — the SAME ordered, rollback-applied
    feature list the evaluate endpoint takes (DRY: one tree contract,
    evaluated then exported) — with the export format selection. The geometry
    service reuses the evaluate-tree dispatch to produce the body, then exports
    THAT body (never a re-modelled shape).

    STEP exports the exact B-rep, so the deflection fields are meaningless for
    it and ignored. STL is a faceted approximation; ``linear_deflection``
    (inherited) and ``angular_deflection`` default to the tessellation defaults
    so the exported mesh matches what the viewport shows.

    If the tree produces no body — a strict-prefix failure (§4.3) or a tree
    with no body-affecting feature — export is a clean error, never a file:
    the geometry service answers a 422 ``tree_export_failed`` envelope, not a
    partial download.
    """

    format: ExportFormat = Field(
        description="Export file format: STEP (exact B-rep) or STL (faceted mesh)"
    )
    angular_deflection: float = Field(
        default=DEFAULT_ANGULAR_DEFLECTION,
        gt=0,
        description=(
            "STL facet angular deflection (rad) between adjacent segments; "
            "ignored for STEP (exact B-rep)"
        ),
    )


def export_tree_filename(request: ExportTreeRequest) -> str:
    """Deterministic download filename for a tree export (Content-Disposition).

    The part id keys the file to its part and stays byte-stable across
    identical requests (determinism is a feature, RESEARCH §9).
    """
    return f"part-{request.part_id}.{request.format}"


class FeatureError(BaseModel):
    """Why one feature failed to evaluate (§4.3)."""

    code: str = Field(
        description='Machine-readable: "profile_not_closed", "boolean_failed", '
        '"reference_unresolved", ...'
    )
    message: str = Field(description="Human-readable, kernel detail sanitized")
    upstream_feature_id: uuid.UUID | None = Field(
        default=None,
        description="Set when the root cause is an earlier feature's output",
    )


class SolvedSketchData(SolvedSketch):
    """Per-feature solved-sketch payload (§7.10): the solver's solved entity
    positions, status, and DOF diagnosis for an ``ok`` sketch feature — what
    the sketcher UI renders. ``kind`` is the :data:`FeatureData` union tag."""

    kind: Literal["solved_sketch"] = "solved_sketch"


#: The typed per-feature ``FeatureResult.data`` payload (design §7.10).
#: Every variant carries a ``kind`` literal tag, so when a second feature
#: type grows a payload this alias becomes the discriminated union
#: ``Annotated[SolvedSketchData | NewData, Field(discriminator="kind")]`` —
#: purely additive on the wire (pydantic forbids a discriminator on a
#: single-member union, hence the plain alias until then).
FeatureData = SolvedSketchData


class FeatureResult(BaseModel):
    """Per-feature evaluation status. Strict-prefix rule (§4.3): the first
    failure is ``error``, every subsequent feature ``skipped``."""

    feature_id: uuid.UUID
    status: Literal["ok", "error", "skipped"]
    error: FeatureError | None = None
    data: FeatureData | None = Field(
        default=None,
        description="Typed per-feature payload for ok features that produce "
        "one (§7.10): solved sketch geometry today; future feature types add "
        "kind-tagged variants additively.",
    )


class EvaluateTreeResult(BaseModel):
    """Statuses plus object-storage references — never kernel types, never
    inline meshes (§4.1). A feature failure is a 200 with per-feature errors;
    the envelope stays reserved for transport/validation failures (§4.3)."""

    part_id: uuid.UUID
    tree_version: int
    features: list[FeatureResult] = Field(description="Same order as the request")
    mesh_glb_id: str | None = Field(
        description="Content-addressed artifact key (sha256:<hex>) of the "
        "LAST-GOOD body mesh; fetch via the geometry service's "
        "GET /api/v1/meshes/{mesh_glb_id} (interim §7.8 path — the key "
        "becomes the object-storage key when that successor lands)"
    )
    properties: ShapeProperties | None = Field(
        description="Mass properties of the last-good body"
    )
    last_good_feature_id: uuid.UUID | None = Field(
        description="Which feature the artifact reflects"
    )
