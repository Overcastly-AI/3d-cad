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
:mod:`loft_wire.geometry` does.
"""

import math
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self, assert_never, cast, get_args

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from loft_wire.datum_angle import DatumAngleLine as DatumAngleLine
from loft_wire.datum_angle import DatumAngleParams as DatumAngleParams
from loft_wire.datum_angle import DatumOriginAxisRef as DatumOriginAxisRef
from loft_wire.datum_angle import DatumSketchLineRef as DatumSketchLineRef
from loft_wire.extrude_extent import EXTRUDE_EXTENT_FIELD, ExtrudeExtent
from loft_wire.feature_expressions import (
    EXPRESSIONS_FIELD,
    STRIP_EXPRESSIONS,
    FeatureExpressions,
    check_expressions,
)
from loft_wire.feature_input import INPUT_ERROR_CHECK, INPUT_ERROR_FIELD
from loft_wire.geometry import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
    EXPORT_FORMAT_DESCRIPTION,
    MESH_QUALITY_NOTE,
    MIN_ANGULAR_DEFLECTION,
    MIN_LINEAR_DEFLECTION,
    ExportFormat,
    ShapeProperties,
    Vec3,
)
from loft_wire.hole_placement import FACE_X_FIELD, FACE_Y_FIELD, derive_hole_position
from loft_wire.instrument import notify_feature_error
from loft_wire.materials import MaterialAssignment, MaterialKey
from loft_wire.merge_field import MERGE_FIELD as MERGE_FIELD
from loft_wire.pipe import DatumAlongPathParams as DatumAlongPathParams
from loft_wire.pipe import PathSegment as PathSegment
from loft_wire.pipe import PathSketchCurve as PathSketchCurve
from loft_wire.pipe import PipeParamsV1 as PipeParamsV1
from loft_wire.plugins import (
    MAX_PLUGIN_EXPANSION,
    MAX_PLUGIN_INPUTS,
    InputName,
    MemberMetadata,
    MemberNameField,
    PluginId,
    RoleName,
    SemVer,
)
from loft_wire.plugins import CustomInputValue as CustomInputValue
from loft_wire.refs import DatumPlaneRef as DatumPlaneRef
from loft_wire.refs import FeatureRef as FeatureRef
from loft_wire.refs import GeomRef as GeomRef
from loft_wire.refs import MidplaneSide as MidplaneSide
from loft_wire.refs import Selector as Selector
from loft_wire.refs import SelectorV1 as SelectorV1
from loft_wire.refs import SubshapeRef as SubshapeRef
from loft_wire.resolution_tiers import (
    SUBSHAPE_RESOLUTION_TIERS as SUBSHAPE_RESOLUTION_TIERS,
)
from loft_wire.resolution_tiers import SketchProjectionReason as SketchProjectionReason
from loft_wire.resolution_tiers import SketchProjectionStatus as SketchProjectionStatus
from loft_wire.resolution_tiers import SubshapeResolutionTier as SubshapeResolutionTier
from loft_wire.sheet_metal import (
    HEM_CLOSED_MAX_RADIUS_RATIO as HEM_CLOSED_MAX_RADIUS_RATIO,
)
from loft_wire.sheet_metal import HEM_CLOSED_RADIUS_RATIO as HEM_CLOSED_RADIUS_RATIO
from loft_wire.sheet_metal import HEM_OPEN_RADIUS_RATIO as HEM_OPEN_RADIUS_RATIO
from loft_wire.sheet_metal import (
    SHEET_METAL_DEFAULT_K_FACTOR as SHEET_METAL_DEFAULT_K_FACTOR,
)
from loft_wire.sheet_metal import CylindricalFaceSignature as CylindricalFaceSignature
from loft_wire.sheet_metal import HemRadiusError as HemRadiusError
from loft_wire.sheet_metal import (
    SheetMetalBaseFlangeParamsV1 as SheetMetalBaseFlangeParamsV1,
)
from loft_wire.sheet_metal import (
    SheetMetalCornerReliefParamsV1 as SheetMetalCornerReliefParamsV1,
)
from loft_wire.sheet_metal import (
    SheetMetalEdgeFlangeParamsV1 as SheetMetalEdgeFlangeParamsV1,
)
from loft_wire.sheet_metal import SheetMetalHemParamsV1 as SheetMetalHemParamsV1
from loft_wire.sheet_metal import (
    resolve_hem_bend_radius_mm as resolve_hem_bend_radius_mm,
)
from loft_wire.shell import SHELL_TYPE_FIELD, ShellType
from loft_wire.signatures import EdgeSelectorV1 as EdgeSelectorV1
from loft_wire.signatures import EdgeSignature as EdgeSignature
from loft_wire.signatures import EdgeSubshapeRef as EdgeSubshapeRef
from loft_wire.signatures import EdgeSubshapeSelector as EdgeSubshapeSelector
from loft_wire.signatures import PlanarFaceSignature as PlanarFaceSignature
from loft_wire.sketch import (
    EntityId,
    Point2D,
    SketchConstraintDiagnosis,
    SketchDefinition,
    SketchProjection,
    SolvedSketch,
)
from loft_wire.twist import MAX_TWIST_ANGLE_DEG as MAX_TWIST_ANGLE_DEG
from loft_wire.twist import MIN_TWIST_ANGLE_DEG as MIN_TWIST_ANGLE_DEG
from loft_wire.twist import is_none as _is_none
from loft_wire.twist import normalised_twist as _normalised_twist
from loft_wire.twist import twist_angle_field as _twist_angle_field

#: Upper bound for a user-facing feature name ("Sketch1", "Extrude1").
FEATURE_NAME_MAX_LENGTH = 200

#: Hard ceiling on an INLINE STEP payload carried in an import feature's params
#: (docs/design/step-import.md §6). A v1 request-validation bound on untrusted
#: external input: an oversize STEP is a 422 at the boundary — rejected BEFORE
#: documents stores it and BEFORE OCCT parses it (the earliest, strongest DoS
#: guard), never a per-feature rebuild error. 16 MiB balances "real mechanical
#: parts fit inline" against "JSONB / request-size / parse-time DoS"; the
#: content-addressed blob-ref successor (§2a) removes this ceiling from the tree.
MAX_INLINE_STEP_CHARS = 16 * 1024 * 1024

# --- Per-request work bounds (engineering audit 2026-07-24 G2) -------------------
#
# The rate limiter caps request FREQUENCY; these constants cap the WORK a single
# authenticated compute request can demand. Sized like the kernel-tolerance
# floors: an order of magnitude beyond any real model in the golden suite /
# a working engineer's part, so a user never feels them, while an attacker
# cannot OOM or monopolize a geometry worker with one request. Over-bound is a
# typed 422 at parse (contract-visible), never a kernel blow-up.

#: Ceiling on the features of ONE evaluate/export/measure/overlay/drawing tree
#: request. Every feature is at least one kernel operation (usually a boolean);
#: real parts run tens-to-low-hundreds of features, so 1000 is far above
#: legitimate use while bounding the per-request kernel work + the buffered
#: JSON body (audit G2 hole 4).
MAX_TREE_FEATURES = 1000

#: Ceiling on a pattern's TOTAL instance count (seed included). Every instance
#: past the seed is a rigid kernel copy feeding one variadic boolean fuse/cut —
#: unbounded ``count`` loops the kernel millions of times in one feature (audit
#: G2 hole 2). 500 matches the MAX_IMPORT_ASSEMBLY_PRODUCTS scale (one bounded
#: "instances per request" posture across the service) and dwarfs any real
#: bolt-circle / perforation array. v1 patterns are SINGLE-direction (no grid
#: variant), so the request total == ``count``; a future grid variant must cap
#: the PRODUCT of its per-direction counts at this same ceiling, not each
#: factor. The lower bound (count >= 1) deliberately stays a rebuild-time
#: ``pattern_bad_count`` (see the pattern module note); only the DoS ceiling is
#: parse-time.
MAX_PATTERN_COUNT = 500

#: Ceiling on loft sections. Each section is a profile-face build + a skin
#: constraint in ONE OCCT loft; real lofts use a handful of sections, so 100 is
#: generous while keeping a single loft feature bounded.
MAX_LOFT_SECTIONS = 100

#: Ceiling on picked-subshape refs in one edge/face selector. Each ref is one
#: signature resolution against the current body plus one edge/face fed to a
#: single fillet/chamfer/shell — 500 picked edges is beyond any real selection
#: while bounding the resolve + kernel-op fan-out of one feature.
MAX_SELECTOR_REFS = 500

#: Ceiling on the features one `features`-scope mirror may name
#: (docs/design/mirror-semantics.md §3.1/§9). Each selected feature costs one
#: exact reflection plus one boolean at rebuild, so the bound is the same shape
#: as MAX_SELECTOR_REFS — far past any real "mirror these features" selection
#: (a whole part is tens of features) while keeping one mirror's kernel fan-out
#: bounded. Over the ceiling is a parse-time 422, never a kernel blow-up.
MAX_MIRROR_SCOPE_FEATURES = 500

#: Ceiling on the features one `features`-scope PATTERN may name
#: (docs/design/pattern-scope.md §2). The mirror's twin, and deliberately the same
#: number: each selected feature costs `count - 1` rigid placements plus one
#: boolean at rebuild, so a pattern's fan-out is ALREADY bounded by
#: MAX_PATTERN_COUNT on the other axis and this bounds the product's second
#: factor. Over the ceiling is a parse-time 422, never a kernel blow-up.
MAX_PATTERN_SCOPE_FEATURES = 500

#: Non-empty (post-strip), bounded feature name.
FeatureName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=FEATURE_NAME_MAX_LENGTH
    ),
]

#: A JSON object — the shape of a stored params payload before validation.
JsonObject = dict[str, Any]


def _drop_schema_default(schema: dict[str, Any]) -> None:
    """Strip the ``default`` key from a field's generated JSON schema.

    ``openapi-typescript`` (default ``default-non-nullable``) makes any property
    that advertises a ``default`` NON-optional in the generated TS type — so a
    defaulted field would force EVERY existing feature literal in the web app to
    supply it, defeating the "additive-optional, backward-compatible" contract.
    Dropping the schema ``default`` (the python default still applies on
    validation) makes such a field OPTIONAL in the client, so existing callers
    that omit it keep compiling and the server fills the default in. The
    ``description`` still documents the absent-reads-<default> behaviour. Shared
    (CLAUDE.md DRY) by the envelope's ``suppressed`` flag and the mirror's
    ``scope``.
    """
    schema.pop("default", None)


# --- §2.4 EdgeSelector — deterministic edge selection (predicate + picked) ---
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


class PickedEdgesSelector(BaseModel):
    """SPECIFIC picked edges, named by stage-1 :class:`EdgeSignature` refs.

    The topological-naming variant (design §2.4/§10) — the "the edge I clicked"
    selection the predicates (``all_edges`` / ``axis_parallel``) structurally
    cannot express: an engineer rounds ONE edge and leaves its neighbour sharp.
    Each ref is an :class:`EdgeSubshapeRef` carrying an :class:`EdgeSignature`
    the geometry service resolves against the current body — nearest-within-
    tolerance, exactly one or an honest error. At least one ref (``min_length=1``
    — an empty picked-edge selection is a request-validation 422, never a silent
    no-op). Added BESIDE the predicates (design §7.6), not replacing them:
    ``all_edges``/``axis_parallel`` remain the right tool for SET selections.
    """

    kind: Literal["edges"]
    refs: list[EdgeSubshapeRef] = Field(
        min_length=1,
        max_length=MAX_SELECTOR_REFS,
        description="The specific picked edges (>= 1, bounded by "
        "MAX_SELECTOR_REFS — work bound, audit G2), each a stage-1 "
        "EdgeSignature reference resolved against the current body",
    )


#: Discriminated edge-selection union for body-modifying features. The
#: ``edges`` (picked, topological-naming) member is ADDITIVE beside the two
#: predicates — existing ``all_edges``/``axis_parallel`` selectors validate and
#: evaluate byte-identically, so fillet/chamfer ``param_version`` stays 1.
EdgeSelector = Annotated[
    AllEdgesSelector | AxisParallelEdgesSelector | PickedEdgesSelector,
    Field(discriminator="kind"),
]


# --- FACE selection — the picked-face sibling of the edge selector (§2.4/§10) ---
#
# The shell feature names the faces to REMOVE (leave open) as SPECIFIC picked
# faces, each a stage-1 :class:`SubshapeRef` (the SAME planar-face signature the
# sketch-on-a-face / on_face datum resolves — topo-naming §4, reused not
# reinvented). There is NO face predicate today (no ``all_faces`` /
# ``axis_normal`` analogue of the edge predicates): shell is inherently a
# pick-the-openings operation, so v1 ships only the picked variant. A future
# predicate joins additively as a ``kind``-discriminated union member (the
# :data:`EdgeSelector` idiom) with no ``param_version`` bump — hence
# ``FaceSelector`` is a plain single-member model today, discriminated on
# ``kind: "faces"`` so that promotion is shape-compatible.


class FaceSelector(BaseModel):
    """The faces to REMOVE (leave open) in a shell, named by stage-1 signatures.

    Each ref is a :class:`SubshapeRef` — the SAME planar-face signature the
    ``on_face`` datum uses (topo-naming §4), resolved against the current body
    nearest-within-tolerance, exactly one or an honest error. The face
    signatures the geometry service resolves are the ones a pick UI echoes
    straight from ``/overlay`` (the sketch-on-face pick set).

    DESIGN DECISION (v1, docs/GEOMETRY-QA.md 2026-07-13): an EMPTY ``refs`` list
    is a valid, meaningful selection — a **fully-enclosed hollow** (the standard
    "hollow but sealed" case: a closed shell with a uniform-thickness cavity and
    NO opening). A non-empty list opens exactly those faces. So — unlike the
    picked-EDGE selector, whose empty list is a request-validation 422 (an empty
    fillet is a silent no-op) — an empty picked-FACE list is a real operation and
    carries no ``min_length``. Duplicate refs that resolve to the same face
    collapse to one (idempotent) at resolution.
    """

    kind: Literal["faces"]
    refs: list[SubshapeRef] = Field(
        default_factory=list[SubshapeRef],
        max_length=MAX_SELECTOR_REFS,
        description="The planar faces to leave OPEN (each a stage-1 face "
        "SubshapeRef resolved against the current body), bounded by "
        "MAX_SELECTOR_REFS (work bound, audit G2). EMPTY = a fully-enclosed "
        "hollow (no opening) — a valid selection, not a 422 (design decision).",
    )


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
    (``geometry.kernel.faces.deterministic_x_dir``) so the 2D→3D mapping is
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


class DatumOffsetFromParams(BaseModel):
    """An EARLIER datum feature's plane slid along its normal (``kind: "offset_from"``).

    Offset CHAINING (docs/design/datum-planes.md §7): ``base`` is a
    :class:`FeatureRef` to an earlier ``datum`` feature, and the plane is that
    datum's RESOLVED plane slid ``offset_mm`` along its normal, with the same
    optional ``flip`` an origin offset has. Chains compose left-to-right: origin
    → datum A → datum B resolves to the analytic composite (each hop is a pure
    ``Plane.offset``). The strict-backward rule (feature-tree §2.2) means the
    parent always evaluated first — a self/forward reference NEVER resolves (a
    write-time 422; the eval-time backstop is ``reference_unresolved``), so
    resolution is a single dict lookup, never a recursion.

    DESIGN DECISION — a SEPARATE ``kind``, not a widened ``base`` union on
    :class:`DatumOffsetParams` (datum-planes §7 sketched the union): widening
    ``base`` to ``Literal[...] | FeatureRef`` changes the GENERATED ts-client
    type of every existing offset datum, breaking each consumer that reads
    ``params.base`` as a plane name (the viewport derives the offset basis
    client-side from it). A new discriminated kind is the established additive
    idiom (``on_face`` proved it): existing ``offset`` payloads stay
    byte-identical on the wire AND type-identical in the generated client, and
    NO ``param_version`` bump is needed.
    """

    kind: Literal["offset_from"]
    base: FeatureRef = Field(
        description="EARLIER `datum` feature whose resolved plane this plane "
        "offsets from (its orientation and origin)."
    )
    offset_mm: float = Field(
        allow_inf_nan=False,
        description="Signed distance along the base datum's normal (mm). 0 "
        "coincides with the base datum; +/- selects side. Any finite value is "
        "valid.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir so "
        "sketch +u is unchanged and +v flips) — the same rule as `offset`.",
    )


class DatumMidplaneParams(BaseModel):
    """A plane midway between two references (``kind: "midplane"``).

    The midplane slice of docs/design/datum-planes.md §7: each side resolves to
    a plane through the same funnels the sketch plane and the ``on_face`` datum
    use, and the datum bisects them. Conventions (documented in datum-planes §7a
    and implemented by ``geometry.kernel.datum.midplane_between`` — DETERMINISTIC,
    RESEARCH §9):

    * PARALLEL sides (incl. anti-parallel normals, e.g. a box's top + bottom
      faces): the plane midway between them; normal = side ``a``'s normal;
      origin = the midpoint of the two resolved origins. Identical/coplanar
      sides degenerate cleanly to the plane itself.
    * NON-PARALLEL sides: the angular-bisector plane through their intersection
      line; normal = ``normalize(n_a + n_b)`` (well-defined for any non-parallel
      pair, perpendicular included — the documented normal-sign rule; flipping a
      side's normal selects the other bisector); origin = the point of the
      intersection line nearest the world origin (the minimum-norm solution —
      a pure closed form of the two planes).
    * Basis: ``z_dir`` = the convention normal above, ``x_dir`` pinned from it
      by ``geometry.kernel.faces.deterministic_x_dir`` (the on_face rule), so
      the 2D→3D mapping is stable across rebuilds.

    A midplane over two RESOLVED sides is total — parallel, angular, and
    identical inputs all yield a valid plane — so its only failures are
    reference resolution: ``reference_unresolved`` (a side names a missing/
    later/non-datum feature) or ``subshape_unresolved``/``subshape_ambiguous``
    (a picked-face side, exactly the ``on_face`` taxonomy).
    """

    kind: Literal["midplane"]
    a: MidplaneSide = Field(
        description="First reference: an origin datum name, an earlier `datum` "
        "feature, or a picked planar face. Its normal signs the parallel-case "
        "midplane."
    )
    b: MidplaneSide = Field(description="Second reference (same forms as `a`).")
    flip: bool = Field(
        default=False,
        description="Reverse the plane normal (negate z_dir, keeping x_dir so "
        "sketch +u is unchanged and +v flips) — the same rule as `offset`.",
    )


#: Datum params: an offset-from-origin plane, an on-a-face plane, an
#: offset-from-another-datum plane (chaining), a midplane between two
#: references, or a plane at an angle about a line (:mod:`loft_wire.datum_angle`)
#: — discriminated on ``kind``. LEGACY persisted params carry no
#: ``kind`` (they predate on_face) — :class:`DatumFeature`'s before-validator
#: injects ``kind: "offset"`` so old rows validate unchanged (additive, NO
#: ``param_version`` bump — datum-planes §4/§7).
DatumParams = Annotated[
    DatumOffsetParams
    | DatumOnFaceParams
    | DatumOffsetFromParams
    | DatumMidplaneParams
    | DatumAngleParams
    | DatumAlongPathParams,
    Field(discriminator="kind"),
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

    Extends :class:`loft_wire.sketch.SketchDefinition` (typed
    ``entities``/``constraints`` — the §1.4 placeholder finalized by the
    "Sketch model + solver API" item), so a persisted sketch's params ARE
    valid solver input: same validation (unique sketch-local entity ids per
    design §2.4) on the documents write path and the geometry request path.
    """

    plane: GeomRef


class ExtrudeParamsV1(BaseModel):
    """Linear extrusion of an earlier sketch feature's profile.

    With a nonzero ``twist_angle_deg`` it is a TWISTED extrusion: the profile
    rotates uniformly about an axis parallel to the extrusion direction while it
    travels, so every point of it traces a true helix and the far-end section is
    the profile rotated by the full twist (docs/design/twisted-extrude.md).

    **The extrude twist is DEPRECATED (read-only legacy).** Twist is authored
    on :class:`SweepParamsV1` (``twist_angle_deg``, "twist along path" as in
    Fusion 360 and SolidWorks). These two fields stay so that every stored
    twisted extrude loads and rebuilds exactly as before, but a write that
    sets or changes one is refused (:mod:`loft_wire.legacy_twist`); a twisted
    sweep along the matching straight path builds the SAME solid.
    Both fields are additive-optional, null by default and OMITTED from a dump
    while null, so an extrude with no twist serializes byte-for-byte as it did
    before they existed (stored row, response, rebuild-cache key) and rebuilds
    on the unchanged prism path — no ``param_version`` bump. A client that edits
    a stored twisted extrude must carry both fields through unchanged.
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature (design §2.2)"
    )
    distance_mm: float = Field(gt=0, description="Extrusion depth (mm)")
    operation: Literal["add", "cut"]
    direction: Literal["normal", "reverse"] = "normal"
    extent: ExtrudeExtent = EXTRUDE_EXTENT_FIELD
    merge: bool = MERGE_FIELD
    twist_angle_deg: float | None = _twist_angle_field(
        "DEPRECATED, read-only legacy: kept so stored extrudes load and "
        "rebuild unchanged; creating or changing it is refused with "
        "`extrude_twist_deprecated` (use a Sweep's `twist_angle_deg`). Twist "
        "over the whole extrusion distance (degrees). The profile "
        "rotates uniformly about the twist axis as it travels, a true helical "
        "sweep. Positive is RIGHT-HANDED about the extrusion direction (a "
        "right-hand helix whichever way `direction` points); negative is "
        "left-handed. None (the default), 0, or any |twist| below 1e-9 deg "
        "is NO twist: it is normalised to absent, and the extrude is a plain "
        "prism, byte-identical to one with no twist. A twist too tight for "
        "the profile, or with too many turns for it to build in reasonable "
        "time, is a `twist_failed` rebuild error."
    )
    twist_center: Point2D | None = Field(
        default=None,
        exclude_if=_is_none,
        description=(
            "DEPRECATED with `twist_angle_deg` (read-only legacy). Where the "
            "twist axis pierces the sketch plane, in the profile sketch's own "
            "(x, y) mm; the axis runs parallel to the extrusion direction. "
            "None is the sketch origin; dropped when there is no twist."
        ),
    )

    @model_validator(mode="after")
    def _normalise_twist(self) -> Self:
        """Refuse a non-finite axis; fold "no twist" into ONE spelling: absent.

        * A twist axis through a non-finite point is no axis at all (422).
        * ``|twist| < MIN_TWIST_ANGLE_DEG`` — ``0``, ``-0`` and anything too
          small to move geometry — becomes ``None``: it is not a twist, and a
          sub-normal one used to hang the kernel's helix (5e-324 deg).
        * With no twist the axis means nothing, so a leftover ``twist_center``
          is dropped too.

        The result is that every untwisted extrude DUMPS identically (no twist
        keys at all), whatever it was spelled as on the way in — the stored row,
        the response and the rebuild-cache key agree with an extrude written
        before the twist existed.
        """
        centre = self.twist_center
        if centre is not None and not (
            math.isfinite(centre.x) and math.isfinite(centre.y)
        ):
            raise ValueError("twist_center must have finite x and y (mm)")
        self.twist_angle_deg = _normalised_twist(self.twist_angle_deg)
        if self.twist_angle_deg is None:
            self.twist_center = None
        elif self.extent == "symmetric":
            raise ValueError("a symmetric extrude cannot carry the legacy twist")
        return self

    @property
    def is_twisted(self) -> bool:
        """Whether this extrude takes the twisted-sweep path (a real twist)."""
        return self.twist_angle_deg is not None


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


class RevolveParamsV1(BaseModel):
    """Revolution of an earlier sketch feature's profile about an axis.

    The revolve sibling of :class:`ExtrudeParamsV1` (design §4.3, second core
    body-affecting feature): it consumes the SAME ``profile`` FeatureRef to an
    earlier sketch and the SAME ``add``/``cut`` boolean against the body chain,
    swapping the linear prism for a swept revolution. The ``axis`` is a
    :data:`RevolveAxis` — a line entity of that same sketch
    (:class:`SketchLineAxis`) or a world origin axis (:class:`OriginAxis`);
    neither is a picked sub-geometry reference, so revolve remains independent
    of topological naming — and ``angle_deg`` is the sweep (full 360° by
    default).

    Two conditions are typed refusals rather than bad solids (design §4.3):

    * the axis must lie IN the profile's sketch plane, or
      ``axis_not_in_sketch_plane``; and
    * the profile must clear the axis — a profile the axis CROSSES would
      revolve into self-intersecting material, so it is
      ``axis_intersects_profile``. A profile that merely TOUCHES the axis is
      valid: that is the ordinary solid of revolution about its own centerline.
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature (design §2.2)"
    )
    axis: RevolveAxis = Field(
        description="Axis of revolution — a line entity of the profile's sketch "
        "or a world origin axis; it must lie in the profile's sketch plane"
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
    merge: bool = MERGE_FIELD

    @model_validator(mode="before")
    @classmethod
    def _legacy_sketch_line_kind(cls, data: Any) -> Any:
        """Read a kind-less ``axis`` blob as a :class:`SketchLineAxis`.

        The pre-REVOLVE-1 ``RevolveAxis`` was a single model whose ``kind``
        carried a DEFAULT, so a params blob persisted as
        ``{"axis": {"entity": "axis"}}`` was valid. Widening ``axis`` into a
        discriminated union makes the discriminator mandatory, which would make
        exactly those rows unreadable. Injecting ``kind: "sketch_line"`` when it
        is absent keeps them valid with no stored-shape change and no
        ``param_version`` bump — the same additive migration
        :meth:`DatumFeature._legacy_offset_kind` performs for kind-less offset
        datums. An axis that states its ``kind`` is untouched.
        """
        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, Any]", data)
        axis = fields.get("axis")
        if not isinstance(axis, dict):
            return fields
        axis_dict = cast("dict[str, Any]", axis)
        if "kind" in axis_dict:
            return fields
        new_axis = dict(axis_dict)
        new_axis["kind"] = "sketch_line"
        new_fields = dict(fields)
        new_fields["axis"] = new_axis
        return new_fields


class SweepParamsV1(BaseModel):
    """Sweep an earlier sketch's closed profile along an earlier sketch's path.

    The first NON-PRISMATIC body-affecting feature (design §4.3): where extrude
    sweeps a profile along the plane normal and revolve about an axis, sweep
    follows an arbitrary PATH wire — the shaft / pipe / rib primitive named
    in the Part-modeling scorecard notes. It consumes the SAME ``profile``
    FeatureRef to an earlier sketch (a single closed wire, built by the shared
    ``build_profile_face``) and the SAME ``add``/``cut`` boolean against the body
    chain as extrude/revolve; the new ingredient is ``path``, a SECOND
    FeatureRef to an earlier sketch whose entities form one wire, open or closed.

    Path representation (v1 DESIGN DECISION — docs/design/feature-tree.md
    §2.1/§2.2, docs/GEOMETRY-QA.md 2026-07-12): the path is a whole earlier
    SKETCH feature referenced by id (option A — the most general model, matching
    how production CAD names a sweep path, and reusing the tree's stable feature
    ids exactly as the ``profile`` slot does). This is NOT topological naming
    (#1): it references a whole feature's evaluated wire, never a picked
    sub-edge — the same mechanism extrude/revolve already use for their profile.

    v1 limits (stated plainly — documented scope, not bugs):

    * the path must resolve to a single connected wire; disjoint path loops are
      ``sweep_path_not_connected``, and a path with no curve entities is
      ``sweep_path_empty`` (construction geometry excluded, as from the profile);
    * a CLOSED path sweeps once around into one capless solid; every joint must
      be G1, else ``sweep_path_not_tangent`` names it (docs/RESEARCH.md §19);
    * an open sweep is **anchored at the profile** — build123d applies the path as a
      relative trajectory from the profile's own location, so the path's
      absolute position is not used. Author the path starting at the profile
      origin, with its first segment perpendicular to the profile plane, for a
      predictable result (as the golden's vertical path over an XY circle is);
    * NO scale-along-path, NO multi-section, NO guide rails, NO per-segment
      transition control — one profile swept along one path (all later,
      additive params — no ``param_version`` bump);
    * a self-intersecting path, or a corner tighter than the profile can turn
      without sweeping through itself, is a kernel ``sweep_failed`` rebuild
      error, never a silently bad body.

    **Twist along the path** (``twist_angle_deg``, TWIST-TO-SWEEP; Fusion 360's
    and SolidWorks' "twist along path"): the profile turns uniformly about the
    PATH as it travels, so every point of it traces a true helix — a helical
    gear's tooth gap, a twisted column. v1 twists along a STRAIGHT path that is
    perpendicular to the profile's sketch plane and does not pass through it
    (it starts on the profile, or lies wholly to one side of it); that sweep is
    exact (docs/design/twisted-extrude.md). Any other path with a twist — an
    arc, a bend, a slanted line, a line through the profile — is the typed
    rebuild error ``twist_path_unsupported``, never an approximated body.
    Additive-optional and omitted from a dump while null, so every untwisted
    sweep serializes and rebuilds byte-for-byte as before (no ``param_version``
    bump).
    """

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature whose entities "
        "form the single CLOSED profile wire (design §2.2)"
    )
    path: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature whose entities "
        "form one wire, open or closed and G1 — the sweep trajectory (§2.2)"
    )
    operation: Literal["add", "cut"]
    merge: bool = MERGE_FIELD
    twist_angle_deg: float | None = _twist_angle_field(
        "Twist along the path (degrees): the total turn of the profile about "
        "the path from one end of the sweep to the other, uniform along it, so "
        "every profile point traces a true helix. Positive is RIGHT-HANDED about "
        "the direction of travel (from the profile along the path, whichever way "
        "the path line was drawn); negative is left-handed. Limit +-3600 (ten "
        "turns). None (the default), 0, or any |twist| below 1e-9 deg is NO "
        "twist: normalised to absent, and the sweep is byte-identical to an "
        "untwisted one. Needs a straight path perpendicular to the profile's "
        "sketch plane that does not cross it, else the rebuild error "
        "`twist_path_unsupported`; a twist with too many turns for the profile "
        "to build in reasonable time is `twist_failed`."
    )

    @model_validator(mode="after")
    def _normalise_twist(self) -> Self:
        """Fold every spelling of "no twist" into ONE: absent (the extrude's
        rule), so an untwisted sweep dumps exactly as it did before the field."""
        self.twist_angle_deg = _normalised_twist(self.twist_angle_deg)
        return self

    @property
    def is_twisted(self) -> bool:
        """Whether this sweep takes the twisted path (a real twist)."""
        return self.twist_angle_deg is not None


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
        max_length=MAX_LOFT_SECTIONS,
        description="Ordered earlier sketch features (>= 2, bounded by "
        "MAX_LOFT_SECTIONS — work bound, audit G2) to blend through; "
        "each forms a single closed profile wire or a single apex point "
        "(design §2.2). Fewer than 2 is a request-validation 422.",
    )
    operation: Literal["add", "cut"]
    merge: bool = MERGE_FIELD


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


class ShellParamsV1(BaseModel):
    """Hollow the current body to a uniform wall thickness, opening picked faces.

    The housing / enclosure / cup primitive (a Part-modeling scorecard item):
    the solid is thinned inward to a uniform wall of ``thickness_mm`` and the
    faces named by ``faces`` are REMOVED, leaving those sides open. Like a
    fillet/chamfer/pattern it modifies the implicit single body chain (design
    §7.6), so it carries no whole-feature ``FeatureRef`` — its dependency on the
    prior body-affecting feature is tree order. The picked openings ARE named
    references, though: each :class:`SubshapeRef` in ``faces`` materializes into
    ``feature_dependencies`` exactly like an ``on_face`` datum's face ref, so
    deleting the referenced body feature is a write-time 409-with-dependents and
    a reorder re-checks strict-backward.

    Thickness is a UNIFORM INWARD offset (the outer envelope is unchanged); an
    empty ``faces`` list hollows to a sealed cavity. A thickness that would
    collapse or self-intersect the cavity (≥ the smallest half-wall) is a
    per-feature ``shell_thickness_too_large`` rebuild error, never a silently
    wrong body (docs/GEOMETRY-QA.md 2026-07-13).
    """

    thickness_mm: float = Field(
        gt=0,
        description="Uniform inward wall thickness (mm). Must be small enough "
        "that the inward cavity does not self-intersect; too large is a "
        "`shell_thickness_too_large` rebuild error.",
    )
    faces: FaceSelector = Field(
        description="The faces to leave OPEN (a picked-face selector). Empty = a "
        "fully-enclosed hollow with no opening (design decision)."
    )
    shell_type: ShellType = SHELL_TYPE_FIELD


# --- Draft params — taper picked faces by an angle (mold/casting release) --------
#
# Draft tapers picked faces AWAY FROM (or toward) a pull direction by a small
# angle: the classic molding/casting release, but also tapered bosses/walls. It
# reuses the picked-FACE :class:`FaceSelector` machinery shell shipped (topo-
# naming §4) — pick the faces to taper, resolved against the current body by the
# SAME stage-1 planar-face signature the ``on_face`` datum uses, NOT a parallel
# taxonomy.
#
# v1 SCOPE DECISION (docs/GEOMETRY-QA.md 2026-07-13 — stated plainly, not
# oversold): the NEUTRAL PLANE (the plane that stays fixed — faces rotate about
# their intersection with it) and the PULL DIRECTION are a PRINCIPAL ORIGIN DATUM
# (XY/XZ/YZ) with an optional offset + flip, reusing the datum machinery
# (``build_datum_plane``) rather than inventing a new picker. The pull direction
# IS that plane's normal (build123d ``Solid.draft`` derives the pull from
# ``neutral_plane.z_dir``), so one datum fixes both. This covers the canonical
# case — "taper these faces by N° about the base plane, pull +Z" — and the base/
# offset/flip knobs cover the other principal planes and offset heights.
#
# What v1 does NOT do (future ADDITIVE increments — a ``kind``-discriminated
# neutral-plane member or new params, NO ``param_version`` bump — the RevolveAxis
# idiom): a neutral plane PICKED as a planar face (SubshapeRef) or referenced as a
# datum feature; VARIABLE-angle draft; PARTING-LINE draft (the neutral line split
# across a face). One constant angle about one principal-datum neutral plane.


class DraftNeutralPlaneV1(BaseModel):
    """v1 draft neutral plane = a principal origin datum, offset + flipped.

    The plane that stays FIXED under the draft (picked faces rotate about their
    intersection with it), and — because build123d's ``Solid.draft`` derives the
    PULL DIRECTION from ``neutral_plane.z_dir`` — also the pull direction (its
    normal). Reuses the datum machinery (``geometry.kernel.build_datum_plane``,
    the same ``base``/``offset_mm``/``flip`` an offset ``datum`` feature uses), so
    the plane is a DETERMINISTIC pure function of its params (RESEARCH §9), needs
    no picked geometry, and carries NO feature reference (independent of
    topological naming #1).

    ``kind`` defaults to ``"datum"`` and seeds a future additive union (a face-
    picked or datum-feature-referenced neutral plane joins as another ``kind``
    with NO ``param_version`` bump — the :data:`PatternGeometry` / RevolveAxis
    idiom).
    """

    kind: Literal["datum"] = "datum"
    base: Literal["XY", "XZ", "YZ"] = Field(
        description="Origin datum the neutral plane is parallel to; its normal is "
        "the PULL direction (out of the mold). +Z for the default XY base."
    )
    offset_mm: float = Field(
        default=0.0,
        allow_inf_nan=False,
        description="Signed distance along `base`'s normal (mm) to the neutral "
        "plane; 0 sits on the origin datum (the base). Any finite value is valid.",
    )
    flip: bool = Field(
        default=False,
        description="Reverse the pull direction (negate the plane normal) — the "
        "OTHER mold half. Additive-optional; absent reads as False.",
    )


class DraftParamsV1(BaseModel):
    """Taper picked faces of the current body by a constant angle (design §4.3).

    The molding/casting RELEASE primitive (also tapered bosses/walls): the faces
    named by ``faces`` are tilted by ``angle_deg`` about their intersection with
    the ``neutral_plane``, so a body pulls cleanly from a mold along the neutral
    plane's normal. Like a fillet/chamfer/shell it modifies the implicit single
    body chain (design §7.6), so it carries no whole-feature ``FeatureRef`` — its
    dependency on the prior body-affecting feature is tree order. The picked faces
    ARE named references, though: each :class:`SubshapeRef` in ``faces``
    materializes into ``feature_dependencies`` exactly like a shell opening or an
    ``on_face`` datum's face ref, so deleting the referenced body feature is a
    write-time 409-with-dependents and a reorder re-checks strict-backward.

    ``faces`` reuses the SAME :class:`FaceSelector` shell uses (topo-naming §4).
    Unlike shell — where an EMPTY selection is a meaningful sealed hollow — a
    draft with NO faces has nothing to taper, so an empty selection is a
    ``no_draft_faces`` rebuild error (draft must pick at least one face), never a
    silent no-op.

    SIGN CONVENTION (measured against OCCT, docs/GEOMETRY-QA.md 2026-07-13): a
    POSITIVE ``angle_deg`` tapers each face INWARD toward the pull direction —
    the top (the ``neutral_plane``-normal end) NARROWS, the standard mold
    release. A NEGATIVE angle tapers OUTWARD (the far end widens — the opposite
    mold half). An angle too large for the geometry (the tapered faces collapse
    to zero width / self-intersect) is a ``draft_failed`` rebuild error — OCCT
    RAISES on that path, it never silently returns a bad body (unlike shell, so
    no material-validity guard is needed — investigation recorded in
    docs/GEOMETRY-QA.md), so ``draft_failed`` is never a silently wrong solid.

    v1 limits (documented scope, not bugs): ONE constant angle, principal-datum
    neutral plane only (see :class:`DraftNeutralPlaneV1`), planar/cylindrical/
    conical faces only (a face OCCT cannot draft is a ``draft_failed``). NO
    variable-angle, NO parting-line, NO face-picked neutral plane (all later,
    additive — no ``param_version`` bump).
    """

    faces: FaceSelector = Field(
        description="The faces to TAPER (a picked-face selector, the SAME stage-1 "
        "signature shell/on_face use). Must name at least one face — an empty "
        "selection is a `no_draft_faces` rebuild error (draft is not a no-op)."
    )
    angle_deg: float = Field(
        gt=-90.0,
        lt=90.0,
        allow_inf_nan=False,
        description="Draft angle (degrees). POSITIVE tapers INWARD toward the "
        "pull direction (top narrows — mold release); NEGATIVE tapers outward. "
        "An angle too large for the geometry is a `draft_failed` rebuild error.",
    )
    neutral_plane: DraftNeutralPlaneV1 = Field(
        description="The fixed plane the picked faces rotate about; its normal is "
        "the pull direction (:class:`DraftNeutralPlaneV1`)."
    )


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
    ``diameter_mm`` into the current body at ``position`` on the planar ``face``,
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
    _derive_position = model_validator(mode="after")(derive_hole_position)


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
#     Feature-scoped ADD patterning (replicating only one chosen boss's tool
#     solid onto a fixed base) needs per-feature tool tracking and is future
#     work (#7 follow-up), NOT this version.
#   * the copies must merge into ONE connected solid (§7.6 single body chain);
#     a pattern whose instances are disjoint is a per-feature `pattern_disjoint`
#     rebuild error until multi-body parts land.
#
# CUT-ARRAY EXTENSION (BACKLOG #3 / showcase F1 — recorded in docs/GEOMETRY-QA.md
# 2026-07-13, option (a)): a pattern also arrays a CUT (bolt-circle / lightening
# holes). NO schema change — the mode is INFERRED at rebuild from the
# immediately-preceding body-affecting feature (this envelope carries no
# FeatureRef; the dependency is tree order). When that source is an extrude-cut,
# the geometry service reconstructs its tool and REMOVES a copy at each
# placement, so one hole-cut + a pattern drills N holes. The DTO is unchanged;
# the whole decision lives in the geometry evaluator (geometry.features.evaluate)
# and geometry.kernel.pattern, keeping this boundary model add/cut-agnostic.
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
#
# ONE carve-out (engineering audit 2026-07-24 G2): the `count` DoS CEILING
# (`le=MAX_PATTERN_COUNT`) IS a parse-time 422. It is not a semantic validity
# check but a per-request work bound — an attacker's count=10_000_000 must be
# rejected before the kernel loops, exactly like the deflection floors — and it
# is single-field, so the cross-field rationale above does not apply. The
# kernel's `_check_count` re-checks the same ceiling as defense-in-depth for
# direct kernel callers.


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
        le=MAX_PATTERN_COUNT,
        description="TOTAL instances INCLUDING the seed (instance 0); an "
        "integer >= 1, at most MAX_PATTERN_COUNT (work bound, audit G2 — over "
        "the ceiling is a parse-time 422). `count < 1` is a "
        "`pattern_bad_count` rebuild error; `count = 1` is a no-op (the body "
        "is unchanged).",
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
        le=MAX_PATTERN_COUNT,
        description="TOTAL instances INCLUDING the seed; an integer >= 1, at "
        "most MAX_PATTERN_COUNT (work bound, audit G2 — over the ceiling is a "
        "parse-time 422). `count < 1` is a `pattern_bad_count` rebuild error; "
        "`count = 1` is a no-op.",
    )


#: Discriminated pattern-geometry union (linear vs circular), the RevolveAxis
#: `kind`-discriminator idiom: a future `path`/`mirror` variant joins additively
#: without a `param_version` bump.
PatternGeometry = Annotated[
    LinearPatternParamsV1 | CircularPatternParamsV1, Field(discriminator="kind")
]


# v2 — THE SCOPE (docs/design/pattern-scope.md, 2026-08-26). The v1 contract is ONE
# field (`pattern`) and the SEED is INFERRED from the body chain, in two places:
# `_pattern_cut_tools` (array the previous feature's removal tool only if that cut
# is the IMMEDIATE predecessor) and the kernel's VACUOUS-CUT FALLBACK (array the
# whole body when no placed tool copy can reach it). Each rule is individually
# defensible; together they mean the same dialog with the same numbers in it
# produces two different KINDS of result and reports `ok` either way. §1 of that
# design measures both flips: an unrelated fillet between the hole and the pattern
# turns 28984.0710 (three holes) into 50040.1770 (three PLATES, bbox X 40 -> 64),
# and moving `spacing_mm` from 8 to 12 on a hole near the +X face turns
# 30798.1512 into 40594.6904. Three product-audit passes have reported this.
#
# The ambiguity is in the INPUT, so `scope` removes it there — the SAME two-member
# `kind`-discriminated union :data:`MirrorScope` uses, with the words changed:
# `body` (the v1 reading, now NAMED) and `features` (an explicit, non-empty,
# TREE-ORDERED selection). SolidWorks ("Features to Pattern"), Fusion (Pattern ->
# Type: Features) and Onshape all ask exactly this question.
#
# Additive under feature-tree §1.4 (`param_version` stays 1): a persisted pattern
# with no `scope` key normalises to `{"kind": "body"}` through
# :meth:`PatternParamsV1._legacy_body_scope`, so every existing row and all four
# shipped pattern goldens validate AND evaluate on the unchanged v1 code path.
# There is deliberately NO "default to the tip" in the DTO (§2.2): the tip is not
# knowable here, and a default that rewrote the meaning of persisted rows would
# reintroduce the very property this removes. Pre-selecting the tip is the DIALOG's
# job, and the dialog sends `scope` explicitly.


class PatternBodyScope(BaseModel):
    """``scope: {"kind": "body"}`` — repeat the CURRENT BODY (the v1 reading).

    The v1 semantic, NAMED rather than implied (design §2): both inference rules
    above run verbatim, on the same code path, producing the same bytes — so the
    shipped pattern goldens' byte identity is STRUCTURAL, not measured. This scope
    still flips as §1 measures; that is what "additive" costs, and the flip is now a
    documented property of a legacy reading the UI never authors rather than the
    only available spelling.
    """

    kind: Literal["body"] = "body"


class PatternFeaturesScope(BaseModel):
    """``scope: {"kind": "features", "features": [...]}`` — repeat these features.

    The v2 reading (design §2/§3): each selected feature's RECORDED RIGID TOOL
    SOLID(S) are PLACED at the pattern's ``k = 1 .. count-1`` placements and that
    feature's OWN operation (``fuse``/``cut``) is re-applied to the active body, in
    TREE order — never array order (§6: array order is UI-incidental, so honouring
    it would make identical models tessellate to different bytes). The placements
    come from the SAME kernel helpers the ``body`` path calls, so what a selection
    repeats can never drift from what a pattern applies.

    ``features`` names :class:`FeatureRef`s rather than bare UUIDs so each selection
    materialises into ``feature_dependencies`` for free (feature-tree §2.3): deleting
    a patterned feature is a 409-with-dependents, a reorder re-checks the
    strict-backward rule, and a forward/self reference is a write-time 422. A
    non-body-affecting or non-repeatable kind (``sketch``/``datum``, and every
    MODIFIER — fillet/chamfer/shell/draft and the sheet-metal family, which have a
    RESULT and no tool) is refused with the typed per-feature
    ``pattern_feature_unsupported`` at rebuild.

    ``min_length=1`` because an empty selection is authoring nonsense, not a no-op
    pattern, and duplicate ids are a 422 rather than silently deduplicated — naming
    a feature twice leaves the intent (twice? once?) unstated, which is the mistake
    v1 made.
    """

    kind: Literal["features"]
    features: list[FeatureRef] = Field(
        min_length=1,
        max_length=MAX_PATTERN_SCOPE_FEATURES,
        description="The features to repeat, each a `FeatureRef` to an earlier "
        "body-affecting feature of this tree. Applied in TREE order (the array "
        "order is ignored — design §6); at least one, at most "
        "MAX_PATTERN_SCOPE_FEATURES (work bound); duplicates are a 422.",
    )

    @model_validator(mode="after")
    def _reject_duplicate_features(self) -> Self:
        """Duplicate selected ids are a 422 (design §2), never deduplicated."""
        seen: set[uuid.UUID] = set()
        for ref in self.features:
            if ref.feature_id in seen:
                raise ValueError(
                    f"Pattern scope names feature {ref.feature_id} more than once; "
                    "a feature is repeated exactly once per instance, so a "
                    "duplicate leaves the intent unstated. Remove the repeat."
                )
            seen.add(ref.feature_id)
        return self


#: The pattern's SCOPE union (design §2), discriminated on ``kind``: `body` (v1) or
#: `features` (v2) — the :data:`MirrorScope` idiom, and a discriminated union rather
#: than ``features: list[FeatureRef] | None`` for the same reason: ``None`` and
#: "repeat the body" would be two spellings of one meaning, the exact smell that
#: made v1's semantic implicit. A future third reading (``kind: "bodies"``,
#: multi-body selection) joins additively with no ``param_version`` bump.
PatternScope = Annotated[
    PatternBodyScope | PatternFeaturesScope, Field(discriminator="kind")
]


class PatternParamsV1(BaseModel):
    """Repeat the current single body into a linear row or circular ring.

    Wraps the discriminated :data:`PatternGeometry` under ``pattern`` (the
    nested-discriminator idiom of :class:`RevolveParamsV1`'s ``axis``). In the
    ``body`` scope a pattern carries NO ``FeatureRef``: it operates on the implicit
    single body chain that exists at its point in the tree (design §7.6), so its
    dependency on the prior body-affecting feature is tree order, not a reference.
    See the module-level DESIGN DECISION note for the v1 "pattern the whole body +
    union" semantics and its stated limitations.

    ``scope`` (v2, docs/design/pattern-scope.md) states WHAT is repeated — the whole
    ``body`` (the reading above, kept verbatim) or an explicit selection of
    ``features``, which DOES materialise ``feature_dependencies``. It defaults to
    ``body`` and a persisted params blob with no ``scope`` key reads as ``body``
    (:meth:`_legacy_body_scope`), so every pattern authored before v2 evaluates on
    unchanged code.
    """

    pattern: PatternGeometry = Field(
        description="Linear or circular pattern geometry (discriminated on `kind`)"
    )
    scope: PatternScope = Field(
        default_factory=PatternBodyScope,
        description="WHAT to repeat (discriminated on `kind`): `body` repeats the "
        "current body (the v1 reading — cut-aware, with the vacuous-cut fallback), "
        "`features` places the recorded tool solids of an explicit tree-ordered "
        "selection and re-applies each feature's own boolean. Absent reads `body`, "
        "so pre-v2 patterns are unchanged (design §2.1).",
        json_schema_extra=_drop_schema_default,
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_body_scope(cls, data: Any) -> Any:
        """Read a scope-less (or explicitly null) params blob as the ``body`` scope.

        The v2 additive migration (design §2.1), the SAME idiom
        :meth:`MirrorParamsV1._legacy_body_scope` uses: params persisted before
        ``scope`` existed carry only ``{pattern}``, so normalising the missing key to
        ``{"kind": "body"}`` keeps them valid with NO stored-shape change and NO
        ``param_version`` bump. ``scope: null`` is normalised too, so a client that
        round-trips an omitted optional as an explicit null is not a 422.
        """
        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, Any]", data)
        if fields.get("scope") is not None:
            return fields
        return {**fields, "scope": {"kind": "body"}}


# --- Mirror params — reflect the current body about a plane + union it -----------
#
# The reflective sibling of the pattern feature (a daily verb in every incumbent):
# where a pattern REPLICATES the current body along world-space vectors, a mirror
# REFLECTS it about a plane and BOOLEAN-UNIONS the reflection into the single body
# chain (design §7.6, option B — the SAME "replicate the current body + union"
# semantics). Like a pattern it carries NO source `FeatureRef`: it mirrors the
# implicit body chain that exists at its point in the tree, so its dependency on
# the prior body-affecting feature is tree order.
#
# The mirror PLANE reuses the EXISTING :data:`GeomRef` plane vocabulary (CLAUDE.md
# DRY rule — no new plane taxonomy): a :class:`DatumPlaneRef` names one of the
# three origin datums (XY/XZ/YZ), or a :class:`FeatureRef` points at an earlier
# `datum` feature (an offset / on-face / midplane plane). That is EXACTLY the
# `plane` a sketch resolves, so the geometry service reuses `resolve_sketch_plane`
# unchanged. A `DatumPlaneRef` names a world plane (no reference edge — like a
# pattern's world vectors, independent of topological naming #1); a `FeatureRef`
# to a `datum` DOES materialise into feature_dependencies (deleting that datum is a
# 409-with-dependents), the SAME reference a sketch-plane FeatureRef creates.
#
# UNLIKE a pattern, a mirror does NOT force one connected lump: the reflection of a
# body that CLEARS the plane is a legitimately DISJOINT second lump (a 2V two-lump
# body — multi-body parts are supported, §MB-0); an OVERLAPPING reflection merges
# to one solid; a SYMMETRIC body's reflection coincides and leaves the body
# unchanged. All mirror geometry validity lives at rebuild in
# `geometry.kernel.mirror`, surfacing as `mirror_failed` (a degenerate/failed
# reflection) or `no_target_body` (no prior body) / `reference_unresolved` (the
# plane names a missing/later/non-datum feature) under the strict-prefix rule.
#
# v2 — THE SCOPE (docs/design/mirror-semantics.md, 2026-07-29). The v1 contract is
# ONE field (`plane`) and the semantic is INFERRED from the body chain; §1 of that
# design proves with three measured numbers that no inference rule can be right for
# every chain, because three legitimate intents map onto the SAME tree shape and
# demand three different volumes (30629.3807 / 29600.0 / 28800.0). The ambiguity is
# in the INPUT, so `scope` removes it there: a `kind`-discriminated union with
# exactly two members — `body` (the v1 reading, now NAMED) and `features` (an
# explicit, non-empty, TREE-ORDERED selection). This is what SolidWorks ("Features
# to Mirror"), Fusion (Mirror → Type: Features) and Onshape all do.
#
# Additive under feature-tree §1.4 (`param_version` stays 1): a persisted mirror
# with no `scope` key normalises to `{"kind": "body"}` through
# :meth:`MirrorParamsV1._legacy_body_scope` — the SAME before-validator idiom
# `DatumFeature._legacy_offset_kind` uses for legacy kind-less datum params — so
# every existing row and every shipped golden validates AND evaluates on the
# unchanged v1 code path. There is deliberately NO automatic "mirror everything up
# to here" default (§3.3: the natural spelling of "everything" returns 28800.0 on a
# chain that LOCKS 29600.0).


class MirrorBodyScope(BaseModel):
    """``scope: {"kind": "body"}`` — reflect the CURRENT BODY (the v1 reading).

    The v1 semantic, NAMED rather than implied (design §3.1): the mirror reflects
    the body that exists at its point in the tree, cut-aware — when the active body
    carries a recorded cut whose reflected tool still reaches it the mirror reflects
    that REMOVAL, otherwise it reflects and unions the whole body. Kept verbatim
    (§6.1): the shipped goldens' byte identity is STRUCTURAL, not measured, because
    this scope dispatches to code the v2 work did not touch.
    """

    kind: Literal["body"] = "body"


class MirrorFeaturesScope(BaseModel):
    """``scope: {"kind": "features", "features": [...]}`` — reflect these features.

    The v2 reading (design §2b/§4): each selected feature's RECORDED RIGID TOOL
    SOLID(S) are reflected about the plane and that feature's OWN operation
    (``fuse``/``cut``) is re-applied to the active body, in TREE order — never array
    order (§8.1: array order is UI-incidental, so honouring it would make identical
    models tessellate to different bytes). Parameters are never re-derived: a
    reflected circular pattern is correct precisely because its PLACEMENTS are
    reflected, where re-deriving the axis would wind the ring backwards (§4.5).

    ``features`` names :class:`FeatureRef`s rather than bare UUIDs so each selection
    materialises into ``feature_dependencies`` for free (feature-tree §2.3): deleting
    a mirrored feature is a 409-with-dependents, a reorder re-checks the
    strict-backward rule, and a forward/self reference is a write-time 422. A
    non-body-affecting or non-reflectable kind (``sketch``/``datum``, and every
    MODIFIER — fillet/chamfer/shell/draft and the sheet-metal family, which have a
    RESULT and no tool, §4.3) is refused with the typed per-feature
    ``mirror_feature_unsupported`` at rebuild.

    ``min_length=1`` because an empty selection is authoring nonsense, not a no-op
    mirror (§3.1), and duplicate ids are a 422 rather than silently deduplicated —
    naming a feature twice leaves the intent (twice? once?) unstated, which is the
    mistake v1 made.
    """

    kind: Literal["features"]
    features: list[FeatureRef] = Field(
        min_length=1,
        max_length=MAX_MIRROR_SCOPE_FEATURES,
        description="The features to reflect, each a `FeatureRef` to an earlier "
        "body-affecting feature of this tree. Applied in TREE order (the array "
        "order is ignored — design §8.1); at least one, at most "
        "MAX_MIRROR_SCOPE_FEATURES (work bound); duplicates are a 422.",
    )

    @model_validator(mode="after")
    def _reject_duplicate_features(self) -> Self:
        """Duplicate selected ids are a 422 (design §8.1), never deduplicated."""
        seen: set[uuid.UUID] = set()
        for ref in self.features:
            if ref.feature_id in seen:
                raise ValueError(
                    f"Mirror scope names feature {ref.feature_id} more than once; "
                    "a feature is reflected exactly once, so a duplicate leaves "
                    "the intent unstated. Remove the repeat."
                )
            seen.add(ref.feature_id)
        return self


#: The mirror's SCOPE union (design §3.1), discriminated on ``kind``: `body` (v1)
#: or `features` (v2). A discriminated union rather than
#: ``features: list[FeatureRef] | None`` deliberately — ``None`` and "mirror the
#: body" would be two spellings of one meaning, the exact smell that made v1's
#: semantic implicit. A future third reading (``kind: "bodies"``, multi-body
#: selection) joins additively with no ``param_version`` bump.
MirrorScope = Annotated[
    MirrorBodyScope | MirrorFeaturesScope, Field(discriminator="kind")
]


class MirrorParamsV1(BaseModel):
    """Reflect the current body about a plane and union the reflection in.

    The mirror feature (BACKLOG P2): a whole-body reflection about ``plane``,
    boolean-unioned into the single body chain (design §7.6) — the reflective
    sibling of the ADD pattern (see the module note for the shared "replicate the
    current body + union" semantics). Like a fillet/chamfer/pattern it carries NO
    source ``FeatureRef``: it mirrors the implicit body chain that exists at its
    point in the tree, so its dependency on the prior body-affecting feature is
    tree order.

    ``plane`` is a :data:`GeomRef` — the SAME plane reference a sketch uses (no
    new plane taxonomy, DRY): a :class:`DatumPlaneRef` (an origin datum XY/XZ/YZ)
    or a :class:`FeatureRef` to an earlier ``datum`` feature (an offset / on-face
    / midplane plane). A ``FeatureRef`` that does not resolve to a ``datum`` of
    this prefix is a write-time 422 (the eval-time backstop is
    ``reference_unresolved``, pinned to the referenced feature).

    The reflection is a true handedness-reversing isometry, NOT a translation
    (proven by the ``mirror-triangle-prism-2x`` golden). It handles every case
    sanely: a body that CLEARS the plane mirrors to a disjoint TWO-lump body
    (volume ``2V``); an OVERLAPPING reflection merges to one solid; a SYMMETRIC
    body is unchanged. A degenerate/failed reflection is a per-feature
    ``mirror_failed`` rebuild error; a mirror with no prior body is
    ``no_target_body`` — never a silently wrong body.

    ``scope`` (v2, design §3) states WHAT is reflected — the whole ``body`` (the
    reading above, kept verbatim) or an explicit selection of ``features``. It
    defaults to ``body`` and a persisted params blob with no ``scope`` key reads as
    ``body`` (:meth:`_legacy_body_scope`), so every mirror authored before v2
    evaluates on unchanged code.
    """

    plane: GeomRef = Field(
        description="Mirror plane — an origin datum (XY/XZ/YZ `DatumPlaneRef`) or "
        "an earlier `datum` feature (`FeatureRef`); the SAME plane vocabulary a "
        "sketch uses (discriminated on `kind`)"
    )
    scope: MirrorScope = Field(
        default_factory=MirrorBodyScope,
        description="WHAT to reflect (discriminated on `kind`): `body` reflects the "
        "current body (the v1 reading — cut-aware, with the reflect-and-union "
        "fallback), `features` reflects the recorded tool solids of an explicit "
        "tree-ordered selection and re-applies each feature's own boolean. Absent "
        "reads `body`, so pre-v2 mirrors are unchanged (design §3.2).",
        json_schema_extra=_drop_schema_default,
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_body_scope(cls, data: Any) -> Any:
        """Read a scope-less (or explicitly null) params blob as the ``body`` scope.

        The v2 additive migration (design §3.2), the SAME idiom
        :meth:`DatumFeature._legacy_offset_kind` uses: params persisted before
        ``scope`` existed carry only ``{plane}``, so normalising the missing key to
        ``{"kind": "body"}`` keeps them valid with NO stored-shape change and NO
        ``param_version`` bump. ``scope: null`` is normalised too, so a client that
        round-trips an omitted optional as an explicit null is not a 422.
        """
        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, Any]", data)
        if fields.get("scope") is not None:
            return fields
        return {**fields, "scope": {"kind": "body"}}


# --- Import params — bring an external STEP part in as the base body ------------
#
# DESIGN DECISION (v1, docs/design/step-import.md): an `import` feature is a
# BODY-AFFECTING BASE feature — like the first extrude it does not modify a prior
# body, it SETS the part's single body chain (§7.6) to the imported solid, and
# every later feature (fillet, cut, shell, sketch-on-face) then operates on that
# body with no new machinery. v1 carries the STEP AP214 part-21 text INLINE
# (option 2b — self-contained, no new storage dependency), bounded hard by
# MAX_INLINE_STEP_CHARS. The `kind` SOURCE discriminator seeds the additive
# migration to a content-addressed blob reference (§2a: a `kind: "blob"` member
# joins with NO param_version bump — the RevolveAxis/DatumParams idiom), and the
# `format` discriminator seeds IGES (a future `format: "iges"` literal). Import
# carries no picked geometry and no FeatureRef — its body is a pure function of
# its own params — so it materializes no feature_dependencies edge (like an
# offset datum), yet it IS body-affecting, so a later SubshapeRef may name a face
# or edge of the imported body ("sketch on an imported part's face").


class ImportParamsV1(BaseModel):
    """Bring an external STEP solid in as the part's base body (v1, inline).

    ``data`` is the STEP AP214 part-21 TEXT inline (docs/design/step-import.md
    §2b), bounded by :data:`MAX_INLINE_STEP_CHARS` — an oversize or empty payload
    is a request-validation 422 at the boundary (§6), never a per-feature rebuild
    error. The geometry service reads it deterministically through a pinned
    ``STEPControl_Reader`` (units pinned to mm, RESEARCH §9): the same bytes yield
    a byte-identical body/mesh across rebuilds and interpreter restarts.

    A file with ONE solid becomes a bare solid body; a file with TWO OR MORE
    solids becomes ONE multi-lump body — a lump-sorted compound of its disjoint
    solids (docs/design/multi-body.md §MB-4), not several bodies. STEP import is
    not a boolean: the file's solids are preserved AS AUTHORED (touching or
    overlapping solids are kept as separate lumps, never silently fused). Only a
    file that yields ZERO solids (open shells / surfaces-only / wireframe) is an
    honest ``import_no_solid`` rebuild error whose message carries the shape
    stats, and unparseable bytes are ``import_parse_failed`` (§5). Sewing/repair,
    IGES, and a positioned insert against an existing body are deferred (§7).

    ``kind``/``format`` default so a future blob-ref source (§2a) and IGES join
    additively with no ``param_version`` bump.
    """

    kind: Literal["inline"] = "inline"
    format: Literal["step"] = "step"
    data: str = Field(
        min_length=1,
        max_length=MAX_INLINE_STEP_CHARS,
        description="STEP AP214 part-21 file text (inline). Bounded/non-empty at "
        "parse time (422); parsed to one or more solids by the geometry service "
        "(multi-solid → one multi-lump body, MB-4b; 0 solids → import_no_solid).",
    )


# --- Boolean params — a boolean between two independently-built bodies -----------
#
# The headline multi-body feature (docs/design/multi-body.md §Decisions-3 / §MB-1):
# a boolean between two bodies built independently (each with its own base
# feature), where MB-0's `merge=False` seam let a part hold more than one lump.
# The operands are `FeatureRef`s to each body's BASE feature — the id that keys a
# body in `EvaluationState.bodies` (§MB-0 Decision 1: a body's identity IS its
# base-feature id) — so each materializes a `feature_dependencies` edge exactly
# like any other FeatureRef (generic documents validation then handles delete/
# reorder safety, no documents code change). The result REPLACES both operands,
# taking over the target's identity slot (keeps target's base id so downstream
# refs resolve) and removing the tool body; it becomes the active body.
#
# OPERATION SCOPE (MB-1a decision, recorded here): the `operation` Literal names
# all three OCCT booleans (`union` = BRepAlgoAPI_Fuse, `subtract` =
# BRepAlgoAPI_Cut, `intersect` = BRepAlgoAPI_Common) so the schema — and the
# generated ts-client type — is STABLE across the MB-2 slice that wires subtract/
# intersect (no `param_version` bump, no client type churn then). This slice
# (MB-1a) WIRES `union` only; the geometry evaluator returns an honest per-feature
# `boolean_not_implemented` for `subtract`/`intersect` until MB-2, never a silent
# wrong body. v1 keeps the single-connected-solid-per-body invariant (§Decisions-3):
# a union of DISJOINT (non-touching) bodies is a `boolean_disjoint` rebuild error
# (multi-lump compound bodies are deferred to MB-4), which is exactly why the
# body set stays a `Solid` per body, never a `Compound`.


class BooleanParamsV1(BaseModel):
    """A boolean between two independently-built bodies (design §Decisions-3).

    ``target`` and ``tool`` are :class:`FeatureRef`s to the BASE feature of each
    operand body (an ``extrude``/``revolve``/``sweep``/``loft``/``import`` — the
    body-CREATING features, NOT a modifier like fillet). ``target`` is the
    SURVIVING body (for ``subtract``, the minuend); ``tool`` is the CONSUMED body
    (the subtrahend). The boolean result takes over the target's identity slot and
    the tool body is removed from the part.

    All three operations are wired (union MB-1a; subtract/intersect MB-2). By
    DEFAULT the v1 single-connected-solid-per-body invariant (§Decisions-3)
    governs the result: a union of non-touching bodies, or a subtract that SEVERS
    the target into ≥2 pieces, is a ``boolean_disjoint`` rebuild error; a subtract
    that removes the whole target, or an intersect with no overlap, is
    ``boolean_empty``.

    MULTI-LUMP BODIES ARE OPT-IN (MB-4 / design §MB-4). Set ``allow_disjoint`` to
    accept a ``>1``-solid result as ONE multi-lump body — a :class:`Compound` of
    the disjoint lumps kept under the target's identity slot (a genuine
    "combine into one body" of, say, two non-touching bosses). It defaults
    ``False`` because a disjoint union is USUALLY a positioning bug, not an
    intent, so v1 keeps the safety error unless the author explicitly opts in.
    An EMPTY result is still ``boolean_empty`` / ``BooleanError`` regardless of
    the flag (there is no material to keep). The flag is additive-optional
    (absent reads ``False`` — the ``merge`` / ``flip`` idiom, NO ``param_version``
    bump).

    v1 MULTI-LUMP LIMIT — coincident lumps are honestly ambiguous
    (design §MB-4, stated plainly): a downstream picked-face/edge reference on a
    multi-lump body resolves by ABSOLUTE-world-coordinate signature, so a lump at
    a distinct position resolves to exactly one subshape. But two lumps that
    truly COINCIDE in space (a self-union of congruent bodies) give congruent
    signatures and resolve to an honest ``subshape_ambiguous`` — the resolver
    refuses to guess, never a wrong-lump modification (topological-naming.md §5).

    v1 TOPOLOGICAL-NAMING LIMIT (MB-3 / design §Decisions-4 — stated plainly, not
    oversold): a downstream feature (fillet/chamfer) CAN name an edge/face CREATED
    by a boolean — the fused body's subshapes get stage-1 signatures like any
    primitive's, so a fillet on a boolean-result edge resolves to exactly one edge
    on a CLEAN rebuild. But that reference is a best-effort stage-1 signature (see
    :class:`SubshapeRef` / :class:`EdgeSubshapeRef`), NOT structurally
    non-retargeting: a topology-CHANGING upstream edit that moves or removes the
    referenced subshape degrades to an honest ``subshape_unresolved`` /
    ``subshape_ambiguous`` — the SAME best-effort posture as every feature,
    booleans being its weakest case (a boolean seam is the documented
    ``subshape_ambiguous`` source). Never a wrong-edge modification or a crash;
    the structural fix is stage-2 provenance naming (topological-naming.md §10).
    """

    operation: Literal["union", "subtract", "intersect"] = Field(
        description="Boolean operation: union (fuse), subtract (target minus tool) "
        "or intersect (common). All three wired (union MB-1a; subtract/intersect "
        "MB-2)."
    )
    target: FeatureRef = Field(
        description="Base feature of the SURVIVING body; the result takes over "
        "its identity slot so downstream refs keep resolving (design §Decisions-3)"
    )
    tool: FeatureRef = Field(
        description="Base feature of the CONSUMED body; removed from the part "
        "once the boolean succeeds (design §Decisions-3)"
    )
    allow_disjoint: bool = Field(
        default=False,
        description="Accept a >1-solid result as ONE multi-lump body (a Compound "
        "of the disjoint lumps) instead of a `boolean_disjoint` error (MB-4). "
        "Defaults False (a disjoint union is usually a positioning bug). An empty "
        "result is still `boolean_empty`. Additive — absent reads False, no "
        "param_version bump.",
    )


# --- §1.3 Versioned envelopes ----------------------------------------------------


class FeatureEnvelopeBase(BaseModel):
    """Envelope fields EVERY feature type carries besides its typed ``params``.

    ``suppressed`` is the persisted feature-suppress flag (BACKLOG "Feature
    suppress"; docs/design/feature-tree.md §4.3a): when ``True`` a tree rebuild
    SKIPS this feature — the body is built from the non-suppressed prefix and
    each later non-suppressed feature evaluates off the last non-suppressed
    body. It lives on the ENVELOPE, not inside ``params``, because it is
    orthogonal to every feature type (a rebuild flag, not a modeling parameter):
    it does NOT change ``BODY_AFFECTING_FEATURE_TYPES``, never forces a
    ``param_version`` bump, and defaults ``False`` so every existing tree/golden
    validates and evaluates byte-identically. Documents stores it in its own
    column beside ``params`` and passes it back through
    :meth:`FeatureTypeRegistry.load`; ``expressions`` (PART-PARAMETERS) is
    stored and read back the same way, and is left out of a dump while null.

    ``suppressed`` is a normal, always-serialized field. It is NOT hidden
    behind a model serializer — a ``@model_serializer`` on this base perturbs
    pydantic's schema generation for the per-type discriminated ``params``
    unions (they collapse to an untyped ``Params``), which would break the
    generated ts-client. The generated CLIENT type is kept OPTIONAL
    (``suppressed?: boolean``) purely by dropping the JSON-schema ``default``
    (:func:`_drop_schema_default`), so existing web callers that omit it still
    compile.
    """

    suppressed: bool = Field(
        default=False,
        description=(
            "Feature suppress flag: when True a tree rebuild SKIPS this feature "
            "and downstream features rebuild off the last non-suppressed body "
            "(BACKLOG feature suppress). Additive-optional — absent reads False, "
            "no param_version bump."
        ),
        json_schema_extra=_drop_schema_default,
    )
    expressions: FeatureExpressions = EXPRESSIONS_FIELD

    @model_validator(mode="after")
    def _expressions_hit_numbers(self) -> Self:
        if self.expressions is not None:
            params = cast(BaseModel, getattr(self, "params"))  # noqa: B009
            check_expressions(params.model_dump(mode="json"), self.expressions)
        return self


class DatumFeature(FeatureEnvelopeBase):
    """``{"type": "datum", "version": 1, "params": {...}}`` envelope.

    A non-body-affecting feature that produces a plane a later sketch sits on
    (docs/design/datum-planes.md §2b). ``params`` is the discriminated
    :data:`DatumParams` union — an ``offset`` plane (§3), an ``on_face`` plane
    (§7), an ``offset_from`` chained plane, a ``midplane`` (§7a), or a plane
    at an ``angle`` about a line (:mod:`loft_wire.datum_angle`). Every
    variant after ``offset`` is ADDITIVE with NO ``param_version`` bump: legacy
    offset params (persisted before ``on_face`` existed) carry no ``kind``
    discriminator, so :meth:`_legacy_offset_kind` injects ``"offset"`` before
    validation and every existing datum row/golden validates unchanged
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


class SketchFeature(FeatureEnvelopeBase):
    """``{"type": "sketch", "version": 1, "params": {...}}`` envelope."""

    type: Literal["sketch"]
    version: Literal[1]
    params: SketchParamsV1


class ExtrudeFeature(FeatureEnvelopeBase):
    """``{"type": "extrude", "version": 1, "params": {...}}`` envelope."""

    type: Literal["extrude"]
    version: Literal[1]
    params: ExtrudeParamsV1


class RevolveFeature(FeatureEnvelopeBase):
    """``{"type": "revolve", "version": 1, "params": {...}}`` envelope."""

    type: Literal["revolve"]
    version: Literal[1]
    params: RevolveParamsV1


class SweepFeature(FeatureEnvelopeBase):
    """``{"type": "sweep", "version": 1, "params": {...}}`` envelope."""

    type: Literal["sweep"]
    version: Literal[1]
    params: SweepParamsV1


class PipeFeature(FeatureEnvelopeBase):
    """``{"type": "pipe", "version": 1, "params": {...}}`` (:mod:`loft_wire.pipe`)."""

    type: Literal["pipe"]
    version: Literal[1]
    params: PipeParamsV1


class LoftFeature(FeatureEnvelopeBase):
    """``{"type": "loft", "version": 1, "params": {...}}`` envelope."""

    type: Literal["loft"]
    version: Literal[1]
    params: LoftParamsV1


class FilletFeature(FeatureEnvelopeBase):
    """``{"type": "fillet", "version": 1, "params": {...}}`` envelope."""

    type: Literal["fillet"]
    version: Literal[1]
    params: FilletParamsV1


class ChamferFeature(FeatureEnvelopeBase):
    """``{"type": "chamfer", "version": 1, "params": {...}}`` envelope."""

    type: Literal["chamfer"]
    version: Literal[1]
    params: ChamferParamsV1


class ShellFeature(FeatureEnvelopeBase):
    """``{"type": "shell", "version": 1, "params": {...}}`` envelope."""

    type: Literal["shell"]
    version: Literal[1]
    params: ShellParamsV1


class DraftFeature(FeatureEnvelopeBase):
    """``{"type": "draft", "version": 1, "params": {...}}`` envelope."""

    type: Literal["draft"]
    version: Literal[1]
    params: DraftParamsV1


class HoleFeature(FeatureEnvelopeBase):
    """``{"type": "hole", "version": 1, "params": {...}}`` envelope.

    A body-MODIFYING feature (design §7.6): it drills a cylinder into the current
    body at a point on a picked planar face (through-all or blind). ``params`` is
    :class:`HoleParamsV1`.
    """

    type: Literal["hole"]
    version: Literal[1]
    params: HoleParamsV1


class PatternFeature(FeatureEnvelopeBase):
    """``{"type": "pattern", "version": 1, "params": {...}}`` envelope."""

    type: Literal["pattern"]
    version: Literal[1]
    params: PatternParamsV1


class MirrorFeature(FeatureEnvelopeBase):
    """``{"type": "mirror", "version": 1, "params": {...}}`` envelope.

    A body-affecting feature (design §7.6): it reflects the current body about a
    plane and boolean-unions the reflection into the single body chain — the
    reflective sibling of :class:`PatternFeature`. ``params`` is
    :class:`MirrorParamsV1`.
    """

    type: Literal["mirror"]
    version: Literal[1]
    params: MirrorParamsV1


class ImportFeature(FeatureEnvelopeBase):
    """``{"type": "import", "version": 1, "params": {...}}`` envelope.

    A body-affecting BASE feature (docs/design/step-import.md §1): it produces
    the imported solid as the part's base body, rather than modifying a prior
    one. ``params`` is :class:`ImportParamsV1` (inline STEP text in v1).
    """

    type: Literal["import"]
    version: Literal[1]
    params: ImportParamsV1


class SheetMetalBaseFlangeFeature(FeatureEnvelopeBase):
    """``{"type": "sheet_metal_base_flange", "version": 1, "params": {...}}`` envelope.

    A body-CREATING base feature (docs/design/sheet-metal.md §4.1): it thickens a
    profile to gauge, producing the sheet-metal part's first body, and anchors the
    part's sheet-metal defaults (``k_factor``/``bend_radius_mm``). ``params`` is
    :class:`SheetMetalBaseFlangeParamsV1`.
    """

    type: Literal["sheet_metal_base_flange"]
    version: Literal[1]
    params: SheetMetalBaseFlangeParamsV1


class SheetMetalEdgeFlangeFeature(FeatureEnvelopeBase):
    """``{"type": "sheet_metal_edge_flange", "version": 1, "params": {...}}`` envelope.

    A body-MODIFYING feature (docs/design/sheet-metal.md §4.2): it folds a flange
    off a straight edge of the sheet body and fuses it across a cylindrical bend
    region, tagging that bend face with a :class:`CylindricalFaceSignature` (§5)
    for the unfold's provenance. ``params`` is :class:`SheetMetalEdgeFlangeParamsV1`.
    """

    type: Literal["sheet_metal_edge_flange"]
    version: Literal[1]
    params: SheetMetalEdgeFlangeParamsV1


class SheetMetalHemFeature(FeatureEnvelopeBase):
    """``{"type": "sheet_metal_hem", "version": 1, "params": {...}}`` envelope.

    A body-MODIFYING feature (parity §2, closed hem): it folds the picked edge ~180
    deg back onto the sheet (reusing the edge flange's bend machinery at a fixed 180
    deg fold), fusing one clean solid, and tags the bend face with a
    :class:`CylindricalFaceSignature` (§5) for the unfold's provenance — exactly as
    an edge flange does. ``params`` is :class:`SheetMetalHemParamsV1`.
    """

    type: Literal["sheet_metal_hem"]
    version: Literal[1]
    params: SheetMetalHemParamsV1


class SheetMetalCornerReliefFeature(FeatureEnvelopeBase):
    """``{"type": "sheet_metal_corner_relief", "version": 1, "params": {...}}``.

    A body-affecting feature (sheet-metal.md §4.4) that cuts a rectangular notch at
    the shared corner of two adjacent edge flanges and — via the analytic relieved
    unfold — makes that corner develop into a single non-overlapping flat blank. It
    names the two bends by :class:`FeatureRef` (the edge-flange features that created
    them); the evaluator resolves each to its recorded
    :class:`CylindricalFaceSignature` (§5) to drive both relief halves. ``params`` is
    :class:`SheetMetalCornerReliefParamsV1`.
    """

    type: Literal["sheet_metal_corner_relief"]
    version: Literal[1]
    params: SheetMetalCornerReliefParamsV1


class BooleanFeature(FeatureEnvelopeBase):
    """``{"type": "boolean", "version": 1, "params": {...}}`` envelope.

    A body-affecting feature that fuses two independently-built bodies
    (docs/design/multi-body.md §Decisions-3 / §MB-1): unlike extrude/revolve/…
    it consumes no sketch and produces no new primitive — it combines two
    existing bodies named by their base features. ``params`` is
    :class:`BooleanParamsV1` (``union`` wired in MB-1a; ``subtract``/``intersect``
    defined, wired in MB-2).
    """

    type: Literal["boolean"]
    version: Literal[1]
    params: BooleanParamsV1


#: Discriminated union of the CURRENT version of every feature type — this is
#: what the OpenAPI contract exports (design §1.4). Older stored versions are
#: upcast on read via :data:`FEATURE_REGISTRY`.
Feature = Annotated[
    DatumFeature
    | SketchFeature
    | ExtrudeFeature
    | RevolveFeature
    | SweepFeature
    | PipeFeature
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | ShellFeature
    | DraftFeature
    | HoleFeature
    | PatternFeature
    | MirrorFeature
    | ImportFeature
    | SheetMetalBaseFlangeFeature
    | SheetMetalEdgeFlangeFeature
    | SheetMetalHemFeature
    | SheetMetalCornerReliefFeature
    | BooleanFeature,
    Field(discriminator="type"),
]

#: Plain (non-annotated) union alias for type annotations of validated values.
FeatureEnvelope = (
    DatumFeature
    | SketchFeature
    | ExtrudeFeature
    | RevolveFeature
    | SweepFeature
    | PipeFeature
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | ShellFeature
    | DraftFeature
    | HoleFeature
    | PatternFeature
    | MirrorFeature
    | ImportFeature
    | SheetMetalBaseFlangeFeature
    | SheetMetalEdgeFlangeFeature
    | SheetMetalHemFeature
    | SheetMetalCornerReliefFeature
    | BooleanFeature
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

    def models(self) -> Mapping[str, type[ModelT]]:
        """Every registered ``type`` → its CURRENT envelope model (read-only view).

        Exposed so a GATE can enumerate the shipped feature vocabulary instead of
        hand-listing it. The geometry composition matrix's coverage audit
        (``test_pair_matrix_covers_every_shipped_verb``) derives its required rows
        from here, so a new body-affecting verb — in particular a new CUT verb —
        cannot ship without a matrix row or an explicitly-reasoned exemption
        (docs/GEOMETRY-QA.md 2026-07-30: a hand-listed axis is exactly how
        revolve/sweep/loft cuts stayed invisible to the matrix). Read-only: the
        registry stays the only mutator of its own tables.
        """
        return MappingProxyType(self._models)

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

    def load(
        self,
        feature_type: str,
        version: int,
        params: JsonObject,
        *,
        suppressed: bool = False,
        expressions: dict[str, str] | None = None,
    ) -> ModelT:
        """Stored columns → current-version validated envelope (read path).

        Design §1.4 mapping-to-JSONB rule: columns → envelope dict → upcast if
        needed → validate. The rest of the system only ever sees
        current-version params.

        ``suppressed`` and ``expressions`` are ENVELOPE-level: documents stores
        each in its own column and passes it BACK here on every read path.
        """
        current = self.current_version(feature_type)
        upcast = self.upcast_params(feature_type, version, params)
        return self._models[feature_type].model_validate(
            {
                "type": feature_type,
                "version": current,
                "params": upcast,
                "suppressed": suppressed,
                "expressions": expressions,
            }
        )


#: The module-level registry — sketch + extrude, both at v1.
FEATURE_REGISTRY: FeatureTypeRegistry[FeatureEnvelope] = FeatureTypeRegistry()
FEATURE_REGISTRY.register(DatumFeature)
FEATURE_REGISTRY.register(SketchFeature)
FEATURE_REGISTRY.register(ExtrudeFeature)
FEATURE_REGISTRY.register(RevolveFeature)
FEATURE_REGISTRY.register(SweepFeature)
FEATURE_REGISTRY.register(PipeFeature)
FEATURE_REGISTRY.register(LoftFeature)
FEATURE_REGISTRY.register(FilletFeature)
FEATURE_REGISTRY.register(ChamferFeature)
FEATURE_REGISTRY.register(ShellFeature)
FEATURE_REGISTRY.register(DraftFeature)
FEATURE_REGISTRY.register(HoleFeature)
FEATURE_REGISTRY.register(PatternFeature)
FEATURE_REGISTRY.register(MirrorFeature)
FEATURE_REGISTRY.register(ImportFeature)
FEATURE_REGISTRY.register(SheetMetalBaseFlangeFeature)
FEATURE_REGISTRY.register(SheetMetalEdgeFlangeFeature)
FEATURE_REGISTRY.register(SheetMetalHemFeature)
FEATURE_REGISTRY.register(SheetMetalCornerReliefFeature)
FEATURE_REGISTRY.register(BooleanFeature)
FEATURE_REGISTRY.validate_chains()


# --- Custom features (PLUGIN-REGISTRY, RESEARCH §23; manifests: loft_wire.plugins) --


class ExpandedMember(BaseModel):
    """One base feature a custom feature expanded to, as stored with it."""

    role: RoleName = Field(description="The manifest role this member takes.")
    index: int = Field(ge=0, lt=MAX_PLUGIN_EXPANSION, description="n within role.")
    name: MemberNameField = None
    id: uuid.UUID = Field(
        description="loft_wire.plugins.member_id(<feature-id>, role, index, name): "
        "the stable id geometry builds, results and picks name this member by."
    )
    feature: Feature
    metadata: MemberMetadata | None = Field(default=None, exclude_if=_is_none)

    @model_validator(mode="after")
    def _numbers_only(self) -> Self:
        if self.feature.expressions is not None or self.feature.suppressed:
            raise ValueError("a generated member carries no formulas or suppression")
        return self


class CustomParamsV1(BaseModel):
    """A custom feature: the plugin it is pinned to, its inputs, and the last
    expansion. Documents expands it on every write and evaluation; geometry
    only receives base features (RESEARCH §23). A server without the plugin
    (or the pinned version) rebuilds the stored expansion, read-only."""

    plugin_id: PluginId
    plugin_version: SemVer = Field(
        description="The pinned plugin version; updating it is an explicit edit."
    )
    inputs: dict[InputName, CustomInputValue] = Field(
        max_length=MAX_PLUGIN_INPUTS,
        description="Input name -> value, validated against the pinned manifest.",
    )
    expansion: list[ExpandedMember] | None = Field(
        default=None,
        max_length=MAX_PLUGIN_EXPANSION,
        exclude_if=_is_none,
        description="The last expansion, written by documents; a request may omit it.",
    )

    @model_validator(mode="after")
    def _members_unique(self) -> Self:
        keys = [(member.role, member.index) for member in self.expansion or []]
        if len(set(keys)) != len(keys):
            raise ValueError("expansion repeats a (role, index)")
        return self


class CustomFeature(FeatureEnvelopeBase):
    """``{"type": "custom", "version": 1, "params": {...}}``: a plugin's feature.

    Authored and stored like any feature, but NOT in :data:`Feature`: it never
    reaches geometry, which receives its expansion instead. Formulas drive
    numeric inputs only (``/inputs/<name>``)."""

    type: Literal["custom"]
    version: Literal[1]
    params: CustomParamsV1

    @model_validator(mode="after")
    def _formulas_drive_inputs(self) -> Self:
        for pointer in self.expressions or {}:
            if not pointer.startswith("/inputs/"):
                raise ValueError(f"expressions[{pointer!r}]: only inputs are driven")
        return self


#: What a client authors and documents stores: a base feature or a custom one.
AuthoredFeature = Annotated[
    DatumFeature
    | SketchFeature
    | ExtrudeFeature
    | RevolveFeature
    | SweepFeature
    | PipeFeature
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | ShellFeature
    | DraftFeature
    | HoleFeature
    | PatternFeature
    | MirrorFeature
    | ImportFeature
    | SheetMetalBaseFlangeFeature
    | SheetMetalEdgeFlangeFeature
    | SheetMetalHemFeature
    | SheetMetalCornerReliefFeature
    | BooleanFeature
    | CustomFeature,
    Field(discriminator="type"),
]
AuthoredEnvelope = FeatureEnvelope | CustomFeature


class AuthoredFeatureRegistry:
    """:data:`FEATURE_REGISTRY` plus the custom feature: the stored vocabulary.

    Delegates every base type (and so every upcast registered there), and owns
    ``custom`` itself, so geometry's registry never learns plugins exist."""

    def current_version(self, feature_type: str) -> int:
        if feature_type == "custom":
            return 1
        return FEATURE_REGISTRY.current_version(feature_type)

    def upcast_params(
        self, feature_type: str, version: int, params: JsonObject
    ) -> JsonObject:
        if feature_type != "custom":
            return FEATURE_REGISTRY.upcast_params(feature_type, version, params)
        if version != 1:
            raise UnknownFeatureVersionError(f"'custom' params at v{version}")
        return params

    def load(
        self,
        feature_type: str,
        version: int,
        params: JsonObject,
        *,
        suppressed: bool = False,
        expressions: dict[str, str] | None = None,
    ) -> AuthoredEnvelope:
        if feature_type != "custom":
            return FEATURE_REGISTRY.load(
                feature_type,
                version,
                params,
                suppressed=suppressed,
                expressions=expressions,
            )
        return CustomFeature.model_validate(
            {
                "type": "custom",
                "version": 1,
                "params": self.upcast_params(feature_type, version, params),
                "suppressed": suppressed,
                "expressions": expressions,
            }
        )


AUTHORED_FEATURES = AuthoredFeatureRegistry()


# --- §2.2/§2.3 Reference helpers --------------------------------------------------


#: Feature types that produce/mutate the body chain — the acceptable targets of
#: a :class:`SubshapeRef` face reference (topo-naming §4: a face is named on a
#: body-affecting feature's result). ``datum``/``sketch`` are NOT body-affecting.
BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "pipe",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "draft",
        # `hole` drills a cylinder into the body (a body-affecting modifier like
        # fillet/shell/draft), so its result faces/edges are nameable by a later
        # SubshapeRef (a datum on the new bore face, a hole near an earlier hole).
        "hole",
        "pattern",
        # `mirror` reflects the current body about a plane and unions the
        # reflection in (a body-affecting modifier like pattern), so its result
        # faces/edges are nameable by a later SubshapeRef (a hole on a mirrored
        # boss, a sketch on the reflected face).
        "mirror",
        # `import` produces the base body (step-import.md §1), so its faces/edges
        # are nameable by a later SubshapeRef — "sketch on an imported part's face".
        "import",
        # `sheet_metal_base_flange` produces the sheet body (sheet-metal.md §4.1),
        # so its faces/edges are nameable by a later SubshapeRef — a sketch/hole on
        # a flange face (§7), or (slice #3) the edge-flange bend attaches to a base
        # edge. A base flange IS a body-affecting result like any extrude.
        "sheet_metal_base_flange",
        # `sheet_metal_edge_flange` folds a flange onto the sheet body (sheet-metal
        # §4.2), so its result faces/edges are nameable by a later SubshapeRef — a
        # hole on a formed flange face, or a second edge flange off a NEW edge the
        # first created (still a depth-1 star off the base, §4.3).
        "sheet_metal_edge_flange",
        # `sheet_metal_hem` folds a ~180 deg return onto the sheet body (parity §2,
        # closed hem) — the SAME body-affecting result as an edge flange (it reuses
        # `build_edge_flange`), so its faces/edges are nameable by a later
        # SubshapeRef (a hole on the hemmed return, a bend off a new edge).
        "sheet_metal_hem",
        # `sheet_metal_corner_relief` cuts a notch into the sheet body (sheet-metal
        # §4.4) — a body-affecting modifier like fillet/shell — so its result
        # faces/edges are nameable by a later SubshapeRef (a hole near a relieved
        # corner). It never keys a standalone body (no `merge`).
        "sheet_metal_corner_relief",
        # `boolean` produces a combined body (multi-body §Decisions-3), so its
        # result faces/edges are nameable by a later SubshapeRef (a fillet on a
        # boolean seam — MB-3, the honest stage-1-degrade-under-edit case).
        "boolean",
    }
)


#: The body-CREATING (base) feature types — the acceptable target/tool of a
#: `boolean` operand ref (multi-body §Decisions-3: a boolean combines two bodies
#: named by their BASE features). A body's identity is its base-feature id
#: (§MB-0 Decision 1), and only these features CREATE a body (extrude/revolve/
#: sweep/loft build a primitive, import brings one in). The MODIFIERS (fillet/
#: chamfer/shell/draft/pattern) mutate the active body in place and never key a
#: body, so they are NOT valid boolean operands; `boolean` itself is excluded too
#: (it takes over its target's base id, not its own — boolean-on-boolean is MB-4).
BASE_BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {"extrude", "revolve", "sweep", "pipe", "loft", "import", "sheet_metal_base_flange"}
)


#: The named-subshape reference kinds (face + edge) — both carry a graph-joining
#: ``feature_id`` and are yielded WHOLE by the walk (their signature payloads
#: carry no nested refs). A runtime alias so the ``isinstance`` check and the
#: type annotations below cannot drift apart.
AnyRef = FeatureRef | SubshapeRef | EdgeSubshapeRef


def iter_feature_refs(value: Any) -> Iterator[AnyRef]:
    """Every :class:`FeatureRef` / :class:`SubshapeRef` / :class:`EdgeSubshapeRef`
    reachable in a model tree.

    Generic pydantic walk (models, lists, tuples, dict values) so extraction can
    never drift from the schema (design §2.3) — a new ref-bearing field is found
    without touching this function. Every ref kind carries a ``feature_id`` that
    joins the dependency graph; topo-naming §4/§10 widened this walk to yield the
    named face (:class:`SubshapeRef`) AND edge (:class:`EdgeSubshapeRef`)
    references, each yielded WHOLE and not descended into (their only
    graph-relevant field is ``feature_id`` — their signature payloads carry no
    refs).
    """
    if isinstance(value, FeatureRef | SubshapeRef | EdgeSubshapeRef):
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
    is a :class:`FeatureRef` (a whole-feature reference), a :class:`SubshapeRef`
    (a named face — topo-naming §4), or an :class:`EdgeSubshapeRef` (a named edge
    — §10); all expose a ``feature_id`` that documents materializes into
    ``feature_dependencies``.
    """

    slot: str
    ref: AnyRef
    allowed_types: frozenset[str]


def _path_references(path: list[PathSegment]) -> list[FeatureReference]:
    """A pipe's or along-path datum's picked curves: a sketch curve depends on
    its sketch, a model edge on the body-affecting feature it names."""
    return [
        FeatureReference(f"path[{index}]", segment.sketch, frozenset({"sketch"}))
        if isinstance(segment, PathSketchCurve)
        else FeatureReference(f"path[{index}]", segment, BODY_AFFECTING_FEATURE_TYPES)
        for index, segment in enumerate(path)
    ]


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
            # re-checks strict-backward for the named ref too. An OFFSET_FROM
            # datum references its parent `datum` feature (chaining — the slot
            # rule that makes a self/forward/non-datum base a write-time 422).
            # A MIDPLANE side is an origin plane (no ref), an earlier `datum`
            # feature (FeatureRef → {datum}), or a picked planar face
            # (SubshapeRef → body-affecting types, the on_face rule).
            match feature.params:
                case DatumOnFaceParams():
                    references.append(
                        FeatureReference(
                            "face", feature.params.face, BODY_AFFECTING_FEATURE_TYPES
                        )
                    )
                case DatumOffsetFromParams():
                    references.append(
                        FeatureReference(
                            "base", feature.params.base, frozenset({"datum"})
                        )
                    )
                case DatumMidplaneParams():
                    for slot, side in (
                        ("a", feature.params.a),
                        ("b", feature.params.b),
                    ):
                        if isinstance(side, FeatureRef):
                            references.append(
                                FeatureReference(slot, side, frozenset({"datum"}))
                            )
                        elif isinstance(side, SubshapeRef):
                            references.append(
                                FeatureReference(
                                    slot, side, BODY_AFFECTING_FEATURE_TYPES
                                )
                            )
                case DatumAngleParams():
                    # A plane at an angle: its LINE is a sketch line (the
                    # sketch's FeatureRef -> {sketch}), a picked edge
                    # (body-affecting) or an origin axis (no ref); its
                    # REFERENCE takes the midplane side's forms and rules.
                    line = feature.params.line
                    if isinstance(line, DatumSketchLineRef):
                        references.append(
                            FeatureReference("line", line.sketch, frozenset({"sketch"}))
                        )
                    elif isinstance(line, EdgeSubshapeRef):
                        references.append(
                            FeatureReference("line", line, BODY_AFFECTING_FEATURE_TYPES)
                        )
                    side = feature.params.reference
                    if isinstance(side, FeatureRef):
                        references.append(
                            FeatureReference("reference", side, frozenset({"datum"}))
                        )
                    elif isinstance(side, SubshapeRef):
                        references.append(
                            FeatureReference(
                                "reference", side, BODY_AFFECTING_FEATURE_TYPES
                            )
                        )
                case DatumAlongPathParams():
                    references.extend(_path_references([feature.params.path]))
                case DatumOffsetParams():
                    pass
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
            # A projected entity names an edge of an earlier body-affecting
            # feature's result (the picked-fillet rule), an in-context one
            # another part's (no dependency). getattr: model_construct'ed.
            for entity in feature.params.entities:
                link = getattr(entity, "projection", None)
                if isinstance(link, SketchProjection) and link.edge is not None:
                    references.append(
                        FeatureReference(
                            f"projection:{entity.id}",
                            link.edge,
                            BODY_AFFECTING_FEATURE_TYPES,
                        )
                    )
        case ExtrudeFeature() | RevolveFeature():
            # Both take a single sketch profile ref; revolve's axis is either a
            # sketch-LOCAL entity id (a line within that same sketch) or a world
            # origin-axis ENUM — neither is a FeatureRef, so the axis never
            # appears in the FeatureRef walk below and a revolve's only
            # dependency is its profile sketch.
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
        case PipeFeature():
            references.extend(_path_references(feature.params.path))
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
        case FilletFeature() | ChamferFeature():
            # Fillet/chamfer modify the implicit single body chain (design §7.6).
            # A PREDICATE selector (all_edges / axis_parallel) carries no ref —
            # it re-selects edges geometrically each rebuild, its only dependency
            # on the prior body-affecting feature is tree order (as before). A
            # PICKED selector (topo-naming §10) names SPECIFIC edges of a
            # body-affecting feature's result: each EdgeSubshapeRef.feature_id
            # materializes into feature_dependencies exactly like a datum-on-face
            # SubshapeRef, so deleting that body feature is a 409-with-dependents
            # and a reorder re-checks strict-backward for the named edge refs.
            if isinstance(feature.params.edges, PickedEdgesSelector):
                for index, ref in enumerate(feature.params.edges.refs):
                    references.append(
                        FeatureReference(
                            f"edges[{index}]", ref, BODY_AFFECTING_FEATURE_TYPES
                        )
                    )
        case ShellFeature():
            # Shell hollows the implicit single body chain (design §7.6) and
            # names the faces to REMOVE (leave open) as picked faces. Each
            # SubshapeRef.feature_id materializes into feature_dependencies
            # exactly like an on_face datum's face ref, so deleting the
            # referenced body feature is a 409-with-dependents and a reorder
            # re-checks strict-backward for the named face refs. An EMPTY faces
            # list (a sealed hollow) carries no refs — no dependency edge, tree
            # order is its only tie to the prior body-affecting feature.
            for index, ref in enumerate(feature.params.faces.refs):
                references.append(
                    FeatureReference(
                        f"faces[{index}]", ref, BODY_AFFECTING_FEATURE_TYPES
                    )
                )
        case DraftFeature():
            # Draft tapers picked faces of the implicit single body chain (design
            # §7.6) and names them as picked faces (the SAME FaceSelector shell
            # uses). Each SubshapeRef.feature_id materializes into
            # feature_dependencies exactly like a shell opening, so deleting the
            # referenced body feature is a 409-with-dependents and a reorder
            # re-checks strict-backward for the named face refs. The neutral plane
            # is a principal datum (no picked geometry — no ref).
            for index, ref in enumerate(feature.params.faces.refs):
                references.append(
                    FeatureReference(
                        f"faces[{index}]", ref, BODY_AFFECTING_FEATURE_TYPES
                    )
                )
        case HoleFeature():
            # A hole drills the implicit single body chain (design §7.6) at a point
            # on a picked planar FACE. That face is a stage-1 SubshapeRef (the SAME
            # signature the on_face datum / shell openings resolve): its feature_id
            # materialises into feature_dependencies, so deleting the placement
            # face's body feature is a 409-with-dependents and a reorder re-checks
            # strict-backward. diameter/position/depth are scalars, not refs.
            references.append(
                FeatureReference(
                    "face", feature.params.face, BODY_AFFECTING_FEATURE_TYPES
                )
            )
        case PatternFeature():
            # A `body`-scope pattern replicates the implicit body about world-space
            # direction/axis vectors (no picked sub-geometry — independent of #1);
            # its dependency on the prior body-affecting feature is tree order, so
            # it carries no refs.
            #
            # v2 `features` scope (pattern-scope.md §2): each selected feature IS a
            # real dependency — the pattern places that feature's recorded tools —
            # so every ref materialises into feature_dependencies with the
            # BODY-AFFECTING allowed-target rule, exactly as a `features`-scope
            # mirror does. Bought for free at write time: deleting a patterned
            # feature is a 409-with-dependents, a reorder re-checks strict-backward,
            # a forward/self reference is a 422, and a `sketch`/`datum` selection is
            # a 422 long before it could be an evaluation-time
            # `pattern_feature_unsupported`.
            if isinstance(feature.params.scope, PatternFeaturesScope):
                for index, ref in enumerate(feature.params.scope.features):
                    references.append(
                        FeatureReference(
                            f"scope.features[{index}]",
                            ref,
                            BODY_AFFECTING_FEATURE_TYPES,
                        )
                    )
        case MirrorFeature():
            # A mirror reflects the implicit body about a plane and unions it
            # (design §7.6) — no source FeatureRef, tree order is its dependency
            # on the prior body-affecting feature. Its `plane` is the SAME GeomRef
            # a sketch uses: a `datum_plane` origin ref carries no feature_id (a
            # world plane — no dependency edge, like a pattern's vectors), but a
            # `datum` FeatureRef DOES materialise into feature_dependencies with
            # the same `datum`-only rule the sketch plane enforces (deleting that
            # datum is a 409-with-dependents; a reorder re-checks strict-backward).
            if isinstance(feature.params.plane, FeatureRef):
                references.append(
                    FeatureReference(
                        "plane", feature.params.plane, frozenset({"datum"})
                    )
                )
            # v2 `features` scope (mirror-semantics.md §3.1): each selected feature
            # IS a real dependency — the mirror reflects that feature's recorded
            # tools — so every ref materialises into feature_dependencies with the
            # BODY-AFFECTING allowed-target rule (the same constraint the on-face
            # datum / picked fillet use). Consequences bought for free at write
            # time: deleting a mirrored feature is a 409-with-dependents, a reorder
            # re-checks strict-backward, a forward/self reference is a 422, and a
            # `sketch`/`datum` selection is a 422 long before it could be an
            # evaluation-time `mirror_feature_unsupported` (§4.4). The `body` scope
            # carries no refs — tree order remains its only dependency.
            if isinstance(feature.params.scope, MirrorFeaturesScope):
                for index, ref in enumerate(feature.params.scope.features):
                    references.append(
                        FeatureReference(
                            f"scope.features[{index}]",
                            ref,
                            BODY_AFFECTING_FEATURE_TYPES,
                        )
                    )
        case ImportFeature():
            # An import PRODUCES the base body from its own inline STEP params
            # (step-import.md §1) — no picked geometry, no FeatureRef, so it
            # materializes no feature_dependencies edge (like an offset datum /
            # a pattern). Its body is a pure function of `data`.
            pass
        case SheetMetalBaseFlangeFeature():
            # A base flange thickens a single sketch profile to gauge (sheet-metal
            # §4.1) — the SAME `profile` FeatureRef → sketch slot extrude uses. Its
            # sheet-metal defaults (k_factor/bend_radius_mm) are scalars, not refs;
            # the neutral plane / bend are the edge-flange slice, not this one.
            references.append(
                FeatureReference(
                    "profile", feature.params.profile, frozenset({"sketch"})
                )
            )
        case SheetMetalEdgeFlangeFeature():
            # An edge flange names the base-flange EDGE it folds off (sheet-metal
            # §4.2) — an EdgeSubshapeRef resolved against the current sheet body,
            # exactly like a picked fillet/chamfer edge. Its feature_id materialises
            # into feature_dependencies (the named base-flange feature), so deleting
            # the base flange is a 409-with-dependents and a reorder re-checks
            # strict-backward. flange_length/bend_angle/radius/K are scalars, not
            # refs. The edge is named on a body-affecting feature's result.
            references.append(
                FeatureReference(
                    "edge", feature.params.edge, BODY_AFFECTING_FEATURE_TYPES
                )
            )
        case SheetMetalHemFeature():
            # A hem names the base-flange EDGE it folds ~180 deg back over (parity
            # §2) — an EdgeSubshapeRef resolved against the current sheet body,
            # exactly like an edge flange / picked fillet edge. Its feature_id
            # materialises into feature_dependencies (the named base-flange feature),
            # so deleting the base flange is a 409-with-dependents and a reorder
            # re-checks strict-backward. length/radius/K/hem_type are scalars, not
            # refs. The edge is named on a body-affecting feature's result.
            references.append(
                FeatureReference(
                    "edge", feature.params.edge, BODY_AFFECTING_FEATURE_TYPES
                )
            )
        case SheetMetalCornerReliefFeature():
            # A corner relief names the TWO edge-flange features whose bends meet at
            # the relieved corner (sheet-metal.md §4.4) — each a FeatureRef the
            # evaluator maps to that flange's recorded CylindricalFaceSignature (§5).
            # Both slots accept `sheet_metal_edge_flange` ONLY (a hem is a 180 deg
            # fold-back, not a corner-forming bend; base/other features have no bend
            # provenance). Each feature_id materialises into feature_dependencies, so
            # deleting a referenced edge flange is a 409-with-dependents and a reorder
            # re-checks strict-backward. relief_type/relief_ratio/size_mm are scalars.
            references.append(
                FeatureReference(
                    "bend_a",
                    feature.params.bend_a,
                    frozenset({"sheet_metal_edge_flange"}),
                )
            )
            references.append(
                FeatureReference(
                    "bend_b",
                    feature.params.bend_b,
                    frozenset({"sheet_metal_edge_flange"}),
                )
            )
        case BooleanFeature():
            # A boolean combines two independently-built bodies named by their
            # BASE features (multi-body §Decisions-3): TARGET (surviving) + TOOL
            # (consumed). Each FeatureRef.feature_id materializes into
            # feature_dependencies exactly like an extrude's profile, so deleting
            # either operand's base feature is a 409-with-dependents and a reorder
            # re-checks strict-backward. Both slots accept only the body-CREATING
            # base features (a boolean operand IS a body — a modifier or another
            # boolean is not a valid operand base here; boolean-on-boolean is MB-4).
            references.append(
                FeatureReference(
                    "target",
                    feature.params.target,
                    BASE_BODY_AFFECTING_FEATURE_TYPES,
                )
            )
            references.append(
                FeatureReference(
                    "tool", feature.params.tool, BASE_BODY_AFFECTING_FEATURE_TYPES
                )
            )
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
    feature: AuthoredFeature
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
    feature: AuthoredFeature | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> Self:
        if self.name is None and self.feature is None:
            raise ValueError("provide at least one of 'name' or 'feature'")
        return self


class FeatureSuppressRequest(BaseModel):
    """Toggle ONLY a feature's suppress flag (feature-tree.md §4.3a).

    A DEDICATED, minimal mutation — distinct from :class:`FeatureUpdate` — so
    suppressing/un-suppressing never touches ``params`` (no re-validation of
    the payload, no dependency-edge rewrite): it flips the envelope-level
    ``suppressed`` flag and bumps ``tree_version`` under the same
    optimistic-concurrency guard as every other write (stale value → 422). A
    suppressed feature is SKIPPED at rebuild (the body is built from the
    non-suppressed prefix), so this changes what an evaluation of the part
    means and is a normal history-recording tree edit (undoable)."""

    expected_tree_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the tree_version the client "
        "last saw; a stale value is rejected 422 (design §1.2)",
    )
    suppressed: bool = Field(
        description="New suppress state: True skips the feature at rebuild, "
        "False re-includes it (feature-tree.md §4.3a)."
    )


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
    feature: AuthoredFeature
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
    can_undo: bool = Field(
        description="True when an earlier history snapshot exists to restore "
        "(docs/design/undo-redo.md) — lets the toolbar disable undo without "
        "a second call"
    )
    can_redo: bool = Field(
        description="True when a later history snapshot exists to restore "
        "(the history cursor is below the ring's top)"
    )


class FeatureMutationResponse(BaseModel):
    """Result of a single-feature mutation: the affected feature + the new
    tree version (the client's next ``expected_tree_version``)."""

    feature: FeatureResponse
    tree_version: int


#: What holds a reference to a feature: another FEATURE of the same part (an
#: extrude consuming its sketch, a fillet naming an edge of an earlier result),
#: or a DRAWING whose section view cuts on this feature's datum (audit P2 #16).
#: Nothing else can — an assembly instances a whole PART, never a feature — so
#: the union is closed and a client may exhaustively switch on it.
FeatureDependentKind = Literal["feature", "drawing"]


class FeatureDependent(BaseModel):
    """One thing that breaks if a feature is deleted.

    ``name`` rides beside the id for the same reason it does on
    :class:`~loft_wire.workspace.DocumentDependent`: the reader is a person
    who named these things, and "referenced by 2 other document(s)" — which is
    what this refusal used to say — ends the conversation instead of starting
    the next action.
    """

    id: uuid.UUID = Field(description="The REFERENCING feature's or drawing's id")
    name: str = Field(description="Its name, as the user sees it in the tree/register")
    kind: FeatureDependentKind = Field(
        description="'feature' (a later feature of this part) or 'drawing' (a "
        "section view cutting on this feature)"
    )


class FeatureDependents(BaseModel):
    """What depends on one feature — the answer to "what breaks if I delete it?"

    Serves TWO surfaces from one shape, which is the point (CLAUDE.md DRY):

    - the ``details`` payload of the delete's ``feature_has_dependents`` 409, and
    - the body of ``GET …/features/{id}/dependents``, which the tree asks BEFORE
      offering the delete, so the confirmation can name what breaks instead of
      letting the user find out from a refusal.

    Both are produced by one server-side query, so the warning a user reads and
    the refusal the server would issue cannot disagree. Empty means the feature
    is free to delete — an honest, common answer, unlike the 409 payload
    (:class:`FeatureDependentsEnvelope`) which by construction is never empty.
    Features first (tree order — the order the user reads them in), then
    drawings alphabetically.
    """

    dependents: list[FeatureDependent] = Field(
        description="Everything referencing this feature; EMPTY when nothing does"
    )


class FeatureDependencyConflictError(BaseModel):
    """The ``error`` member of a feature-delete 409, with typed ``details``."""

    code: str = Field(
        description="'feature_has_dependents' — the code a client branches on"
    )
    message: str = Field(description="Human summary; the tree shows the list")
    details: FeatureDependents
    request_id: str | None = Field(
        default=None, description="Correlation id of the refused request"
    )


class FeatureDependentsEnvelope(BaseModel):
    """A feature-delete 409 as it appears on the wire (standard envelope).

    Declared as the documented 409 model of the feature delete so it reaches
    ``packages/contracts`` and therefore the generated TS client — the tree
    lists the features by name from a TYPE rather than from a hopeful parse of
    an untyped ``details`` blob (UI-REVIEW 2026-07-30 F3).
    """

    error: FeatureDependencyConflictError


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


class UndoRedoRequest(BaseModel):
    """Restore the adjacent history snapshot (docs/design/undo-redo.md).

    Undo/redo ARE document edits: each bumps ``tree_version`` under the same
    optimistic-concurrency guard as every other write (stale → 422), and the
    response is the restored tree (ids preserved VERBATIM — the load-bearing
    snapshot decision). At a boundary — undo at the ring's floor, redo at its
    top — the op is a CLEAN no-op, not an error: 200 with the current tree,
    version unchanged. ``can_undo``/``can_redo`` on the tree response let the
    UI disable the controls, so a click racing that state is harmless.
    """

    expected_tree_version: int = Field(ge=0)


# --- §4 Evaluation contract (documents → geometry) ---------------------------------


class EvaluatedFeatureInput(BaseModel):
    """One ordered entry of an evaluation request."""

    id: uuid.UUID = Field(description="Feature identity for refs + result keying")
    feature: Annotated[Feature, STRIP_EXPRESSIONS]
    input_error: Annotated["FeatureError | None", INPUT_ERROR_CHECK] = INPUT_ERROR_FIELD


class EvaluateTreeRequest(BaseModel):
    """Evaluate an ordered, validated, current-version feature list (§4.2).

    Documents applies the rollback bar BEFORE sending: geometry receives
    exactly the prefix to evaluate and never needs to know rollback exists.
    """

    part_id: uuid.UUID
    tree_version: int = Field(
        ge=0,
        description="The part tree_version documents composed this request from. "
        "Echoed back verbatim on the result, where it is the PROVENANCE stamp of "
        "the returned body (EvaluateTreeResult.tree_version) as well as a "
        "cache/correlation key.",
    )
    features: list[EvaluatedFeatureInput] = Field(
        max_length=MAX_TREE_FEATURES,
        description="Ordered prefix (rollback already applied), bounded by "
        "MAX_TREE_FEATURES (work bound, audit G2)",
    )
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        ge=MIN_LINEAR_DEFLECTION,
        description="Presentation parameter (mm), NEVER persisted per feature "
        "(design §8.3). Floored at MIN_LINEAR_DEFLECTION (work bound, audit G2).",
    )
    materials: MaterialAssignment | None = Field(
        default=None,
        description="What the part's bodies are made of (docs/design/"
        "materials.md): a document default plus per-body overrides. Omitted / "
        "null = no material, so the result reports NO mass (absent, not zero). "
        "Unlike length units — presentation metadata the kernel never sees — "
        "material is an INPUT to evaluation, because mass is derived from it.",
    )


#: Which rebuild a warm is for, named for what the user is about to do. Both
#: names address the SAME rebuild-cache checkpoint: every evaluation records
#: per-face provenance and ``record_history`` is no longer in the prefix key
#: (PERF-REAL-3), so ``/evaluate``, ``/overlay``, ``/measure`` and the rest
#: resume from one entry per part. The worker collapses the list and warms that
#: entry once (``geometry.warm``). The two names remain because they are wire
#: contract, and the web client still sends both:
#:
#: * ``evaluate`` — the rebuild behind committing the edit;
#: * ``provenance`` — the rebuild behind the FIRST FACE PICK after that commit,
#:   which was the visible one while it had an entry of its own (docs/PERF.md
#:   measured 29 s at 200 features).
WarmLineage = Literal["evaluate", "provenance"]

#: Cap on how many names one warm may list: one per ``WarmLineage`` value. Both
#: address one checkpoint, so listing both costs no more than listing one; the
#: bound only keeps a request from carrying an unbounded list.
MAX_WARM_LINEAGES = 2


# ATTRIBUTION NOTE (orchestrator, 2026-08-01): the four prefetch/warm DTOs below
# (WarmTreeRequest, WarmTreeResult, WarmCancelRequest, PrefetchRequest, plus
# WarmLineage / PrefetchTargetKind) were written by the kernel agent for PERF-1b
# and shipped in `e2f3fa0`. They landed in the *tree* one commit earlier, in
# `17404ab` (folders), because that agent staged this file wholesale while the
# prefetch work was uncommitted in it. No work was lost and `17404ab` is green on
# its own — the models are unreachable from any route in that tree, so its
# OpenAPI is unchanged — but `git log` credits the wrong slice. Annotating rather
# than rewriting shared history that siblings have already rebased onto.


class WarmTreeRequest(BaseModel):
    """Ask the geometry worker to speculatively cache a feature-tree prefix.

    **This request cannot produce an artifact** (docs/PERF.md PERF-1b): the only
    thing it can do is make a LATER, ordinary evaluate cheaper by leaving an
    evaluator checkpoint in the per-worker rebuild cache, addressed by the same
    content hash that evaluate probes. There is deliberately no "prefetched
    result" to fetch — see :class:`WarmTreeResult`.

    It is issued on a genuine declaration of intent, and only those two:

    * an **open feature editor** — editing feature ``k`` declares ``0..k-1``
      settled for as long as the dialog is open, so ``tree`` is the current tree
      and ``prefix_length`` is ``k``;
    * a **travel stop** on the timeline — that is a shorter tree in its own
      right, so ``tree`` IS the shorter tree and ``prefix_length`` is omitted.
    """

    ticket: Annotated[str, StringConstraints(min_length=1, max_length=200)] = Field(
        description="Opaque identity of the INTENT, chosen by the caller and "
        "namespaced by the gateway per user. Submitting a ticket that is already "
        "running is a no-op (a re-render must not restart its own warm), a new "
        "ticket supersedes the running one, and `POST /warm/cancel` with this "
        "ticket retires it — which is what closing the editor or ending the drag "
        "does."
    )
    tree: EvaluateTreeRequest = Field(
        description="The tree whose prefix to warm — the very request a later "
        "evaluate will send, so the warm lands on the key that request probes."
    )
    prefix_length: int | None = Field(
        default=None,
        ge=1,
        le=MAX_TREE_FEATURES,
        description="How many leading features of `tree` to evaluate; null = all "
        "of them. Clamped to the tree's length. An open editor for feature k "
        "sends k here (an edit at k cannot change the hash of anything before "
        "it); a travel stop sends null and a shorter tree.",
    )
    lineages: list[WarmLineage] = Field(
        default_factory=lambda: ["evaluate"],
        max_length=MAX_WARM_LINEAGES,
        description="Which rebuilds to warm. Both names address the SAME "
        "rebuild-cache entry (every evaluation records per-face provenance), so "
        "the worker warms it once, under one budget, whether one name or both "
        "is listed; an empty list warms nothing. An open editor sends both: the "
        "commit (`evaluate`) and the face pick that follows it (`provenance`) "
        "resume from that one entry.",
    )


#: What the user did that makes a prefix worth speculating on. Both are genuine
#: declarations of intent — which is the entire admission criterion, because
#: prefetch hides latency and never reduces work:
#:
#: * ``feature_edit`` — the editor for this feature is OPEN, so every feature
#:   before it is settled for as long as the dialog is;
#: * ``travel_stop`` — the timeline's rollback marker is being dragged to this
#:   feature, and that stop is a shorter tree in its own right.
#:
#: Register/document hover is deliberately NOT here: it is ordinary client-side
#: query prefetch and worth nothing against a rebuild curve.
PrefetchTargetKind = Literal["feature_edit", "travel_stop"]


class PrefetchRequest(BaseModel):
    """Warm the rebuild cache for a part, addressed the way the CLIENT sees it.

    The browser knows the intent and the feature id; it does not know (and must
    not assemble) the evaluation-ready feature list — documents owns that,
    rollback bar and param upcasts included. So this carries the intent, and the
    gateway turns it into the geometry service's :class:`WarmTreeRequest` using
    the SAME ``/evaluation-request`` hop a real evaluate uses, which is what
    makes the warm land on the key the real evaluate will probe.

    Best-effort by construction: a target that is not in the current evaluation
    prefix (rolled back past, or already deleted) is a 200 with
    ``accepted: false``, never an error — a prefetch that cannot be honoured just
    means the next rebuild is as slow as it always was.
    """

    ticket: Annotated[str, StringConstraints(min_length=1, max_length=100)] = Field(
        description="Client-chosen identity of this intent (e.g. one per open "
        "editor). Namespaced per user by the gateway, so one client can never "
        "cancel another's speculation."
    )
    part_id: uuid.UUID = Field(description="The part being edited or scrubbed.")
    kind: PrefetchTargetKind
    feature_id: uuid.UUID = Field(
        description="The feature the intent points at: the one whose editor is "
        "open, or the one the travel stop is being dropped after."
    )


class WarmCancelRequest(BaseModel):
    """Retire a warm ticket. Idempotent, and never an error."""

    ticket: Annotated[str, StringConstraints(min_length=1, max_length=200)] = Field(
        description="The ticket submitted to `POST /warm`. Unknown or already "
        "finished → `accepted: false`, which is a normal outcome, not a fault."
    )


class WarmTreeResult(BaseModel):
    """The reply to a warm — deliberately EMPTY of geometry.

    There is no mesh id, no mass property, no feature status and no body here,
    and that is a structural guarantee rather than an omission: a speculative
    rebuild that could be published would eventually be published for a tree it
    does not exactly correspond to, which is the silent-wrong-geometry class this
    repo has closed five times. A warm can only ever be *used* by a request whose
    feature prefix hashes identically, through the ordinary cache key.

    So the two fields say what happened to the SCHEDULING, and nothing else.
    """

    ticket: str = Field(description="Echo of the submitted ticket.")
    accepted: bool = Field(
        description="Whether this call changed the worker's speculation: true = "
        "queued (or, for /warm/cancel, a running ticket was retired); false = "
        "nothing to do — the same ticket was already in flight, the tree had no "
        "prefix worth warming, or the cancelled ticket had already finished. "
        "Never an error either way: prefetch is best-effort by construction."
    )


#: Upper bound for a document name carried on an export request (matches
#: ``PartName`` / ``AssemblyName``, which is where these values come from).
EXPORT_DOCUMENT_NAME_MAX_LENGTH = 200

#: A document's human-readable name, carried on an EXPORT request only.
#:
#: **Why export-only** (the decision, since it looks like it belongs on the
#: evaluate request): a name is presentation metadata, and the evaluation
#: contract deliberately carries only INTENT plus the one non-geometric input
#: mass is derived from (``materials``, materials.md §9a) — length units are kept
#: off it for exactly this reason. But a FILE outlives the screen that explained
#: it: a shop that receives ``a3f2c1e8-....step`` containing ``PRODUCT('SOLID')``
#: cannot tell what it is, and exporting five parts to quote a job means five
#: hand-renames (audit N4). So the name rides the request that produces a file,
#: where it can change the file's NAME and its PRODUCT and nothing else — the
#: kernel never sees it, and evaluation stays byte-identical with or without it.
DocumentName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EXPORT_DOCUMENT_NAME_MAX_LENGTH,
    ),
]


def document_slug(name: str) -> str:
    """A safe download basename component from a document name.

    THE one slug rule for every download this product names after a document
    (CLAUDE.md DRY): lower-case, non-alphanumeric runs collapsed to a single
    hyphen, edges trimmed. Ported from ``apps/web/src/drawing/exportSvg.ts``
    ``sanitizeDrawingFilename`` and shared by the drawing artifact
    (``artifact_filename``), the part export (:func:`export_tree_filename`) and
    the assembly export (``assembly_export_filename``), so all three name a file
    identically. Returns ``""`` for a name with no alphanumerics at all — the
    caller decides its own fallback, because "drawing" is not a sensible default
    for a part.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


class ExportTreeRequest(EvaluateTreeRequest):
    """Evaluate a feature tree and export its LAST-GOOD body as a CAD file.

    Extends :class:`EvaluateTreeRequest` — the SAME ordered, rollback-applied
    feature list the evaluate endpoint takes (DRY: one tree contract,
    evaluated then exported) — with the export format selection. The geometry
    service reuses the evaluate-tree dispatch to produce the body, then exports
    THAT body (never a re-modelled shape).

    STEP exports the exact B-rep, so the deflection fields are meaningless for
    it and ignored. STL, 3MF and GLB are faceted approximations;
    ``linear_deflection`` (inherited) and ``angular_deflection`` default to the
    tessellation defaults so the exported mesh matches what the viewport shows.

    If the tree produces no body — a strict-prefix failure (§4.3) or a tree
    with no body-affecting feature — export is a clean error, never a file:
    the geometry service answers a 422 ``tree_export_failed`` envelope, not a
    partial download.
    """

    format: ExportFormat = Field(description=EXPORT_FORMAT_DESCRIPTION)
    angular_deflection: float = Field(
        default=DEFAULT_ANGULAR_DEFLECTION,
        ge=MIN_ANGULAR_DEFLECTION,
        description=(
            "Facet angular deflection (rad) between adjacent segments for STL "
            f"and 3MF; {MESH_QUALITY_NOTE}, and fixed service-wide for GLB. "
            "Floored at MIN_ANGULAR_DEFLECTION (work bound, audit G2)."
        ),
    )
    name: DocumentName | None = Field(
        default=None,
        description="The part's human-readable document name. Names the exported "
        "STEP PRODUCT / 3MF object and the download filename; omitted / null falls "
        "back to the part id. EXPORT-only on purpose (see DocumentName) — it is not "
        "on EvaluateTreeRequest, because a name must never be an input to geometry.",
    )


def export_tree_filename(request: ExportTreeRequest) -> str:
    """Deterministic download filename for a tree export (Content-Disposition).

    Named after the PART (``motor-mount-bracket.step``) when the request carries
    the document name, so what lands in Downloads is what a vendor can read
    (audit N4). Falls back to ``part-<id>.<format>`` when it does not — still
    unique, never a collision. Byte-stable for identical requests either way
    (determinism is a feature, RESEARCH §9).
    """
    slug = document_slug(request.name) if request.name is not None else ""
    return f"{slug or f'part-{request.part_id}'}.{request.format}"


# CONSTRUCTING A ``FeatureError`` IS INSTRUMENTED (see ``model_post_init`` below:
# :func:`loft_wire.instrument.notify_feature_error`), which is a side effect on a
# DTO and therefore owes an explanation. The alternative is a ``.inc()`` beside each
# of the ~85 ``FeatureError(code=…)`` sites across the kernel handlers — and the
# 86th, written next month by someone who has never read this file, would
# silently not be counted. That is this repo's "a gate that cannot fail" defect
# wearing a different hat: an operator would see a flat line and conclude nothing
# was wrong. The contract DTO is the ONE thing every feature failure in the
# product is rendered through, so it is the seam that cannot be bypassed. Cost is
# a counter increment on a path that only runs when something already failed.
#
# One honest consequence: the gateway re-validates geometry's response into this
# same model (``gateway/features.py``), so a proxied failure is counted once in
# geometry (where it happened) and once in the gateway (where it was observed).
# Each service exports its own ``/metrics``, so the two are distinct series —
# attribute failures to the geometry job and do not sum across jobs.
# ``docs/OBSERVABILITY.md`` says so where an operator will read it.
#
# The notification is INDIRECT — an observer registry in :mod:`loft_wire.instrument`
# rather than a direct ``py_kit.metrics`` import — because this module ships in a
# distribution whose only dependency is pydantic, and a Prometheus counter would
# have dragged ``prometheus_client``, FastAPI and ``pydantic-settings`` back into
# it. That module's docstring names the hazard the indirection creates (an
# unregistered observer is a flat line, which is this same defect one step
# removed) and the two things that hold it down.
#
# The rationale is a COMMENT on purpose: a model docstring is this schema's
# ``description`` in ``packages/contracts`` and the TS client, where an API
# consumer should not have to read instrumentation trivia.
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
    sketch_diagnosis: SketchConstraintDiagnosis | None = Field(
        default=None,
        description="Typed over-constraint classification for the "
        '"sketch_conflicting" code: which constraints conflict vs. are redundant, '
        "so the sketcher reads the diagnosis by field instead of parsing "
        "``message`` (BACKLOG #6). None for non-sketch-conflict errors.",
    )

    def model_post_init(self, context: Any, /) -> None:
        """Count this failure by code (see the comment above the class)."""
        notify_feature_error(self.code)


class SolvedSketchData(SolvedSketch):
    """Per-feature solved-sketch payload (§7.10): the solver's solved entity
    positions, status, and DOF diagnosis for an ``ok`` sketch feature — what
    the sketcher UI renders. ``kind`` is the :data:`FeatureData` union tag."""

    kind: Literal["solved_sketch"] = "solved_sketch"
    diagnosis: SketchConstraintDiagnosis | None = Field(
        default=None,
        description="Typed over-constraint classification for a SOLVED-but-over-"
        "constrained sketch (``overconstrained`` status): the redundant, "
        "removable constraints named so the sketcher can flag them without "
        "parsing text (BACKLOG #6). None for a cleanly-constrained sketch. The "
        'unsolvable ("conflicting") case rides FeatureError.sketch_diagnosis.',
    )
    projections: list[SketchProjectionStatus] = Field(
        default_factory=list["SketchProjectionStatus"],
        description="One status per projected entity, in entity order: whether "
        "it followed its body edge on this rebuild, and why not when sick. "
        "Empty for a sketch with no projected entities.",
    )
    profile_entities: list[EntityId] = Field(
        default_factory=list[EntityId],
        description="Ids of the curves that bound the sketch's profile, in "
        "entity order: the exact selection every body feature (extrude, "
        "revolve, sweep, loft) builds its profile from, so a live preview "
        "stitches the same curves the commit will. Construction entities and "
        "points are never in it; a projected curve is in it only where it "
        "helps close a region (Fusion 360's rule, QA-PROJECTED-PROFILE).",
    )


#: The typed per-feature ``FeatureResult.data`` payload (design §7.10).
#: Every variant carries a ``kind`` literal tag, so when a second feature
#: type grows a payload this alias becomes the discriminated union
#: ``Annotated[SolvedSketchData | NewData, Field(discriminator="kind")]`` —
#: purely additive on the wire (pydantic forbids a discriminator on a
#: single-member union, hence the plain alias until then).
FeatureData = SolvedSketchData


class SubshapeResolutionSummary(BaseModel):
    """How one feature's picked subshape references resolved on THIS rebuild.

    A WARNING channel, never a refusal (§7.3): a feature that rebuilt on a
    ``durable`` or ``adjacent`` match is ``ok`` and its body is built, but the
    stage-1 matchers behind those tiers are best-effort and can, rarely, re-find
    the WRONG subshape without erroring. ``worst_tier != "exact"`` is the signal
    a client shows (the counterpart of the ``subshape_unresolved`` /
    ``subshape_ambiguous`` errors, for the references that DID resolve).
    One count per picked reference, in the tier that resolved it."""

    worst_tier: SubshapeResolutionTier = Field(
        description="The least certain tier any reference of this feature "
        "resolved at: 'exact' < 'named' < 'durable' < 'adjacent'."
    )
    exact: int = Field(
        ge=0, description="References whose stored signature matched verbatim."
    )
    durable: int = Field(
        ge=0,
        description="References re-found on a rebuild invariant after the "
        "subshape moved or changed shape.",
    )
    adjacent: int = Field(
        ge=0,
        description="Edge references re-found as the edge shared by their two "
        "stored neighbouring faces (§14).",
    )
    named: int = Field(
        default=0,
        ge=0,
        description="References re-found by their stored history-based name "
        "(DESIGN-INTENT-REFS) after the exact signature missed.",
    )


class FeatureResult(BaseModel):
    """Per-feature evaluation status. Strict-prefix rule (§4.3): the first build
    failure is ``error``, every later feature ``skipped``; a feature sent with an
    ``input_error`` is ``error`` and the later ones still build. ``suppressed``
    (§4.3a) is a deliberate skip, distinct from a downstream ``skipped``, so the
    tree UI can show it dimmed rather than red."""

    feature_id: uuid.UUID
    status: Literal["ok", "error", "skipped", "suppressed"]
    error: FeatureError | None = None
    data: FeatureData | None = Field(
        default=None,
        description="Typed per-feature payload for ok features that produce "
        "one (§7.10): solved sketch geometry today; future feature types add "
        "kind-tagged variants additively.",
    )
    subshape_resolution: SubshapeResolutionSummary | None = Field(
        default=None,
        description="For an ok feature that names picked edges/faces: which "
        "tier re-found them on this rebuild. Null when the feature has no "
        "picked subshape reference (or did not evaluate ok). A worst_tier other "
        "than 'exact' means the feature rebuilt on a best-effort re-match - "
        "worth a dismissable warning, never a refusal.",
    )


class BodyLumpInfo(BaseModel):
    """Per-body lump count of an evaluated tree (docs/design/multi-body.md §MB-4).

    The whole-part aggregate ``properties.topology.shells`` cannot tell a
    disjoint-union / multi-solid-import body (one body, several disjoint LUMPS)
    from a single-lump body: a sealed hollow inflates the shell count, and the
    aggregate sums across every body. This per-body entry carries the honest
    lump count so a consumer (the Bodies panel) can flag a multi-lump body.

    ``base_feature_id`` is the body's identity — the id of the feature that
    CREATED it (§MB-0 Decision 1), the same key ``EvaluationState.bodies`` uses —
    so a caller maps the count back to the body/row it names. ``lumps`` is the
    number of disjoint connected solids (``>= 1``; a single-lump body reports
    ``1``), counted by ``geometry.kernel.lumps.lump_count``.
    """

    base_feature_id: uuid.UUID = Field(
        description="Id of the feature that created this body (its §MB-0 identity)"
    )
    lumps: int = Field(
        ge=1,
        description="Number of disjoint connected solids (lumps) of this body; "
        "1 for a single-lump body, >1 for a disjoint union / multi-solid import.",
    )
    material: MaterialKey | None = Field(
        default=None,
        description="The material RESOLVED for this body (its own override, "
        "else the document default); null = none assigned, so no mass.",
    )
    mass_g: float | None = Field(
        default=None,
        description="This body's mass (g) = its volume x its material's density, "
        "or null when it has no material. The whole-part `properties.mass_g` is "
        "null as soon as ONE body is null; this says which (materials.md §4).",
    )


class EvaluateTreeResult(BaseModel):
    """Statuses plus object-storage references — never kernel types, never
    inline meshes (§4.1). A feature failure is a 200 with per-feature errors;
    the envelope stays reserved for transport/validation failures (§4.3)."""

    part_id: uuid.UUID
    tree_version: int = Field(
        ge=0,
        description="PROVENANCE: the part tree_version this result — every "
        "`features` status, `mesh_glb_id`, and `properties` — was BUILT FROM "
        "(echoed from the request documents composed off that exact tree). A "
        "consumer compares it against the part's current "
        "`PartResponse.tree_version` (the shared `is_stale_for_tree` rule) to "
        "know whether the body it is displaying still reflects the tree, instead "
        "of inferring currency from whether a request is in flight.",
    )
    features: list[FeatureResult] = Field(description="Same order as the request")
    bodies: list[BodyLumpInfo] = Field(
        default_factory=list[BodyLumpInfo],
        description="Per-body lump count of the last-good body set (§MB-4), "
        "tree-ordered by the feature that created each body. Lets a consumer flag "
        "a multi-lump (disjoint-union / multi-solid-import) body the whole-part "
        "`properties.topology.shells` aggregate cannot distinguish. Additive: "
        "absent/empty for a tree with no body-affecting feature.",
    )
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
