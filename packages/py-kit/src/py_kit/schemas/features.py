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
from typing import Annotated, Any, Literal, Self, assert_never, get_args

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from py_kit.schemas.geometry import DEFAULT_LINEAR_DEFLECTION, ShapeProperties
from py_kit.schemas.sketch import SketchDefinition, SolvedSketch

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


#: Discriminated reference union. A ``subshape`` variant is reserved for the
#: Phase 2 topological-naming design (design §2.4) — additive, do not
#: implement yet.
GeomRef = Annotated[DatumPlaneRef | FeatureRef, Field(discriminator="kind")]


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


class SketchParamsV1(SketchDefinition):
    """Sketch on a plane — datum planes only in v1 (design §2.1).

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


# --- §1.3 Versioned envelopes ----------------------------------------------------


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


class FilletFeature(BaseModel):
    """``{"type": "fillet", "version": 1, "params": {...}}`` envelope."""

    type: Literal["fillet"]
    version: Literal[1]
    params: FilletParamsV1


#: Discriminated union of the CURRENT version of every feature type — this is
#: what the OpenAPI contract exports (design §1.4). Older stored versions are
#: upcast on read via :data:`FEATURE_REGISTRY`.
Feature = Annotated[
    SketchFeature | ExtrudeFeature | FilletFeature, Field(discriminator="type")
]

#: Plain (non-annotated) union alias for type annotations of validated values.
FeatureEnvelope = SketchFeature | ExtrudeFeature | FilletFeature


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
FEATURE_REGISTRY.register(SketchFeature)
FEATURE_REGISTRY.register(ExtrudeFeature)
FEATURE_REGISTRY.register(FilletFeature)
FEATURE_REGISTRY.validate_chains()


# --- §2.2/§2.3 Reference helpers --------------------------------------------------


def iter_feature_refs(value: Any) -> Iterator[FeatureRef]:
    """Every :class:`FeatureRef` reachable inside a validated model tree.

    Generic pydantic walk (models, lists, tuples, dict values) so extraction
    can never drift from the schema (design §2.3) — a new ref-bearing field
    is found without touching this function.
    """
    if isinstance(value, FeatureRef):
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
    (e.g. a sketch plane in v1 accepts datum planes only — design §2.1).
    """

    slot: str
    ref: FeatureRef
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
        case SketchFeature():
            if isinstance(feature.params.plane, FeatureRef):
                # v1 sketches sit on datum planes only; no feature type
                # produces a sketchable plane yet, so a FeatureRef here is
                # always invalid.
                references.append(
                    FeatureReference("plane", feature.params.plane, frozenset())
                )
        case ExtrudeFeature():
            references.append(
                FeatureReference(
                    "profile", feature.params.profile, frozenset({"sketch"})
                )
            )
        case FilletFeature():
            # No FeatureRef: fillet rounds the implicit single body chain
            # (design §7.6) and selects edges by a geometric predicate, not by
            # a per-feature subshape reference (design §2.4). Its ordering
            # dependency on the prior body-affecting feature is the tree order.
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
