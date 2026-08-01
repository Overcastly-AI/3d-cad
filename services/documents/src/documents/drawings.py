"""``/api/v1/drawings`` — drawing CRUD (layout of sheets/views/dimensions/notes).

Implements the write rules of docs/design/drawings.md §2/§3: a NEW document type
(§2.1) — a LAYOUT that references parts/assemblies — with owner-scoped auth +
uniform-404 visibility (mirroring :mod:`documents.assemblies`), optimistic
concurrency via ``doc_version`` (stale write → **422**, keeping 409 unambiguous
for the dependents conflict), cross-document integrity enforced at write time (a
view's referenced part/assembly must exist; deleting a referenced document is a
**409-with-dependents** that now surfaces drawing views as well as assembly
instances — the shared :func:`documents.parts.reject_if_instanced`), and
dense-integer renumbering of the stable sheet/view/dimension/annotation order.

This service never imports kernel code (CLAUDE.md service boundaries): a dimension
names model geometry with pure-pydantic :class:`~py_kit.schemas.features.
EdgeSignature` refs, never a kernel type. A drawing is a pure LEAF consumer
(nothing references it — design §2.2), so — unlike assemblies — no acyclicity
walk is needed; deleting a drawing simply cascades its whole layout.
"""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query, status
from py_kit import ConflictError, NotFoundError, ValidationApiError, get_logger
from py_kit.db import SessionDep
from py_kit.schemas.assemblies import RefDocumentKind
from py_kit.schemas.drawings import (
    MAX_DRAWING_ANNOTATIONS,
    MAX_DRAWING_DIMENSIONS,
    MAX_DRAWING_SHEETS,
    MAX_DRAWING_VIEWS,
    AngularDimensionParams,
    Annotation,
    AnnotationCreate,
    AnnotationMutationResponse,
    AnnotationResponse,
    DiameterDimensionParams,
    Dimension,
    DimensionCreate,
    DimensionMutationResponse,
    DimensionParams,
    DimensionResponse,
    DrawingBomLine,
    DrawingBomResponse,
    DrawingCreate,
    DrawingListResponse,
    DrawingResponse,
    DrawingTreeResponse,
    DrawingUpdate,
    RadiusDimensionParams,
    SectionViewParams,
    SheetContent,
    SheetCreate,
    SheetMutationResponse,
    SheetResponse,
    SheetUpdate,
    ViewCreate,
    ViewMutationResponse,
    ViewResponse,
    ViewScale,
    ViewUpdate,
)
from py_kit.schemas.drawings import (
    SheetPoint as SheetPointDTO,
)
from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from documents import db
from documents.assemblies import resolve_document_names
from documents.assembly_history import ordered_instances
from documents.filing import resolve_destination
from documents.parts import (
    Principal,
    get_owned_drawing,
    referenced_document_exists,
)

_logger = get_logger("documents.drawings")

router = APIRouter(prefix="/api/v1/drawings", tags=["drawings"])

#: Reconstruct a stored dimension / annotation row's params into its union.
_DIMENSION_ADAPTER: TypeAdapter[Dimension] = TypeAdapter(Dimension)
_ANNOTATION_ADAPTER: TypeAdapter[Annotation] = TypeAdapter(Annotation)

_OrderedModel = (
    type[db.Sheet] | type[db.View] | type[db.Dimension] | type[db.Annotation]
)


# --- shared plumbing --------------------------------------------------------------


def _ensure_fresh(drawing: db.Drawing, expected_version: int) -> None:
    """Optimistic-concurrency gate: stale writes are 422 (design §2.1).

    422 — NOT 409 — so the two write-failure modes are distinguishable by status
    alone (409 stays reserved for the delete-with-dependents conflict).
    """
    if drawing.doc_version != expected_version:
        raise ValidationApiError(
            "Stale drawing version: the drawing changed since it was last read.",
            code="stale_drawing_version",
            details={"provided": expected_version, "current": drawing.doc_version},
        )


async def _count(
    session: AsyncSession,
    model: _OrderedModel,
    scope_column: InstrumentedAttribute[uuid.UUID],
    scope_id: uuid.UUID,
) -> int:
    """How many rows the scope already holds (the append position)."""
    result = await session.execute(
        select(func.count()).select_from(model).where(scope_column == scope_id)
    )
    return int(result.scalar_one())


async def _renumber_dense(
    session: AsyncSession,
    model: _OrderedModel,
    scope_column: InstrumentedAttribute[uuid.UUID],
    scope_id: uuid.UUID,
) -> None:
    """Compact a scope's ``order_index`` to a dense 0..n-1 after a delete.

    Rows are re-read in current order and reassigned ascending: each new index is
    <= the row's current index and processed lowest-first, so no in-flight value
    ever collides with an existing one — correct under IMMEDIATE unique checking
    (no deferrable constraint needed). Robust to a DB CASCADE that removed rows in
    the MIDDLE of the scope (a view delete cascades its dimensions, leaving gaps
    in the sheet's dimension order).
    """
    result = await session.execute(
        select(model.id, model.order_index)
        .where(scope_column == scope_id)
        .order_by(model.order_index)
    )
    for new_index, (row_id, order_index) in enumerate(result.all()):
        if order_index != new_index:
            await session.execute(
                update(model).where(model.id == row_id).values(order_index=new_index)
            )


async def _sheet_views(session: AsyncSession, sheet_id: uuid.UUID) -> list[db.View]:
    """A sheet's views in ``order_index`` order, typed as :class:`db.View`.

    The narrow twin of :func:`_ordered` (which returns the untyped row union):
    the sheet-consistency guards below need the VIEW columns (``ref_document_id`` /
    ``scale_*`` / ``projection``), and reading them once also supplies the append
    position — one query where ``_count`` + a read would have been two.
    """
    result = await session.execute(
        select(db.View)
        .where(db.View.sheet_id == sheet_id)
        .order_by(db.View.order_index)
    )
    return list(result.scalars())


async def _ordered(
    session: AsyncSession,
    model: _OrderedModel,
    scope_column: InstrumentedAttribute[uuid.UUID],
    scope_id: uuid.UUID,
) -> list[db.Sheet | db.View | db.Dimension | db.Annotation]:
    """A scope's rows, ``ORDER BY order_index`` (total by uniqueness)."""
    result = await session.execute(
        select(model)
        .where(scope_column == scope_id)
        .order_by(model.order_index)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _get_sheet(
    session: AsyncSession, drawing: db.Drawing, sheet_id: uuid.UUID
) -> db.Sheet:
    """A sheet of *drawing*, or 404 (unknown id == another drawing's id)."""
    sheet = await session.get(db.Sheet, sheet_id)
    if sheet is None or sheet.drawing_id != drawing.id:
        raise NotFoundError("Sheet not found.", code="sheet_not_found")
    return sheet


async def _get_view_and_sheet(
    session: AsyncSession, drawing: db.Drawing, view_id: uuid.UUID
) -> tuple[db.View, db.Sheet]:
    """A view of *drawing* + its owning sheet, or 404 (foreign id == unknown)."""
    view = await session.get(db.View, view_id)
    if view is None:
        raise NotFoundError("View not found.", code="view_not_found")
    sheet = await session.get(db.Sheet, view.sheet_id)
    if sheet is None or sheet.drawing_id != drawing.id:
        raise NotFoundError("View not found.", code="view_not_found")
    return view, sheet


async def _get_dimension_and_sheet(
    session: AsyncSession, drawing: db.Drawing, dimension_id: uuid.UUID
) -> tuple[db.Dimension, db.Sheet]:
    """A dimension of *drawing* + its sheet, or 404 (foreign id == unknown)."""
    dimension = await session.get(db.Dimension, dimension_id)
    if dimension is None:
        raise NotFoundError("Dimension not found.", code="dimension_not_found")
    sheet = await session.get(db.Sheet, dimension.sheet_id)
    if sheet is None or sheet.drawing_id != drawing.id:
        raise NotFoundError("Dimension not found.", code="dimension_not_found")
    return dimension, sheet


async def _get_annotation_and_sheet(
    session: AsyncSession, drawing: db.Drawing, annotation_id: uuid.UUID
) -> tuple[db.Annotation, db.Sheet]:
    """An annotation of *drawing* + its sheet, or 404 (foreign id == unknown)."""
    annotation = await session.get(db.Annotation, annotation_id)
    if annotation is None:
        raise NotFoundError("Annotation not found.", code="annotation_not_found")
    sheet = await session.get(db.Sheet, annotation.sheet_id)
    if sheet is None or sheet.drawing_id != drawing.id:
        raise NotFoundError("Annotation not found.", code="annotation_not_found")
    return annotation, sheet


def _ensure_sheet_source(
    siblings: list[db.View],
    ref_document_id: uuid.UUID,
    ref_document_kind: str,
    scale: ViewScale,
) -> None:
    """One sheet, one source document, one scale (engineering audit **H2**) → 422.

    **The design decision, stated once here.** A sheet composes from EXACTLY ONE
    source document at EXACTLY ONE scale: ``ComposeDrawingRequest`` carries a single
    ``part``/``assembly`` source and a single ``scale``, so the gateway necessarily
    reduces a sheet to its FIRST view's document + scale
    (``gateway.drawings._compose_request``). Before this guard the schema permitted
    a sheet whose views named different parts or different scales, and the export
    then projected EVERY view from view 0's part at view 0's scale — silently, with
    the other views' captions intact. A wrong drawing that prints is worse than a
    refused one, so documents REFUSES the inconsistent write (option (a) of the
    audit's two): the invariant the whole stack already assumes is now enforced at
    the only place that can create the violation.

    Per-view sources / per-view scales are a real feature (multi-part detail
    sheets), not a bug fix: threading them means per-view sources through
    ``ComposeDrawingRequest`` + geometry, a separate slice (BACKLOG). Until then a
    caller re-points a sheet by deleting its views (the same rule that already makes
    re-pointing a view a delete + recreate) or drafts on another sheet.
    """
    if not siblings:
        return
    source = siblings[0]
    if (
        ref_document_id != source.ref_document_id
        or ref_document_kind != source.ref_document_kind
    ):
        raise ValidationApiError(
            "Every view on a sheet must reference the same document: this sheet "
            f"already drafts {source.ref_document_kind} {source.ref_document_id}. "
            "Use another sheet for a different part or assembly.",
            code="sheet_source_document_mismatch",
            details={
                "sheet_ref_document_id": str(source.ref_document_id),
                "sheet_ref_document_kind": source.ref_document_kind,
                "ref_document_id": str(ref_document_id),
                "ref_document_kind": ref_document_kind,
            },
        )
    if (scale.numerator, scale.denominator) != (source.scale_num, source.scale_den):
        raise ValidationApiError(
            "Every view on a sheet must share one scale: this sheet drafts at "
            f"{source.scale_num}:{source.scale_den}. Per-view scale is not "
            "composed in v1.",
            code="sheet_view_scale_mismatch",
            details={
                "sheet_scale": f"{source.scale_num}:{source.scale_den}",
                "scale": f"{scale.numerator}:{scale.denominator}",
            },
        )


def _ensure_unique_projection(
    siblings: list[db.View], projection: str, view_id: uuid.UUID | None = None
) -> None:
    """One view per projection per sheet (engineering audit **H3**) → 422.

    The application twin of ``uq_views_sheet_projection`` (migration 0011): the
    composer keys anchors by projection and the frontend keys its view maps by
    projection, so a second ``front``/``section`` view on one sheet never composed
    AND made a drag-to-place PATCH persist onto the other row. A typed 422 here
    turns what would be an IntegrityError 500 into an honest refusal (and states
    WHY, which the DB error cannot). ``view_id`` excludes the row being updated so
    a no-op re-projection of a view onto itself stays legal.
    """
    clash = next(
        (
            other
            for other in siblings
            if other.projection == projection and other.id != view_id
        ),
        None,
    )
    if clash is not None:
        raise ValidationApiError(
            f"This sheet already carries a {projection!r} view. One view per "
            "projection per sheet; use another sheet for a second one.",
            code="duplicate_view_projection",
            details={"projection": projection, "existing_view_id": str(clash.id)},
        )


def _validate_dimension(dimension: DimensionParams) -> None:
    """Write-time semantic checks a dimension can carry (design §3.1) → 422.

    The kernel-free checks documents CAN make on the DTO (the measured value is
    geometry's job): a diameter/radius must name a CIRCULAR edge, and an angular
    dimension must name two STRAIGHT edges — a typed 422 at the boundary, never a
    500 or a nonsense stored dimension. Malformed / mis-typed payloads are already
    a FastAPI request-validation 422 via the discriminated :data:`Dimension`
    union; this catches the geometrically-inconsistent-but-well-typed case.
    """
    if isinstance(dimension, DiameterDimensionParams | RadiusDimensionParams):
        if dimension.edge.curve != "circle":
            raise ValidationApiError(
                f"A {dimension.type} dimension requires a circular edge; the "
                f"referenced edge is '{dimension.edge.curve}'.",
                code="dimension_requires_circular_edge",
                details={"type": dimension.type, "curve": dimension.edge.curve},
            )
    elif isinstance(dimension, AngularDimensionParams):
        for label, edge in (("edge_a", dimension.edge_a), ("edge_b", dimension.edge_b)):
            if edge.curve != "line":
                raise ValidationApiError(
                    "An angular dimension requires two straight edges; "
                    f"'{label}' is '{edge.curve}'.",
                    code="dimension_requires_straight_edges",
                    details={label: edge.curve},
                )


# --- serialization ----------------------------------------------------------------


def _sheet_response(sheet: db.Sheet) -> SheetResponse:
    """Row → DTO (``from_attributes``): the title_block JSONB is validated by
    pydantic into a TitleBlock (or stays None)."""
    return SheetResponse.model_validate(sheet)


def _view_response(view: db.View) -> ViewResponse:
    """Row → DTO: the scale + position scalar columns are re-composed into their
    :class:`ViewScale` / :class:`SheetPoint` models."""
    return ViewResponse(
        id=view.id,
        sheet_id=view.sheet_id,
        ref_document_id=view.ref_document_id,
        ref_document_kind=view.ref_document_kind,  # type: ignore[arg-type]
        ref_pinned_version=view.ref_pinned_version,
        projection=view.projection,  # type: ignore[arg-type]
        scale=ViewScale(numerator=view.scale_num, denominator=view.scale_den),
        position=SheetPointDTO(x_mm=view.pos_x_mm, y_mm=view.pos_y_mm),
        auto_place=view.auto_place,
        section_params=(
            SectionViewParams.model_validate(view.section_params)
            if view.section_params is not None
            else None
        ),
        order_index=view.order_index,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _dimension_response(dimension: db.Dimension) -> DimensionResponse:
    """Row → DTO: the params JSONB reassembled into the discriminated union."""
    return DimensionResponse(
        id=dimension.id,
        sheet_id=dimension.sheet_id,
        view_id=dimension.view_id,
        order_index=dimension.order_index,
        dimension=_DIMENSION_ADAPTER.validate_python(dimension.params),
    )


def _annotation_response(annotation: db.Annotation) -> AnnotationResponse:
    """Row → DTO: the params JSONB reassembled into the annotation model."""
    return AnnotationResponse(
        id=annotation.id,
        sheet_id=annotation.sheet_id,
        order_index=annotation.order_index,
        annotation=_ANNOTATION_ADAPTER.validate_python(annotation.params),
    )


async def _by_sheet[SheetScoped: (db.View, db.Dimension, db.Annotation)](
    session: AsyncSession,
    model: type[SheetScoped],
    sheet_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[SheetScoped]]:
    """All of *sheet_ids*' rows of *model*, grouped by sheet, in stored order.

    ONE query for the whole drawing instead of one per sheet (engineering audit
    **H5**): ``_tree_response`` is the body of ``GET /drawings/{id}`` AND of every
    delete route, and it used to issue three queries PER SHEET. Ordering by
    ``(sheet_id, order_index)`` makes each group's insertion order the stored
    order, so the grouping is a single pass with no per-group sort.
    """
    if not sheet_ids:
        return {}
    result = await session.execute(
        select(model)
        .where(model.sheet_id.in_(sheet_ids))
        .order_by(model.sheet_id, model.order_index)
        .execution_options(populate_existing=True)
    )
    grouped: dict[uuid.UUID, list[SheetScoped]] = {
        sheet_id: [] for sheet_id in sheet_ids
    }
    for row in result.scalars():
        grouped[row.sheet_id].append(row)
    return grouped


async def _tree_response(
    session: AsyncSession, drawing: db.Drawing
) -> DrawingTreeResponse:
    sheets = [
        sheet
        for sheet in await _ordered(session, db.Sheet, db.Sheet.drawing_id, drawing.id)
        if isinstance(sheet, db.Sheet)
    ]
    sheet_ids = [sheet.id for sheet in sheets]
    views = await _by_sheet(session, db.View, sheet_ids)
    dimensions = await _by_sheet(session, db.Dimension, sheet_ids)
    annotations = await _by_sheet(session, db.Annotation, sheet_ids)
    contents = [
        SheetContent(
            sheet=_sheet_response(sheet),
            views=[_view_response(v) for v in views[sheet.id]],
            dimensions=[_dimension_response(d) for d in dimensions[sheet.id]],
            annotations=[_annotation_response(a) for a in annotations[sheet.id]],
        )
        for sheet in sheets
    ]
    return DrawingTreeResponse(
        drawing=DrawingResponse.model_validate(drawing),
        doc_version=drawing.doc_version,
        sheets=contents,
    )


# --- drawing routes ---------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_drawing(
    request: DrawingCreate, owner_id: Principal, session: SessionDep
) -> DrawingResponse:
    """Create a drawing (201; 409 on a duplicate name IN ITS FOLDER).

    ``folder_id`` files it on creation (#WS2) — see :func:`documents.parts.
    create_part` for why filing is part of the create rather than a second call.
    """
    await resolve_destination(session, owner_id, request.folder_id, "drawing")
    drawing = db.Drawing(
        owner_id=owner_id, name=request.name, folder_id=request.folder_id
    )
    session.add(drawing)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A drawing named {request.name!r} already exists.",
            code="drawing_name_taken",
        ) from None
    _logger.info("drawing_created", drawing_id=str(drawing.id), owner_id=str(owner_id))
    return DrawingResponse.model_validate(drawing)


@router.get("")
async def list_drawings(
    owner_id: Principal, session: SessionDep
) -> DrawingListResponse:
    """The caller's drawings, oldest first (deterministic id tiebreak)."""
    result = await session.execute(
        select(db.Drawing)
        .where(db.Drawing.owner_id == owner_id)
        .order_by(db.Drawing.created_at, db.Drawing.id)
    )
    return DrawingListResponse(
        drawings=[DrawingResponse.model_validate(row) for row in result.scalars()]
    )


@router.get("/{drawing_id}")
async def get_drawing(
    drawing_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> DrawingTreeResponse:
    """One owned drawing with its full sheet/view/dimension/annotation tree."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id)
    return await _tree_response(session, drawing)


# --- the sheet's bill of materials (design §7 BOM — a DERIVED read model) ---------


async def _bom_source_assembly(
    session: AsyncSession,
    owner_id: uuid.UUID,
    drawing: db.Drawing,
    sheet_id: uuid.UUID | None,
) -> tuple[db.Sheet, db.Assembly]:
    """The sheet to bill + the ASSEMBLY it drafts, or a typed refusal (design §7).

    Selects the requested ``sheet_id`` (the FIRST sheet when omitted — the same
    default ``?sheet=`` gives the compose/export routes) and resolves its single
    source document. "One sheet, one source" is an ENFORCED invariant
    (:func:`_ensure_sheet_source`), so the sheet's first view IS its source.

    Every failure is typed and honest rather than an empty list:
    ``sheet_not_found`` (404 — no sheets at all, or an id from another drawing),
    ``sheet_has_no_views`` (422 — nothing laid out, so no source document),
    ``drawing_bom_source_not_assembly`` (422 — a PART drawing genuinely has no bill
    of materials; an empty BOM would falsely read as "no items"), and
    ``drawing_bom_source_missing`` (422 — the source assembly is gone; normally
    impossible, since deleting a referenced document is a 409-with-dependents).
    """
    if sheet_id is None:
        sheets = await _ordered(session, db.Sheet, db.Sheet.drawing_id, drawing.id)
        if not sheets:
            raise NotFoundError(
                "This drawing has no sheets to bill.", code="sheet_not_found"
            )
        sheet = sheets[0]
        assert isinstance(sheet, db.Sheet)
    else:
        sheet = await _get_sheet(session, drawing, sheet_id)

    views = await _sheet_views(session, sheet.id)
    if not views:
        raise ValidationApiError(
            "This sheet has no views, so it references no document to bill; lay "
            "out its standard views first.",
            code="sheet_has_no_views",
            details={"sheet_id": str(sheet.id)},
        )
    source = views[0]
    if source.ref_document_kind != "assembly":
        raise ValidationApiError(
            "This sheet drafts a part, and a part drawing has no bill of "
            "materials; a BOM is derived from an assembly's instances.",
            code="drawing_bom_source_not_assembly",
            details={
                "sheet_id": str(sheet.id),
                "ref_document_id": str(source.ref_document_id),
                "ref_document_kind": source.ref_document_kind,
            },
        )
    assembly = await session.get(db.Assembly, source.ref_document_id)
    if assembly is None or assembly.owner_id != owner_id:
        raise ValidationApiError(
            "The assembly this sheet drafts no longer exists, so its bill of "
            "materials cannot be derived.",
            code="drawing_bom_source_missing",
            details={
                "sheet_id": str(sheet.id),
                "ref_document_id": str(source.ref_document_id),
            },
        )
    return sheet, assembly


async def _bom_lines(
    session: AsyncSession, assembly: db.Assembly
) -> list[DrawingBomLine]:
    """Number the assembly's direct instances into drawing BOM lines (design §7).

    **Item numbers are DERIVED here, never stored** (the identity decision, design
    §7.1): the instances are walked in the assembly's own stable ``order_index``
    (its display/BOM order) and each referenced document takes the next item number
    at its FIRST appearance, quantities accumulating onto that line. Consequences,
    stated: a part RENAME never renumbers (unlike the name-sorted
    ``GET /assemblies/{id}/bom``, whose order is a display convenience); adding,
    removing, or reordering an instance does — a real edit, and the reason nothing
    downstream may cache a number.

    FLAT, like the assembly BOM: a rigid sub-assembly instance is a single
    ``kind: "assembly"`` line, never expanded. A referenced document deleted while
    still instanced keeps its line with ``missing`` true and a null name — the
    quantity is never silently dropped.
    """
    instances = await ordered_instances(session, assembly.id)
    order: list[tuple[uuid.UUID, RefDocumentKind]] = []
    quantities: dict[tuple[uuid.UUID, RefDocumentKind], int] = {}
    for instance in instances:
        key = (
            instance.ref_document_id,
            cast(RefDocumentKind, instance.ref_document_kind),
        )
        if key not in quantities:
            order.append(key)
            quantities[key] = 0
        quantities[key] += 1
    names = await resolve_document_names(session, assembly.owner_id, set(order))
    return [
        DrawingBomLine(
            item_number=index + 1,
            ref_document_id=ref_id,
            ref_document_kind=kind,
            name=names.get((ref_id, kind)),
            missing=(ref_id, kind) not in names,
            quantity=quantities[(ref_id, kind)],
        )
        for index, (ref_id, kind) in enumerate(order)
    ]


@router.get("/{drawing_id}/bom")
async def get_drawing_bom(
    drawing_id: uuid.UUID,
    owner_id: Principal,
    session: SessionDep,
    sheet: Annotated[
        uuid.UUID | None,
        Query(
            description="Which sheet to bill (a sheet id from the drawing tree); "
            "omit to bill the FIRST sheet, the same default the compose/export "
            "routes take. An unknown/foreign id is a `sheet_not_found` 404.",
        ),
    ] = None,
) -> DrawingBomResponse:
    """The sheet's bill of materials — numbered items derived from its assembly.

    A pure READ MODEL (no table, no migration, no write path): the sheet's single
    source document must be an ASSEMBLY, and its DIRECT instances roll up into
    ``item_number``-ed lines. **The numbers are derived on every read from the
    assembly's stable instance order and are never persisted on the drawing** —
    the drift class a stored number would create (the assembly changes; the print
    keeps the old number and is silently wrong) is designed out rather than
    detected. ``assembly_version`` is echoed so a tip-tracking client can see the
    source move under it.

    Typed refusals, never a misleading empty list: ``sheet_not_found`` (404),
    ``sheet_has_no_views`` / ``drawing_bom_source_not_assembly`` /
    ``drawing_bom_source_missing`` (422). Uniform 404 for an unknown or foreign
    drawing.
    """
    drawing = await get_owned_drawing(session, owner_id, drawing_id)
    sheet_row, assembly = await _bom_source_assembly(session, owner_id, drawing, sheet)
    lines = await _bom_lines(session, assembly)
    return DrawingBomResponse(
        drawing_id=drawing.id,
        sheet_id=sheet_row.id,
        assembly_id=assembly.id,
        assembly_version=assembly.doc_version,
        lines=lines,
        total_instances=sum(line.quantity for line in lines),
    )


@router.patch("/{drawing_id}")
async def update_drawing(
    drawing_id: uuid.UUID,
    request: DrawingUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> DrawingResponse:
    """Rename a drawing (bumps ``doc_version``; envelope 409 on a name clash)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    drawing.name = request.name
    drawing.doc_version += 1
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            f"A drawing named {request.name!r} already exists.",
            code="drawing_name_taken",
        ) from None
    _logger.info(
        "drawing_updated", drawing_id=str(drawing.id), doc_version=drawing.doc_version
    )
    return DrawingResponse.model_validate(drawing)


@router.delete("/{drawing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drawing(
    drawing_id: uuid.UUID, owner_id: Principal, session: SessionDep
) -> None:
    """Delete an owned drawing (204; uniform 404 for unknown/foreign ids).

    A drawing is a pure LEAF (nothing references it — design §2.2), so there is no
    dependents pre-check: the drawing→sheets→views→dimensions and
    sheets→annotations CASCADE removes its entire layout.
    """
    drawing = await get_owned_drawing(session, owner_id, drawing_id)
    await session.delete(drawing)
    await session.commit()
    _logger.info("drawing_deleted", drawing_id=str(drawing_id), owner_id=str(owner_id))


# --- sheet routes -----------------------------------------------------------------


@router.post("/{drawing_id}/sheets", status_code=status.HTTP_201_CREATED)
async def create_sheet(
    drawing_id: uuid.UUID,
    request: SheetCreate,
    owner_id: Principal,
    session: SessionDep,
) -> SheetMutationResponse:
    """Add a sheet to a drawing (append at the tip)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    position = await _count(session, db.Sheet, db.Sheet.drawing_id, drawing_id)
    # Write-side twin of `DrawingTreeResponse.sheets`' `max_length` parse bound
    # (audit H5, the G2 idiom): every read of this drawing serializes the WHOLE
    # sheet tree, so an unbounded sheet count is an unbounded response — and once
    # persisted past the DTO ceiling the drawing could not be read back at all.
    if position >= MAX_DRAWING_SHEETS:
        raise ValidationApiError(
            f"A drawing holds at most {MAX_DRAWING_SHEETS} sheets (per-request "
            "work bound); delete sheets before adding more.",
            code="sheet_limit_exceeded",
            details={"max_sheets": MAX_DRAWING_SHEETS},
        )
    sheet = db.Sheet(
        id=uuid.uuid4(),
        drawing_id=drawing_id,
        name=request.name,
        size=request.size,
        orientation=request.orientation,
        projection=request.projection,
        title_block=(
            request.title_block.model_dump(mode="json")
            if request.title_block is not None
            else None
        ),
        order_index=position,
    )
    session.add(sheet)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "sheet_created",
        drawing_id=str(drawing_id),
        sheet_id=str(sheet.id),
        doc_version=drawing.doc_version,
    )
    return SheetMutationResponse(
        sheet=_sheet_response(sheet), doc_version=drawing.doc_version
    )


@router.patch("/{drawing_id}/sheets/{sheet_id}")
async def update_sheet(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: SheetUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> SheetMutationResponse:
    """Update a sheet's header (bumps ``doc_version``)."""
    if (
        request.name is None
        and request.size is None
        and request.orientation is None
        and request.projection is None
        and request.title_block is None
    ):
        raise ValidationApiError(
            "Provide at least one of name, size, orientation, projection, or "
            "title_block.",
            code="empty_sheet_update",
        )
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    sheet = await _get_sheet(session, drawing, sheet_id)

    if request.name is not None:
        sheet.name = request.name
    if request.size is not None:
        sheet.size = request.size
    if request.orientation is not None:
        sheet.orientation = request.orientation
    if request.projection is not None:
        sheet.projection = request.projection
    if request.title_block is not None:
        sheet.title_block = request.title_block.model_dump(mode="json")

    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "sheet_updated",
        drawing_id=str(drawing_id),
        sheet_id=str(sheet_id),
        doc_version=drawing.doc_version,
    )
    return SheetMutationResponse(
        sheet=_sheet_response(sheet), doc_version=drawing.doc_version
    )


@router.delete("/{drawing_id}/sheets/{sheet_id}")
async def delete_sheet(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard (design §2.1)")
    ],
    owner_id: Principal,
    session: SessionDep,
) -> DrawingTreeResponse:
    """Delete a sheet (cascades its views/dimensions/annotations); renumbers the
    remaining sheets dense (bumps ``doc_version``)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, expected_version)
    sheet = await _get_sheet(session, drawing, sheet_id)

    await session.delete(sheet)
    await session.flush()
    await _renumber_dense(session, db.Sheet, db.Sheet.drawing_id, drawing_id)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "sheet_deleted",
        drawing_id=str(drawing_id),
        sheet_id=str(sheet_id),
        doc_version=drawing.doc_version,
    )
    return await _tree_response(session, drawing)


# --- view routes ------------------------------------------------------------------


@router.post(
    "/{drawing_id}/sheets/{sheet_id}/views", status_code=status.HTTP_201_CREATED
)
async def create_view(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: ViewCreate,
    owner_id: Principal,
    session: SessionDep,
) -> ViewMutationResponse:
    """Add a view referencing a part / assembly (append at the tip).

    Enforces cross-document integrity (§2.2): the referenced document must exist
    and belong to the caller (else ``ref_document_not_found`` 422). No acyclicity
    check — a drawing is a leaf consumer (§2.2). ``ref_pinned_version`` is stored
    NULL: v1 tracks the referenced document's tip (§2.3).

    Also enforces the SHEET-consistency invariant (design §2.2 "one sheet, one
    source"; engineering audit H2): every view of a sheet must reference the SAME
    document at the SAME scale, because composition threads exactly one source +
    one scale per sheet (``ComposeDrawingRequest``). A mismatch is a typed
    ``sheet_source_document_mismatch`` / ``sheet_view_scale_mismatch`` 422 —
    the alternative was silently projecting every view from the first view's part
    at the first view's scale, i.e. a wrong drawing a shop would cut from.
    """
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    sheet = await _get_sheet(session, drawing, sheet_id)

    if not await referenced_document_exists(
        session, owner_id, request.ref_document_id, request.ref_document_kind
    ):
        raise ValidationApiError(
            f"Referenced {request.ref_document_kind} {request.ref_document_id} "
            "does not exist.",
            code="ref_document_not_found",
            details={
                "ref_document_id": str(request.ref_document_id),
                "ref_document_kind": request.ref_document_kind,
            },
        )

    siblings = await _sheet_views(session, sheet.id)
    position = len(siblings)
    # Write-side twin of the compose/evaluate `max_length=MAX_DRAWING_VIEWS`
    # parse bound (audit G2): a sheet must never accumulate views the compose
    # contract rejects, or every later export read would fail building the DTO.
    if position >= MAX_DRAWING_VIEWS:
        raise ValidationApiError(
            f"A sheet holds at most {MAX_DRAWING_VIEWS} views (per-request "
            "work bound); delete views before adding more.",
            code="view_limit_exceeded",
            details={"max_views": MAX_DRAWING_VIEWS},
        )
    _ensure_sheet_source(
        siblings, request.ref_document_id, request.ref_document_kind, request.scale
    )
    _ensure_unique_projection(siblings, request.projection)
    view = db.View(
        id=uuid.uuid4(),
        sheet_id=sheet.id,
        ref_document_id=request.ref_document_id,
        ref_document_kind=request.ref_document_kind,
        ref_pinned_version=None,  # v1 tracks tip (§2.3)
        projection=request.projection,
        scale_num=request.scale.numerator,
        scale_den=request.scale.denominator,
        pos_x_mm=request.position.x_mm,
        pos_y_mm=request.position.y_mm,
        auto_place=request.auto_place,
        section_params=(
            request.section_params.model_dump(mode="json")
            if request.section_params is not None
            else None
        ),
        order_index=position,
    )
    session.add(view)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "view_created",
        drawing_id=str(drawing_id),
        view_id=str(view.id),
        ref_document_id=str(view.ref_document_id),
        doc_version=drawing.doc_version,
    )
    return ViewMutationResponse(
        view=_view_response(view), doc_version=drawing.doc_version
    )


@router.patch("/{drawing_id}/views/{view_id}")
async def update_view(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    request: ViewUpdate,
    owner_id: Principal,
    session: SessionDep,
) -> ViewMutationResponse:
    """Re-frame / re-scale / re-place a view (bumps ``doc_version``).

    The drag-to-place write path (drawing-export.md §4.2): a frontend PERSISTS a
    dragged position by patching ``position`` + ``auto_place=false`` — the position
    then survives reload and the compose/export path honors it verbatim (threaded
    into ``SheetViewPlacement.auto_place``) instead of auto-placing. ``auto_place=true``
    returns the view to bounds-aware auto-layout.

    Re-pointing the referenced document is deliberately NOT an update (it changes
    which body the view's dimensions resolve against) — delete + recreate.
    """
    if (
        request.projection is None
        and request.scale is None
        and request.position is None
        and request.auto_place is None
    ):
        raise ValidationApiError(
            "Provide at least one of projection, scale, position, or auto_place.",
            code="empty_view_update",
        )
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    view, _sheet = await _get_view_and_sheet(session, drawing, view_id)

    if request.projection is not None and request.projection != view.projection:
        # H3: re-projecting onto a projection the sheet already carries would
        # collapse two rows into one composed view (and mis-target later drags).
        _ensure_unique_projection(
            await _sheet_views(session, view.sheet_id), request.projection, view.id
        )

    if request.scale is not None and (
        request.scale.numerator,
        request.scale.denominator,
    ) != (view.scale_num, view.scale_den):
        # The H2 invariant on the UPDATE path: re-scaling ONE view of a
        # multi-view sheet would compose every view at view 0's scale (see
        # `_ensure_sheet_source`), so a divergent re-scale is refused. Re-scaling
        # a single-view sheet, or a sheet re-scaled view-by-view to a value it
        # already shares, stays legal.
        siblings = [
            other
            for other in await _sheet_views(session, view.sheet_id)
            if other.id != view.id
        ]
        _ensure_sheet_source(
            siblings, view.ref_document_id, view.ref_document_kind, request.scale
        )

    if request.projection is not None:
        view.projection = request.projection
    if request.scale is not None:
        view.scale_num = request.scale.numerator
        view.scale_den = request.scale.denominator
    if request.position is not None:
        view.pos_x_mm = request.position.x_mm
        view.pos_y_mm = request.position.y_mm
    if request.auto_place is not None:
        view.auto_place = request.auto_place

    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "view_updated",
        drawing_id=str(drawing_id),
        view_id=str(view_id),
        doc_version=drawing.doc_version,
    )
    return ViewMutationResponse(
        view=_view_response(view), doc_version=drawing.doc_version
    )


@router.delete("/{drawing_id}/views/{view_id}")
async def delete_view(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard (design §2.1)")
    ],
    owner_id: Principal,
    session: SessionDep,
) -> DrawingTreeResponse:
    """Delete a view; also removes the dimensions it carries (bumps version).

    A dimension is meaningless without the view it annotates — the ``view_id``
    CASCADE removes the view's dimensions. Both the sheet's views AND its
    dimensions are then renumbered dense (the cascade can leave gaps in the
    per-sheet dimension order). Returns the updated tree (the client's new
    ``doc_version``)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, expected_version)
    view, sheet = await _get_view_and_sheet(session, drawing, view_id)

    await session.delete(view)
    await session.flush()
    await _renumber_dense(session, db.View, db.View.sheet_id, sheet.id)
    await _renumber_dense(session, db.Dimension, db.Dimension.sheet_id, sheet.id)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "view_deleted",
        drawing_id=str(drawing_id),
        view_id=str(view_id),
        doc_version=drawing.doc_version,
    )
    return await _tree_response(session, drawing)


# --- dimension routes -------------------------------------------------------------


@router.post(
    "/{drawing_id}/views/{view_id}/dimensions", status_code=status.HTTP_201_CREATED
)
async def create_dimension(
    drawing_id: uuid.UUID,
    view_id: uuid.UUID,
    request: DimensionCreate,
    owner_id: Principal,
    session: SessionDep,
) -> DimensionMutationResponse:
    """Add a dimension to a view (append at the tip, ordered per sheet).

    The dimension's geometry references resolve against the view's referenced body
    geometry-side (design §3.3); documents stores the reference + type and runs
    the kernel-free write-time checks (:func:`_validate_dimension`)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    view, sheet = await _get_view_and_sheet(session, drawing, view_id)
    _validate_dimension(request.dimension)

    position = await _count(session, db.Dimension, db.Dimension.sheet_id, sheet.id)
    # Write-side twin of the `max_length=MAX_DRAWING_DIMENSIONS` parse bound
    # (audit G2) — same rationale as the view cap above.
    if position >= MAX_DRAWING_DIMENSIONS:
        raise ValidationApiError(
            f"A sheet holds at most {MAX_DRAWING_DIMENSIONS} dimensions "
            "(per-request work bound); delete dimensions before adding more.",
            code="dimension_limit_exceeded",
            details={"max_dimensions": MAX_DRAWING_DIMENSIONS},
        )
    dimension = db.Dimension(
        id=uuid.uuid4(),
        sheet_id=sheet.id,
        view_id=view.id,
        order_index=position,
        type=request.dimension.type,
        params=request.dimension.model_dump(mode="json"),
    )
    session.add(dimension)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "dimension_created",
        drawing_id=str(drawing_id),
        view_id=str(view_id),
        dimension_id=str(dimension.id),
        dimension_type=dimension.type,
        doc_version=drawing.doc_version,
    )
    return DimensionMutationResponse(
        dimension=_dimension_response(dimension), doc_version=drawing.doc_version
    )


@router.delete("/{drawing_id}/dimensions/{dimension_id}")
async def delete_dimension(
    drawing_id: uuid.UUID,
    dimension_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard (design §2.1)")
    ],
    owner_id: Principal,
    session: SessionDep,
) -> DrawingTreeResponse:
    """Delete a dimension; renumbers the sheet's dimensions dense (bumps version)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, expected_version)
    dimension, sheet = await _get_dimension_and_sheet(session, drawing, dimension_id)

    await session.delete(dimension)
    await session.flush()
    await _renumber_dense(session, db.Dimension, db.Dimension.sheet_id, sheet.id)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "dimension_deleted",
        drawing_id=str(drawing_id),
        dimension_id=str(dimension_id),
        doc_version=drawing.doc_version,
    )
    return await _tree_response(session, drawing)


# --- annotation routes ------------------------------------------------------------


@router.post(
    "/{drawing_id}/sheets/{sheet_id}/annotations", status_code=status.HTTP_201_CREATED
)
async def create_annotation(
    drawing_id: uuid.UUID,
    sheet_id: uuid.UUID,
    request: AnnotationCreate,
    owner_id: Principal,
    session: SessionDep,
) -> AnnotationMutationResponse:
    """Add an annotation (v1: a note) to a sheet (append at the tip)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, request.expected_version)
    sheet = await _get_sheet(session, drawing, sheet_id)

    position = await _count(session, db.Annotation, db.Annotation.sheet_id, sheet.id)
    # Write-side twin of the `max_length=MAX_DRAWING_ANNOTATIONS` parse bound
    # (audit G2) — same rationale as the view cap above.
    if position >= MAX_DRAWING_ANNOTATIONS:
        raise ValidationApiError(
            f"A sheet holds at most {MAX_DRAWING_ANNOTATIONS} annotations "
            "(per-request work bound); delete annotations before adding more.",
            code="annotation_limit_exceeded",
            details={"max_annotations": MAX_DRAWING_ANNOTATIONS},
        )
    annotation = db.Annotation(
        id=uuid.uuid4(),
        sheet_id=sheet.id,
        order_index=position,
        type=request.annotation.type,
        params=request.annotation.model_dump(mode="json"),
    )
    session.add(annotation)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "annotation_created",
        drawing_id=str(drawing_id),
        sheet_id=str(sheet_id),
        annotation_id=str(annotation.id),
        doc_version=drawing.doc_version,
    )
    return AnnotationMutationResponse(
        annotation=_annotation_response(annotation), doc_version=drawing.doc_version
    )


@router.delete("/{drawing_id}/annotations/{annotation_id}")
async def delete_annotation(
    drawing_id: uuid.UUID,
    annotation_id: uuid.UUID,
    expected_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard (design §2.1)")
    ],
    owner_id: Principal,
    session: SessionDep,
) -> DrawingTreeResponse:
    """Delete an annotation; renumbers the sheet's annotations dense (bumps
    version)."""
    drawing = await get_owned_drawing(session, owner_id, drawing_id, for_update=True)
    _ensure_fresh(drawing, expected_version)
    annotation, sheet = await _get_annotation_and_sheet(session, drawing, annotation_id)

    await session.delete(annotation)
    await session.flush()
    await _renumber_dense(session, db.Annotation, db.Annotation.sheet_id, sheet.id)
    drawing.doc_version += 1
    await session.commit()
    _logger.info(
        "annotation_deleted",
        drawing_id=str(drawing_id),
        annotation_id=str(annotation_id),
        doc_version=drawing.doc_version,
    )
    return await _tree_response(session, drawing)
