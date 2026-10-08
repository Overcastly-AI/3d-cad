"""History names for stored picks that predate them (DESIGN-INTENT-BACKFILL).

The documents half: serve the tree, and write geometry's names back SAFELY.
Documents never computes a name (it may not import the kernel) and never
calls geometry (the gateway orchestrates, :mod:`gateway.ref_backfill`). What
it owns is the stored data, so every guard on the write lives here, in one
transaction under the part-row lock (``get_owned_part(for_update=True)``, the
lock every tree mutation takes):

- **Stale guard.** The report names the ``tree_version`` it was computed
  from. If the tree moved since (a size edit landed while geometry ran),
  NOTHING is written: a name computed for the old sizes is exactly the guess
  the backfill exists not to make. The part stays pending and the next open
  retries.
- **Per-ref guards.** A name is written only where the reference is still at
  its pointer, its stored signature still has the digest the name was
  computed for, and its ``topo_name`` is still null
  (:func:`loft_wire.ref_names.apply_ref_names`). A re-pick in between is left
  alone, and a second apply of the same report writes nothing (idempotent).
- **Metadata, not an edit.** Only null name fields change, so the params
  re-validate to the same model, ``feature_dependencies`` cannot change
  (asserted), ``updated_at`` does not move (part or feature), and no undo step
  is added: the head history snapshot is amended in place
  (:meth:`~documents.history_core.DocumentHistory.amend_head`).
  ``tree_version`` is NOT bumped: the write runs in the background while the
  user works, and a bump would refuse their next edit as stale (the e2e lane
  caught exactly that) or resync their tree mid-drag. It needs no bump: at
  the part's current sizes the names cannot change the body (geometry proves
  it byte for byte), every geometry cache keys on params rather than on the
  version, and the last-evaluate verdict stays true. The one thing a client
  holding the pre-write params could do is save them back without the
  names; :func:`loft_wire.ref_names.carry_ref_names` in the feature PATCH
  copies a name back onto any pick whose signature is unchanged, so a stale
  save cannot drop them (and, the part being checked, nothing loops).
- **Journal.** Every write is a ``ref_name_backfills`` row holding the params
  before and after, the report and the geometry build, so an operator can see
  what changed and revert it (``POST .../ref-names/revert``).
"""

import copy
import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query
from loft_wire.features import (
    FEATURE_REGISTRY,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    FeatureEnvelope,
    feature_references,
)
from loft_wire.ref_names import (
    RefBackfillPart,
    RefBackfillPartList,
    RefNameOutcome,
    RefNamesApplyRequest,
    RefNamesApplyResult,
    RefNamesFailure,
    RefNamesFailureResult,
    RefNamesRequestResponse,
    RefNamesRevertResult,
    apply_ref_names,
    tree_needs_ref_names,
)
from py_kit import get_logger
from py_kit.db import SessionDep
from py_kit.metrics import record_ref_backfill_write
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db, history
from documents.parts import Principal, get_owned_part

_logger = get_logger("documents.ref_backfill")

router = APIRouter(prefix="/api/v1/parts", tags=["ref-backfill"])

#: The operator sweep's listing (no principal: it spans owners). Internal
#: like every documents route; the gateway exposes no twin of it.
sweep_router = APIRouter(prefix="/api/v1/ref-backfill", tags=["ref-backfill"])


async def _features(session: AsyncSession, part_id: uuid.UUID) -> list[db.Feature]:
    result = await session.execute(
        select(db.Feature)
        .where(db.Feature.part_id == part_id)
        .order_by(db.Feature.order_index)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


def _load(feature: db.Feature) -> FeatureEnvelope:
    """The stored row as a current-version envelope (upcast on read, §1.4)."""
    return FEATURE_REGISTRY.load(
        feature.type,
        feature.param_version,
        feature.params,
        suppressed=feature.suppressed,
    )


#: Failed runs (a geometry error or timeout, a stale write) before an open
#: stops retrying: the part is stamped checked, journaled ``kind='gave_up'``,
#: and only ``python -m gateway.ref_backfill --part`` tries it again. Without
#: this a part whose cold rebuild outlives the gateway timeout would start one
#: on every open, forever, queued in front of the user's own requests.
MAX_ATTEMPTS = 3

#: Wait after the 1st and 2nd failure before an open may retry.
BACKOFF: tuple[timedelta, ...] = (timedelta(minutes=10), timedelta(hours=1))


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite hands timezone-aware columns back naive; they were written UTC."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


async def _record_failure(
    session: AsyncSession, part: db.Part, reason: str
) -> RefNamesFailureResult:
    """Count one failed run on a pending part (the caller holds the row lock)
    and back off, or give up after :data:`MAX_ATTEMPTS`. Commits."""
    if part.ref_names_checked_version is not None:
        return RefNamesFailureResult(result="ignored", attempts=part.ref_names_attempts)
    attempts = part.ref_names_attempts + 1
    values: dict[str, Any] = {
        "ref_names_attempts": attempts,
        "updated_at": db.Part.updated_at,
    }
    next_try: datetime | None = None
    gave_up = attempts >= MAX_ATTEMPTS
    if gave_up:
        values["ref_names_checked_version"] = part.tree_version
        values["ref_names_next_try_at"] = None
        session.add(
            db.RefNameBackfill(
                part_id=part.id,
                kind="gave_up",
                trigger=reason,
                tree_version_before=part.tree_version,
                tree_version_after=part.tree_version,
                params_before={},
                params_after={},
            )
        )
    else:
        next_try = datetime.now(UTC) + BACKOFF[attempts - 1]
        values["ref_names_next_try_at"] = next_try
    await session.execute(
        update(db.Part)
        .where(db.Part.id == part.id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    record_ref_backfill_write("gave_up" if gave_up else "backoff")
    _logger.warning(
        "ref_backfill_failed",
        part_id=str(part.id),
        reason=reason,
        attempts=attempts,
        gave_up=gave_up,
    )
    return RefNamesFailureResult(
        result="gave_up" if gave_up else "backoff",
        attempts=attempts,
        next_try_at=next_try,
    )


async def backfill_written_params(
    session: AsyncSession, part_id: uuid.UUID, feature_id: uuid.UUID
) -> dict[str, Any] | None:
    """The params the latest un-reverted backfill write gave *feature_id*, or
    ``None``: the only source :func:`loft_wire.ref_names.carry_ref_names` may
    copy names from on a feature PATCH. Scoping the carry to names the
    background write put there (the one write that does not bump
    ``tree_version``) keeps every other name the client's to drop."""
    rows = (
        await session.execute(
            select(db.RefNameBackfill.params_after)
            .where(
                db.RefNameBackfill.part_id == part_id,
                db.RefNameBackfill.kind == "backfill",
                db.RefNameBackfill.reverted_at.is_(None),
            )
            .order_by(db.RefNameBackfill.created_at.desc())
        )
    ).scalars()
    for params_after in rows:
        entry: Any = params_after.get(str(feature_id))
        if not isinstance(entry, dict):
            continue
        params: Any = cast(dict[str, Any], entry).get("params")
        if isinstance(params, dict):
            return cast(dict[str, Any], params)
    return None


@router.post("/{part_id}/ref-names/failure")
async def record_ref_names_failure(
    part_id: uuid.UUID,
    request: RefNamesFailure,
    owner_id: Principal,
    session: SessionDep,
) -> RefNamesFailureResult:
    """The gateway reports a run that wrote nothing (geometry error, timeout,
    or a documents write that did not land): count it and back off."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    return await _record_failure(session, part, request.reason)


@router.get("/{part_id}/ref-names-request")
async def get_ref_names_request(
    part_id: uuid.UUID,
    owner_id: Principal,
    session: SessionDep,
    force: Annotated[
        bool,
        Query(description="Build the request even if the part was checked."),
    ] = False,
    ignore_backoff: Annotated[
        bool,
        Query(description="Retry a pending part that is backing off (sweep)."),
    ] = False,
) -> RefNamesRequestResponse:
    """Whether the part needs the backfill, and if so the tree geometry must
    rebuild: EVERY feature (the rollback bar is ignored, so picks past it are
    named too), params upcast, suppress flags kept (a suppressed feature
    resolves nothing and is reported ``not_evaluated``)."""
    part = await get_owned_part(session, owner_id, part_id)
    pending = force or part.ref_names_checked_version is None
    until = _aware(part.ref_names_next_try_at)
    backing_off = (
        not force
        and not ignore_backoff
        and until is not None
        and until > datetime.now(UTC)
    )
    if not pending or backing_off:
        return RefNamesRequestResponse(
            needed=False,
            tree_version=part.tree_version,
            ref_names_checked_version=part.ref_names_checked_version,
            backoff_until=until if backing_off else None,
        )
    features = [
        EvaluatedFeatureInput(id=row.id, feature=_load(row))
        for row in await _features(session, part.id)
    ]
    needed = tree_needs_ref_names(features)
    return RefNamesRequestResponse(
        needed=needed,
        tree_version=part.tree_version,
        ref_names_checked_version=part.ref_names_checked_version,
        request=(
            EvaluateTreeRequest(
                part_id=part.id, tree_version=part.tree_version, features=features
            )
            if needed
            else None
        ),
    )


def _referenced(envelope: FeatureEnvelope) -> set[uuid.UUID]:
    return {reference.ref.feature_id for reference in feature_references(envelope)}


def _report_digest(request: RefNamesApplyRequest) -> str:
    return hashlib.sha256(request.report.model_dump_json().encode("utf-8")).hexdigest()


@router.post("/{part_id}/ref-names")
async def apply_ref_names_route(
    part_id: uuid.UUID,
    request: RefNamesApplyRequest,
    owner_id: Principal,
    session: SessionDep,
) -> RefNamesApplyResult:
    """Write a geometry report's names into the part, under the part-row lock
    (module docstring for every guard). ``dry_run`` runs every guard and
    reports what WOULD be written, writing nothing."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    if (
        part.tree_version != request.tree_version
        or request.report.tree_version != request.tree_version
    ):
        _logger.info(
            "ref_backfill_stale",
            part_id=str(part.id),
            provided=request.tree_version,
            current=part.tree_version,
        )
        record_ref_backfill_write("stale")
        current = part.tree_version
        if not request.dry_run:
            # A stale run still cost a cold rebuild: it counts toward the backoff.
            await _record_failure(session, part, "stale")
        return RefNamesApplyResult(result="stale", tree_version=current)

    rows = await _features(session, part.id)
    by_id = {row.id: row for row in rows}
    named: dict[uuid.UUID, list[RefNameOutcome]] = defaultdict(list)
    for outcome in request.report.outcomes:
        if outcome.outcome == "named":
            named[outcome.feature_id].append(outcome)

    result = RefNamesApplyResult(result="unchanged", tree_version=part.tree_version)
    changes: list[tuple[db.Feature, int, dict[str, Any]]] = []
    for feature_id, outcomes in named.items():
        row = by_id.get(feature_id)
        if row is None:
            result.refs_signature_changed += len(outcomes)
            continue
        envelope = _load(row)
        written, results = apply_ref_names(
            envelope.params.model_dump(mode="json"), outcomes
        )
        result.refs_signature_changed += sum(
            r in ("signature_changed", "missing") for r in results
        )
        result.refs_already_named += results.count("already_named")
        applied = results.count("applied")
        if not applied:
            continue
        named_envelope = FEATURE_REGISTRY.load(
            row.type, envelope.version, written, suppressed=row.suppressed
        )
        if _referenced(named_envelope) != _referenced(envelope):  # pragma: no cover
            raise RuntimeError(
                f"a name write changed feature {row.id}'s references; refusing"
            )
        result.refs_written += applied
        changes.append(
            (row, envelope.version, named_envelope.params.model_dump(mode="json"))
        )
    result.features_written = len(changes)

    if request.dry_run:
        await session.rollback()
        record_ref_backfill_write("dry_run")
        return result.model_copy(update={"result": "dry_run"})

    before = part.tree_version
    values: dict[str, Any] = {
        "ref_names_checked_version": before,
        "ref_names_attempts": 0,
        "ref_names_next_try_at": None,
        # Pinned: present in the SET clause, so the onupdate default never fires.
        "updated_at": db.Part.updated_at,
    }
    if changes:
        params_before: dict[str, Any] = {}
        params_after: dict[str, Any] = {}
        for row, version, params in changes:
            params_before[str(row.id)] = {
                "param_version": row.param_version,
                "params": copy.deepcopy(row.params),
            }
            params_after[str(row.id)] = {"param_version": version, "params": params}
            await session.execute(
                update(db.Feature)
                .where(db.Feature.id == row.id)
                .values(
                    params=params,
                    param_version=version,
                    updated_at=db.Feature.updated_at,
                )
                .execution_options(synchronize_session=False)
            )
        after = before  # metadata: no bump (module docstring)
        session.add(
            db.RefNameBackfill(
                part_id=part.id,
                kind="backfill",
                trigger=request.trigger,
                tree_version_before=before,
                tree_version_after=after,
                params_before=params_before,
                params_after=params_after,
                report=request.report.model_dump(mode="json"),
                report_sha256=_report_digest(request),
                kernel=request.report.kernel,
            )
        )
    await session.execute(
        update(db.Part)
        .where(db.Part.id == part.id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await session.refresh(part)
    if changes:
        await history.PART_HISTORY.amend_head(session, part)
    await session.commit()
    outcome = "written" if changes else "unchanged"
    record_ref_backfill_write(outcome)
    _logger.info(
        "ref_backfill_applied",
        part_id=str(part.id),
        result=outcome,
        refs_written=result.refs_written,
        refs_signature_changed=result.refs_signature_changed,
        refs_already_named=result.refs_already_named,
        tree_version=part.tree_version,
    )
    return result.model_copy(
        update={"result": outcome, "tree_version": part.tree_version}
    )


@router.post("/{part_id}/ref-names/revert")
async def revert_ref_names(
    part_id: uuid.UUID,
    owner_id: Principal,
    session: SessionDep,
    force: Annotated[
        bool,
        Query(
            description="Revert even though the part was edited after the "
            "write. Later features may rely on the names: a fillet or shell "
            "can silently move to another subshape on the next size edit."
        ),
    ] = False,
) -> RefNamesRevertResult:
    """Undo the part's latest un-reverted backfill write (operator tool).

    Restores each touched feature's row exactly as it was stored before the
    write (``param_version`` and params), but only where the feature still
    holds what the backfill wrote; a feature edited since is skipped and
    counted. Unlike the write it bumps ``tree_version`` (so a tab holding the
    named params cannot save them back unnoticed); the head snapshot is
    amended, ``updated_at`` pinned, journaled. The part stays
    checked, so it is not named again on the next open (force a sweep with
    ``--part`` to redo it)."""
    part = await get_owned_part(session, owner_id, part_id, for_update=True)
    journal = (
        await session.execute(
            select(db.RefNameBackfill)
            .where(
                db.RefNameBackfill.part_id == part.id,
                db.RefNameBackfill.kind == "backfill",
                db.RefNameBackfill.reverted_at.is_(None),
            )
            .order_by(db.RefNameBackfill.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if journal is None:
        return RefNamesRevertResult(
            result="nothing_to_revert", tree_version=part.tree_version
        )
    if not force and part.tree_version != journal.tree_version_after:
        # Edited since: an unchanged feature's names may now be what a later
        # edit's fillet, shell or hole resolves through. Taking them away is a
        # silent retarget waiting for the next size edit, so it takes --force.
        _logger.warning(
            "ref_backfill_revert_refused",
            part_id=str(part.id),
            written_at=journal.tree_version_after,
            tree_version=part.tree_version,
        )
        return RefNamesRevertResult(
            result="refused",
            tree_version=part.tree_version,
            detail=(
                f"The part was edited after the backfill (tree version "
                f"{journal.tree_version_after} -> {part.tree_version}); later "
                "features may rely on the names. Pass force to revert anyway."
            ),
        )
    by_id = {str(row.id): row for row in await _features(session, part.id)}
    restored_before: dict[str, Any] = {}
    restored_after: dict[str, Any] = {}
    skipped = 0
    for feature_id, after in journal.params_after.items():
        row = by_id.get(feature_id)
        if (
            row is None
            or row.params != after["params"]
            or row.param_version != after["param_version"]
        ):
            skipped += 1
            continue
        before = journal.params_before[feature_id]
        restored_before[feature_id] = after
        restored_after[feature_id] = before
        await session.execute(
            update(db.Feature)
            .where(db.Feature.id == row.id)
            .values(
                params=before["params"],
                param_version=before["param_version"],
                updated_at=db.Feature.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
    version = part.tree_version
    # Unlike the background write, a revert BUMPS tree_version: it is a rare
    # operator action, and without the bump a tab still holding the named
    # params would save them straight back (its expected version would still
    # match). With it, that save is refused as stale and the tab resyncs.
    after = version + 1 if restored_after else version
    values: dict[str, Any] = {"updated_at": db.Part.updated_at}
    if restored_after:
        values["tree_version"] = after
        values["ref_names_checked_version"] = after
        if part.last_eval_tree_version == version:
            values["last_eval_tree_version"] = after
    await session.execute(
        update(db.Part)
        .where(db.Part.id == part.id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    journal.reverted_at = datetime.now(UTC)
    session.add(
        db.RefNameBackfill(
            part_id=part.id,
            kind="revert",
            trigger=None,
            tree_version_before=version,
            tree_version_after=after,
            params_before=restored_before,
            params_after=restored_after,
        )
    )
    await session.refresh(part)
    if restored_after:
        await history.PART_HISTORY.amend_head(session, part)
    await session.commit()
    record_ref_backfill_write("reverted")
    _logger.info(
        "ref_backfill_reverted",
        part_id=str(part.id),
        features_restored=len(restored_after),
        features_skipped=skipped,
        tree_version=part.tree_version,
    )
    return RefNamesRevertResult(
        result="reverted",
        tree_version=part.tree_version,
        features_restored=len(restored_after),
        features_skipped=skipped,
    )


@sweep_router.get("/parts")
async def list_backfill_parts(
    session: SessionDep,
    pending: Annotated[
        bool, Query(description="Only parts never checked (the default).")
    ] = True,
    part_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
) -> RefBackfillPartList:
    """Parts for the operator sweep, oldest first, with their owners."""
    query = select(db.Part).order_by(db.Part.created_at, db.Part.id).limit(limit)
    if part_id is not None:
        query = query.where(db.Part.id == part_id)
    elif pending:
        query = query.where(db.Part.ref_names_checked_version.is_(None))
    rows = (await session.execute(query)).scalars()
    return RefBackfillPartList(
        parts=[
            RefBackfillPart(
                part_id=row.id,
                owner_id=row.owner_id,
                tree_version=row.tree_version,
                ref_names_checked_version=row.ref_names_checked_version,
            )
            for row in rows
        ]
    )
