"""Drawing boundary DTOs — sheets, views, dimensions, annotations + CRUD contract.

Implements docs/design/drawings.md §2 (the persisted shapes) — the single
source of truth (CLAUDE.md DRY rule): the documents service validates writes
and serves its drawing CRUD API with these models, the geometry service will
parse the generation request with the SAME models (§4/§5, a later slice), and
``just gen`` exports them to ``packages/contracts`` / ``packages/ts-client``.
Pure pydantic only — kernel types never appear here (CLAUDE.md service
boundaries).

A drawing is a LAYOUT (design §2.1) — sheets, each holding views + dimensions +
annotations that *reference* a part/assembly by id — NOT a part feature history
or an assembly graph. It is a first-class document type, sibling of part and
assembly, and reuses their PATTERNS (owner-scoped auth, uniform-404 visibility,
the ``doc_version`` optimistic-concurrency counter, cross-document 409-with-
dependents) but not their tables.

A DIMENSION names model geometry with the EXACT shipped topological-naming
machinery — :class:`~py_kit.schemas.features.EdgeSignature`, reused VERBATIM
(the same signature a ``concentric`` mate resolves for its axis and the
``/overlay`` pick surface emits — design §3.3), never a parallel taxonomy and
never an index into a projected-edge list (design §3.3 rejects (A)). The MEASURED
value is computed by the geometry service later; documents stores only the
reference + the dimension type + the authored 2D placement. Units are fixed per
field, encoded in field names (``offset_mm``, ``x_mm``) exactly as
:mod:`py_kit.schemas.geometry` does.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from py_kit.schemas.assemblies import (
    AssemblySolveDiagnosis,
    AssemblySolveStatus,
    BomLine,
    EvaluateAssemblyRequest,
    InstanceEvaluationError,
    MateEvaluationError,
    RefDocumentKind,
)
from py_kit.schemas.features import (
    MAX_TREE_FEATURES,
    EdgeSignature,
    EvaluatedFeatureInput,
    FeatureError,
    GeomRef,
    document_slug,
)
from py_kit.schemas.folders import FOLDER_ID_DESCRIPTION

#: Upper bound for a user-facing drawing name ("Bracket — Detail").
DRAWING_NAME_MAX_LENGTH = 200

# --- Per-request work bounds (engineering audit 2026-07-24 G2) -------------------
#
# The rate limiter caps request FREQUENCY; these constants cap the WORK one
# drawing evaluate/compose request can demand. Over-bound is a typed 422 at
# parse, never a worker OOM/monopolization.

#: Ceiling on views in one drawing evaluate/compose request. Exact HLR
#: (``HLRBRep_Algo``) runs PER VIEW — the expensive op — and a real sheet holds
#: a handful of views (the standard front/top/right/iso plus sections), so 32
#: is far beyond legitimate use while bounding the per-request HLR fan-out.
MAX_DRAWING_VIEWS = 32

#: Ceiling on dimensions in one drawing evaluate/compose request. Each is an
#: exact B-rep measurement + a placement pass; a dense production sheet runs
#: tens of dimensions, so 500 is generous.
MAX_DRAWING_DIMENSIONS = 500

#: Ceiling on note annotations in one compose request — placement/serialization
#: work only, same generous scale as dimensions.
MAX_DRAWING_ANNOTATIONS = 500

#: Ceiling on SHEETS in one drawing (engineering audit H5 — the bound G2 missed).
#: Every read of a drawing serializes its WHOLE sheet tree (``GET /drawings/{id}``
#: and the body of every delete route), so an unbounded sheet count is an
#: unbounded response — one POST per sheet until the document is unreadable and
#: unrecoverable except by deleting it. A real multi-sheet print set runs a
#: handful to a few dozen sheets, so 100 is far beyond legitimate use while
#: keeping the tree read bounded.
MAX_DRAWING_SHEETS = 100

#: Upper bound for a per-sheet name ("Sheet 1").
SHEET_NAME_MAX_LENGTH = 200

#: Upper bound for a title-block free-text field (design §9 open-q 6: v1 holds
#: free text; a structured/field-mapped title block is a fast-follow).
TITLE_BLOCK_FIELD_MAX_LENGTH = 500

#: Upper bound for a note annotation's text body.
NOTE_TEXT_MAX_LENGTH = 5000

#: Non-empty (post-strip), bounded drawing name.
DrawingName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=DRAWING_NAME_MAX_LENGTH
    ),
]

#: Non-empty (post-strip), bounded sheet name.
SheetName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=SHEET_NAME_MAX_LENGTH
    ),
]

#: A bounded title-block field (whitespace-trimmed; empty allowed → treated as
#: unset by the caller). Free text in v1 (design §9 open-q 6).
TitleBlockField = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=TITLE_BLOCK_FIELD_MAX_LENGTH),
]

#: Non-empty (post-strip), bounded note text.
NoteText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=NOTE_TEXT_MAX_LENGTH
    ),
]

#: Standard sheet sizes (ISO A-series + ANSI). What documents stores; the
#: composed artifact's physical extents are resolved geometry-side (design §4.2).
SheetSize = Literal[
    "A4", "A3", "A2", "A1", "A0", "ANSI_A", "ANSI_B", "ANSI_C", "ANSI_D"
]

#: Sheet orientation.
SheetOrientation = Literal["landscape", "portrait"]

#: Projection convention — third-angle (ISO default) vs first-angle. A SHEET
#: convention (design §1.2), NOT a projection difference: same projected edges,
#: different placement.
SheetProjectionConvention = Literal["third_angle", "first_angle"]

#: The standard orthographic + isometric projection directions a view stores
#: (design §2.2), plus ``flat_pattern`` — a sheet-metal body's unfold as a view
#: (sheet-metal.md §7). ``flat_pattern`` SKIPS HLR: a :class:`FlatPattern` is
#: already 2D, so geometry feeds its ``edge_role``-tagged outline straight into the
#: shipped :class:`ProjectedViewEdge` shape (never a projection frame). The
#: projection ENUM is ALL documents persists — mapping a standard direction to a 3D
#: frame + running HLR (or, for ``flat_pattern``, running the unfold) is the
#: geometry service's job (design §1.2 / sheet-metal.md §6/§7), never here.
#:
#: ``section`` is a full PLANAR section of a single-body part (drawings-section.md v1):
#: like ``flat_pattern`` it is NOT one of the third-angle quartet — it is placed by its
#: OWN evaluate + compose branch, and the cutting plane rides in a sibling
#: :class:`SectionViewParams` (the projection enum stays a pure direction; the plane is
#: geometry-resolved, never here).
ViewProjection = Literal["front", "top", "right", "iso", "flat_pattern", "section"]

#: An unfolded flat-pattern edge's ROLE (sheet-metal.md §6): a ``body`` edge is a
#: real cut outline; a ``bend`` edge is a fold line (rendered as its own dashed-blue
#: stroke, not a visible/hidden BODY-edge distinction). Additive to
#: :class:`ProjectedViewEdge` (defaulting ``body``), so every existing HLR view is
#: unaffected — the ONE new field the flat-pattern reuse needs (§6).
EdgeRole = Literal["body", "bend"]

#: A bend's fold sense in a flat pattern's bend table (sheet-metal.md §1/§6).
BendDirection = Literal["up", "down"]


class SectionViewParams(BaseModel):
    """The cutting plane + half selection of a section view (drawings-section.md §1).

    v1 specifies the section's cutting plane by DATUM REFERENCE, not a drawn cutting
    line (§1): ``plane`` is the shipped :data:`~py_kit.schemas.features.GeomRef`
    (``DatumPlaneRef`` for one of the XY/XZ/YZ origin planes, or a ``FeatureRef`` to
    an axis-aligned offset / midplane datum FEATURE in the referenced part) — the
    EXACT union a sketch's plane reference uses, so no parallel plane taxonomy is
    introduced (DRY). The geometry service resolves it, checks the v1 axis-aligned
    precondition (a non-principal normal is a typed ``section_plane_not_principal``,
    §7), cuts, and hatches. ``flip`` chooses which half is removed (§4): ``false``
    (default) removes the eye-side material (the standard "cut away what is between
    you and the plane"), ``true`` the far side.
    """

    plane: GeomRef = Field(
        description="The cutting plane, as a datum reference (reused GeomRef): a "
        "DatumPlaneRef (XY/XZ/YZ) or a FeatureRef to an axis-aligned offset/midplane "
        "datum. A non-principal-axis normal is out of v1 (typed error, §7)."
    )
    flip: bool = Field(
        default=False,
        description="Which half is removed (§4): false (default) removes the eye-side "
        "material; true the far side.",
    )


#: The v1 dimension set (design §3.1).
DimensionType = Literal["linear", "diameter", "radius", "angular"]

#: One of an edge signature's two canonically-ordered endpoints (design §3.3):
#: a point-to-point linear dimension names an edge + one of its ends, sidestepping
#: the unshipped bare-vertex signature (topological-naming Open Q 10).
DimensionEndpoint = Literal["end_a", "end_b"]


# --- sheet-space geometry -------------------------------------------------------


class SheetPoint(BaseModel):
    """A 2D point in SHEET space (mm), origin at the title-block corner (§9 q4).

    Sheet space is millimetres at 1:1; a view's scale maps model-mm → sheet-mm
    (design §9 open-q 4). Used for view placement, dimension text, and note
    positions. Full precision; a non-finite coordinate is a request-validation
    422 (``allow_inf_nan=False``), never a silently-defaulted position.
    """

    x_mm: float = Field(
        allow_inf_nan=False, description="X on the sheet, mm from the origin corner"
    )
    y_mm: float = Field(
        allow_inf_nan=False, description="Y on the sheet, mm from the origin corner"
    )


class ViewScale(BaseModel):
    """A view's drawing scale as an exact rational ``numerator:denominator``.

    Stored as two integers (design §2.2 ``scale_num``/``scale_den``) so the scale
    is EXACT — 1:2 is ``1/2``, never a lossy float. A model-mm length maps to
    ``length * numerator / denominator`` sheet-mm. Both are >= 1.
    """

    numerator: int = Field(ge=1, description="Scale numerator (1 for 1:N)")
    denominator: int = Field(ge=1, description="Scale denominator (N for 1:N)")


#: The default view scale — full size (1:1).
DEFAULT_VIEW_SCALE = ViewScale(numerator=1, denominator=1)


class TitleBlock(BaseModel):
    """Free-text title-block fields (design §9 open-q 6 — v1 holds free text).

    Every field is optional; a structured/field-mapped title block auto-filled
    from the referenced part is a fast-follow. The composed artifact stamps these
    geometry-side (design §4.2).
    """

    title: TitleBlockField | None = Field(default=None, description="Drawing title")
    author: TitleBlockField | None = Field(default=None, description="Author / drafter")
    date: TitleBlockField | None = Field(default=None, description="Free-text date")
    notes: TitleBlockField | None = Field(default=None, description="Free-text notes")


# --- how a dimension names model geometry (design §3.3) -------------------------
#
# A dimension names a MODEL edge with the shipped EdgeSignature (reused VERBATIM
# — the same fingerprint a `concentric` mate's axis and a picked-edge fillet use,
# topological-naming.md §10). The VIEW (via `view_id`) already scopes which part
# body the signature resolves against, so — unlike a mate's `MateAxisRef`, which
# must carry an `instance_id` — a dimension ref needs only the signature. The
# geometry service resolves it against the view's evaluated body and measures the
# value (design §3.3/§5); documents stores the reference only.


class DimensionEndpointRef(BaseModel):
    """One canonical endpoint of a model edge (design §3.3 point-to-point linear).

    ``endpoint`` selects ``end_a`` or ``end_b`` of the ``signature``'s
    canonically-ordered pair — a vertex named through an EDGE, so v1 needs no
    (unshipped) bare-vertex signature (topological-naming Open Q 10).
    """

    signature: EdgeSignature = Field(
        description="The model edge whose endpoint this names (reused EdgeSignature)"
    )
    endpoint: DimensionEndpoint = Field(
        description="Which canonical end of the edge (end_a / end_b)"
    )


class DimensionPlacement(BaseModel):
    """Authored 2D placement of a dimension on the sheet (design §3.1).

    Placement is AUTHORED data (which side of the geometry the dimension line +
    witness lines sit, and the text position); the measured VALUE is always taken
    from the model, never typed (a v1 drawing dimension is driven-by-geometry,
    never driving — design §3.1). ``offset_mm`` is the signed distance of the
    dimension line from the geometry in the view plane; ``text_pos`` optionally
    overrides the text placement.
    """

    offset_mm: float = Field(
        default=0.0,
        allow_inf_nan=False,
        description="Signed offset of the dimension line from the geometry (mm)",
    )
    text_pos: SheetPoint | None = Field(
        default=None, description="Optional text-position override (sheet mm)"
    )


# --- the v1 dimension set (design §3.1) -----------------------------------------


class EdgeLengthMeasurement(BaseModel):
    """Measure the length of a single model edge (design §3.1 linear)."""

    mode: Literal["edge_length"] = "edge_length"
    edge: EdgeSignature = Field(description="The model edge whose length is measured")


class PointToPointMeasurement(BaseModel):
    """Measure the distance between two model-edge endpoints (design §3.1/§3.3)."""

    mode: Literal["point_to_point"] = "point_to_point"
    a: DimensionEndpointRef = Field(description="First endpoint")
    b: DimensionEndpointRef = Field(description="Second endpoint")


#: Discriminated linear-measurement source: a single edge's length, OR the
#: distance between two edge-endpoints (design §3.1).
LinearMeasurement = Annotated[
    EdgeLengthMeasurement | PointToPointMeasurement, Field(discriminator="mode")
]


class LinearDimensionParams(BaseModel):
    """A linear dimension — an edge length or a point-to-point distance (§3.1)."""

    type: Literal["linear"] = "linear"
    measurement: LinearMeasurement = Field(
        description="What is measured (an edge's length or two endpoints)"
    )
    placement: DimensionPlacement = Field(
        default_factory=DimensionPlacement, description="Authored 2D placement"
    )


class DiameterDimensionParams(BaseModel):
    """A diameter dimension on a circular model edge (design §3.1).

    ``edge`` must resolve to a CIRCULAR edge (``curve == "circle"``) — the
    identical reuse a ``concentric`` mate makes for its axis (design §3.3), so one
    signature names a hole for both mating and dimensioning. The measured value
    (2·radius) is computed geometry-side.
    """

    type: Literal["diameter"] = "diameter"
    edge: EdgeSignature = Field(description="Circular model edge (curve == 'circle')")
    placement: DimensionPlacement = Field(
        default_factory=DimensionPlacement, description="Authored 2D placement"
    )


class RadiusDimensionParams(BaseModel):
    """A radius dimension on a circular / arc model edge (design §3.1)."""

    type: Literal["radius"] = "radius"
    edge: EdgeSignature = Field(description="Circular / arc model edge")
    placement: DimensionPlacement = Field(
        default_factory=DimensionPlacement, description="Authored 2D placement"
    )


class AngularDimensionParams(BaseModel):
    """An angular dimension between two straight model edges (design §3.1)."""

    type: Literal["angular"] = "angular"
    edge_a: EdgeSignature = Field(description="First straight model edge")
    edge_b: EdgeSignature = Field(description="Second straight model edge")
    placement: DimensionPlacement = Field(
        default_factory=DimensionPlacement, description="Authored 2D placement"
    )


#: Discriminated v1 dimension union (design §3.1). A richer dimension kind joins
#: additively (the feature-tree.md §1.4 discipline) with no version churn.
Dimension = Annotated[
    LinearDimensionParams
    | DiameterDimensionParams
    | RadiusDimensionParams
    | AngularDimensionParams,
    Field(discriminator="type"),
]

#: Plain (non-annotated) union alias for annotating validated values.
DimensionParams = (
    LinearDimensionParams
    | DiameterDimensionParams
    | RadiusDimensionParams
    | AngularDimensionParams
)


# --- dimension measurement (design §3 / §8 DoD) ---------------------------------
#
# The geometry service resolves a dimension's EdgeSignature ref(s) against the
# view's evaluated MODEL body and measures the TRUE value FROM THE MODEL (design
# §3.1) — never the foreshortened 2D projection. `linear`/`diameter`/`radius` are
# millimetres; `angular` is degrees (hence the explicit `unit`). `foreshortened`
# (design §3.2) is set when the measured feature is not parallel to the view plane:
# the value is STILL model-true, and the flag lets the UI warn "dimension this in a
# true-size view". A ref that no longer resolves is a typed `subshape_unresolved`,
# a congruent twin `subshape_ambiguous`, and a wrong-type ref (a diameter on a
# non-circular edge, an angular on a non-straight edge) `dimension_wrong_type` — the
# reused subshape resolution taxonomy, never a 500 (design §3.3 / §5).

#: Unit of a measured dimension value — millimetres (linear/diameter/radius) or
#: degrees (angular). Encoded explicitly so a consumer never guesses from `type`.
DimensionUnit = Literal["mm", "deg"]

#: HOW a dimension's model reference resolved against the rebuilt body
#: (topological-naming.md §11). ``exact``: the stored stage-1 signature matched
#: verbatim (a clean rebuild, or an edit that did not touch the measured feature).
#: ``durable``: the stored signature no longer matched — the edit CHANGED the very
#: feature being measured (the widened plate's overall-length edge, the resized
#: hole's rim) — and the reference was re-anchored on the rebuild-INVARIANT of its
#: curve kind (a straight edge's supporting line + overlapping span; a circular
#: edge's centre, plane and angular station). Either way the stamped value is
#: measured off the CURRENT body, so a design change re-measures instead of
#: destroying the dimension (audit N1).
DimensionAnchorTier = Literal["exact", "durable"]


class DimensionAnchor(BaseModel):
    """Where a measured dimension's reference(s) landed on the CURRENT body (§11).

    The re-anchoring result: ``tier`` says whether the stored stage-1 signature
    matched verbatim (``exact``) or had to be re-anchored on its curve-kind
    invariant (``durable``), and ``primary``/``secondary`` carry the CURRENT
    signatures of the edges the dimension now names — the primary being the
    dimension's main edge (the measured edge / the circle / ``edge_a`` / the first
    point-to-point endpoint's edge) and the secondary the second one where the
    dimension type has one (``edge_b``, the second endpoint's edge).

    They are what the composer matches against the PROJECTED edges, so an annotation
    lands on the geometry that is actually there after a rebuild rather than on the
    stale authored signature (which is exactly why a re-measured dimension used to
    still vanish from the sheet). A client may also persist them to heal the stored
    ref, and ``tier == "durable"`` is the honest signal that the reference moved.
    """

    tier: DimensionAnchorTier = Field(
        description="'exact' (stored signature matched verbatim) or 'durable' "
        "(re-anchored on the curve-kind rebuild invariant, §11)"
    )
    primary: EdgeSignature | None = Field(
        default=None,
        description="Current signature of the dimension's primary edge, or null "
        "when the dimension names no edge",
    )
    secondary: EdgeSignature | None = Field(
        default=None,
        description="Current signature of the dimension's second edge (angular "
        "`edge_b` / the second point-to-point endpoint's edge); null otherwise",
    )


class MeasuredDimension(BaseModel):
    """A dimension's value measured from the MODEL, or a typed resolution error.

    On success ``value`` + ``unit`` carry the model-true measurement and ``error``
    is null; ``foreshortened`` flags a feature not parallel to the view plane
    (design §3.2 — the value is still model-true). On failure ``value``/``unit``
    are null and ``error`` is a typed ``subshape_unresolved`` / ``subshape_ambiguous``
    / ``dimension_wrong_type`` (never a 500 — design §3.3). Mirrors the per-view
    :class:`DrawingViewResult` success/error envelope for a single dimension.
    """

    value: float | None = Field(
        default=None,
        description="Model-true measured value (mm for linear/diameter/radius, "
        "degrees for angular); null when `error` is set",
    )
    unit: DimensionUnit | None = Field(
        default=None, description="'mm' or 'deg'; null when `error` is set"
    )
    foreshortened: bool = Field(
        default=False,
        description="True when the measured feature is not parallel to the view "
        "plane (design §3.2). The value is STILL model-true; the flag warns the UI "
        "to dimension it in a true-size view.",
    )
    error: FeatureError | None = Field(
        default=None,
        description="Typed resolution failure (`subshape_unresolved` / "
        "`subshape_ambiguous` / `dimension_wrong_type`), or null on success",
    )
    anchor: DimensionAnchor | None = Field(
        default=None,
        description="Where the dimension's reference(s) landed on the CURRENT body "
        "(topological-naming §11) — the re-anchored signatures + whether the match "
        "was `exact` or `durable`. Null when the dimension could not be resolved at "
        "all (`error` set) or for a caller-synthesised value. Additive: a consumer "
        "that ignores it reads the same value it always did.",
    )


# --- annotations (design §2.2 — v1 minimal) -------------------------------------


class NoteAnnotationParams(BaseModel):
    """A free text note placed on the sheet (design §2.2 v1 minimal).

    v1 ships the ``note`` kind only (text + sheet position); a ``leader`` (a note
    with a pointer) joins additively later — hence :data:`Annotation` is a plain
    alias today (pydantic forbids a single-member discriminated union), promoted
    to a ``type``-discriminated union when the second kind lands.
    """

    type: Literal["note"] = "note"
    text: NoteText = Field(description="The note body")
    position: SheetPoint = Field(description="Anchor position on the sheet (mm)")


#: v1 annotation union — one member (``note``), so a plain alias (the same idiom
#: as :data:`~py_kit.schemas.features.Selector`).
Annotation = NoteAnnotationParams

#: Plain alias for annotating validated values (symmetry with DimensionParams).
AnnotationParams = NoteAnnotationParams


# --- CRUD / response DTOs (documents API + gateway aggregation) ------------------
#
# Mirror the assembly CRUD DTOs (AssemblyCreate/AssemblyResponse, …) including the
# `expected_version` optimistic-concurrency guard (stale write → 422, keeping 409
# unambiguous for the delete-with-dependents conflict — assemblies.md §1.2).


class DrawingCreate(BaseModel):
    """Create a drawing owned by the calling user (design §2.1)."""

    name: DrawingName = Field(
        description="Drawing name; unique per FOLDER (#WS2), whitespace-trimmed, "
        f"1-{DRAWING_NAME_MAX_LENGTH} characters"
    )
    folder_id: uuid.UUID | None = Field(
        default=None,
        description="File it into this folder on creation, or null (the default) "
        "to leave it unfiled at the root of its drawer. Present so filing inside "
        "a folder is ONE call: a create-then-move pair could fail between the "
        "two and leave the document somewhere the user did not put it. Must be "
        "the caller's own folder OF THIS DOCUMENT'S KIND.",
    )


class DrawingUpdate(BaseModel):
    """Rename a drawing. Bumps ``doc_version`` (any mutation bumps — §2.1)."""

    expected_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the doc_version the client last "
        "saw; a stale value is rejected 422 (design §2.1)",
    )
    name: DrawingName = Field(description="New drawing name")


class DrawingResponse(BaseModel):
    """A drawing header as stored — identity, ownership, and its OCC token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID = Field(description="Owning user id (gateway-verified)")
    folder_id: uuid.UUID | None = Field(default=None, description=FOLDER_ID_DESCRIPTION)
    doc_version: int = Field(
        description="Monotonic optimistic-concurrency counter (design §2.1)"
    )
    created_at: datetime
    updated_at: datetime


class DrawingListResponse(BaseModel):
    """The caller's drawings, oldest first (wrapper leaves room for paging)."""

    drawings: list[DrawingResponse]


class SheetCreate(BaseModel):
    """Add a sheet to a drawing (append at the tip; design §2.2)."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    name: SheetName = Field(description='Sheet name ("Sheet 1")')
    size: SheetSize = Field(default="A4", description="Sheet size (ISO / ANSI)")
    orientation: SheetOrientation = Field(
        default="landscape", description="Sheet orientation"
    )
    projection: SheetProjectionConvention = Field(
        default="third_angle",
        description="Projection convention (third-angle default, design §1.2)",
    )
    title_block: TitleBlock | None = Field(
        default=None, description="Free-text title block (design §9 q6)"
    )


class SheetUpdate(BaseModel):
    """Update a sheet's header (design §2.2). At least one field must be provided."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    name: SheetName | None = None
    size: SheetSize | None = None
    orientation: SheetOrientation | None = None
    projection: SheetProjectionConvention | None = None
    title_block: TitleBlock | None = Field(
        default=None,
        description="Replacement title block (None leaves it unchanged; clear via "
        "an empty TitleBlock)",
    )


class SheetResponse(BaseModel):
    """A sheet as stored (design §2.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    drawing_id: uuid.UUID
    name: str
    size: SheetSize
    orientation: SheetOrientation
    projection: SheetProjectionConvention
    title_block: TitleBlock | None
    order_index: int = Field(description="Stable sheet order (dense 0..n-1)")
    created_at: datetime
    updated_at: datetime


class ViewCreate(BaseModel):
    """Add a view referencing a part / assembly at a projection (design §2.2).

    ``ref_document_id`` is a cross-document reference, NOT an FK (design §2.2,
    identical to an assembly instance): documents enforces existence at write time
    and deleting the referenced document is a 409-with-dependents. v1 tracks the
    referenced document's TIP (``ref_pinned_version`` present but NULL — design
    §2.3, the schema is pin-ready). ``projection`` is the standard orthographic /
    iso direction (all documents stores — mapping it to a 3D frame + HLR is
    geometry's job). ``order_index`` is appended at the tip when omitted.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    ref_document_id: uuid.UUID = Field(
        description="The part / assembly document this view projects"
    )
    ref_document_kind: RefDocumentKind = Field(
        default="part",
        description="'part' (v1) or 'assembly' (assembly views are the fast-follow, "
        "design §7)",
    )
    projection: ViewProjection = Field(
        description="Projection direction (front / top / right / iso / flat_pattern / "
        "section)"
    )
    scale: ViewScale = Field(
        default=DEFAULT_VIEW_SCALE, description="Drawing scale (rational; 1:1 default)"
    )
    position: SheetPoint = Field(description="View placement on the sheet (mm)")
    auto_place: bool = Field(
        default=True,
        description="Placement mode (drawing-export.md §4.2, mirrors "
        ":class:`SheetViewPlacement`): True (default) = the composer DERIVES the "
        "anchor (bounds-aware auto-layout), so `position` rides along for "
        "persistence but does not drive anchoring; False = the composer HONORS "
        "`position` verbatim (the drag-to-place seam). Additive — an omitted value "
        "keeps the auto-layout behaviour byte-identical.",
    )
    section_params: SectionViewParams | None = Field(
        default=None,
        description="The cutting plane + flip for a `section` view (drawings-"
        "section.md §1); required iff `projection == 'section'`, NULL for every "
        "other view. "
        "Documents validates the ref shape and persists it as JSONB (the geometry "
        "service resolves + cuts).",
    )


class ViewUpdate(BaseModel):
    """Re-frame / re-scale / re-place a view (design §2.2).

    Every field is optional; at least one must be provided. Re-pointing the
    referenced document is NOT an update (it changes which body the view's
    dimensions resolve against) — that is a delete + recreate.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    projection: ViewProjection | None = None
    scale: ViewScale | None = None
    position: SheetPoint | None = None
    auto_place: bool | None = Field(
        default=None,
        description="Placement mode (mirrors :class:`SheetViewPlacement`): set False "
        "to PERSIST a dragged position so the composer honors `position` verbatim "
        "(the drag-to-place seam — typically sent alongside `position`); set True to "
        "return the view to bounds-aware auto-layout. Null (default) leaves the mode "
        "unchanged. At least one of the update fields must be provided.",
    )


class ViewResponse(BaseModel):
    """A view as stored (design §2.2)."""

    id: uuid.UUID
    sheet_id: uuid.UUID
    ref_document_id: uuid.UUID
    ref_document_kind: RefDocumentKind
    ref_pinned_version: int | None = Field(
        description="Pinned referenced-document version, or null = track tip. NULL "
        "in v1 (design §2.3 — the schema is pin-ready)."
    )
    projection: ViewProjection
    scale: ViewScale
    position: SheetPoint
    auto_place: bool = Field(
        default=True,
        description="Placement mode (mirrors :class:`SheetViewPlacement`): True "
        "(default) = the composer auto-places (bounds-aware); False = a persisted "
        "drag-to-place position the composer honors verbatim. Survives reload — the "
        "compose/export path threads it into `SheetViewPlacement.auto_place`.",
    )
    section_params: SectionViewParams | None = Field(
        default=None,
        description="The section view's cutting plane + flip (drawings-section.md §1); "
        "NULL for every non-section view",
    )
    order_index: int = Field(
        description="Stable view order on the sheet (dense 0..n-1)"
    )
    created_at: datetime
    updated_at: datetime


class DimensionCreate(BaseModel):
    """Add a dimension to a view (append at the tip; design §3).

    ``dimension`` is the discriminated :data:`Dimension` union; its geometry
    references (via :class:`~py_kit.schemas.features.EdgeSignature`) resolve
    against the view's referenced body geometry-side. ``order_index`` is stable
    per sheet, appended at the tip.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    dimension: Dimension = Field(description="The dimension (discriminated on `type`)")


class DimensionResponse(BaseModel):
    """A dimension as stored, with its params envelope reassembled (design §3)."""

    id: uuid.UUID
    sheet_id: uuid.UUID
    view_id: uuid.UUID
    order_index: int = Field(description="Stable per-sheet order (dense 0..n-1)")
    dimension: Dimension


class AnnotationCreate(BaseModel):
    """Add an annotation to a sheet (append at the tip; design §2.2)."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §2.1)"
    )
    annotation: Annotation = Field(description="The annotation (v1: a note)")


class AnnotationResponse(BaseModel):
    """An annotation as stored (design §2.2)."""

    id: uuid.UUID
    sheet_id: uuid.UUID
    order_index: int = Field(description="Stable per-sheet order (dense 0..n-1)")
    annotation: Annotation


# --- aggregate read + mutation responses ----------------------------------------


class SheetContent(BaseModel):
    """One sheet plus its views, dimensions, and annotations (design §2.2)."""

    sheet: SheetResponse
    views: list[ViewResponse]
    dimensions: list[DimensionResponse]
    annotations: list[AnnotationResponse]


class DrawingTreeResponse(BaseModel):
    """A drawing plus its full sheet → view/dimension/annotation tree + OCC token.

    The read model a client renders (design §2.2): the drawing header, its sheets
    in ``order_index`` order (each with its views/dimensions/annotations in
    ``order_index`` order), and the ``doc_version`` the client echoes as its next
    ``expected_version``.
    """

    drawing: DrawingResponse
    doc_version: int = Field(description="Echoed OCC token (== drawing.doc_version)")
    sheets: list[SheetContent] = Field(
        max_length=MAX_DRAWING_SHEETS,
        description="The drawing's sheets in order_index order, bounded by "
        "MAX_DRAWING_SHEETS (work bound, audit H5 — every drawing read serializes "
        "the whole tree). documents refuses to persist past the ceiling "
        "(`sheet_limit_exceeded` 422), so the bound can never make a stored "
        "drawing unreadable.",
    )


class SheetMutationResponse(BaseModel):
    """Result of a single-sheet mutation: the sheet + the new version."""

    sheet: SheetResponse
    doc_version: int


class ViewMutationResponse(BaseModel):
    """Result of a single-view mutation: the view + the new version."""

    view: ViewResponse
    doc_version: int


class DimensionMutationResponse(BaseModel):
    """Result of a single-dimension mutation: the dimension + the new version."""

    dimension: DimensionResponse
    doc_version: int


class AnnotationMutationResponse(BaseModel):
    """Result of a single-annotation mutation: the annotation + the new version."""

    annotation: AnnotationResponse
    doc_version: int


# --- §1.2/§4 view-evaluation contract (documents → geometry → gateway → web) -----
#
# Mirrors EvaluateTreeRequest / EvaluateAssemblyRequest (feature-tree §4 /
# assemblies §4): one transport-agnostic request/response pair, pure pydantic — no
# kernel/OCCT type crosses the boundary (CLAUDE.md). documents sends INTENT (the
# referenced part's ordered feature prefix + the requested standard views),
# geometry is the sole evaluator — it evaluates the part body ONCE (reusing
# ``evaluate_tree``) then runs exact HLR (``geometry.drawings.project_view``) per
# requested view — and the response is per-view canonically-ordered neutral 2D
# edges OR a typed per-view projection error. This is Drawings v1 slice #3 ("part
# → projected view geometry as a typed API response"); sheet auto-layout,
# dimension provenance/measurement (§3.3), and SVG export (§4) are later slices.

#: The neutral 2D primitive kinds an HLR-projected edge classifies into (design
#: §1.3) — the boundary twin of ``geometry.drawings.project.EdgePrimitive``. Real
#: lines and circles stay EXACT (a diameter dimension reads a true radius, §1.1);
#: only a genuinely free-form curve degrades to a sampled ``polyline``.
ProjectedEdgePrimitive = Literal["line", "circle", "arc", "polyline"]


class ProjectedPoint(BaseModel):
    """A 2D point of a projected view edge, in view-plane mm at the view's scale.

    View-local millimetres (model-mm x the view scale, design §9 q4) — NOT yet
    placed at a sheet position (sheet layout is a later slice). A projected edge's
    endpoints, midpoint, centre, and polyline sample points are all this type.
    """

    x_mm: float = Field(description="X in the view plane (mm, model-mm x scale)")
    y_mm: float = Field(description="Y in the view plane (mm, model-mm x scale)")


class SectionFaceLoop(BaseModel):
    """One section cross-section face as canonical projected boundary loops (§5/§6).

    A section view's cut face, projected into the view plane (view mm at the view's
    scale — the SAME frame as the view's ``edges``, so the hatch lands on the drawn
    outline). ``outer`` is the face's outer boundary; ``holes`` are its interior (bore)
    boundaries. Each loop is a closed polyline pinned to a deterministic start vertex
    and winding (outer CCW, holes CW in the view frame, drawings-section.md §6) so the
    payload is byte-stable regardless of OCCT's edge order. The compose layer generates
    the crosshatch from these loops (even-odd scanline clip: holes carve gaps); the
    projection layer stays purely geometry. Empty for every non-section view — additive,
    so existing views are unaffected (the ``bend_table`` pattern).
    """

    outer: list[ProjectedPoint] = Field(
        description="The face's outer boundary as a closed projected polyline"
    )
    holes: list[list[ProjectedPoint]] = Field(
        default_factory=list["list[ProjectedPoint]"],
        description="Interior (bore) boundaries, each a closed projected polyline",
    )


class ProjectedViewEdge(BaseModel):
    """One classified 2D edge of a projected view (design §1.3) — a neutral
    primitive, never a kernel handle (the boundary twin of
    ``geometry.drawings.project.ProjectedEdge``).

    ``visible`` distinguishes solid-drawn (``True``) from hidden/dashed (``False``,
    occluded). ``start``/``end`` are the canonical (orientation-independent)
    endpoints and ``midpoint`` a point ON the edge. ``center``/``radius`` are
    populated for ``circle``/``arc`` (a real projected circle a Ø/radius dimension
    reads off, §1.1); ``points`` holds the sampled vertices of a ``polyline``
    (empty for the analytic kinds). Edges arrive in the canonical total order
    (§1.4) — a consumer serialising them verbatim gets byte-deterministic output.
    """

    primitive: ProjectedEdgePrimitive = Field(description="Neutral 2D primitive kind")
    visible: bool = Field(
        description="True = solid (visible); False = dashed (hidden/occluded)"
    )
    start: ProjectedPoint = Field(description="Canonical first endpoint")
    end: ProjectedPoint = Field(description="Canonical second endpoint")
    midpoint: ProjectedPoint = Field(
        description="A point ON the edge (orientation-independent)"
    )
    center: ProjectedPoint | None = Field(
        default=None, description="Circle/arc centre (null for line/polyline)"
    )
    radius: float | None = Field(
        default=None, description="Circle/arc radius, mm x scale (null otherwise)"
    )
    points: list[ProjectedPoint] = Field(
        default_factory=list["ProjectedPoint"],
        description="Sampled polyline vertices (empty for line/circle/arc)",
    )
    edge_role: EdgeRole = Field(
        default="body",
        description="Outline role (sheet-metal.md §6): 'body' = a real cut edge "
        "(every HLR view edge, the default — additive so existing consumers are "
        "unaffected); 'bend' = a flat-pattern fold line, rendered as its own dashed-"
        "blue stroke rather than the visible/hidden BODY-edge styling. Orthogonal to "
        "`visible` (a bend line is neither a solid nor an occluded body edge).",
    )
    source_edge: EdgeSignature | None = Field(
        default=None,
        description="The MODEL edge this projected edge provenance-maps to (design "
        "§3.3) — the shipped EdgeSignature a dimension names (the SAME fingerprint a "
        "`concentric` mate and a picked-edge fillet use). Null when the edge has no "
        "single clean model source: a silhouette/outline edge (§1.5), a genuinely "
        "free-form projection, or an ambiguous coincident projection. A pick on a "
        "dimensionable edge yields this ref directly (design §3.3 / §5 form 1).",
    )
    dimensionable: bool = Field(
        default=False,
        description="True iff `source_edge` is a single unambiguous model edge, so a "
        "dimension may attach to this projected edge (design §3.3). False for "
        "silhouette/outline edges and ambiguous coincident projections — HONEST "
        "un-dimensionability rather than a wrong signature (§1.5).",
    )
    start_is_end_a: bool | None = Field(
        default=None,
        description="For a STRAIGHT dimensionable edge (design §3.3): True iff this "
        "edge's canonical `start` projected point corresponds to `source_edge`'s "
        "canonical `end_a` (False → `end_b`). The model→projected endpoint "
        "correspondence the lexicographic canonicalisation of `start`/`end` would "
        "otherwise drop — it lets a point-to-point linear dimension name the correct "
        "model endpoint (`DimensionEndpointRef.endpoint`) from a picked projected end "
        "WITHOUT re-deriving the view frame + projection. Null for a non-straight "
        "edge (circle/arc/polyline) or any edge with no single clean model source "
        "(silhouette/free-form/ambiguous, §1.5) — same optional-provenance style as "
        "`source_edge`.",
    )


class BendTableRow(BaseModel):
    """One row of a flat-pattern view's bend table (sheet-metal.md §6/§7).

    The shop's fold instructions for one bend line: a stable per-bend label
    (``bend_id``), its fold ``angle_deg`` and inner ``radius_mm``, the fold
    ``direction`` (up/down relative to the base flange), and the ``bend_allowance_mm``
    (``BA = angle_rad * (radius + K * thickness)``, §1 — the developed length the
    flat strip replaces). Every value is already computed by the unfold; documents
    stores none of it — it is derived geometry-side alongside the flat-pattern edges.

    Correlation to the drawing edges is POSITIONAL, not id-based:
    :class:`ProjectedViewEdge` carries no id, so the i-th ``edge_role="bend"`` edge
    (in the view's edge-list order) is this row's fold line — both the bend edges and
    this table are emitted in the same deterministic fold-position order (§6). A
    consumer keys a table row to its fold stroke by zipping the ``"bend"`` edges with
    ``bend_table`` in order, never by matching ``bend_id`` against an edge field.
    """

    bend_id: str = Field(
        description="Stable per-bend label (e.g. 'bend-1'); NOT an edge id — "
        "bend rows correlate to 'bend' edges positionally, in fold-position order (§6)"
    )
    angle_deg: float = Field(description="Fold angle (degrees)")
    radius_mm: float = Field(description="Inner bend radius (mm)")
    direction: BendDirection = Field(description="Fold sense up/down (§1)")
    bend_allowance_mm: float = Field(
        description="Bend allowance BA = angle_rad * (radius + K * thickness), mm (§1)"
    )


class DrawingViewResult(BaseModel):
    """One requested view's projection outcome inside a 200 (design §1.3/§1.5).

    On success, ``edges`` carries the view's canonically-ordered visible+hidden 2D
    edges and ``error`` is null. On an exact-HLR failure (a fragile body — tangent
    edges, self-intersections, §1.5), ``edges`` is empty and ``error`` is a typed
    ``view_projection_failed`` (the boundary form of
    ``geometry.drawings.ViewProjectionError``) — never a 500, never a silently
    empty success. A per-view failure NEVER fails the whole request; the other
    requested views still project (mirroring the per-feature/per-mate posture).

    For a ``flat_pattern`` view (sheet-metal.md §7) the SAME ``edges`` list carries
    the unfold's outline — cut edges as ``edge_role="body"``, fold lines as
    ``edge_role="bend"`` — and ``bend_table`` carries the per-bend fold data the
    frontend renders as an annotation table. ``bend_table`` is empty for every
    standard HLR view (additive — a non-sheet-metal consumer is unaffected). A
    ``flat_pattern`` asked of a non-sheet-metal body is a typed per-view
    ``flat_pattern_not_sheet_metal`` error, and an unresolvable bend a
    ``subshape_unresolved`` (never a wrong flat pattern — §5).
    """

    view: ViewProjection = Field(description="The projection direction of this view")
    scale: ViewScale = Field(description="The scale applied (echoes the request)")
    edges: list[ProjectedViewEdge] = Field(
        default_factory=list["ProjectedViewEdge"],
        description="Canonically-ordered visible+hidden 2D edges (empty on error)",
    )
    bend_table: list[BendTableRow] = Field(
        default_factory=list["BendTableRow"],
        description="Per-bend fold rows for a flat_pattern view (sheet-metal.md §6/"
        "§7); empty for every standard HLR view and on error",
    )
    section_faces: list[SectionFaceLoop] = Field(
        default_factory=list["SectionFaceLoop"],
        description="Cross-section boundary loops for a `section` view (drawings-"
        "section.md §5) — the region the compose layer hatches; empty for every "
        "standard HLR / flat_pattern view and on error (additive, existing views "
        "unaffected — the `bend_table` pattern).",
    )
    error: FeatureError | None = Field(
        default=None,
        description="Typed per-view failure (`view_projection_failed` for HLR, "
        "`flat_pattern_not_sheet_metal` / `subshape_unresolved` for a flat pattern, "
        "`section_plane_not_principal` / `section_plane_misses_body` / `section_empty` "
        "for a section), or null on success (design §1.5 / §7)",
    )


class DrawingDimensionInput(BaseModel):
    """A dimension to MEASURE against a view in a drawing-evaluate request (§3/§5).

    The evaluate-request analogue of a persisted :class:`DimensionResponse`: it
    pairs the authored dimension params with the ``view`` whose projection frame
    supplies the §3.2 foreshortening reference — the geometry-request twin of the
    ``view_id`` a stored dimension carries (here the standard :data:`ViewProjection`
    direction the evaluate request already projects). ``id`` is an OPTIONAL
    correlation token echoed back on the matching :class:`MeasuredDimensionResult`
    so the client maps a measured value onto the dimension it authored (documents'
    dimension id); a transient/library measurement may omit it. The measured VALUE
    is taken from the MODEL, never the projection (design §3.1) — ``view`` only sets
    the foreshortening flag, it never changes the value.
    """

    id: uuid.UUID | None = Field(
        default=None,
        description="Optional correlation id echoed on the result (the stored "
        "dimension id); null for a transient/library measurement",
    )
    view: ViewProjection = Field(
        description="Which requested view's frame measures it — supplies the §3.2 "
        "foreshortening reference only; the value is model-true regardless (§3.1)"
    )
    dimension: Dimension = Field(
        description="The dimension to measure (discriminated on `type`)"
    )


class MeasuredDimensionResult(BaseModel):
    """One requested dimension's measured outcome inside a 200 (design §3/§5).

    Pairs the echoed correlation ``id`` + the ``view`` it was measured in with the
    model-true :class:`MeasuredDimension` (value + unit + ``foreshortened``, OR a
    typed ``subshape_unresolved`` / ``subshape_ambiguous`` / ``dimension_wrong_type``
    error on its ``error`` channel). A per-dimension measurement failure is THAT
    dimension's typed error — never a 500, never a failure of the whole request or
    of any OTHER dimension/view — the same never-500 posture as the per-view
    :class:`DrawingViewResult` and the per-feature/per-mate strict-prefix rule.
    """

    id: uuid.UUID | None = Field(
        default=None,
        description="Echoed correlation id (matches the request input), or null",
    )
    view: ViewProjection = Field(
        description="The view direction this dimension was measured in"
    )
    measured: MeasuredDimension = Field(
        description="Model-true value + unit + foreshortened flag, or a typed error"
    )


class EvaluateDrawingViewsRequest(BaseModel):
    """Project a part into its requested standard drawing views (design §1.2/§4).

    documents sends INTENT — the referenced part's ordered, rollback-applied
    feature prefix (reusing the feature-tree §4 contract VERBATIM, so geometry
    stays the sole evaluator and no kernel body crosses) plus the standard views to
    project, the drawing scale, and (optionally) the drawing's dimensions to
    measure. geometry evaluates the part body ONCE (``evaluate_tree``) then runs
    exact HLR per requested view AND measures each dimension off the SAME exact body
    (design §3.1 — model-true, never the projection). Deterministic (RESEARCH §9):
    the same request yields byte-identical projected edges + measured values,
    in-process AND across an interpreter restart.
    """

    part_id: uuid.UUID = Field(description="The referenced part's identity (echoed)")
    tree_version: int = Field(description="Echoed back; cache/correlation key")
    features: list[EvaluatedFeatureInput] = Field(
        max_length=MAX_TREE_FEATURES,
        description="The part's ordered feature prefix (feature-tree §4 "
        "contract), bounded by MAX_TREE_FEATURES (work bound, audit G2)",
    )
    views: list[ViewProjection] = Field(
        max_length=MAX_DRAWING_VIEWS,
        description="The standard views to project (subset of front/top/right/iso); "
        "processed and returned in request order. Bounded by MAX_DRAWING_VIEWS "
        "(work bound, audit G2 — HLR runs per view).",
    )
    scale: ViewScale = Field(
        default=DEFAULT_VIEW_SCALE,
        description="Drawing scale (rational; 1:1 default) applied to every view",
    )
    dimensions: list[DrawingDimensionInput] = Field(
        default_factory=list["DrawingDimensionInput"],
        max_length=MAX_DRAWING_DIMENSIONS,
        description="Dimensions to measure against the evaluated body, each tagged "
        "with its view (design §3/§5), bounded by MAX_DRAWING_DIMENSIONS (work "
        "bound, audit G2). Empty (the default) → no measurement and the "
        "response is projected edges only, byte-for-byte the slice-#3 behaviour "
        "(fully backward-compatible).",
    )
    section_params: dict[int, SectionViewParams] = Field(
        default_factory=dict[int, "SectionViewParams"],
        description="Per-view section parameters, keyed by the INDEX into `views` of "
        "each `section` view (drawings-section.md §1). The `section` view at "
        "`views[i]` takes its cutting plane + flip from `section_params[i]`; a "
        "`section` view with no matching entry resolves to a typed "
        "`section_params_missing` (never a crash). Keyed PER-VIEW (not a single "
        "request-level value) so params bind to a SPECIFIC view and more than one "
        "section view is representable. Empty (the default) → no section view: a "
        "non-section request carries an empty map and behaves byte-for-byte as the "
        "pre-section state.",
    )


class EvaluateDrawingViewsResult(BaseModel):
    """Per-view projected geometry for a part, with an honest whole-part failure
    channel (design §1.5/§4).

    ``views`` carries one :class:`DrawingViewResult` per requested view, in request
    order — each either its canonically-ordered 2D edges or a typed per-view
    projection error. ``part_error`` is set ONLY when the part tree produced no
    body (a strict-prefix feature failure or a body-less tree): there is nothing to
    project, so ``views`` is empty and the failing feature's error rides here (the
    single-part analogue of the assembly per-instance ``no_body``). A feature/HLR
    failure is a 200 with a typed error, never a 500 — the py-kit error envelope
    stays reserved for transport/validation failures of this call itself.
    """

    part_id: uuid.UUID
    tree_version: int
    views: list[DrawingViewResult] = Field(
        default_factory=list["DrawingViewResult"],
        description="One result per requested view, in request order (empty when "
        "`part_error` is set)",
    )
    dimensions: list[MeasuredDimensionResult] = Field(
        default_factory=list["MeasuredDimensionResult"],
        description="One measured result per requested dimension, in request order "
        "(design §3/§5). Empty when no dimensions were requested or when "
        "`part_error` is set (no body to measure against).",
    )
    part_error: FeatureError | None = Field(
        default=None,
        description="Set when the part evaluated to no body (nothing to project or "
        "measure); `views` and `dimensions` are then empty (design §4)",
    )


# --- §4.2 server-composed export contract (drawing-export.md, Approach C) --------
#
# The load-bearing decision (drawing-export.md §"one placement source"): the
# geometry service OWNS drafting placement. `evaluate_drawing_views` (reused
# VERBATIM) supplies projected geometry + measured values; `place_sheet` then
# PLACES them on the sheet — view anchoring, extension/dimension lines, arrowheads,
# angular arc sweep, text position/angle, sibling-collision flip — producing a
# `ComposedSheet` of placed primitives in sheet-mm (SVG space, y-flip applied).
# Three pure serializers (`serialize_svg | serialize_pdf | serialize_dxf`) render
# that ONE model, so the artifact and the on-screen sheet share a single placement
# source (the `start_is_end_a` unification applied to placement). Kept GENERAL
# (per-view part intent, a `SheetLayout` that scales to multi-part/assembly)
# though v1 ships single-part / 4-standard-view / single-scale.

#: The composed-artifact formats (drawing-export.md §libraries). SVG is
#: dependency-free hand-emitted XML (DE-1a); PDF (reportlab, DE-2) and DXF (ezdxf,
#: DE-3) are later slices — the composer + `ComposedSheet` are format-agnostic.
ArtifactFormat = Literal["svg", "pdf", "dxf"]

#: Media type per artifact format. SVG is IANA ``image/svg+xml``; PDF
#: ``application/pdf``; DXF the widely-recognised ``image/vnd.dxf``.
ARTIFACT_MEDIA_TYPES: dict[ArtifactFormat, str] = {
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "dxf": "image/vnd.dxf",
}


def artifact_filename(title: str, artifact_format: ArtifactFormat) -> str:
    """A safe download basename for a composed artifact — ``<slug>.<ext>``.

    Delegates to the ONE slug rule (:func:`~py_kit.schemas.features.document_slug`
    — lower-case, non-alphanumeric runs → single hyphen, edges trimmed), which
    ports ``apps/web/src/drawing/exportSvg.ts::sanitizeDrawingFilename`` verbatim
    so the server-composed download and the client's own SVG export name a file
    identically, and which the part / assembly exports now share (audit N4). The
    ``drawing`` fallback is local: an unnameable DRAWING is a drawing, while an
    unnameable part falls back to its id. The suggested name only — the artifact
    bytes are format-determined by ``ARTIFACT_MEDIA_TYPES``.
    """
    return f"{document_slug(title) or 'drawing'}.{artifact_format}"


class SheetViewPlacement(BaseModel):
    """One view's placement on the sheet (drawing-export.md §4.2 SheetLayout).

    GENERAL per-view intent (multi-part/assembly ready): each placed view names
    its ``projection`` direction, its authored sheet ``position``, and its
    ``scale``.

    Placement is a two-mode contract (drawing-export.md §4.2, FINDINGS #6):

    * ``auto_place`` (default ``True``): the composer DERIVES the anchor. The
      standard front/top/right/iso quartet is laid out by ``boundsAwareLayout`` (the
      on-screen renderer's behaviour); an ADDITIVE ``section`` / ``flat_pattern``
      view is placed in a FREE slot that never overlaps the already-placed views
      (previously it was dropped dead-centre and collided with the quartet). Here
      ``position`` is carried for generality/persistence but does not drive anchoring.
    * ``auto_place = False``: the composer HONORS ``position`` verbatim — the view is
      centred at that authored sheet point. This is the seam a drag-to-place UI
      drives (the frontend follow-up): documents stores the dragged position and the
      backend respects it, so a hand-placed view lands exactly where authored.

    ``position`` (when honored) is the view CENTRE in sheet millimetres, y-UP from the
    bottom-left origin — the SAME frame the auto anchors use, so an authored and an
    auto-placed view are directly comparable. v1 ships the 4 standard views
    auto-placed at one shared scale.
    """

    projection: ViewProjection = Field(description="Projection direction of the view")
    position: SheetPoint = Field(description="Authored sheet position (mm)")
    scale: ViewScale = Field(
        default=DEFAULT_VIEW_SCALE, description="View scale (rational; 1:1 default)"
    )
    auto_place: bool = Field(
        default=True,
        description="True (default): the composer derives the anchor (bounds-aware "
        "for the standard quartet, a non-overlapping free slot for section/"
        "flat_pattern). False: honor `position` verbatim (the drag-to-place seam, "
        "FINDINGS #6). Additive — an omitted value keeps the auto-layout behaviour "
        "byte-identical.",
    )


class SheetLayout(BaseModel):
    """A sheet's layout for composition — size, orientation, title block, views.

    The sheet-side half of a :class:`ComposeDrawingRequest` (drawing-export.md
    §4.2): the physical sheet (``size``/``orientation``/``projection``), the
    title-block content, and the placed ``views``. ``title`` is the drawing name
    stamped in the title block (the on-screen sheet stamps the drawing NAME, not
    the free-text :class:`TitleBlock` fields, in v1). Kept general so a future
    multi-part / multi-scale sheet composes through the SAME model.
    """

    size: SheetSize = Field(default="A4", description="Sheet size (ISO / ANSI)")
    orientation: SheetOrientation = Field(
        default="landscape", description="Sheet orientation"
    )
    projection: SheetProjectionConvention = Field(
        default="third_angle",
        description="Projection convention (third-angle default, design §1.2)",
    )
    title: DrawingName = Field(
        description="Drawing name stamped in the title block (design §4.2)"
    )
    title_block: TitleBlock | None = Field(
        default=None, description="Free-text title block (design §9 q6; v1 unused)"
    )
    views: list[SheetViewPlacement] = Field(
        max_length=MAX_DRAWING_VIEWS,
        description="The placed views (which projections to compose + their "
        "order), bounded by MAX_DRAWING_VIEWS (work bound, audit G2)",
    )


class ComposeDrawingRequest(EvaluateDrawingViewsRequest):
    """Compose a drawing into a placed sheet + serialized artifact (design §4.2).

    Extends :class:`EvaluateDrawingViewsRequest` (the evaluate INPUTS — ``part_id``
    / ``tree_version`` / ``features`` / ``views`` / ``scale`` / ``dimensions`` are
    inherited VERBATIM, so composition reuses ``evaluate_drawing_views`` as its
    sole geometry source, no re-projection) with the ``layout`` (sheet + placed
    views) and the requested ``format``. The geometry service evaluates the part
    ONCE, places the sheet (``place_sheet``), and serializes to the requested
    artifact — deterministic (RESEARCH §9): same request ⇒ byte-identical artifact.

    **Assembly source (design §7, Drawings #4).** A view referencing an ASSEMBLY
    (not a single part) carries the resolved assembly graph in ``assembly`` — the
    reused :class:`~py_kit.schemas.assemblies.EvaluateAssemblyRequest` (instances +
    mates + version) documents resolves for the referenced assembly document. When
    ``assembly`` is set the geometry service projects the SOLVED assembly compound
    (``evaluate_assembly_drawing_views`` — the ``/drawing/assembly/evaluate``
    machinery) INSTEAD of a single part body, then folds the resulting per-view HLR
    edges into the sheet exactly as a part view (the SAME ``place_sheet``); the
    inherited part fields (``part_id`` / ``tree_version`` / ``features``) then carry
    the assembly's echoed id/version + an empty feature list and are not evaluated.
    ``None`` (the default) is a PART compose, byte-identical to the pre-assembly
    contract — the additive posture the ``section_params`` / notes fields carry.
    """

    layout: SheetLayout = Field(description="Sheet layout (size + title block + views)")
    assembly: EvaluateAssemblyRequest | None = Field(
        default=None,
        description="The resolved assembly graph for an ASSEMBLY-referencing view "
        "(design §7): geometry projects the solved assembly compound instead of a "
        "single part body, folding the per-view HLR edges into the sheet exactly as a "
        "part view. NULL (default) = a part compose (byte-identical to the "
        "pre-assembly contract); the inherited part fields are then ignored.",
    )
    annotations: list[Annotation] = Field(
        default_factory=list["Annotation"],
        max_length=MAX_DRAWING_ANNOTATIONS,
        description="Sheet annotations (v1: free-text notes) placed at their authored "
        "sheet positions; empty by default, bounded by MAX_DRAWING_ANNOTATIONS "
        "(work bound, audit G2). Composed onto the sheet + serialized in "
        "all three formats. Part of the content-addressed artifact cache key (DE-4), "
        "so a note edit misses the cache and recomposes.",
    )
    format: ArtifactFormat = Field(
        default="svg", description="Artifact format to serialize (svg | pdf | dxf)"
    )


# --- the composed (placed) sheet — sheet-mm primitives (drawing-export.md §4.2) --
#
# `ComposedSheet` is the PLACED-primitive model the three serializers render: every
# coordinate is in sheet millimetres in FINAL SVG space (y-DOWN, origin top-left —
# the view y-flip is already applied), so a serializer emits coordinates verbatim
# and never re-reasons about axes or reflected arc sweeps. It is a pure geometric
# description (no kernel type, no interactivity) — picks/hover/endpoint handles stay
# client-side over the neutral `ProjectedViewEdge` list. The placement math that
# produces it is ported faithfully from the shipped `apps/web/src/drawing/{layout,
# dimensions}.ts` (parity-gated).


class ComposedPoint(BaseModel):
    """A 2D point in FINAL sheet-SVG space (mm, y-DOWN, top-left origin)."""

    x_mm: float = Field(description="X on the sheet (mm, SVG space)")
    y_mm: float = Field(description="Y on the sheet (mm, SVG space, y-down)")


#: Shared help text for the placed-edge ``edge_role`` field — carried THROUGH
#: composition from the source :class:`ProjectedViewEdge` (sheet-metal.md §6/§7) so a
#: serializer / the frontend can style a flat-pattern ``bend`` fold line as its own
#: dashed-blue stroke rather than the visible/hidden BODY-edge styling. ``body`` (the
#: default) on every HLR view edge — additive, so a standard sheet composes identically.
_EDGE_ROLE_DESC = (
    "Outline role carried through composition (sheet-metal.md §6): 'body' (default, "
    "every HLR edge) or 'bend' (a flat-pattern fold line, styled as a distinct "
    "dashed-blue stroke). Orthogonal to `visible`."
)


class ComposedLineEdge(BaseModel):
    """A placed straight projected edge (sheet-mm SVG space)."""

    kind: Literal["line"] = "line"
    visible: bool = Field(description="True = solid; False = hidden (dashed)")
    x1: float
    y1: float
    x2: float
    y2: float
    edge_role: EdgeRole = Field(default="body", description=_EDGE_ROLE_DESC)


class ComposedCircleEdge(BaseModel):
    """A placed projected circle — exact (a Ø/radius dimension reads its radius)."""

    kind: Literal["circle"] = "circle"
    visible: bool = Field(description="True = solid; False = hidden (dashed)")
    cx: float
    cy: float
    r: float
    edge_role: EdgeRole = Field(default="body", description=_EDGE_ROLE_DESC)


class ComposedPolylineEdge(BaseModel):
    """A placed sampled edge (arc / free-form) as a polyline (sheet-mm SVG space)."""

    kind: Literal["polyline"] = "polyline"
    visible: bool = Field(description="True = solid; False = hidden (dashed)")
    points: list[ComposedPoint] = Field(description="Ordered vertices (SVG space)")
    edge_role: EdgeRole = Field(default="body", description=_EDGE_ROLE_DESC)


#: A placed view edge — the boundary twin of the frontend ``SvgEdge`` union.
ComposedEdge = Annotated[
    ComposedLineEdge | ComposedCircleEdge | ComposedPolylineEdge,
    Field(discriminator="kind"),
]


class ComposedHatchLine(BaseModel):
    """One crosshatch stroke of a placed section face (final sheet-SVG space)."""

    x1: float
    y1: float
    x2: float
    y2: float


class ComposedHatch(BaseModel):
    """A section view's placed crosshatch (drawings-section.md §5) — the parallel
    fill strokes of every cross-section face.

    Generated by :func:`geometry.drawings.compose.place_sheet`'s section branch: a set
    of parallel lines at the ANSI 45° angle and a fixed sheet-mm spacing, analytically
    clipped (even-odd scanline) to each face's outer loop minus its interior loops — so
    the hole is left blank. Every coordinate is in FINAL sheet-SVG space (mm, y-DOWN,
    top-left origin — the same space every other placed primitive uses), so a
    serializer draws each ``lines`` segment verbatim. Deterministic (§6): the loops,
    angle, spacing, and clip origin are pure functions of the projected geometry, so
    the same section ⇒ byte-identical strokes. Export-only in v1 (§5): the DOM sheet
    shows the section's edges + cut-face outline but no on-screen crosshatch.
    """

    lines: list[ComposedHatchLine] = Field(
        description="Clipped 45° crosshatch strokes (sheet-SVG space), scanline order"
    )


class ComposedDimLine(BaseModel):
    """One straight rule of a placed dimension (extension or dimension line)."""

    x1: float
    y1: float
    x2: float
    y2: float
    role: Literal["extension", "dimension"] = Field(
        description="`extension` = thin witness line; `dimension` = arrowed measure"
    )


class ComposedArrow(BaseModel):
    """A filled arrowhead triangle — tip + two barb wings, in order (SVG space)."""

    points: list[ComposedPoint] = Field(description="The three triangle vertices")


class ComposedDimText(BaseModel):
    """A placed dimension's stamped value — position, upright angle, label string."""

    x: float
    y: float
    angle: float = Field(description="Upright text angle (degrees)")
    value: str = Field(description="Stamped label ('Ø10.000' / '~40.000' / '90.0°')")


class ComposedMeasuredDimension(BaseModel):
    """A placed, measured dimension: rules + arrowheads + the stamped value."""

    kind: Literal["measured"] = "measured"
    dimension_id: uuid.UUID | None = Field(
        default=None, description="Correlation id (echoes the request), or null"
    )
    dimension_type: DimensionType = Field(description="linear/diameter/radius/angular")
    lines: list[ComposedDimLine] = Field(description="Extension + dimension lines")
    arrows: list[ComposedArrow] = Field(description="Filled arrowhead triangles")
    text: ComposedDimText = Field(description="The stamped value")
    foreshortened: bool = Field(
        default=False,
        description="True: model-true value, foreshortened drawn length (§3.2)",
    )


class ComposedDimensionError(BaseModel):
    """A placed dimension the model could not measure — an honest marker (§3.3).

    The marker glyph alone was a defect (audit N1): a 2.6 mm dashed circle holding a
    bare ``!`` tells a machinist nothing, and the exported PDF/DXF carried the same
    mark. So the placed error also carries ``message`` — a SHORT, upper-case sheet
    caption in plain words ("LINEAR DIM: REFERENCE LOST - RE-PICK THE EDGE") — and
    ``text``, where the serializers stamp it beside the marker. This is the
    dimension-level twin of the typed per-view reason :class:`ComposedView` stamps
    under a failed view (FINDINGS #15): the machine-readable ``code`` plus the human
    sentence, on the print itself.
    """

    kind: Literal["error"] = "error"
    dimension_id: uuid.UUID | None = Field(
        default=None, description="Correlation id (echoes the request), or null"
    )
    dimension_type: DimensionType = Field(description="linear/diameter/radius/angular")
    at: ComposedPoint = Field(description="Marker position (SVG space)")
    code: str = Field(description="Typed measurement-failure code (never a value)")
    message: str = Field(
        default="",
        description="Short plain-language sheet caption for the failure ('LINEAR "
        "DIM: REFERENCE LOST - RE-PICK THE EDGE'), stamped beside the marker so the "
        "print says WHY in words (audit N1). Empty = no caption (marker only).",
    )
    text: ComposedPoint | None = Field(
        default=None,
        description="Where the `message` caption is stamped (SVG space, baseline-"
        "left); null when there is no caption",
    )


#: A placed dimension — measured (full geometry) or a typed error marker.
ComposedDimension = Annotated[
    ComposedMeasuredDimension | ComposedDimensionError,
    Field(discriminator="kind"),
]


class ComposedView(BaseModel):
    """One placed view on the sheet — its edges, dimensions, caption (design §4.2).

    ``failed`` marks a view with no projection (an HLR failure or an absent
    result): the serializer stamps a "VIEW FAILED" placeholder at ``anchor`` and
    ``edges``/``dimensions`` are empty. ``anchor`` is the view-centre in SVG space
    (the placeholder + caption reference it); ``label``/``label_pos`` are the
    stamped caption ("FRONT") and its position.

    ``error`` carries the TYPED per-view failure through composition (FINDINGS #15):
    the :class:`~py_kit.schemas.features.FeatureError` (code + human message) from the
    source :class:`DrawingViewResult` — a ``view_projection_failed`` /
    ``section_plane_not_principal`` / ``section_empty`` /
    ``flat_pattern_not_sheet_metal`` / ``section_params_missing`` — so the sheet/print
    can show WHY a view is empty instead of a bare "VIEW FAILED". Null on success and
    on an ABSENT result (a requested view with no evaluation, ``failed`` set but no
    typed reason to carry).
    """

    projection: ViewProjection = Field(description="Projection direction")
    failed: bool = Field(description="True when the view has no projected geometry")
    error: FeatureError | None = Field(
        default=None,
        description="Typed per-view failure carried through composition (FINDINGS "
        "#15): the source view's FeatureError (code + message), so a failed view "
        "prints its reason instead of a bare 'VIEW FAILED'. Null on success or when "
        "the view had no evaluated result at all (no typed reason to carry).",
    )
    anchor: ComposedPoint = Field(description="View-centre in SVG space")
    label: str = Field(description="Caption text (e.g. 'FRONT')")
    label_pos: ComposedPoint = Field(description="Caption position (SVG space)")
    edges: list[ComposedEdge] = Field(
        default_factory=list["ComposedEdge"], description="Placed projected edges"
    )
    dimensions: list[ComposedDimension] = Field(
        default_factory=list["ComposedDimension"], description="Placed dimensions"
    )
    hatch: ComposedHatch | None = Field(
        default=None,
        description="A section view's placed crosshatch (drawings-section.md §5); null "
        "for every non-section view — additive, so a standard/flat-pattern view "
        "composes byte-identically (the `bend_table` pattern).",
    )


class ComposedTitleBlock(BaseModel):
    """The placed bottom-right title block (drawing-export.md §4.2).

    Geometry (box + the two internal rules) plus the stamped values: the always-on
    drawing ``title`` (truncated to fit), ``scale`` label and ``size`` display, plus
    the OPTIONAL free-text :class:`TitleBlock` fields ``author`` / ``date`` / ``notes``
    (each truncated to fit its cell, ``None`` when unset). The fixed captions ("TITLE" /
    "SCALE" / "SIZE" / "LOFT · PART DRAWING" and, for the optional fields, "DRAWN" /
    "DATE" / "NOTES") are the serializer's rendering constants (matching the on-screen
    title block). A ``None`` optional field is stamped by NO serializer — caption and
    value both omitted — so a title block with no free-text composes byte-identically to
    its pre-free-text golden (the additive posture the notes/bend-table fields carry).
    """

    x: float
    y: float
    width: float
    height: float
    split_x: float = Field(description="X of the vertical rule (left | right cells)")
    mid_y: float = Field(description="Y of the horizontal rule in the right cell")
    title: str = Field(description="Drawing title, truncated to fit the cell")
    scale: str = Field(description="Scale label ('1:1')")
    size: str = Field(description="Sheet size, display form ('A4', 'ANSI A')")
    author: str | None = Field(
        default=None,
        description="Author/drafter, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )
    date: str | None = Field(
        default=None,
        description="Free-text date, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes, truncated to fit; None (stamps nothing) when the "
        "authored field is unset or blank",
    )


class ComposedBendTable(BaseModel):
    """A flat-pattern sheet's placed bend-table annotation block (sheet-metal.md §6/§7).

    The shop's fold instructions for the placed flat blank, laid out as a quiet-corner
    block: the rectangle it occupies (``x``/``y``/``width``/``height`` in FINAL sheet-
    SVG space — y-down, top-left origin, the same space every other placed primitive
    uses) plus the per-bend ``rows`` (the :class:`BendTableRow` data the flat-pattern
    :class:`DrawingViewResult` already carries, passed through unchanged). The block is
    placed clear of the flat blank's drawn extent so it never overlaps the geometry.

    Correlation to the placed fold strokes is POSITIONAL (sheet-metal.md §6), never an
    id linkage: the i-th ``rows`` entry pairs with the i-th ``edge_role="bend"``
    :class:`ComposedEdge` of the flat-pattern view, both in the unfold's deterministic
    fold-position order. A consumer zips the ``"bend"`` edges with ``rows`` in order.
    """

    x: float = Field(description="Block left edge (mm, SVG space)")
    y: float = Field(description="Block top edge (mm, SVG space, y-down)")
    width: float = Field(description="Block width (mm)")
    height: float = Field(description="Block height (mm)")
    rows: list[BendTableRow] = Field(
        description="Per-bend fold rows, in fold-position order (positionally paired "
        "with the flat-pattern view's `edge_role='bend'` edges, §6)"
    )


class ComposedNote(BaseModel):
    """A placed free-text note annotation (design §2.2 v1 — text at a sheet point).

    The composed twin of :class:`NoteAnnotationParams`: the note ``text`` and its
    anchor ``x``/``y`` in FINAL sheet-SVG space (mm, y-DOWN, top-left origin — the
    same space every other placed primitive on :class:`ComposedSheet` uses), so a
    serializer stamps it verbatim (no re-reasoning about axes). The three serializers
    render it as left-anchored graphite-ink text, consistent with the title-block
    stamped values. Additive to the sheet: an empty ``notes`` list emits nothing, so a
    sheet with no notes composes byte-identically to its pre-notes golden. A note whose
    anchor falls outside the sheet is placed verbatim (clipped by the viewer), the same
    honest posture as a title-block text run — never a crash.
    """

    x: float = Field(description="Note anchor X (mm, SVG space)")
    y: float = Field(description="Note anchor Y (mm, SVG space, y-down)")
    text: str = Field(description="The note body, rendered verbatim")


#: Sheet-level layout problem kinds (audit N2). ``views_overlap``: two placed views'
#: ink boxes intersect — the sheet is unreadable and MUST NOT ship silently.
#: ``views_crowded``: they clear, but by less than the documented minimum clearance
#: (:data:`~geometry.drawings.compose.MIN_VIEW_CLEARANCE_MM`) — legible today,
#: one design change away from colliding (the 0.70 mm near-tangency the audit
#: measured before the widening).
LayoutIssueCode = Literal["views_overlap", "views_crowded"]

#: Severity of a :class:`ComposedLayoutIssue`. ``error``: the sheet is not
#: shop-readable (overlapping views); ``warning``: readable but fragile.
LayoutIssueSeverity = Literal["error", "warning"]


class ComposedLayoutIssue(BaseModel):
    """Two placed views that collide, or nearly do (audit N2).

    Auto-layout used to pack the standard quartet to near-tangency and then export
    the collision that the next design change produced — an overlapping print,
    silently, in SVG/PDF/DXF alike. Composition now MEASURES every pair of placed
    views and reports what it found here, in millimetres, and the serializers stamp
    the issues as a banner on the sheet so a colliding print is never silent.

    ``views`` names the two projections; ``overlap_x_mm``/``overlap_y_mm`` are the
    signed gaps between their ink boxes on each axis — POSITIVE where the boxes
    overlap on that axis, NEGATIVE (a clearance) where they do not. Boxes overlap
    only when BOTH are positive; ``clearance_mm`` is then 0.0 and otherwise the true
    (smallest-axis) white gap between them.
    """

    code: LayoutIssueCode = Field(description="views_overlap | views_crowded")
    severity: LayoutIssueSeverity = Field(description="error | warning")
    views: list[ViewProjection] = Field(
        min_length=2,
        max_length=2,
        description="The two colliding/crowded projections, in canonical order",
    )
    overlap_x_mm: float = Field(
        description="Signed X-axis overlap (mm): positive = the boxes overlap in X, "
        "negative = that much X clearance"
    )
    overlap_y_mm: float = Field(
        description="Signed Y-axis overlap (mm): positive = overlap, negative = "
        "clearance"
    )
    clearance_mm: float = Field(
        description="White gap between the two boxes (mm); 0.0 when they overlap"
    )
    message: str = Field(
        description="Plain-language sheet caption ('TOP / ISOMETRIC VIEWS OVERLAP BY "
        "6.33 x 60.00 MM - REPOSITION BEFORE RELEASE')"
    )
    at: ComposedPoint = Field(
        description="Where the serializers stamp this line of the sheet banner (SVG "
        "space, baseline-left) — placement stays the composer's job (design §4.2)"
    )


# --- the thread schedule: a tapped hole reaching the PRINT (BACKLOG #50) ---------
#
# `19c9dc2` shipped cosmetic threads: the kernel bores the ISO tap-drill diameter and
# carries a typed designation, the editor shows it and the feature tree badges it —
# and it reached NO output. A tapped hole's solid is byte-identical to its bore, so
# until the designation is STAMPED ON THE PRINT the shop cannot tell an M6 tapped hole
# from a 5 mm drilled one, and the part is manufactured wrong. `ebeab51` corrected the
# checkbox copy so it stopped promising a drawing note (the honest stopgap); this is
# the note.
#
# What it carries, and why those three columns: the DESIGNATION is what the drawing
# calls out, the QUANTITY is what the shop counts, and the TAP DRILL is the number the
# machinist actually sets up (it is not the designation, and deriving it by hand from a
# table is where mistakes happen). All three are DERIVED from the feature params at
# compose time — never stored, so a re-tapped hole can never leave a stale callout on
# the next print (the assembly-BOM "derived, never stored" posture).
#
# Deliberately NOT done, with the reasons, so a later reader does not mistake omission
# for oversight:
#
# * **A BOM column.** The assembly/drawing BOM is one line per referenced DOCUMENT
#   (`BomLine`: ref id + name + quantity). A thread lives on a FEATURE inside a part,
#   and a part with four M6 and two M8 tapped holes has no single thread value — the
#   column would be blank or wrong for exactly the parts that have threads, which is
#   the overstated-surface defect this work exists to remove. The per-part, per-
#   designation shape the data actually has is this schedule. (A FASTENER BOM — where
#   the line IS a screw and "M6x1x20" is its identity — is a different, real feature;
#   it needs a fastener library, not a column.)
# * **A STEP annotation.** Semantic threads ride AP242 PMI (`applied_group_assignment`
#   over a shape-aspect), which OCCT's writer does not emit and no AP214 export can
#   express at all. Writing raw PMI entities by hand into a file OCCT produced would be
#   an unvalidated hand-assembled part-21 fragment that most receivers ignore — cost
#   far above zero, benefit near it. The bore we DO write is the manufactured feature
#   (a thread is cut by a tap, not the mill), and the drawing is the document that
#   carries the callout, which is exactly how the incumbents ship cosmetic threads.


class ThreadCalloutRow(BaseModel):
    """One line of the thread schedule — a designation, its count, its tap drill."""

    designation: str = Field(
        description='Drawing designation, ASCII ("M6x1") — the kernel\'s '
        "`format_designation`, never re-derived here"
    )
    quantity: int = Field(
        ge=1, description="How many holes in the part carry this designation"
    )
    tap_drill_mm: float = Field(
        gt=0,
        description="ISO recommended tap drill (nominal - pitch, mm) — the "
        "diameter the kernel actually bored, and what the shop sets up",
    )


class ComposedThreadSchedule(BaseModel):
    """The placed thread-schedule block — anchor rect + rows (BACKLOG #50).

    The bottom-left twin of the flat-pattern bend table (top-left) and the title
    block (bottom-right): a bordered box of derived rows, in sheet-mm SVG space,
    rendered identically by all three serializers.
    """

    x: float = Field(description="Block left edge (mm, SVG space)")
    y: float = Field(description="Block top edge (mm, SVG space, y-down)")
    width: float = Field(description="Block width (mm)")
    height: float = Field(description="Block height (mm)")
    rows: list[ThreadCalloutRow] = Field(
        description="One row per distinct designation, in the part's TREE order of "
        "first appearance (never request-array order — RESEARCH §9)"
    )


class ComposedSheet(BaseModel):
    """A fully placed drawing sheet — the model the three serializers render (§4.2).

    Every coordinate is sheet-mm in final SVG space (y-down, top-left origin). The
    product of ``geometry.drawings.compose.place_sheet`` — a pure function of the
    evaluated geometry + the :class:`SheetLayout` (deterministic, RESEARCH §9). The
    paper + border rectangles are pure functions of ``width_mm``/``height_mm``/
    ``margin_mm`` (the serializer derives them), keeping this model lean.
    """

    width_mm: float = Field(description="Sheet width (mm) — the SVG viewBox width")
    height_mm: float = Field(description="Sheet height (mm) — the SVG viewBox height")
    margin_mm: float = Field(description="Border inset from the sheet edge (mm)")
    title: str = Field(description="Drawing name (metadata / accessible label)")
    scale_label: str = Field(description="The sheet scale label ('1:1')")
    views: list[ComposedView] = Field(
        default_factory=list["ComposedView"],
        description="Placed views in canonical (front/top/right/iso) order",
    )
    title_block: ComposedTitleBlock = Field(description="The placed title block")
    bend_table: ComposedBendTable | None = Field(
        default=None,
        description="A flat-pattern sheet's placed bend-table block (rows + anchor "
        "rect, sheet-metal.md §7); null for every standard (HLR) sheet — additive, so "
        "a standard sheet composes byte-identically.",
    )
    notes: list[ComposedNote] = Field(
        default_factory=list["ComposedNote"],
        description="Placed free-text note annotations (design §2.2), each stamped at "
        "its sheet anchor; empty for a sheet with no notes — additive, so a note-free "
        "sheet composes byte-identically to its pre-notes golden.",
    )
    layout_issues: list[ComposedLayoutIssue] = Field(
        default_factory=list["ComposedLayoutIssue"],
        description="Measured view-collision diagnostics (audit N2): overlapping or "
        "sub-clearance view pairs, each with millimetre numbers and a plain-language "
        "message. EMPTY for a clean sheet — additive, so a clean sheet composes "
        "byte-identically. Non-empty ⇒ the serializers stamp a banner on the print.",
    )
    thread_schedule: ComposedThreadSchedule | None = Field(
        default=None,
        description="The placed THREAD SCHEDULE block (BACKLOG #50) — one row per "
        "distinct tapped-hole designation in the part, with its quantity and tap "
        "drill. Null for a part with no tapped hole — additive, so an untapped "
        "sheet composes byte-identically to its pre-thread golden.",
    )


# --- §7 assembly-view projection contract (documents → geometry → gateway → web) --
#
# The assembly analogue of EvaluateDrawingViewsRequest (design §7): where the part
# request carries ONE feature tree, an assembly view projects the UNION of every
# instance's body at its SOLVED world placement. The request REUSES the shipped
# EvaluateAssemblyRequest VERBATIM (instances + mates + version — no duplication of
# the instance/mate shape, CLAUDE.md DRY), so geometry solves the assembly (the SAME
# solve_assembly the evaluate/interference/export routes call), places each instance
# body, composes ONE compound, and runs the SAME exact HLR (project_view) per view.
# The projected edges are the identical neutral ProjectedViewEdge shape a part view
# emits, so a drawing consumer renders assembly + part views through one code path.
# Standard orthographic + iso views only (front/top/right/iso); flat_pattern / section
# are part-body view kinds and are a typed per-view error for an assembly (§7).


class EvaluateAssemblyDrawingViewsRequest(BaseModel):
    """Project a solved ASSEMBLY into its requested standard drawing views (§7).

    documents sends INTENT — the assembly graph (via the reused
    :class:`~py_kit.schemas.assemblies.EvaluateAssemblyRequest`: each instance's
    part feature prefix + authored/grounded placement + the mate graph) plus the
    standard views to project and the drawing scale. geometry is the sole evaluator:
    it solves the assembly ONCE (``solve_assembly`` — each unique part evaluated
    once, the mate graph solved to per-instance world placements), places every
    bodied instance at its SOLVED world pose, composes them into one compound, and
    runs exact HLR (``project_view``) per requested view. No kernel/OCCT type crosses
    the boundary — the response is the same pure-pydantic :class:`ProjectedViewEdge`
    list a part view emits. Deterministic (RESEARCH §9): the BLAS-pinned solve + the
    canonical HLR edge order yield byte-identical projected edges for the same request,
    in-process AND across an interpreter restart.
    """

    assembly: EvaluateAssemblyRequest = Field(
        description="The assembly graph to project (reused VERBATIM — instances + "
        "mates + version); geometry solves it with the SAME solve_assembly the "
        "evaluate/interference/export routes use"
    )
    views: list[ViewProjection] = Field(
        max_length=MAX_DRAWING_VIEWS,
        description="The standard views to project (subset of front/top/right/iso); "
        "processed and returned in request order, bounded by MAX_DRAWING_VIEWS "
        "(work bound, audit G2). `flat_pattern` / `section` are "
        "part-body view kinds — a typed per-view error for an assembly (§7)",
    )
    scale: ViewScale = Field(
        default=DEFAULT_VIEW_SCALE,
        description="Drawing scale (rational; 1:1 default) applied to every view",
    )


class EvaluateAssemblyDrawingViewsResult(BaseModel):
    """Per-view projected geometry for an assembly, plus the solve context (§7).

    ``views`` carries one :class:`DrawingViewResult` per requested view, in request
    order — each either the assembly's canonically-ordered visible+hidden 2D edges
    (the union of every placed instance's silhouettes, hidden lines where one
    instance occludes another) or a typed per-view error (``view_projection_failed``
    for an HLR failure, ``assembly_view_unsupported_projection`` for a flat_pattern /
    section view kind). ``assembly_error`` is set ONLY when NO instance produced a
    body (nothing to project); ``views`` is then empty (the assembly analogue of the
    part ``part_error``). ``status`` / ``diagnosis`` / ``instance_errors`` /
    ``mate_errors`` echo the SAME solve context ``evaluate_assembly`` reports, so a
    bad instance or mate is a typed per-entry error inside a 200 — never a 500, never
    a silently-empty view (design §4/§7).
    """

    assembly_id: uuid.UUID
    version: int = Field(description="Echoed back; cache/correlation key")
    views: list[DrawingViewResult] = Field(
        default_factory=list["DrawingViewResult"],
        description="One result per requested view, in request order (empty when "
        "`assembly_error` is set)",
    )
    status: AssemblySolveStatus = Field(
        description="The mate-solve status (echoes the evaluate route, design §4)"
    )
    diagnosis: AssemblySolveDiagnosis | None = Field(
        default=None, description="Under/over-constrained diagnosis, or null"
    )
    instance_errors: list[InstanceEvaluationError] = Field(
        default_factory=list["InstanceEvaluationError"],
        description="Per-instance body-evaluation failures (a bodyless part is "
        "DROPPED from the projection, the rest still project) — typed, never a 500",
    )
    mate_errors: list[MateEvaluationError] = Field(
        default_factory=list["MateEvaluationError"],
        description="Per-mate resolution failures dropped from the solve (design §4)",
    )
    assembly_error: FeatureError | None = Field(
        default=None,
        description="Set when NO instance produced a body (nothing to project); "
        "`views` is then empty (the assembly analogue of the part `part_error`)",
    )


# --- §7 BOM — a drawing's item list, DERIVED from the assembly it drafts ----------
#
# THE identity decision (design §7.1, Drawings #4 BOM slice): an item number is
# **derived, never stored**. A drawing does not persist "part X is item 3" — it
# persists nothing at all about the BOM; the numbered list is recomputed from the
# assembly's own stable instance order on every read. This is §3.3's rejected-(A)
# argument applied one document up: storing an index into a list somebody else owns
# is the silent-drift defect class. The consequences are stated, not hidden:
#
# * numbering is FIRST-APPEARANCE over the assembly's `order_index` (its stable
#   display/BOM order), NOT the name-sorted order `GET /assemblies/{id}/bom`
#   reports — so RENAMING a part never renumbers a released print, while adding /
#   removing / reordering an instance does (a real change the drafter made);
# * the assembly is tracked at TIP (§2.3, `ref_pinned_version` is NULL in v1), so
#   `assembly_version` is echoed on every read: a client that cached a BOM can see
#   the source moved under it. Pinning flips this additively with the versioning
#   item, exactly as views/assemblies do;
# * a document deleted while still instanced stays a line with `missing` true and a
#   null name (the shipped `BomLine` honesty, reused verbatim) — the quantity never
#   silently vanishes.


class DrawingBomLine(BomLine):
    """One NUMBERED line of a drawing's bill of materials (design §7 BOM).

    The shipped assembly :class:`~py_kit.schemas.assemblies.BomLine` (group key +
    resolved name + `missing` + quantity, reused VERBATIM — no parallel taxonomy)
    plus the one thing a *drawing* adds: the ``item_number`` a balloon stamps.

    ``item_number`` is **derived**, not authored: lines are numbered 1..n in the
    order each referenced document FIRST appears in the assembly's stable instance
    ``order_index``. It is therefore a pure function of the assembly graph — two
    reads of an unchanged assembly number identically, and a part RENAME (which
    re-sorts the name-ordered assembly BOM) leaves every number untouched.
    """

    item_number: int = Field(
        ge=1,
        description="1-based item number, DERIVED from the assembly's stable "
        "instance order (first appearance of this referenced document) — never "
        "stored on the drawing, so it can never drift from the assembly",
    )


class DrawingBomResponse(BaseModel):
    """A drawing sheet's bill of materials — the item list a balloon numbers (§7).

    A pure READ MODEL (no table, no migration): the sheet's single source document
    (the enforced one-sheet-one-source invariant, §2.2) must be an ASSEMBLY, and its
    DIRECT instances are rolled up into numbered :class:`DrawingBomLine` s. FLAT —
    a rigid sub-assembly instance is one ``kind: "assembly"`` line, never expanded
    (the same v1 bound the assembly BOM states; recursive/indented is a follow-up).

    A sheet drafting a PART has no bill of materials: that is a typed
    ``drawing_bom_source_not_assembly`` 422, not a 200 with an empty list — an empty
    BOM would read as "this assembly has no parts", which is a different and false
    statement (the honest-degradation posture the whole drawings pillar takes).

    ``assembly_version`` is the source assembly's ``doc_version`` AT READ TIME. v1
    tracks the assembly TIP (§2.3), so this is the staleness handle: a client that
    balloons a sheet and later reads a different ``assembly_version`` knows the item
    list may have renumbered, without the numbers themselves ever having been stored
    and gone quietly wrong.
    """

    drawing_id: uuid.UUID
    sheet_id: uuid.UUID = Field(description="The sheet whose source was rolled up")
    assembly_id: uuid.UUID = Field(description="The assembly this sheet drafts")
    assembly_version: int = Field(
        ge=0,
        description="The source assembly's `doc_version` at read time — the "
        "staleness handle for a tip-tracking (unpinned) view, §2.3",
    )
    lines: list[DrawingBomLine] = Field(
        default_factory=list["DrawingBomLine"],
        description="One numbered line per referenced document, in derived "
        "`item_number` order (an assembly with no instances yields an empty list)",
    )
    total_instances: int = Field(
        ge=0, description="Sum of every line's quantity (direct-instance count)"
    )
