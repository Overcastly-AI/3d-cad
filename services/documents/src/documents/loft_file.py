"""The documents half of the ``.loft`` file (docs/FILE-FORMAT.md).

Two routes, and the gateway is their only caller:

* ``GET /api/v1/parts/{id}/loft-tree`` — the part as a :class:`LoftTree`: every
  feature in tree order with its params UPCAST to the current ``param_version``
  (so an exported file never carries a version this build cannot also write),
  the display unit, the material assignment and the travel stop. No
  ``order_index``, no dependency edges, no timestamps, no undo history.
* ``POST /api/v1/parts/import-loft`` — create a NEW part from a tree the gateway
  has already unzipped and verified (:func:`loft_wire.loft_file.read_loft`).

What an import guarantees:

* **The same validation as** ``POST /features``. Every feature goes through
  :class:`~loft_wire.features.FeatureCreate`, the import-with-prior-body rule
  and :func:`~documents.features.validate_references` (same part, strictly
  earlier, type-compatible), in tree order. A file cannot store a tree the
  feature routes would have refused.
* **Versions.** An older ``param_version`` is upcast through the registry; a
  NEWER one, or a feature type this build does not know, is a 422 that names the
  feature — never a guess.
* **Edges are derived again** from the params, exactly as a feature write
  derives them; the file does not carry them and could not be trusted to.
* **Ids.** The file's part and feature ids are kept, so a part that travels
  install -> file -> install keeps the ids its drawings and scripts know. If ANY
  of them already exists here (the same file imported twice, or a part that
  never left), ALL of them are re-minted through
  :func:`~documents.duplicate.remap_ids` — a partial remap would leave a tree
  wired to somebody else's features. A re-mint also rewrites the feature id
  embedded in each picked subshape's ``topo_name`` (and drops the hashed ones,
  whose digest hides the old id), so the named tier keeps working.
* **Name.** A taken name becomes "<name> copy" (:func:`copy_name`), the
  duplicate rule, so importing the same file twice gives a copy.
* **One transaction.** The part, its features and their edges commit together
  or not at all. The new part has no undo history and no evaluate record;
  documents never imports the kernel, so the gateway rebuilds it.
"""

import json
import re
import uuid
from typing import Any, NoReturn, cast

from fastapi import APIRouter, status
from loft_wire.features import (
    FEATURE_REGISTRY,
    FeatureCreate,
    JsonObject,
    UnknownFeatureVersionError,
)
from loft_wire.loft_file import LoftImportRequest, LoftTree, LoftTreeFeature
from loft_wire.materials import MaterialAssignment
from loft_wire.parts import PART_NAME_MAX_LENGTH, PartResponse
from loft_wire.units import LengthUnit
from loft_wire.workspace import copy_name
from py_kit import ConflictError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.duplicate import remap_ids, taken_names
from documents.features import (
    part_materials,
    reject_import_with_prior_body,
    validate_references,
)
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.loft_file")

router = APIRouter(prefix="/api/v1/parts", tags=["parts"])

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: Params keys that hold a history-based subshape name (loft_wire.signatures).
_TOPO_NAME_KEYS = frozenset({"topo_name", "end_a_topo_name"})


# --- export -----------------------------------------------------------------------


@router.get("/{part_id}/loft-tree")
async def get_loft_tree(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> LoftTree:
    """The part's tree as ``tree.json`` holds it (uniform 404 for foreign parts)."""
    part = await get_owned_part(session, owner_id, part_id)
    rows = (
        await session.execute(
            select(db.Feature)
            .where(db.Feature.part_id == part.id)
            .order_by(db.Feature.order_index)
        )
    ).scalars()
    features: list[LoftTreeFeature] = []
    for row in rows:
        envelope = FEATURE_REGISTRY.load(
            row.type, row.param_version, row.params, suppressed=row.suppressed
        )
        features.append(
            LoftTreeFeature(
                id=row.id,
                name=row.name,
                type=row.type,
                param_version=envelope.version,
                suppressed=row.suppressed,
                params=envelope.model_dump(mode="json")["params"],
            )
        )
    return LoftTree(
        name=part.name,
        length_unit=cast(LengthUnit, part.length_unit),
        materials=part_materials(part),
        rollback_feature_id=part.rollback_feature_id,
        features=features,
    )


# --- import -----------------------------------------------------------------------


def _rewrite_topo_name(name: str, mapping: dict[str, str]) -> str | None:
    """Re-point a ``topo_name`` at the re-minted feature ids, or drop it.

    A face name is ``{feature_uuid}:{label}`` and an edge name a JSON pair of
    face names (``geometry.kernel.naming``). Every uuid in it is rewritten and a
    pair is sorted again, as the kernel writes it. A HASHED name
    (``{uuid}:#{digest}``) is dropped: its digest covers a label that names the
    OLD ids, so it can never match again. Dropping it costs only the named
    tier — the resolver falls back to the geometric ones, never to a wrong pick.
    """
    if ":#" in name:
        return None
    rewritten = _UUID_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), name)
    if rewritten.startswith("["):
        try:
            pair: Any = json.loads(rewritten)
        except ValueError:
            return rewritten
        if isinstance(pair, list):
            items = cast(list[Any], pair)
            if all(isinstance(item, str) for item in items):
                names = sorted(cast(list[str], items))
                return json.dumps(names, separators=(",", ":"))
    return rewritten


def remap_loft_params(value: Any, mapping: dict[str, str]) -> Any:
    """:func:`remap_ids`, plus the ``topo_name`` rewrite a re-mint needs.

    No mapping (the ids were kept) means no change at all — a hashed name is
    still valid then, because the ids its digest covers are the ids it has.
    """
    if not mapping:
        return value
    if isinstance(value, dict):
        entries = cast(dict[str, Any], value)
        out: dict[str, Any] = {}
        for key, item in entries.items():
            if key in _TOPO_NAME_KEYS and isinstance(item, str):
                out[key] = _rewrite_topo_name(item, mapping)
            else:
                out[mapping.get(key, key)] = remap_loft_params(item, mapping)
        return out
    if isinstance(value, list):
        return [remap_loft_params(item, mapping) for item in cast(list[Any], value)]
    return remap_ids(value, mapping)


def _refuse(
    feature: LoftTreeFeature, message: str, code: str, **details: Any
) -> NoReturn:
    raise ValidationApiError(
        f"Feature {feature.name!r} ({feature.type}): {message}",
        code=code,
        details={
            "feature_id": str(feature.id),
            "feature_name": feature.name,
            "feature_type": feature.type,
            **details,
        },
    )


def _current_params(feature: LoftTreeFeature) -> tuple[int, JsonObject]:
    """The feature's params at the CURRENT version, or a 422 naming it."""
    try:
        current = FEATURE_REGISTRY.current_version(feature.type)
    except UnknownFeatureVersionError:
        _refuse(
            feature,
            "this Loft does not know this feature type. Upgrade Loft to open the file.",
            "loft_feature_unknown_type",
        )
    if feature.param_version > current:
        _refuse(
            feature,
            f"saved with params v{feature.param_version}, newer than this "
            f"Loft's v{current}. Upgrade Loft to open the file.",
            "loft_feature_too_new",
            param_version=feature.param_version,
            supported_version=current,
        )
    try:
        params = FEATURE_REGISTRY.upcast_params(
            feature.type, feature.param_version, feature.params
        )
    except UnknownFeatureVersionError:
        _refuse(
            feature,
            f"params v{feature.param_version} cannot be read by this Loft.",
            "loft_feature_invalid",
        )
    return current, params


def _feature_create(
    feature: LoftTreeFeature, version: int, params: JsonObject
) -> FeatureCreate:
    """The SAME request model ``POST /features`` validates, or a 422 naming it."""
    try:
        return FeatureCreate.model_validate(
            {
                "name": feature.name,
                "feature": {
                    "type": feature.type,
                    "version": version,
                    "params": params,
                    "suppressed": feature.suppressed,
                },
                "expected_tree_version": 0,
            }
        )
    except ValidationError as exc:
        _refuse(
            feature,
            "its params are invalid.",
            "loft_feature_invalid",
            errors=[
                {"loc": [str(p) for p in error["loc"]], "msg": error["msg"]}
                for error in exc.errors()[:20]
            ],
        )


async def _any_id_exists(
    session: AsyncSession, part_id: uuid.UUID, feature_ids: list[uuid.UUID]
) -> bool:
    """Does this install already hold the part id or any of the feature ids?

    Across EVERY owner, deliberately: ids are primary keys, so an id another
    user holds collides exactly like one this user holds.
    """
    if await session.get(db.Part, part_id) is not None:
        return True
    if not feature_ids:
        return False
    found = await session.execute(
        select(db.Feature.id).where(db.Feature.id.in_(feature_ids)).limit(1)
    )
    return found.first() is not None


@router.post("/import-loft", status_code=status.HTTP_201_CREATED)
async def import_loft(
    request: LoftImportRequest, owner_id: Principal, session: SessionDep
) -> PartResponse:
    """Create a part from a verified ``.loft`` tree, in one transaction (201)."""
    tree = request.tree
    file_ids = [feature.id for feature in tree.features]
    if len(set(file_ids)) != len(file_ids):
        raise ValidationApiError(
            "The .loft tree lists a feature id twice.",
            code="loft_feature_id_duplicate",
        )
    if tree.rollback_feature_id is not None and tree.rollback_feature_id not in (
        set(file_ids)
    ):
        raise ValidationApiError(
            "The .loft tree's rollback bar names a feature it does not hold.",
            code="loft_rollback_invalid",
        )
    # Versions first: a too-new feature is refused before anything else is done.
    current = [_current_params(feature) for feature in tree.features]

    mapping: dict[str, str] = {}
    if await _any_id_exists(session, request.document_id, file_ids):
        mapping = {
            str(old): str(uuid.uuid4()) for old in [request.document_id, *file_ids]
        }
    new_id = {old: uuid.UUID(mapping.get(str(old), str(old))) for old in file_ids}
    part_id = uuid.UUID(mapping.get(str(request.document_id), str(request.document_id)))

    taken = await taken_names(session, db.Part, owner_id, None)
    name = (
        tree.name
        if tree.name not in taken
        else copy_name(tree.name, taken, max_length=PART_NAME_MAX_LENGTH)
    )
    materials = (
        None
        if tree.materials is None
        else MaterialAssignment.model_validate(
            remap_ids(tree.materials.model_dump(mode="json"), mapping)
        ).model_dump(mode="json")
    )
    # Validate the WHOLE tree before writing anything, in tree order, against
    # the rows built so far: the POST /features rules, feature by feature.
    rows: list[db.Feature] = []
    by_id: dict[uuid.UUID, db.Feature] = {}
    edges: list[tuple[uuid.UUID, list[uuid.UUID]]] = []
    for position, (feature, (version, params)) in enumerate(
        zip(tree.features, current, strict=True)
    ):
        create = _feature_create(
            feature, version, cast(JsonObject, remap_loft_params(params, mapping))
        )
        try:
            reject_import_with_prior_body(create.feature, position, rows)
            targets = validate_references(create.feature, position, by_id)
        except ValidationApiError as exc:
            _refuse(feature, exc.message, exc.code, reason=exc.details)
        row = db.Feature(
            id=new_id[feature.id],
            part_id=part_id,
            order_index=position,
            name=create.name,
            type=create.feature.type,
            param_version=create.feature.version,
            params=create.feature.params.model_dump(mode="json"),
            suppressed=create.feature.suppressed,
        )
        rows.append(row)
        by_id[row.id] = row
        edges.append((row.id, targets))

    part = db.Part(
        id=part_id,
        owner_id=owner_id,
        name=name,
        folder_id=None,
        length_unit=tree.length_unit,
        materials=materials,
        tree_version=1,
    )
    try:
        session.add(part)
        await session.flush()  # the part row before its FK-dependent features
        session.add_all(rows)
        await session.flush()  # feature rows before their FK-dependent edges
        for feature_id, targets in edges:
            for target_id in sorted(set(targets)):
                session.add(
                    db.FeatureDependency(
                        part_id=part.id,
                        feature_id=feature_id,
                        references_feature_id=target_id,
                    )
                )
        if tree.rollback_feature_id is not None:
            part.rollback_feature_id = new_id[tree.rollback_feature_id]
        await session.commit()
    except IntegrityError:
        # A name or an id taken by a concurrent write since the checks above.
        await session.rollback()
        raise ConflictError(
            f"A part named {name!r} or with this file's ids was created at the "
            "same moment; import the file again.",
            code="part_name_taken",
        ) from None
    _logger.info(
        "part_imported_from_loft",
        part_id=str(part.id),
        owner_id=str(owner_id),
        features=len(rows),
        reminted=bool(mapping),
    )
    return PartResponse.model_validate(part)
