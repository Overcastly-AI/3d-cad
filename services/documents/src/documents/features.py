"""``/api/v1/parts/{part_id}/features`` — the ordered feature tree.

Implements the write rules of docs/design/feature-tree.md: reference validity
(§2.2 — same part, strictly earlier, type-compatible), materialized
``feature_dependencies`` edges rewritten in the same transaction (§2.3), the
409-with-dependents delete pre-check (§2.3), optimistic concurrency via
``tree_version`` (stale write → **422**, keeping 409 unambiguous for the
dependents conflict — §1.2), rollback-bar semantics (§3), and dense-integer
renumbering (§1.2).

Renumbering is written collision-free under IMMEDIATE unique checking
(suffix shifts walk in index order; reorders run in two phases through a
disjoint index range), so the same code is correct on Postgres — where
``uq_features_part_order`` is additionally DEFERRABLE — and on the SQLite
test dialect, which cannot defer unique constraints (documents/db.py).

Trust model, principal header, and uniform-404 ownership scoping are shared
with :mod:`documents.parts`; feature routes authorize against the OWNING part
(§1.2) — features carry no ACLs of their own.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from py_kit import ConflictError, NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.features import (
    BODY_AFFECTING_FEATURE_TYPES,
    FEATURE_REGISTRY,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    FeatureCreate,
    FeatureEnvelope,
    FeatureMutationResponse,
    FeatureReorderRequest,
    FeatureResponse,
    FeatureSuppressRequest,
    FeatureTreeResponse,
    FeatureUpdate,
    RollbackBarMove,
    UndoRedoRequest,
    feature_references,
)
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db, history
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.features")

router = APIRouter(prefix="/api/v1/parts", tags=["features"])


# --- shared plumbing --------------------------------------------------------------


def _ensure_fresh(part: db.Part, expected_tree_version: int) -> None:
    """Optimistic-concurrency gate: stale writes are 422 (design §1.2).

    422 — NOT 409 — so the two write-failure modes are distinguishable by
    status alone (409 stays reserved for the delete-with-dependents conflict).
    """
    if part.tree_version != expected_tree_version:
        raise ValidationApiError(
            "Stale tree version: the part's feature tree changed since it "
            "was last read.",
            code="stale_tree_version",
            details={
                "provided": expected_tree_version,
                "current": part.tree_version,
            },
        )


async def _ordered_features(
    session: AsyncSession, part_id: uuid.UUID
) -> list[db.Feature]:
    """The part's tree, ``ORDER BY order_index`` (total by uniqueness).

    ``populate_existing`` refreshes identity-map instances whose
    ``order_index`` was renumbered via Core UPDATEs in this transaction.
    """
    result = await session.execute(
        select(db.Feature)
        .where(db.Feature.part_id == part_id)
        .order_by(db.Feature.order_index)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _get_feature(
    session: AsyncSession, part: db.Part, feature_id: uuid.UUID
) -> db.Feature:
    """A feature of *part*, or 404 (unknown id == another part's id)."""
    feature = await session.get(db.Feature, feature_id)
    if feature is None or feature.part_id != part.id:
        raise NotFoundError("Feature not found.", code="feature_not_found")
    return feature


def _reject_import_with_prior_body(
    envelope: FeatureEnvelope,
    position: int,
    features: list[db.Feature],
) -> None:
    """Guard the import base-feature invariant (docs/design/step-import.md §1).

    An ``import`` SETS the part's base body, so — like the geometry service's
    per-feature ``import_with_prior_body`` rebuild error (§5) — it is only valid
    when no body-producing feature precedes it. Enforcing it at write time turns
    the "STEP onto a part that already has a body" case into a legible 422 at
    upload/create, rather than a feature that is persisted only to fail every
    later evaluation. Non-body-affecting features before the import (an early
    datum or sketch) are fine — only a prior body is rejected.
    """
    if envelope.type != "import":
        return
    prior_body = next(
        (
            feature
            for feature in features
            if feature.order_index < position
            and feature.type in BODY_AFFECTING_FEATURE_TYPES
        ),
        None,
    )
    if prior_body is not None:
        raise ValidationApiError(
            "An import sets the part's base body, so it cannot follow another "
            "body-producing feature.",
            code="import_with_prior_body",
            details={
                "prior_feature_id": str(prior_body.id),
                "prior_feature_type": prior_body.type,
            },
        )


def _validate_references(
    envelope: FeatureEnvelope,
    order_index: int,
    features_by_id: dict[uuid.UUID, db.Feature],
) -> list[uuid.UUID]:
    """Apply the §2.2 write rules; return the referenced feature ids.

    1. same part — the lookup map is built from this part's features only, so
       a cross-part (or unknown) id fails here; the composite FKs are the DB
       backstop.
    2. strictly earlier — target ``order_index`` < the referrer's.
    3. type-compatible — the slot's ``allowed_types`` from py-kit.
    """
    target_ids: list[uuid.UUID] = []
    for reference in feature_references(envelope):
        ref_id = reference.ref.feature_id
        target = features_by_id.get(ref_id)
        if target is None:
            raise ValidationApiError(
                f"Referenced feature {ref_id} does not exist in this part.",
                code="reference_not_found",
                details={"slot": reference.slot, "feature_id": str(ref_id)},
            )
        if target.order_index >= order_index:
            raise ValidationApiError(
                f"Referenced feature {ref_id} must come strictly earlier in the tree.",
                code="reference_not_earlier",
                details={"slot": reference.slot, "feature_id": str(ref_id)},
            )
        if target.type not in reference.allowed_types:
            raise ValidationApiError(
                f"Slot {reference.slot!r} cannot reference a {target.type!r} feature.",
                code="reference_type_invalid",
                details={
                    "slot": reference.slot,
                    "feature_id": str(ref_id),
                    "actual_type": target.type,
                    "allowed_types": sorted(reference.allowed_types),
                },
            )
        target_ids.append(target.id)
    return target_ids


async def _rewrite_edges(
    session: AsyncSession,
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    target_ids: list[uuid.UUID],
) -> None:
    """Rewrite the feature's materialized dependency edges (design §2.3)."""
    await session.execute(
        delete(db.FeatureDependency).where(
            db.FeatureDependency.feature_id == feature_id
        )
    )
    for target_id in sorted(set(target_ids)):
        session.add(
            db.FeatureDependency(
                part_id=part_id,
                feature_id=feature_id,
                references_feature_id=target_id,
            )
        )


async def _shift_indexes(
    session: AsyncSession, part_id: uuid.UUID, from_index: int, by: int
) -> None:
    """Shift ``order_index`` of every feature at/after *from_index* by ±1.

    Row-at-a-time in collision-free order (descending for +1, ascending for
    -1) so the shuffle is legal even under IMMEDIATE unique checking (SQLite).
    """
    result = await session.execute(
        select(db.Feature.id, db.Feature.order_index)
        .where(db.Feature.part_id == part_id, db.Feature.order_index >= from_index)
        .order_by(db.Feature.order_index.desc() if by > 0 else db.Feature.order_index)
    )
    for feature_id, order_index in result.all():
        await session.execute(
            update(db.Feature)
            .where(db.Feature.id == feature_id)
            .values(order_index=order_index + by)
        )


def _bar_index(part: db.Part, features: list[db.Feature]) -> int | None:
    """The rollback bar's ``order_index``, or None when the bar is at the tip."""
    if part.rollback_feature_id is None:
        return None
    for feature in features:
        if feature.id == part.rollback_feature_id:
            return feature.order_index
    # Unreachable by invariant (bar always points into the part, §1.2/§3);
    # fail loudly rather than mislabel rolled-back rows.
    raise RuntimeError(
        f"rollback bar {part.rollback_feature_id} not found in part {part.id}"
    )


def _to_response(feature: db.Feature, bar_index: int | None) -> FeatureResponse:
    """Row → DTO: envelope reassembled, params upcast on read (design §1.4)."""
    return FeatureResponse(
        id=feature.id,
        part_id=feature.part_id,
        order_index=feature.order_index,
        name=feature.name,
        feature=FEATURE_REGISTRY.load(
            feature.type,
            feature.param_version,
            feature.params,
            suppressed=feature.suppressed,
        ),
        rolled_back=bar_index is not None and feature.order_index > bar_index,
        created_at=feature.created_at,
        updated_at=feature.updated_at,
    )


async def _tree_response(session: AsyncSession, part: db.Part) -> FeatureTreeResponse:
    features = await _ordered_features(session, part.id)
    bar_index = _bar_index(part, features)
    can_undo, can_redo = await history.PART_HISTORY.availability(session, part)
    return FeatureTreeResponse(
        part_id=part.id,
        tree_version=part.tree_version,
        rollback_feature_id=part.rollback_feature_id,
        features=[_to_response(feature, bar_index) for feature in features],
        can_undo=can_undo,
        can_redo=can_redo,
    )


# --- routes -----------------------------------------------------------------------


@router.get("/{part_id}/features")
async def get_feature_tree(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> FeatureTreeResponse:
    """The ordered feature tree (uniform 404 for unknown/foreign parts)."""
    part = await get_owned_part(session, owner_id, part_id)
    return await _tree_response(session, part)


async def evaluation_prefix(
    session: AsyncSession, part: db.Part
) -> list[EvaluatedFeatureInput]:
    """The part's evaluation-ready feature prefix (design §4.2 / §3 / §1.4).

    The shared body behind :func:`get_evaluation_request` AND the assembly
    evaluation-request (``documents.assemblies``, which needs the SAME prefix per
    instanced part — DRY, one rollback/upcast implementation). The rollback bar is
    applied HERE (only the prefix up to and including the bar, §3) and every params
    blob is upcast to its current version on read (§1.4), so geometry only ever sees
    a current-version, rollback-applied list — never a hint that rollback exists.
    """
    features = await _ordered_features(session, part.id)
    bar_index = _bar_index(part, features)
    return [
        EvaluatedFeatureInput(
            id=feature.id,
            feature=FEATURE_REGISTRY.load(
                feature.type,
                feature.param_version,
                feature.params,
                suppressed=feature.suppressed,
            ),
        )
        for feature in features
        if bar_index is None or feature.order_index <= bar_index
    ]


@router.get("/{part_id}/evaluation-request")
async def get_evaluation_request(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> EvaluateTreeRequest:
    """The evaluation-ready feature list (design §4.2), for the gateway to
    forward to the geometry service verbatim.

    Documents owns everything geometry must never know about: the rollback
    bar is applied HERE (only the prefix up to and including the bar is
    returned, §3), params are upcast to current versions on read (§1.4), and
    the order is the total ``order_index`` order. ``tree_version`` rides
    along as the cache/correlation key.
    """
    part = await get_owned_part(session, owner_id, part_id)
    return EvaluateTreeRequest(
        part_id=part.id,
        tree_version=part.tree_version,
        features=await evaluation_prefix(session, part),
    )


@router.get("/{part_id}/features/{feature_id}")
async def get_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureResponse:
    """One feature of an owned part."""
    part = await get_owned_part(session, owner_id, part_id)
    feature = await _get_feature(session, part, feature_id)
    features = await _ordered_features(session, part.id)
    return _to_response(feature, _bar_index(part, features))


@router.post("/{part_id}/features", status_code=status.HTTP_201_CREATED)
async def create_feature(
    part_id: uuid.UUID,
    request: FeatureCreate,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureMutationResponse:
    """Append a feature — or, while rolled back, insert it immediately after
    the bar and move the bar to it (design §3)."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)

    features = await _ordered_features(session, part.id)
    features_by_id = {feature.id: feature for feature in features}
    bar_index = _bar_index(part, features)
    position = len(features) if bar_index is None else bar_index + 1

    _reject_import_with_prior_body(request.feature, position, features)
    target_ids = _validate_references(request.feature, position, features_by_id)

    await _shift_indexes(session, part.id, position, +1)
    feature = db.Feature(
        id=uuid.uuid4(),
        part_id=part.id,
        order_index=position,
        name=request.name,
        type=request.feature.type,
        param_version=request.feature.version,
        params=request.feature.params.model_dump(mode="json"),
        # A feature CAN be born suppressed (slice-1 review 🔴: create must NOT
        # silently drop `suppressed: true`) — persist the envelope flag verbatim.
        suppressed=request.feature.suppressed,
    )
    session.add(feature)
    await session.flush()  # row must exist before its edges (FK)
    await _rewrite_edges(session, part.id, feature.id, target_ids)
    if part.rollback_feature_id is not None:
        part.rollback_feature_id = feature.id  # bar follows the insert (§3)
    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "feature_created",
        part_id=str(part.id),
        feature_id=str(feature.id),
        feature_type=feature.type,
        order_index=feature.order_index,
        tree_version=part.tree_version,
    )
    new_bar = _bar_index(part, await _ordered_features(session, part.id))
    return FeatureMutationResponse(
        feature=_to_response(feature, new_bar), tree_version=part.tree_version
    )


@router.patch("/{part_id}/features/{feature_id}")
async def update_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    request: FeatureUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureMutationResponse:
    """Rename and/or replace params. ANY mutation bumps ``tree_version``
    (uniform rule, design §1.2) — including a name-only change."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)
    feature = await _get_feature(session, part, feature_id)

    if request.feature is not None:
        if request.feature.type != feature.type:
            raise ValidationApiError(
                "A feature's type is immutable; delete and recreate to "
                "change its kind.",
                code="feature_type_immutable",
                details={"current": feature.type, "provided": request.feature.type},
            )
        features = await _ordered_features(session, part.id)
        features_by_id = {row.id: row for row in features}
        target_ids = _validate_references(
            request.feature, feature.order_index, features_by_id
        )
        feature.param_version = request.feature.version
        feature.params = request.feature.params.model_dump(mode="json")
        # The envelope carries `suppressed`; a params replace persists it too so
        # an update never resets the flag (the dedicated toggle is the usual
        # path, but a full-envelope PATCH must round-trip it — feature-tree §4.3a).
        feature.suppressed = request.feature.suppressed
        await _rewrite_edges(session, part.id, feature.id, target_ids)
    if request.name is not None:
        feature.name = request.name

    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "feature_updated",
        part_id=str(part.id),
        feature_id=str(feature.id),
        tree_version=part.tree_version,
    )
    bar_index = _bar_index(part, await _ordered_features(session, part.id))
    return FeatureMutationResponse(
        feature=_to_response(feature, bar_index), tree_version=part.tree_version
    )


@router.patch("/{part_id}/features/{feature_id}/suppress")
async def suppress_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    request: FeatureSuppressRequest,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureMutationResponse:
    """Flip ONLY a feature's suppress flag (feature-tree.md §4.3a).

    A dedicated, minimal mutation: unlike :func:`update_feature` it never
    touches ``params`` (no re-validation, no dependency-edge rewrite) — it sets
    the envelope-level ``suppressed`` column and, like every tree write, bumps
    ``tree_version`` under the optimistic-concurrency guard (stale → 422) and
    records a history snapshot so the toggle is undoable. A suppressed feature
    is SKIPPED at rebuild (the evaluation-request marks it, geometry skips it),
    so this changes what an evaluation of the part means.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)
    feature = await _get_feature(session, part, feature_id)

    feature.suppressed = request.suppressed
    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "feature_suppress_toggled",
        part_id=str(part.id),
        feature_id=str(feature.id),
        suppressed=feature.suppressed,
        tree_version=part.tree_version,
    )
    bar_index = _bar_index(part, await _ordered_features(session, part.id))
    return FeatureMutationResponse(
        feature=_to_response(feature, bar_index), tree_version=part.tree_version
    )


@router.delete("/{part_id}/features/{feature_id}")
async def delete_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    expected_tree_version: Annotated[
        int,
        Query(ge=0, description="Optimistic-concurrency guard (see FeatureCreate)"),
    ],
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Delete a feature; 409 listing dependents when it is still referenced.

    The friendly conflict comes from documents' pre-check on the materialized
    edges (design §2.3); the deferred target-side FK remains the DB backstop.
    Returns the renumbered tree (the client's new ``tree_version``).
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, expected_tree_version)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)
    feature = await _get_feature(session, part, feature_id)

    dependents = (
        (
            await session.execute(
                select(db.Feature)
                .join(
                    db.FeatureDependency,
                    db.FeatureDependency.feature_id == db.Feature.id,
                )
                .where(db.FeatureDependency.references_feature_id == feature_id)
                .order_by(db.Feature.order_index)
            )
        )
        .scalars()
        .all()
    )
    if dependents:
        raise ConflictError(
            f"Feature {feature.name!r} is referenced by "
            f"{len(dependents)} other feature(s); delete or re-point them "
            "first.",
            code="feature_has_dependents",
            details={
                "dependents": [
                    {"id": str(row.id), "name": row.name} for row in dependents
                ]
            },
        )

    if part.rollback_feature_id == feature.id:
        part.rollback_feature_id = None  # bar resets to the tip (§3)
    deleted_index = feature.order_index
    await session.execute(
        delete(db.FeatureDependency).where(
            db.FeatureDependency.feature_id == feature.id
        )
    )
    await session.delete(feature)
    await session.flush()
    await _shift_indexes(session, part.id, deleted_index + 1, -1)
    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "feature_deleted",
        part_id=str(part.id),
        feature_id=str(feature_id),
        tree_version=part.tree_version,
    )
    return await _tree_response(session, part)


@router.put("/{part_id}/features/order")
async def reorder_features(
    part_id: uuid.UUID,
    request: FeatureReorderRequest,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Apply a full permutation of the tree, re-checking backward-only refs
    (§2.2 rule 2) under the new order before renumbering."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)
    pre_op = await history.PART_HISTORY.baseline_state(session, part)

    features = await _ordered_features(session, part.id)
    current_ids = {feature.id for feature in features}
    if (
        len(request.order) != len(features)
        or len(set(request.order)) != len(request.order)
        or set(request.order) != current_ids
    ):
        raise ValidationApiError(
            "Reorder payload must be a permutation of ALL feature ids of this part.",
            code="order_not_permutation",
            details={"expected_count": len(features)},
        )
    final_index = {feature_id: i for i, feature_id in enumerate(request.order)}

    edges = (
        (
            await session.execute(
                select(db.FeatureDependency).where(
                    db.FeatureDependency.part_id == part.id
                )
            )
        )
        .scalars()
        .all()
    )
    for edge in edges:
        if final_index[edge.feature_id] <= final_index[edge.references_feature_id]:
            raise ValidationApiError(
                "Reorder would move a feature before one of its references "
                "(references must point strictly backward).",
                code="reference_not_earlier",
                details={
                    "feature_id": str(edge.feature_id),
                    "references_feature_id": str(edge.references_feature_id),
                },
            )

    # Two-phase renumber through a disjoint range (0..n-1 → n..2n-1 → final)
    # so no per-row state is ever duplicated under IMMEDIATE unique checking.
    offset = len(features)
    for feature in features:
        await session.execute(
            update(db.Feature)
            .where(db.Feature.id == feature.id)
            .values(order_index=final_index[feature.id] + offset)
        )
    for feature in features:
        await session.execute(
            update(db.Feature)
            .where(db.Feature.id == feature.id)
            .values(order_index=final_index[feature.id])
        )
    part.tree_version += 1
    await history.PART_HISTORY.record(session, part, pre_op)
    await session.commit()
    _logger.info(
        "features_reordered",
        part_id=str(part.id),
        tree_version=part.tree_version,
    )
    return await _tree_response(session, part)


@router.put("/{part_id}/rollback")
async def move_rollback_bar(
    part_id: uuid.UUID,
    request: RollbackBarMove,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Move the rollback bar (design §3). Nothing below the bar is deleted or
    mutated; features after it are only MARKED rolled back."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)

    if request.rollback_feature_id is not None:
        bar_feature = await session.get(db.Feature, request.rollback_feature_id)
        if bar_feature is None or bar_feature.part_id != part.id:
            raise ValidationApiError(
                "Rollback bar must point at a feature of this part.",
                code="reference_not_found",
                details={"feature_id": str(request.rollback_feature_id)},
            )
    part.rollback_feature_id = request.rollback_feature_id
    part.tree_version += 1  # changes what an evaluation means (§3)
    await session.commit()
    _logger.info(
        "rollback_bar_moved",
        part_id=str(part.id),
        rollback_feature_id=str(request.rollback_feature_id),
        tree_version=part.tree_version,
    )
    return await _tree_response(session, part)


async def _restore_history_step(
    part_id: uuid.UUID,
    request: UndoRedoRequest,
    owner_id: uuid.UUID,
    session: AsyncSession,
    direction: history.Direction,
) -> FeatureTreeResponse:
    """Shared undo/redo body (docs/design/undo-redo.md).

    Undo/redo ARE document edits: the same OCC guard as every other write
    (stale → 422), a ``tree_version`` bump, and the restored tree in the
    response so the client re-renders (and re-evaluates) authoritatively.

    Boundary shape — undo at the ring's floor / redo at its top is a CLEAN
    no-op per the design ("clean no-ops, not errors"): 200 with the CURRENT
    tree, ``tree_version`` untouched, nothing committed. The UI disables the
    controls via ``can_undo``/``can_redo`` on this same response, so a click
    racing a just-changed history state lands harmlessly here and resyncs.
    """
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    _ensure_fresh(part, request.expected_tree_version)
    if await history.PART_HISTORY.restore_adjacent(session, part, direction):
        part.tree_version += 1
        await session.commit()
        _logger.info(
            "history_restored",
            part_id=str(part.id),
            direction=direction,
            history_cursor=part.history_cursor,
            tree_version=part.tree_version,
        )
    return await _tree_response(session, part)


@router.post("/{part_id}/undo")
async def undo(
    part_id: uuid.UUID,
    request: UndoRedoRequest,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Restore the previous history snapshot VERBATIM (ids preserved).

    Clean no-op at the baseline; stale ``expected_tree_version`` → 422.
    """
    return await _restore_history_step(part_id, request, owner_id, session, "undo")


@router.post("/{part_id}/redo")
async def redo(
    part_id: uuid.UUID,
    request: UndoRedoRequest,
    owner_id: Principal,
    session: SessionDep,
) -> FeatureTreeResponse:
    """Restore the next history snapshot VERBATIM (ids preserved).

    Clean no-op at the top of the ring; stale ``expected_tree_version`` → 422.
    """
    return await _restore_history_step(part_id, request, owner_id, session, "redo")
