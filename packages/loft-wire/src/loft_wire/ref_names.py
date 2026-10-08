"""History names for picks stored before they existed (DESIGN-INTENT-BACKFILL).

A pick made since DESIGN-INTENT-REFS (2026-10-01) stores a ``topo_name`` beside
its geometric signature, so a dimension edit that moves the subshape still
finds it (RESEARCH §14). A pick stored before that, a Hole rim picked before
HOLE-NAMES, or an old ``.loft`` import has none, and loses the subshape on the
first size edit. The backfill names each such pick ONCE, while it still
resolves EXACTLY at the part's current sizes: the geometry service rebuilds the
tree cold, and for each unnamed reference whose strict signature tier pins one
subshape it reports the names the pick side would stamp today. Documents writes
them, under the part-row lock, only into fields that are still null.

The wire half lives here so documents (which may not import the kernel) and
geometry (which may not touch Postgres) agree on three things by construction:

* WHERE a reference is: a JSON pointer into the feature's ``params``
  (:func:`iter_subshape_ref_paths`), the same walk as
  :func:`~loft_wire.features.iter_feature_refs`, so a ref-bearing field added
  later is found without touching this module (census-tested);
* WHICH stored signature a name was computed for: :func:`signature_digest`, so
  a pick re-made between the geometry run and the write is left alone;
* HOW a name is written: :func:`apply_ref_names`, a pure function that only
  ever fills a null field and never touches a geometric one.

Only ``named`` outcomes carry names. Everything else is the honest reason a
pick got none: a non-exact match (``not_exact:<tier>``: the part was edited
since the pick, so the subshape the pick meant is a guess and is never named),
``unresolved`` / ``ambiguous`` (as the strict tier sees it), ``no_name`` (the
subshape has no history name, e.g. an imported body), ``name_not_unique`` (the
name would not pin the same subshape on its own), or ``not_evaluated`` (the
feature never ran: suppressed, or after a failure).
"""

import copy
import hashlib
import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from loft_wire.features import EvaluateTreeRequest, SubshapeRef
from loft_wire.signatures import TOPO_NAME_MAX_LENGTH, EdgeSubshapeRef

#: Why a reference did or did not get a name. ``named`` is the only outcome
#: that writes anything.
RefNameOutcomeKind = Literal[
    "named",
    "already_named",
    "not_exact:durable",
    "not_exact:adjacent",
    "not_exact:named",
    "unresolved",
    "ambiguous",
    "no_name",
    "name_not_unique",
    "not_evaluated",
]

#: Every outcome, in a fixed order (metrics labels, reports).
REF_NAME_OUTCOMES: tuple[RefNameOutcomeKind, ...] = (
    "named",
    "already_named",
    "not_exact:durable",
    "not_exact:adjacent",
    "not_exact:named",
    "unresolved",
    "ambiguous",
    "no_name",
    "name_not_unique",
    "not_evaluated",
)

_Name = Field(default=None, min_length=1, max_length=TOPO_NAME_MAX_LENGTH)


class RefNameOutcome(BaseModel):
    """What the backfill found for ONE stored subshape reference."""

    feature_id: uuid.UUID
    path: str = Field(
        description="JSON pointer (RFC 6901) to the reference inside the "
        "feature's params, e.g. `/edges/refs/0` or `/entities/3/projection/edge`."
    )
    kind: Literal["face", "edge"]
    signature_sha256: str = Field(
        min_length=64,
        max_length=64,
        description="signature_digest() of the stored signature the outcome was "
        "computed for. Documents writes a name only while the stored signature "
        "still has this digest.",
    )
    outcome: RefNameOutcomeKind
    topo_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=TOPO_NAME_MAX_LENGTH,
        description="The subshape's history name (only on `named`).",
    )
    end_a_topo_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=TOPO_NAME_MAX_LENGTH,
        description="Edge only: the name of the one face the edge ends on at "
        "end_a, where the pick side would stamp one.",
    )
    adjacent_topo_names: list[str | None] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Edge only, when the stored signature carries "
        "adjacent_faces: each adjacent face's name, aligned with them.",
    )


class RefNamesReport(BaseModel):
    """Geometry's answer for one tree: one outcome per stored subshape ref."""

    tree_version: int = Field(ge=0)
    kernel: str = Field(
        max_length=256,
        description="The geometry build that computed the names (journaled).",
    )
    outcomes: list[RefNameOutcome]


class RefNamesRequestResponse(BaseModel):
    """Documents' answer to "does this part need a backfill, and of what"."""

    needed: bool = Field(
        description="True when the part has not been checked yet and some "
        "stored subshape reference has no topo_name."
    )
    tree_version: int = Field(ge=0)
    ref_names_checked_version: int | None
    request: EvaluateTreeRequest | None = Field(
        default=None,
        description="The FULL tree (rollback bar ignored, params upcast) for "
        "geometry's cold rebuild; null when not needed.",
    )


class RefNamesApplyRequest(BaseModel):
    """Write a geometry report into the part (documents, part-row locked)."""

    tree_version: int = Field(
        ge=0, description="The tree_version the report was computed from."
    )
    report: RefNamesReport
    dry_run: bool = False
    trigger: Literal["open", "sweep"] = "open"


RefNamesApplyResultKind = Literal["written", "unchanged", "stale", "dry_run"]


class RefNamesApplyResult(BaseModel):
    result: RefNamesApplyResultKind
    tree_version: int
    refs_written: int = 0
    refs_signature_changed: int = 0
    refs_already_named: int = 0
    features_written: int = 0


class RefNamesRevertResult(BaseModel):
    result: Literal["reverted", "nothing_to_revert"]
    tree_version: int
    features_restored: int = 0
    features_skipped: int = 0


class RefBackfillPart(BaseModel):
    part_id: uuid.UUID
    owner_id: uuid.UUID
    tree_version: int
    ref_names_checked_version: int | None


class RefBackfillPartList(BaseModel):
    parts: list[RefBackfillPart]


# --- the walk -----------------------------------------------------------------

AnySubshapeRef = SubshapeRef | EdgeSubshapeRef


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def iter_subshape_ref_paths(
    value: Any, prefix: str = ""
) -> Iterator[tuple[str, AnySubshapeRef]]:
    """Every face / edge reference under *value*, with its JSON pointer.

    The same generic pydantic walk as
    :func:`~loft_wire.features.iter_feature_refs` (models by field name, lists by
    index, dict values by key), so a ref-bearing field added to any feature is
    found without a change here. Pointers are into ``model_dump(mode="json")``
    of *value*: field names, never aliases (documents stores params dumped the
    same way).
    """
    if isinstance(value, SubshapeRef | EdgeSubshapeRef):
        yield prefix, value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from iter_subshape_ref_paths(
                getattr(value, name), f"{prefix}/{_escape(name)}"
            )
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            yield from iter_subshape_ref_paths(item, f"{prefix}/{index}")
    elif isinstance(value, dict):
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            yield from iter_subshape_ref_paths(item, f"{prefix}/{_escape(str(key))}")  # pyright: ignore[reportUnknownArgumentType]


def resolve_pointer(document: Any, pointer: str) -> Any:
    """The value at RFC 6901 *pointer* in a JSON *document*; KeyError if absent."""
    node = document
    if pointer == "":
        return node
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    for raw in pointer[1:].split("/"):
        token = _unescape(raw)
        if isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):  # pyright: ignore[reportUnknownArgumentType]
                raise KeyError(pointer)
            node = node[int(token)]  # pyright: ignore[reportUnknownVariableType]
        elif isinstance(node, dict):
            if token not in node:
                raise KeyError(pointer)
            node = node[token]  # pyright: ignore[reportUnknownVariableType]
        else:
            raise KeyError(pointer)
    return node  # pyright: ignore[reportUnknownVariableType]


def signature_digest(signature: Mapping[str, Any] | BaseModel) -> str:
    """SHA-256 of a stored signature's canonical JSON (sorted keys, compact).

    Both sides hash the signature as pydantic dumps it in JSON mode, so the
    digest of a signature geometry received equals the digest of the one
    documents still holds iff nobody re-picked it in between."""
    data = (
        signature.model_dump(mode="json")
        if isinstance(signature, BaseModel)
        else signature
    )
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ref_is_unnamed(ref: AnySubshapeRef) -> bool:
    """Whether a stored reference lacks its primary history name."""
    return ref.selector.signature.topo_name is None


def tree_needs_ref_names(features: Sequence[Any]) -> bool:
    """Whether any feature envelope (or EvaluatedFeatureInput) of *features*
    holds a subshape reference without a ``topo_name``."""
    for item in features:
        params = getattr(getattr(item, "feature", item), "params", None)
        for _path, ref in iter_subshape_ref_paths(params):
            if ref_is_unnamed(ref):
                return True
    return False


# --- the write -----------------------------------------------------------------

ApplyRefResult = Literal[
    "applied", "not_named", "signature_changed", "already_named", "missing"
]


def apply_ref_names(
    params: Mapping[str, Any], outcomes: Sequence[RefNameOutcome]
) -> tuple[dict[str, Any], list[ApplyRefResult]]:
    """*params* with each ``named`` outcome's names written in, and per outcome
    what happened. PURE: *params* is not modified.

    A name is written only where the reference is still there (``missing``
    otherwise), its stored signature still has the digest the name was
    computed for (``signature_changed``), and its ``topo_name`` is still null
    (``already_named``). Then only NULL name fields are filled; no geometric
    field and no existing name is ever touched. Any other outcome is
    ``not_named`` and changes nothing."""
    out: dict[str, Any] = copy.deepcopy(dict(params))
    results: list[ApplyRefResult] = []
    for outcome in outcomes:
        if outcome.outcome != "named" or outcome.topo_name is None:
            results.append("not_named")
            continue
        try:
            ref = resolve_pointer(out, outcome.path)
            signature = ref["selector"]["signature"]
        except (KeyError, TypeError):
            results.append("missing")
            continue
        if not isinstance(signature, dict):
            results.append("missing")
            continue
        if signature_digest(signature) != outcome.signature_sha256:  # pyright: ignore[reportUnknownArgumentType]
            results.append("signature_changed")
            continue
        if signature.get("topo_name") is not None:  # pyright: ignore[reportUnknownMemberType]
            results.append("already_named")
            continue
        signature["topo_name"] = outcome.topo_name
        if outcome.kind == "edge":
            if (
                outcome.end_a_topo_name is not None
                and signature.get("end_a_topo_name") is None  # pyright: ignore[reportUnknownMemberType]
            ):
                signature["end_a_topo_name"] = outcome.end_a_topo_name
            adjacent = signature.get("adjacent_faces")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            names = outcome.adjacent_topo_names
            if isinstance(adjacent, list) and names is not None:
                for face, name in zip(adjacent, names, strict=False):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
                    if (
                        name is not None
                        and isinstance(face, dict)
                        and face.get("topo_name") is None  # pyright: ignore[reportUnknownMemberType]
                    ):
                        face["topo_name"] = name
        results.append("applied")
    return out, results
