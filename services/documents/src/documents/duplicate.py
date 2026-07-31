"""``POST /api/v1/{parts,assemblies,drawings}/{id}/duplicate`` — copy a document.

WHAT A DUPLICATE COPIES, stated per kind, because "duplicate" is exactly the
verb a user can be silently wrong about (a copy that quietly carries less than
the user thinks is the same defect class as a register showing a stale name):

- **A part** — the WHOLE feature tree at its current version: every feature in
  order, with its params, its suppressed flag, its dependency edges, and the
  travel stop, plus the header's display unit and material assignment. The
  feature *ids* are new, and every id reference INSIDE the copied params is
  rewritten to the new ids (:func:`remap_ids`), so the copy is a self-contained
  tree and not one wired back into the original.
- **An assembly** — the instance list and the mates. NOT the referenced parts:
  an instance is a reference, so both assemblies point at the same parts, and
  editing a part still shows up in both. That is the behaviour a user wants (you
  duplicate an assembly to try a different arrangement of the same parts) and it
  is the only one that is honest about what an instance is. Mate params are
  rewritten onto the copied instances.
- **A drawing** — its sheets, views, dimensions and annotations. NOT the
  referenced part/assembly, for the same reason as an instance: a view is a
  reference.

WHAT NO DUPLICATE COPIES, in every kind:

- **Undo history.** A copy's history starts empty (``history_cursor`` NULL). An
  undo stack is a record of what *this document's* editor did; inheriting the
  original's would let an undo on the copy restore states this document was
  never in.
- **The last-evaluate record** (parts). The copy has never been evaluated, so
  its ``eval_state`` reads ``never`` and the register says so. Carrying the
  verdict over would be a claim about a document nothing has ever built —
  defensible arithmetic ("the tree is identical"), but still a surface asserting
  something it does not know. Opening the copy evaluates it and the record fills
  in a second later.

Naming is :func:`py_kit.schemas.workspace.copy_name` — "Bracket copy", then
"Bracket copy 2" — shared by all three so the rule is one rule. The route
RETURNS the created document, so the register renders the name the server
actually assigned rather than the one the client predicted.

Routes live here rather than in ``documents.parts`` / ``.assemblies`` /
``.drawings`` because the three implementations share the id-remap and the
naming rule, and splitting them across three modules would have duplicated both.
"""

import uuid
from collections.abc import Sequence
from typing import Any, cast

from fastapi import APIRouter, status
from py_kit import ConflictError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.assemblies import ASSEMBLY_NAME_MAX_LENGTH, AssemblyResponse
from py_kit.schemas.drawings import DRAWING_NAME_MAX_LENGTH, DrawingResponse
from py_kit.schemas.parts import PART_NAME_MAX_LENGTH, PartResponse
from py_kit.schemas.workspace import copy_name
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.db import (
    Annotation,
    Assembly,
    Dimension,
    Drawing,
    Feature,
    FeatureDependency,
    Instance,
    Mate,
    Part,
    Sheet,
    View,
)
from documents.parts import (
    Principal,
    get_owned_assembly,
    get_owned_drawing,
    get_owned_part,
)

_logger = get_logger("documents.duplicate")

parts_router = APIRouter(prefix="/api/v1/parts", tags=["parts"])
assemblies_router = APIRouter(prefix="/api/v1/assemblies", tags=["assemblies"])
drawings_router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])


def remap_ids(value: Any, mapping: dict[str, str]) -> Any:
    """Rewrite every old id STRING inside a JSON params payload to its new id.

    Feature params, mate params and annotation params all reference their
    siblings by id, serialized as plain strings (``FeatureRef.feature_id``,
    ``SubshapeRef.feature_id``, ``MateFaceRef.instance_id``, …). A copy that
    kept those strings would be a document wired back into the one it was copied
    from — the "silently copies less than the user thinks" failure, in its worst
    form: it would look right until the original was edited.

    Rewriting by VALUE rather than by field path is deliberate. The alternative —
    re-validating each params blob against its DTO and walking known ref fields —
    would need this module to know every params union in the product, and would
    silently stop copying correctly the day a new verb adds a reference field.
    Matching on the id string cannot miss one: the ids are freshly minted uuid4s
    for this operation, so a collision with an unrelated string is not a risk
    worth trading correctness-by-default for.

    Keys are remapped as well as values — some payloads key maps by id.
    """
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [remap_ids(item, mapping) for item in items]
    if isinstance(value, dict):
        entries = cast(dict[Any, Any], value)
        return {
            (mapping.get(key, key) if isinstance(key, str) else key): remap_ids(
                item, mapping
            )
            for key, item in entries.items()
        }
    return value


async def _taken_names(
    session: AsyncSession,
    model: type[Part] | type[Assembly] | type[Drawing],
    owner_id: uuid.UUID,
) -> set[str]:
    """Every name this owner already used for that document kind.

    Read inside the same transaction as the insert; the per-owner unique index
    is still the authority, so a concurrent duplicate of the same document
    surfaces as the usual 409 rather than silently taking a name.
    """
    rows = await session.execute(select(model.name).where(model.owner_id == owner_id))
    return set(rows.scalars())


@parts_router.post("/{part_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_part(
    part_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> PartResponse:
    """Copy a part and its whole feature tree at its current version (201).

    See the module docstring for exactly what is and is not copied. The copy is
    a NEW document at ``tree_version`` 0 with no evaluate record — it is not a
    version, a branch or a link, and nothing about it stays tied to the source.
    """
    source = await get_owned_part(session, owner_id, part_id)
    taken = await _taken_names(session, Part, owner_id)
    copy = Part(
        owner_id=owner_id,
        name=copy_name(source.name, taken, max_length=PART_NAME_MAX_LENGTH),
        length_unit=source.length_unit,
        materials=source.materials,
    )
    session.add(copy)
    await session.flush()

    features = (
        (
            await session.execute(
                select(Feature)
                .where(Feature.part_id == source.id)
                .order_by(Feature.order_index)
            )
        )
        .scalars()
        .all()
    )
    # Mint every new id up front: the params rewrite needs the WHOLE map, since a
    # feature may reference any earlier feature in the tree.
    new_id = {feature.id: uuid.uuid4() for feature in features}
    mapping = {str(old): str(new) for old, new in new_id.items()}
    for feature in features:
        session.add(
            Feature(
                id=new_id[feature.id],
                part_id=copy.id,
                order_index=feature.order_index,
                name=feature.name,
                type=feature.type,
                param_version=feature.param_version,
                params=remap_ids(feature.params, mapping),
                suppressed=feature.suppressed,
            )
        )
    edges = (
        (
            await session.execute(
                select(FeatureDependency).where(FeatureDependency.part_id == source.id)
            )
        )
        .scalars()
        .all()
    )
    for edge in edges:
        # Copy the materialized edges rather than re-deriving them: the source
        # tree's edges are already the validated truth (documents.features
        # rewrites them on every write), so re-parsing would be a second
        # implementation of the extraction that could disagree with the first.
        session.add(
            FeatureDependency(
                part_id=copy.id,
                feature_id=new_id[edge.feature_id],
                references_feature_id=new_id[edge.references_feature_id],
            )
        )
    if source.rollback_feature_id is not None:
        # The travel stop is part of where you were, so it travels with the copy.
        copy.rollback_feature_id = new_id[source.rollback_feature_id]

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "A part with the copy's name already exists; rename it and try again.",
            code="part_name_taken",
        ) from None
    _logger.info(
        "part_duplicated",
        part_id=str(copy.id),
        source_part_id=str(source.id),
        features=len(features),
    )
    return PartResponse.model_validate(copy)


@assemblies_router.post("/{assembly_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_assembly(
    assembly_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> AssemblyResponse:
    """Copy an assembly's instances and mates — NOT the parts they name (201).

    Both assemblies reference the same parts afterwards; editing one of those
    parts still shows up in both, which is what an instance IS. See the module
    docstring.
    """
    source = await get_owned_assembly(session, owner_id, assembly_id)
    taken = await _taken_names(session, Assembly, owner_id)
    copy = Assembly(
        owner_id=owner_id,
        name=copy_name(source.name, taken, max_length=ASSEMBLY_NAME_MAX_LENGTH),
        length_unit=source.length_unit,
    )
    session.add(copy)
    await session.flush()

    instances = (
        (
            await session.execute(
                select(Instance)
                .where(Instance.assembly_id == source.id)
                .order_by(Instance.order_index)
            )
        )
        .scalars()
        .all()
    )
    new_id = {instance.id: uuid.uuid4() for instance in instances}
    mapping = {str(old): str(new) for old, new in new_id.items()}
    for instance in instances:
        session.add(
            Instance(
                id=new_id[instance.id],
                assembly_id=copy.id,
                ref_document_id=instance.ref_document_id,
                ref_document_kind=instance.ref_document_kind,
                ref_pinned_version=instance.ref_pinned_version,
                name=instance.name,
                grounded=instance.grounded,
                placement=instance.placement,
                order_index=instance.order_index,
            )
        )
    mates = (
        (
            await session.execute(
                select(Mate)
                .where(Mate.assembly_id == source.id)
                .order_by(Mate.order_index)
            )
        )
        .scalars()
        .all()
    )
    for mate in mates:
        session.add(
            Mate(
                assembly_id=copy.id,
                order_index=mate.order_index,
                type=mate.type,
                params=remap_ids(mate.params, mapping),
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "An assembly with the copy's name already exists; rename it and try again.",
            code="assembly_name_taken",
        ) from None
    _logger.info(
        "assembly_duplicated",
        assembly_id=str(copy.id),
        source_assembly_id=str(source.id),
        instances=len(instances),
        mates=len(mates),
    )
    return AssemblyResponse.model_validate(copy)


@drawings_router.post("/{drawing_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_drawing(
    drawing_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> DrawingResponse:
    """Copy a drawing's sheets, views, dimensions and annotations (201).

    The views keep pointing at the same part/assembly — a view is a reference,
    like an instance. See the module docstring.
    """
    source = await get_owned_drawing(session, owner_id, drawing_id)
    taken = await _taken_names(session, Drawing, owner_id)
    copy = Drawing(
        owner_id=owner_id,
        name=copy_name(source.name, taken, max_length=DRAWING_NAME_MAX_LENGTH),
    )
    session.add(copy)
    await session.flush()

    sheets = (
        (
            await session.execute(
                select(Sheet)
                .where(Sheet.drawing_id == source.id)
                .order_by(Sheet.order_index)
            )
        )
        .scalars()
        .all()
    )
    sheet_ids = [sheet.id for sheet in sheets]
    views: Sequence[View] = (
        (
            await session.execute(
                select(View)
                .where(View.sheet_id.in_(sheet_ids))
                .order_by(View.order_index)
            )
        )
        .scalars()
        .all()
    )
    new_sheet_id = {sheet.id: uuid.uuid4() for sheet in sheets}
    new_view_id = {view.id: uuid.uuid4() for view in views}
    mapping = {str(old): str(new) for old, new in (new_sheet_id | new_view_id).items()}
    for sheet in sheets:
        session.add(
            Sheet(
                id=new_sheet_id[sheet.id],
                drawing_id=copy.id,
                name=sheet.name,
                size=sheet.size,
                orientation=sheet.orientation,
                projection=sheet.projection,
                title_block=sheet.title_block,
                order_index=sheet.order_index,
            )
        )
    for view in views:
        session.add(
            View(
                id=new_view_id[view.id],
                sheet_id=new_sheet_id[view.sheet_id],
                ref_document_id=view.ref_document_id,
                ref_document_kind=view.ref_document_kind,
                ref_pinned_version=view.ref_pinned_version,
                projection=view.projection,
                scale_num=view.scale_num,
                scale_den=view.scale_den,
                pos_x_mm=view.pos_x_mm,
                pos_y_mm=view.pos_y_mm,
                auto_place=view.auto_place,
                # A section plane may name a datum FEATURE of the referenced
                # part; that part is NOT copied, so those ids stay as they are —
                # `mapping` only holds this drawing's own sheet/view ids.
                section_params=remap_ids(view.section_params, mapping),
                order_index=view.order_index,
            )
        )
    dimensions = (
        (
            await session.execute(
                select(Dimension)
                .where(Dimension.sheet_id.in_(sheet_ids))
                .order_by(Dimension.order_index)
            )
        )
        .scalars()
        .all()
    )
    for dimension in dimensions:
        session.add(
            Dimension(
                sheet_id=new_sheet_id[dimension.sheet_id],
                view_id=new_view_id[dimension.view_id],
                order_index=dimension.order_index,
                type=dimension.type,
                params=remap_ids(dimension.params, mapping),
            )
        )
    annotations = (
        (
            await session.execute(
                select(Annotation)
                .where(Annotation.sheet_id.in_(sheet_ids))
                .order_by(Annotation.order_index)
            )
        )
        .scalars()
        .all()
    )
    for annotation in annotations:
        session.add(
            Annotation(
                sheet_id=new_sheet_id[annotation.sheet_id],
                order_index=annotation.order_index,
                type=annotation.type,
                params=remap_ids(annotation.params, mapping),
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "A drawing with the copy's name already exists; rename it and try again.",
            code="drawing_name_taken",
        ) from None
    _logger.info(
        "drawing_duplicated",
        drawing_id=str(copy.id),
        source_drawing_id=str(source.id),
        sheets=len(sheets),
        views=len(views),
    )
    return DrawingResponse.model_validate(copy)
