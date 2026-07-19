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
from py_kit.schemas.sketch import (
    EntityId,
    SketchConstraintDiagnosis,
    SketchDefinition,
    SolvedSketch,
)

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


# --- Stage-1 topological naming: EDGE signatures (topological-naming.md §2b/§10) ---
#
# The SECOND SubshapeRef consumer the topo-naming design anticipated (§10, "edge
# selection is BACKLOG #2"), mirroring the planar-face signature above. An
# EdgeSubshapeRef names ONE edge of a body-affecting feature's result by a
# geometric SIGNATURE (§2b), NOT an enumeration index (§1.3 rejects indices).
# Same stage-1 posture as the face signature, stated with the same honesty: a
# signature is BEST-EFFORT — it resolves the same edge across the common edits
# (parametric changes that do not move the edge; upstream inserts that do not
# touch it) and FAILS HONESTLY (``subshape_unresolved`` / ``subshape_ambiguous``)
# for most others, but a drastic model change CAN retarget to a
# coincidentally-congruent edge without erroring. It is NOT structurally
# non-retargeting; only stage-2 provenance (coordinate-blind) makes that
# structural. The exactly-one-or-error rule is load-bearing, but note WHAT it
# guards: the signature is ABSOLUTE-position-based, so mirror-congruent edges of
# a symmetric part have DISTINCT signatures and never tie — a picked edge
# resolves only to the edge at that position. The real ``subshape_ambiguous``
# source is two edges that truly COINCIDE in space (a boolean seam, a
# non-manifold duplicate, a near-collision within tolerance), where the resolver
# refuses to guess.


class EdgeSignature(BaseModel):
    """§2b stage-1 geometric fingerprint of an EDGE — typed, kernel-free.

    Full-precision invariants (§7.2 forbids quantizing the stored identity),
    chosen to distinguish the edges of a manifold solid: the ``curve`` family
    (line/circle/other — a straight edge and an arc of equal length never
    collide), the two canonically-ordered endpoints ``end_a``/``end_b`` (sorted
    lexicographically so the signature is INDEPENDENT of the topological edge
    orientation OCCT happens to assign), the ``midpoint`` (curve param 0.5 — it
    separates two collinear edges that share an endpoint, and pins a full-circle
    seam edge whose endpoints coincide), and the ``length_mm``. Two DISTINCT
    edges of an authored part differ in at least one field (endpoints/midpoint
    by whole mm, or length, or curve kind) — including the mirror-congruent
    edges of a symmetric part, which have DISTINCT absolute positions and so do
    NOT tie. Only edges that truly coincide in space (a boolean seam, a
    non-manifold duplicate) resolve to an honest ``subshape_ambiguous`` (§5),
    never a guess. Matching is nearest-within-tolerance at the documented
    subshape tolerance (geometry.kernel.edges / docs/GEOMETRY-QA.md), never an
    ad-hoc epsilon.
    """

    subshape_type: Literal["edge"] = "edge"
    curve: Literal["line", "circle", "other"] = Field(
        description="Curve family — line | circle | other (spline/ellipse/…)"
    )
    end_a: Vec3 = Field(
        description="One endpoint, world mm; the lexicographically SMALLER of the "
        "two so the pair is orientation-independent (full precision)"
    )
    end_b: Vec3 = Field(
        description="The other endpoint, world mm; the lexicographically LARGER. "
        "Equals end_a for a closed edge (a full circle's coincident seam)."
    )
    midpoint: Vec3 = Field(
        description="Curve midpoint (param 0.5), world mm (full precision)"
    )
    length_mm: float = Field(gt=0, description="Edge arc length (mm), full precision")


class EdgeSelectorV1(BaseModel):
    """Stage-1 edge selector payload: the geometric signature alone (§3, §4).

    The edge sibling of :class:`SelectorV1`. ``selector_version`` is the
    discriminator of the (currently single-member) edge selector union,
    decoupled from feature ``param_version`` (§4); stage 2 adds a signature +
    provenance member additively, with no change to persisted v1 rows.
    """

    selector_version: Literal[1] = 1
    signature: EdgeSignature


#: Version-discriminated edge selector union (§4). One member (stage 1) today,
#: so a plain alias; stage 2 promotes it to a discriminated union — the same
#: idiom as the face :data:`Selector`.
EdgeSubshapeSelector = EdgeSelectorV1


class EdgeSubshapeRef(BaseModel):
    """Stage-1 reference to ONE edge of a body-affecting feature's result.

    The edge sibling of :class:`SubshapeRef` (topological-naming.md §4/§10).
    ``feature_id`` is the stage-1 anchor — "the prior body-affecting feature
    whose body I signature-match against" (§4) — and materializes into
    ``feature_dependencies`` like a :class:`SubshapeRef`/:class:`FeatureRef` (via
    the widened :func:`iter_feature_refs` / :func:`feature_references`), so
    deleting that feature is a write-time 409-with-dependents and a reorder
    re-checks strict-backward. ``subshape_type`` is ``"edge"``. A pick UI echoes
    a picked edge's ``/overlay`` :class:`EdgeSignature` straight into ``selector``.
    """

    kind: Literal["subshape"]
    feature_id: uuid.UUID
    subshape_type: Literal["edge"]
    selector: EdgeSubshapeSelector


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
        description="The specific picked edges (>= 1), each a stage-1 "
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
        description="The planar faces to leave OPEN (each a stage-1 face "
        "SubshapeRef resolved against the current body). EMPTY = a fully-enclosed "
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


#: One side of a midplane: an origin datum plane name, an EARLIER ``datum``
#: feature, or a picked PLANAR model face (the stage-1 signature the ``on_face``
#: datum resolves — topological-naming.md §4, reused not reinvented).
#: Discriminated on ``kind`` (``datum_plane`` | ``feature`` | ``subshape``);
#: only FACE subshape refs validate (an edge ref has ``subshape_type: "edge"``
#: and is a request-validation 422).
MidplaneSide = Annotated[
    DatumPlaneRef | FeatureRef | SubshapeRef, Field(discriminator="kind")
]


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
#: offset-from-another-datum plane (chaining), or a midplane between two
#: references — discriminated on ``kind``. LEGACY persisted params carry no
#: ``kind`` (they predate on_face) — :class:`DatumFeature`'s before-validator
#: injects ``kind: "offset"`` so old rows validate unchanged (additive, NO
#: ``param_version`` bump — datum-planes §4/§7).
DatumParams = Annotated[
    DatumOffsetParams | DatumOnFaceParams | DatumOffsetFromParams | DatumMidplaneParams,
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

    Extends :class:`py_kit.schemas.sketch.SketchDefinition` (typed
    ``entities``/``constraints`` — the §1.4 placeholder finalized by the
    "Sketch model + solver API" item), so a persisted sketch's params ARE
    valid solver input: same validation (unique sketch-local entity ids per
    design §2.4) on the documents write path and the geometry request path.
    """

    plane: GeomRef


#: The multi-body "Merge result" flag (docs/design/multi-body.md §MB-0,
#: Decision 2), shared by every ADDITIVE body-affecting feature
#: (extrude/revolve/sweep/loft) — CLAUDE.md DRY rule, one definition. It applies
#: to the ADD operation only: ``True`` fuses the new solid into the ACTIVE body
#: (the historical single-body behaviour, and the "create the first body if none
#: exists yet" case); ``False`` STARTS a new active body — the second-body path
#: that lets a part end with more than one lump. Ignored for a CUT (which always
#: modifies the active body). Additive-optional and defaulting ``True``, so
#: legacy rows (persisted with no ``merge`` key) read ``True`` and behave exactly
#: as before — the ``flip``/``direction`` idiom, NO ``param_version`` bump.
MERGE_FIELD = Field(
    default=True,
    description=(
        "Merge result (ADD only): True fuses the new solid into the active body "
        "(default, historical single-body behaviour / starts the first body); "
        "False starts a NEW body (multi-body, design multi-body.md §MB-0). "
        "Ignored for a CUT. Additive — absent reads True, no param_version bump."
    ),
)


class ExtrudeParamsV1(BaseModel):
    """Linear extrusion of an earlier sketch feature's profile."""

    profile: FeatureRef = Field(
        description="Must resolve to an EARLIER sketch feature (design §2.2)"
    )
    distance_mm: float = Field(gt=0, description="Extrusion depth (mm)")
    operation: Literal["add", "cut"]
    direction: Literal["normal", "reverse"] = "normal"
    merge: bool = MERGE_FIELD


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
    merge: bool = MERGE_FIELD


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
    merge: bool = MERGE_FIELD


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

    Thickness is a UNIFORM INWARD offset (the wall grows into the solid, so the
    outer envelope is unchanged). An empty ``faces`` list hollows to a sealed
    (fully-enclosed) cavity; a non-empty list opens those faces
    (:class:`FaceSelector`). A thickness that would collapse or self-intersect
    the cavity (≥ the smallest half-wall) is a per-feature
    ``shell_thickness_too_large`` rebuild error, never a silently wrong body
    (docs/GEOMETRY-QA.md 2026-07-13).
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


# --- Sheet-metal hem — a ~180 deg fold-back of an edge (v1: CLOSED) ---------------
#
# A HEM folds the sheet's edge ~180 deg back onto itself, forming a doubled, safe
# edge (the incumbents' Hem tool — SolidWorks/Fusion). It is the near-trivial win
# of the parity roadmap (docs/design/sheet-metal-parity.md §2 Hem row / Parity
# roadmap #3): a CLOSED hem is mechanically a SPECIALIZATION of the shipped edge
# flange — a fixed 180 deg fold with a small inner radius, folding the return flat
# back over the parent face. Verified geometrically (kernel-architect, 2026-07-19):
# `build_edge_flange` at `bend_angle_deg = 180` with a small radius produces ONE
# clean valid solid (the return sits 2*radius above the base with an air gap, so
# it CANNOT self-intersect — proven down to radius 1e-6), and the shipped
# `unfold_sheet_metal` develops it correctly as a bend at pi (BA = pi * (radius +
# K * thickness)). So a closed hem REUSES `build_edge_flange`'s bend machinery
# verbatim (bend_angle fixed at 180) — no new kernel geometry code, no new unfold.
#
# It is a DISTINCT feature type (not a `hem_type` flag on the edge flange) for the
# same reasons the edge flange is distinct from a raw sweep (§4.2), plus one more:
# a hem's authoring gesture NEVER sets a fold angle (it is always ~180) — the user
# picks an edge + a return length, exactly the incumbent Hem tool. `hem_type`
# forward-declares the four incumbent hem shapes; v1 ships `"closed"` only (open /
# teardrop / rolled each need a NEW curved cross-section profile the exact-
# cross-section extrude does not build, so they are separate fast-follow slices —
# parity §2). Additive: a new `hem_type` Literal member lands with NO param_version
# bump.


class SheetMetalHemParamsV1(BaseModel):
    """A hem folded off a straight edge of the sheet — v1 CLOSED hem (parity §2).

    A closed hem folds the picked edge ~180 deg back FLAT against the parent face,
    with a small inner ``bend_radius_mm`` giving the doubled edge its tight,
    near-zero air gap (the gap between the two layers is ~2 * bend_radius). It is a
    specialization of the edge flange: the geometry side reuses ``build_edge_flange``
    with the fold angle FIXED at 180 deg, so the fused body is one clean solid and
    the flat pattern develops it as any bend (``BA = pi * (radius + K * thickness)``,
    §1) — its bend-table row reads angle 180 deg.

    ``edge`` is an :class:`EdgeSubshapeRef` naming the base-flange edge to hem — the
    SAME stage-1 :class:`EdgeSignature` machinery a fillet/chamfer or edge-flange
    pick uses (topological-naming §10); its ``feature_id`` materialises the
    dependency on the base-flange feature. ``length_mm`` is the developed flat
    length of the folded-back return (to the bend tangent line, §9 golden #1's
    convention). ``bend_radius_mm`` / ``k_factor`` default from the part's base
    flange (:class:`SheetMetalBaseFlangeParamsV1`) when omitted (``None``) and may
    be OVERRIDDEN per-hem — a tight closed hem sets a SMALL radius (e.g. ~0.5 *
    thickness) rather than the part's general bend radius.

    A ZERO ``bend_radius_mm`` (a truly zero-gap / zero-radius closed hem) is a
    degenerate fold; the ``gt=0`` bound rejects it as a typed validation error
    rather than admitting a degenerate solid (honest degradation — parity §3).

    Like a fillet/shell it MODIFIES the implicit single body chain (design §7.6) —
    it carries no ``merge`` (it always fuses into the sheet body the edge belongs
    to) — so its only whole-feature dependency is the named-edge ref + tree order.
    """

    edge: EdgeSubshapeRef = Field(
        description="The base-flange STRAIGHT edge to hem (a stage-1 EdgeSignature "
        "reference resolved against the current sheet body). The return folds ~180 "
        "deg back over this edge's adjacent flat face."
    )
    hem_type: Literal["closed"] = Field(
        default="closed",
        description="Hem shape. v1 ships 'closed' only (the return folds flat back "
        "against the parent — parity §2). Open / teardrop / rolled hems each need a "
        "curved cross-section profile and are deferred (additive Literal members, "
        "no param_version bump). Absent reads 'closed'.",
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
        "~2 * this. Omitted (None) inherits the part's base-flange default "
        "`bend_radius_mm`; a value overrides it per-hem. A tight closed hem uses a "
        "SMALL radius (~0.5 * thickness). A zero radius (zero-gap degenerate fold) "
        "is rejected by the `gt=0` bound.",
    )
    k_factor: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Neutral-axis fraction K in [0, 1] for the hem's bend allowance "
        "(§1). Omitted (None) inherits the part's base-flange default `k_factor` "
        "(0.44 v1 baseline); a value overrides it per-hem.",
    )


# --- §1.3 Versioned envelopes ----------------------------------------------------


class DatumFeature(BaseModel):
    """``{"type": "datum", "version": 1, "params": {...}}`` envelope.

    A non-body-affecting feature that produces a plane a later sketch sits on
    (docs/design/datum-planes.md §2b). ``params`` is the discriminated
    :data:`DatumParams` union — an ``offset`` plane (§3), an ``on_face`` plane
    (§7), an ``offset_from`` chained plane, or a ``midplane`` (§7a). Every
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


class ShellFeature(BaseModel):
    """``{"type": "shell", "version": 1, "params": {...}}`` envelope."""

    type: Literal["shell"]
    version: Literal[1]
    params: ShellParamsV1


class DraftFeature(BaseModel):
    """``{"type": "draft", "version": 1, "params": {...}}`` envelope."""

    type: Literal["draft"]
    version: Literal[1]
    params: DraftParamsV1


class PatternFeature(BaseModel):
    """``{"type": "pattern", "version": 1, "params": {...}}`` envelope."""

    type: Literal["pattern"]
    version: Literal[1]
    params: PatternParamsV1


class ImportFeature(BaseModel):
    """``{"type": "import", "version": 1, "params": {...}}`` envelope.

    A body-affecting BASE feature (docs/design/step-import.md §1): it produces
    the imported solid as the part's base body, rather than modifying a prior
    one. ``params`` is :class:`ImportParamsV1` (inline STEP text in v1).
    """

    type: Literal["import"]
    version: Literal[1]
    params: ImportParamsV1


class SheetMetalBaseFlangeFeature(BaseModel):
    """``{"type": "sheet_metal_base_flange", "version": 1, "params": {...}}`` envelope.

    A body-CREATING base feature (docs/design/sheet-metal.md §4.1): it thickens a
    profile to gauge, producing the sheet-metal part's first body, and anchors the
    part's sheet-metal defaults (``k_factor``/``bend_radius_mm``). ``params`` is
    :class:`SheetMetalBaseFlangeParamsV1`.
    """

    type: Literal["sheet_metal_base_flange"]
    version: Literal[1]
    params: SheetMetalBaseFlangeParamsV1


class SheetMetalEdgeFlangeFeature(BaseModel):
    """``{"type": "sheet_metal_edge_flange", "version": 1, "params": {...}}`` envelope.

    A body-MODIFYING feature (docs/design/sheet-metal.md §4.2): it folds a flange
    off a straight edge of the sheet body and fuses it across a cylindrical bend
    region, tagging that bend face with a :class:`CylindricalFaceSignature` (§5)
    for the unfold's provenance. ``params`` is :class:`SheetMetalEdgeFlangeParamsV1`.
    """

    type: Literal["sheet_metal_edge_flange"]
    version: Literal[1]
    params: SheetMetalEdgeFlangeParamsV1


class SheetMetalHemFeature(BaseModel):
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


class BooleanFeature(BaseModel):
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
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | ShellFeature
    | DraftFeature
    | PatternFeature
    | ImportFeature
    | SheetMetalBaseFlangeFeature
    | SheetMetalEdgeFlangeFeature
    | SheetMetalHemFeature
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
    | LoftFeature
    | FilletFeature
    | ChamferFeature
    | ShellFeature
    | DraftFeature
    | PatternFeature
    | ImportFeature
    | SheetMetalBaseFlangeFeature
    | SheetMetalEdgeFlangeFeature
    | SheetMetalHemFeature
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
FEATURE_REGISTRY.register(ShellFeature)
FEATURE_REGISTRY.register(DraftFeature)
FEATURE_REGISTRY.register(PatternFeature)
FEATURE_REGISTRY.register(ImportFeature)
FEATURE_REGISTRY.register(SheetMetalBaseFlangeFeature)
FEATURE_REGISTRY.register(SheetMetalEdgeFlangeFeature)
FEATURE_REGISTRY.register(SheetMetalHemFeature)
FEATURE_REGISTRY.register(BooleanFeature)
FEATURE_REGISTRY.validate_chains()


# --- §2.2/§2.3 Reference helpers --------------------------------------------------


#: Feature types that produce/mutate the body chain — the acceptable targets of
#: a :class:`SubshapeRef` face reference (topo-naming §4: a face is named on a
#: body-affecting feature's result). ``datum``/``sketch`` are NOT body-affecting.
BODY_AFFECTING_FEATURE_TYPES = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "draft",
        "pattern",
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
    {"extrude", "revolve", "sweep", "loft", "import", "sheet_metal_base_flange"}
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
        case PatternFeature():
            # A pattern replicates the implicit body about world-space direction/
            # axis vectors (no picked sub-geometry — independent of #1); its
            # dependency on the prior body-affecting feature is tree order.
            pass
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
    sketch_diagnosis: SketchConstraintDiagnosis | None = Field(
        default=None,
        description="Typed over-constraint classification for the "
        '"sketch_conflicting" code: which constraints conflict vs. are redundant, '
        "so the sketcher reads the diagnosis by field instead of parsing "
        "``message`` (BACKLOG #6). None for non-sketch-conflict errors.",
    )


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
