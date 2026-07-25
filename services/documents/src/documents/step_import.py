"""``POST /api/v1/step-import`` — turn a geometry STEP read into Loft documents.

The documents half of the assembly-import pillar (BACKLOG P1, slice 2b). The
gateway forwards the geometry service's structured read
(:class:`~py_kit.schemas.step_import.StepAssemblyImportResult` — pure pydantic,
no kernel type) here; this service materialises it into a REAL Loft graph:

* ``has_assembly_structure=True`` → an **assembly** document plus one **part**
  per unique ``body_step_id`` (deduped) seeded with an ``import`` feature holding
  ``ImportParamsV1(data=<the body resolved from the read's shared ``bodies``
  map>)`` — the EXACT single-body ingest, ZERO new path — and one named
  **instance** per product at its ``placement``. A part occurring twice (same
  ``body_step_id``) is ONE part document with TWO instances, and its B-rep
  travelled over the wire ONCE (bodies are carried per address, not per product).
* ``has_assembly_structure=False`` → the **MB-4b fallback**: one single-body part
  seeded with the same ``import`` feature, no assembly (backward compatible).

Transactionality (v1, documented): the WHOLE graph is created in ONE session and
committed ONCE. Any failure before the commit — an oversize product count, a
name collision, a bodyless read — rolls the transaction back, so a partial
upload never leaves an orphan assembly or part (all-or-nothing). Imported parts
do not eagerly seed undo history; the first user edit lazily captures the
import-feature state as its baseline (the designed lazy-baseline behaviour,
:mod:`documents.history`), so the imported part behaves exactly like one built
through ``POST /features``. An imported assembly is born fully-formed with no
undo history (you cannot undo the import itself into an empty graph).

This service never imports kernel code (CLAUDE.md service boundaries): it reads
the STEP body only as opaque ``import`` feature text, exactly as the single-body
import already does.
"""

import uuid
from typing import NamedTuple

from fastapi import APIRouter, status
from py_kit import ConflictError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.features import ImportParamsV1
from py_kit.schemas.parts import PartResponse
from py_kit.schemas.step_import import (
    MAX_IMPORT_ASSEMBLY_PRODUCTS,
    AssemblyImportResult,
    ImportAssemblyRequest,
    ImportedProduct,
    SingleBodyImportResult,
    StepAssemblyImportResult,
    StepImportResponse,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents import db
from documents.assemblies import graph_response
from documents.parts import Principal

_logger = get_logger("documents.step_import")

router = APIRouter(prefix="/api/v1/step-import", tags=["step-import"])

#: Ceiling on a document name (assembly + part share the 200-char bound).
_NAME_MAX = 200

#: The base for a per-import feature name (matches the gateway single-body path).
_IMPORT_FEATURE_NAME = "Imported STEP"


def _clean_name(raw: str | None, fallback: str) -> str:
    """A non-empty, bounded, whitespace-trimmed name (STEP names are untrusted).

    A product/PRODUCT name from an external file can be empty-after-strip, absent
    (``None``), or arbitrarily long; normalise it to a valid Loft document/instance
    name, falling back to *fallback* when it carries nothing usable.
    """
    if raw is not None:
        cleaned = raw.strip()[:_NAME_MAX]
        if cleaned:
            return cleaned
    return fallback[:_NAME_MAX] or "Imported"


def _unique_name(base: str, used: set[str]) -> str:
    """*base*, disambiguated with a `` (n)`` suffix against already-used names.

    Part names are unique per owner (a DB constraint); products can share a name
    while carrying distinct bodies, and an import can collide with the owner's
    existing parts. Generate a collision-free name in-memory (deterministic,
    order-stable) so the atomic transaction never trips the unique constraint on
    the common case — a genuine concurrent race still rolls back cleanly.
    """
    if base not in used:
        return base
    stem = base[: _NAME_MAX - 8]  # leave room for the " (999)" suffix
    counter = 2
    while True:
        candidate = f"{stem} ({counter})"
        if candidate not in used:
            return candidate
        counter += 1


def _import_params(body_step: str) -> ImportParamsV1:
    """Validate a product's local-frame B-rep as an ``import`` feature payload.

    ``body_step`` is a bounded STEP fragment (a slice of the already-bounded
    upload), so this is defence-in-depth: a fragment that somehow exceeds the
    inline cap is a clean 422 here, never an unhandled ValidationError.
    """
    try:
        return ImportParamsV1(kind="inline", format="step", data=body_step)
    except ValidationError as exc:
        raise ValidationApiError(
            "A product's imported body is not a valid inline STEP payload.",
            code="import_invalid_body",
        ) from exc


async def _add_import_part(
    session: AsyncSession, owner_id: uuid.UUID, name: str, body_step: str
) -> db.Part:
    """Add a part + its ``import`` base feature to the session (no commit).

    Ids are assigned explicitly (not deferred) so instances can reference the
    part before the single end-of-transaction commit. The part is flushed BEFORE
    its FK-dependent feature (the ``POST /features`` pattern) so the row exists
    for the feature's foreign key. Mirrors the single-body import: one ``import``
    feature at ``order_index`` 0 and ``tree_version`` bumped to 1; history is
    left lazily unseeded (module docstring). A duplicate part name surfaces as
    an :class:`IntegrityError` at this flush — the caller maps it to a 409 and
    rolls back (so no orphan documents remain).
    """
    params = _import_params(body_step)
    part = db.Part(id=uuid.uuid4(), owner_id=owner_id, name=name, tree_version=1)
    session.add(part)
    await session.flush()  # the part row must exist before its FK-dependent feature
    session.add(
        db.Feature(
            id=uuid.uuid4(),
            part_id=part.id,
            order_index=0,
            name=_IMPORT_FEATURE_NAME,
            type="import",
            param_version=1,
            params=params.model_dump(mode="json"),
        )
    )
    return part


async def _owner_part_names(session: AsyncSession, owner_id: uuid.UUID) -> set[str]:
    """The owner's existing part names — seeds the collision-free name generator."""
    result = await session.execute(
        select(db.Part.name).where(db.Part.owner_id == owner_id)
    )
    return set(result.scalars())


class _BodiedProduct(NamedTuple):
    """A product paired with its RESOLVED editable body (never ``None``)."""

    product: ImportedProduct
    body_step_id: str
    body_step: str


def _bodied_products(result: StepAssemblyImportResult) -> list[_BodiedProduct]:
    """Products whose editable body resolves out of the read's shared ``bodies``.

    Bodies travel ONCE per content address (``bodies[body_step_id]``), so this is
    where the shared map is resolved — through
    :meth:`~py_kit.schemas.step_import.StepAssemblyImportResult.body_step_for`, the
    single resolver — and where a product that cannot seed an editable part is
    dropped: no solid (no ``body_step_id``) or an address missing from the map (a
    malformed read). The geometry reader already 422s a file that yields NO solids
    (``import_no_solid``), so this normally keeps every product; it defends the
    boundary against a partial/mixed read, and pairing product with body here
    means the creation paths below never re-derive (or assert) it.
    """
    bodied: list[_BodiedProduct] = []
    for product in result.products:
        body_step = result.body_step_for(product)
        if product.body_step_id is not None and body_step is not None:
            bodied.append(_BodiedProduct(product, product.body_step_id, body_step))
    return bodied


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_from_step_import(
    request: ImportAssemblyRequest,
    owner_id: Principal,
    session: SessionDep,
) -> StepImportResponse:
    """Materialise a geometry STEP read into an assembly or a single-body part.

    Atomic (module docstring): the whole graph commits once or not at all. A
    product count over :data:`MAX_IMPORT_ASSEMBLY_PRODUCTS` is a 422
    ``import_too_many_products`` (defence-in-depth behind the gateway's own cap);
    a read with no solid product is a 422 ``import_no_solid``; a document-name
    collision is a 409 (``assembly_name_taken`` / ``part_name_taken``) — all
    before any commit, so no orphan documents are left behind.
    """
    result = request.result
    if len(result.products) > MAX_IMPORT_ASSEMBLY_PRODUCTS:
        raise ValidationApiError(
            f"Imported assembly has {len(result.products)} products, over the "
            f"{MAX_IMPORT_ASSEMBLY_PRODUCTS}-instance import ceiling.",
            code="import_too_many_products",
            details={
                "products": len(result.products),
                "max_products": MAX_IMPORT_ASSEMBLY_PRODUCTS,
            },
        )
    bodied = _bodied_products(result)
    if not bodied:
        raise ValidationApiError(
            "The imported STEP produced no solid body.",
            code="import_no_solid",
        )

    if not result.has_assembly_structure:
        return await _create_single_body(session, owner_id, request.name, bodied[0])
    return await _create_assembly(session, owner_id, request.name, bodied)


async def _create_single_body(
    session: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    bodied: _BodiedProduct,
) -> SingleBodyImportResult:
    """The MB-4b fallback: one single-body part, no assembly (backward compatible)."""
    try:
        part = await _add_import_part(session, owner_id, name, bodied.body_step)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A part named {name!r} already exists.", code="part_name_taken"
        ) from None
    _logger.info(
        "step_import_single_body", part_id=str(part.id), owner_id=str(owner_id)
    )
    return SingleBodyImportResult(
        part=PartResponse.model_validate(part), tree_version=part.tree_version
    )


async def _create_assembly(
    session: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    bodied: list[_BodiedProduct],
) -> AssemblyImportResult:
    """Create the assembly + deduped parts + named instances, atomically."""
    assembly = db.Assembly(id=uuid.uuid4(), owner_id=owner_id, name=name)
    session.add(assembly)
    try:
        # Flush early so an assembly-name collision surfaces as its own 409
        # (distinct from a later part-name conflict); rolls back → no orphans.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"An assembly named {name!r} already exists.",
            code="assembly_name_taken",
        ) from None

    used_names = await _owner_part_names(session, owner_id)
    part_by_body: dict[str, db.Part] = {}
    try:
        for index, (product, body_id, body_step) in enumerate(bodied):
            part = part_by_body.get(body_id)
            if part is None:
                part_name = _unique_name(_clean_name(product.name, name), used_names)
                used_names.add(part_name)
                part = await _add_import_part(session, owner_id, part_name, body_step)
                part_by_body[body_id] = part
            session.add(
                db.Instance(
                    id=uuid.uuid4(),
                    assembly_id=assembly.id,
                    ref_document_id=part.id,
                    ref_document_kind="part",
                    ref_pinned_version=None,  # v1 tracks tip (assemblies §1.3)
                    name=_clean_name(product.name, f"Instance <{index + 1}>"),
                    # Ground the first instance so the imported assembly carries an
                    # anchor at its authored world pose (the solver wants >= 1
                    # grounded instance, assemblies §1.2).
                    grounded=index == 0,
                    placement=product.placement.model_dump(mode="json"),
                    order_index=index,
                )
            )
        # doc_version reflects the N instance writes materialised in this import.
        assembly.doc_version = len(bodied)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "A part name produced by this import collides with an existing part.",
            code="part_name_taken",
        ) from None

    _logger.info(
        "step_import_assembly",
        assembly_id=str(assembly.id),
        owner_id=str(owner_id),
        parts=len(part_by_body),
        instances=len(bodied),
    )
    graph = await graph_response(session, assembly)
    return AssemblyImportResult(
        assembly=graph, part_ids=[part.id for part in part_by_body.values()]
    )
