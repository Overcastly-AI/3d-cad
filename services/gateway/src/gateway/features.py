"""``/api/v1/parts/{part_id}/features`` — auth-protected feature-tree
aggregation over the documents service.

Same posture as :mod:`gateway.parts` (apps/web talks ONLY to the gateway):
every route resolves the caller through the JWT bearer dependency and
forwards via :func:`gateway.parts.forward_documents`, which attaches the
verified principal header. DTOs are the shared py-kit feature models —
never hand-duplicated — so request bodies are fully validated at the gateway
before anything goes upstream, and upstream 404/409/422 envelopes (including
the ``feature_has_dependents`` conflict and ``stale_tree_version``) are
re-surfaced verbatim under the gateway's request id.

``POST /{part_id}/evaluate`` is the one two-hop aggregation: documents builds
the evaluation-ready request (rollback + upcasts applied), the gateway relays
it to the geometry service, and the typed ``EvaluateTreeResult`` — solved
sketch payloads included — returns to the caller. This keeps "the web app
talks only to the gateway" true for feature evaluation without documents ever
calling geometry itself.

That same route owns the last-evaluate BOOKKEEPING (feature-tree.md §4.4a).
The gateway is the only participant holding both the verified principal and
geometry's real answer, so it — not the browser — writes the verdict a register
reads; it does so in a background task after the response, so the write can
neither delay nor fail the evaluate.
"""

import uuid
from typing import Annotated, Any

import httpx2 as httpx
from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status
from py_kit import get_logger
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExportTreeRequest,
    FeatureCreate,
    FeatureDependents,
    FeatureDependentsEnvelope,
    FeatureMutationResponse,
    FeatureReorderRequest,
    FeatureResponse,
    FeatureSuppressRequest,
    FeatureTreeResponse,
    FeatureUpdate,
    RollbackBarMove,
    UndoRedoRequest,
)
from py_kit.schemas.geometry import EXPORT_MEDIA_TYPES, ExportFormat, export_responses
from py_kit.schemas.parts import PartEvaluationRecord

from gateway.auth import CurrentUser
from gateway.db import User
from gateway.parts import forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.upstream import forward, raise_upstream_error

_logger = get_logger("gateway.features")

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: The geometry hop of the evaluate aggregation (error surfaces name it).
_GEOMETRY = "Geometry"

#: The documented 409 of the feature delete. Declaring the model is what makes
#: the refusal ACTIONABLE end to end: it puts
#: :class:`~py_kit.schemas.features.FeatureDependents` in the OpenAPI contract
#: and therefore in the generated TS client, so the feature tree names the
#: features and drawings that hold the reference instead of printing "2 other
#: document(s)" (UI-REVIEW 2026-07-30 F3). Same shape as the document-level
#: ``DEPENDENCY_CONFLICT_RESPONSE`` in :mod:`gateway.parts` — one refusal
#: grammar at both levels of the product.
FEATURE_DEPENDENTS_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": FeatureDependentsEnvelope,
        "description": (
            "Still referenced by later features or drawing views; "
            "`details.dependents` names them."
        ),
    }
}

router = APIRouter(prefix="/api/v1/parts", tags=["features"])


@router.get("/{part_id}/features")
async def get_feature_tree(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> FeatureTreeResponse:
    """The part's ordered feature tree (404 for unknown/foreign parts)."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/features"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.get("/{part_id}/features/{feature_id}")
async def get_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
) -> FeatureResponse:
    """One feature of the caller's part."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/features/{feature_id}"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/features", status_code=status.HTTP_201_CREATED)
async def create_feature(
    part_id: uuid.UUID,
    request: FeatureCreate,
    user: CurrentUser,
    http_request: Request,
) -> FeatureMutationResponse:
    """Create a feature (201; 422 envelope on stale version / bad refs)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/features",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)


@router.patch("/{part_id}/features/{feature_id}")
async def update_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    request: FeatureUpdate,
    user: CurrentUser,
    http_request: Request,
) -> FeatureMutationResponse:
    """Rename and/or replace a feature's params."""
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)


@router.patch("/{part_id}/features/{feature_id}/suppress")
async def suppress_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    request: FeatureSuppressRequest,
    user: CurrentUser,
    http_request: Request,
) -> FeatureMutationResponse:
    """Toggle a feature's suppress flag (feature-tree.md §4.3a).

    Flips ONLY ``suppressed`` (a suppressed feature is skipped at rebuild),
    bumping ``tree_version`` under the same optimistic-concurrency guard as
    every other feature write — a stale version is documents' 422 envelope,
    re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "PATCH",
        f"/api/v1/parts/{part_id}/features/{feature_id}/suppress",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)


@router.get("/{part_id}/features/{feature_id}/dependents")
async def feature_dependents(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
) -> FeatureDependents:
    """What breaks if this feature is deleted (200; empty list when nothing).

    Asked by the feature tree BEFORE it offers the delete, so the confirmation
    names the features and drawings that would break rather than letting the
    user discover them from a refusal. Answered by the same documents-side query
    that builds the delete's 409, so the warning and the refusal cannot disagree.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "GET",
        f"/api/v1/parts/{part_id}/features/{feature_id}/dependents",
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureDependents.model_validate_json(upstream.content)


@router.delete(
    "/{part_id}/features/{feature_id}", responses=FEATURE_DEPENDENTS_RESPONSE
)
async def delete_feature(
    part_id: uuid.UUID,
    feature_id: uuid.UUID,
    expected_tree_version: Annotated[
        int, Query(ge=0, description="Optimistic-concurrency guard")
    ],
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Delete a feature; 409 NAMING the dependents when it is still referenced.

    See :data:`FEATURE_DEPENDENTS_RESPONSE` — the refusal's ``details`` is a
    typed list of what breaks, not a count.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "DELETE",
        f"/api/v1/parts/{part_id}/features/{feature_id}",
        params={"expected_tree_version": str(expected_tree_version)},
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.put("/{part_id}/features/order")
async def reorder_features(
    part_id: uuid.UUID,
    request: FeatureReorderRequest,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Apply a full permutation of the tree (backward-only refs re-checked)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        f"/api/v1/parts/{part_id}/features/order",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


async def record_last_evaluation(
    http_request: Request,
    user: User,
    part_id: uuid.UUID,
    result: EvaluateTreeResult,
) -> None:
    """Persist the evaluate verdict on the part row — best effort, never fatal.

    Runs as a Starlette background task AFTER the evaluate response has been
    sent, for two reasons that are requirements, not conveniences
    (docs/design/feature-tree.md §4.4a):

    - **It cannot slow an evaluate down.** The user's result is already on the
      wire; the bookkeeping round-trip is off the critical path.
    - **It cannot fail an evaluate.** Every exception is swallowed and logged
      (``forward`` raises a 502 ``ApiError`` on an unreachable documents, and a
      raced tree edit can answer 404) — a successful rebuild must never surface
      as an error because a status column could not be written. The cost of a
      lost write is bounded and self-healing: the record simply stays at its
      previous value, which ``eval_state`` already reports as ``stale`` once the
      tree moves on, and the next evaluate rewrites it.

    The verdict is read from geometry's own answer — ``failed`` iff some feature
    returned ``error`` (the strict-prefix rule, §4.3; a ``suppressed`` or
    downstream ``skipped`` feature is not a failure) — and stamped with
    ``result.tree_version``, the version documents built the request from, so
    the record names the tree it describes.
    """
    record = PartEvaluationRecord(
        tree_version=result.tree_version,
        status="failed"
        if any(feature.status == "error" for feature in result.features)
        else "ok",
    )
    try:
        upstream = await forward_documents(
            http_request,
            user,
            "PUT",
            f"/api/v1/parts/{part_id}/last-evaluation",
            record.model_dump_json(),
        )
    # Deliberately broad: NOTHING here may escape into the evaluate's task group.
    except Exception as exc:
        _logger.warning(
            "eval_status_record_failed",
            part_id=str(part_id),
            reason=type(exc).__name__,
        )
        return
    if upstream.status_code != status.HTTP_200_OK:
        _logger.warning(
            "eval_status_record_rejected",
            part_id=str(part_id),
            upstream_status=upstream.status_code,
        )


@router.post("/{part_id}/evaluate", dependencies=[COMPUTE_RATE_LIMIT])
async def evaluate_part(
    part_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> EvaluateTreeResult:
    """Evaluate the part's current feature tree (feature-tree design §4).

    The full loop behind one authenticated call: documents serves the
    evaluation-ready list (rollback bar applied, params upcast — §4.2), the
    gateway forwards it verbatim to the stateless geometry service, and the
    typed result comes back with per-feature statuses and solved-sketch
    ``data`` payloads (§7.10). Feature failures are a 200 with per-feature
    errors (§4.3); the error envelope here means the aggregation itself
    failed (404 unknown part, 502 unreachable upstream, ...).

    A 200 also records the verdict on the part row for the registers' rebuild-
    health column (§4.4a) — in a background task, after the response, so the
    bookkeeping can neither slow this call down nor fail it
    (:func:`record_last_evaluation`).
    """
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/evaluation-request"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(upstream.content)

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    evaluated = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/evaluate",
        service=_GEOMETRY,
        json_content=evaluation_request.model_dump_json(),
    )
    if evaluated.status_code != status.HTTP_200_OK:
        raise_upstream_error(evaluated, service=_GEOMETRY)
    result = EvaluateTreeResult.model_validate_json(evaluated.content)
    background_tasks.add_task(
        record_last_evaluation, http_request, user, part_id, result
    )
    return result


_EXPORT_RESPONSES = export_responses(
    "The exported CAD file of the part's current evaluated body, proxied "
    "byte-exact from the geometry service: STEP AP214 part 21 (`model/step`, "
    "exact B-rep) or binary STL (`model/stl`, faceted mesh). "
    "`Content-Disposition` carries the suggested download filename. A tree "
    "that evaluates to no body is a 422 `tree_export_failed` envelope."
)


@router.post(
    "/{part_id}/export",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def export_part(
    part_id: uuid.UUID,
    format: Annotated[
        ExportFormat, Query(description="Export file format: STEP or STL")
    ],
    user: CurrentUser,
    http_request: Request,
) -> Response:
    """Export the part's current evaluated body as a STEP or STL download.

    The export twin of :func:`evaluate_part` and the same two-hop aggregation:
    documents serves the evaluation-ready feature list (rollback bar applied,
    params upcast — §4.2), the gateway wraps it with the requested format into
    an ``ExportTreeRequest`` and relays it to the stateless geometry service's
    tree-export route, and the file bytes stream back byte-exact. Auth-scoped
    like every parts route (the principal reaches documents, never geometry).
    A tree with no body is the geometry service's 422 ``tree_export_failed``
    envelope, re-surfaced verbatim.
    """
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/evaluation-request"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    evaluation_request = EvaluateTreeRequest.model_validate_json(upstream.content)
    export_request = ExportTreeRequest.model_validate(
        {**evaluation_request.model_dump(mode="json"), "format": format}
    )

    geometry_client: httpx.AsyncClient = http_request.app.state.geometry_client
    exported = await forward(
        geometry_client,
        http_request,
        "POST",
        "/api/v1/export/tree",
        service=_GEOMETRY,
        json_content=export_request.model_dump_json(),
    )
    if exported.status_code != status.HTTP_200_OK:
        raise_upstream_error(exported, service=_GEOMETRY)
    headers: dict[str, str] = {}
    if "content-disposition" in exported.headers:
        headers["Content-Disposition"] = exported.headers["content-disposition"]
    return Response(
        content=exported.content,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers=headers,
    )


@router.post("/{part_id}/undo")
async def undo_part(
    part_id: uuid.UUID,
    request: UndoRedoRequest,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Undo one feature-tree history step (docs/design/undo-redo.md).

    The restored tree comes back with its new ``tree_version``; at the
    ring's floor this is documents' clean no-op (current tree, version
    unchanged). Stale ``expected_tree_version`` → 422, resurfaced verbatim.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/undo",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.post("/{part_id}/redo")
async def redo_part(
    part_id: uuid.UUID,
    request: UndoRedoRequest,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Redo one feature-tree history step (clean no-op at the ring's top)."""
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/redo",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)


@router.put("/{part_id}/rollback")
async def move_rollback_bar(
    part_id: uuid.UUID,
    request: RollbackBarMove,
    user: CurrentUser,
    http_request: Request,
) -> FeatureTreeResponse:
    """Move the rollback bar (null = bar at the tip)."""
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        f"/api/v1/parts/{part_id}/rollback",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureTreeResponse.model_validate_json(upstream.content)
