"""``.loft`` part export and import (docs/FILE-FORMAT.md).

The gateway is the one hop that holds the verified principal, documents and
geometry at once, so the file is assembled and taken apart HERE, with the whole
format in :mod:`loft_wire.loft_file`:

* ``GET /api/v1/parts/{id}/export.loft`` — documents serves the tree
  (``/loft-tree``), the named versions with their trees (``/loft-versions``)
  and the evaluation request; geometry evaluates it (mass properties for the
  manifest) and exports the STEP body (``cache/body.step``);
  :func:`~loft_wire.loft_file.pack_part` writes the canonical bytes. A tree with
  no body still exports — it simply has no cache.
* ``POST /api/v1/parts/import`` — the ``.loft`` is the raw request body, capped
  WHILE it streams; it is read in memory by
  :func:`~loft_wire.loft_file.read_loft` (whitelist, caps, zip-bomb ratio,
  sha256s, format version), the verified tree goes to documents (which applies
  the ``POST /features`` validation and the id policy), and the new part is
  rebuilt from that tree — never from the file's cached body, which is never
  sent to the kernel. The rebuilt volume is compared with the manifest's; a
  mismatch, a hand-edited tree or a tree that fails to rebuild are WARNINGS on
  the 201, never refusals: the user's data is imported either way.

Both routes are auth-gated and rate-limited like every OCCT-CPU route.
"""

import asyncio
import math
import uuid
from importlib import metadata
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from loft_wire.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    ExportTreeRequest,
)
from loft_wire.loft_file import (
    LOFT_MEDIA_TYPE,
    LOFT_VOLUME_REL_TOLERANCE,
    MAX_LOFT_UPLOAD_BYTES,
    LoftArchive,
    LoftCacheProperties,
    LoftFileError,
    LoftImportRequest,
    LoftImportResponse,
    LoftTree,
    LoftVersionList,
    LoftWarning,
    loft_filename,
    pack_part,
    read_loft,
)
from loft_wire.parts import PartResponse
from py_kit import ValidationApiError, get_logger

from gateway.affinity import forward_geometry
from gateway.auth import CurrentUser
from gateway.db import User
from gateway.features import record_last_evaluation
from gateway.parts import forward_documents
from gateway.ratelimit import COMPUTE_RATE_LIMIT
from gateway.step_import import read_capped_body
from gateway.upstream import raise_upstream_error

_logger = get_logger("gateway.loft_file")

_DOCUMENTS = "Documents"
_GEOMETRY = "Geometry"


def _loft_version() -> str:
    """The Loft build that writes the file (``manifest.loft_version``)."""
    try:
        return metadata.version("loft-wire")
    except metadata.PackageNotFoundError:
        return "0.0.0"


#: Read once: the manifest must not depend on anything that varies per request.
LOFT_VERSION = _loft_version()

router = APIRouter(prefix="/api/v1/parts", tags=["parts"])

_EXPORT_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            LOFT_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}
        },
        "description": "The part as a `.loft` file (a data-only zip: manifest.json, "
        "tree.json, blobs/, cache/body.step; docs/FILE-FORMAT.md). Byte-identical "
        "for the same part on the same Loft build. `Content-Disposition` carries "
        "the suggested filename.",
    }
}

_IMPORT_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        },
        "description": "The `.loft` file bytes (raw request body, at most "
        f"{MAX_LOFT_UPLOAD_BYTES} bytes).",
    }
}


async def _documents_json(http_request: Request, user: User, path: str) -> bytes:
    upstream = await forward_documents(http_request, user, "GET", path)
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_DOCUMENTS)
    return upstream.content


async def _evaluate(
    http_request: Request, user: User, part_id: uuid.UUID
) -> tuple[EvaluateTreeRequest, EvaluateTreeResult]:
    """The part's current tree, evaluated (the evaluate route's two hops)."""
    request = EvaluateTreeRequest.model_validate_json(
        await _documents_json(
            http_request, user, f"/api/v1/parts/{part_id}/evaluation-request"
        )
    )
    evaluated = await forward_geometry(
        http_request,
        str(user.id),
        "POST",
        "/api/v1/evaluate",
        service=_GEOMETRY,
        json_content=request.model_dump_json(),
    )
    if evaluated.status_code != status.HTTP_200_OK:
        raise_upstream_error(evaluated, service=_GEOMETRY)
    return request, EvaluateTreeResult.model_validate_json(evaluated.content)


@router.get(
    "/{part_id}/export.loft",
    response_class=Response,
    responses=_EXPORT_RESPONSES,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def export_part_loft(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> Response:
    """Export one of the caller's parts as a `.loft` file.

    The file holds the parametric tree (what an import rebuilds from), the
    part's named versions, and the exported STEP body and its mass properties
    as an untrusted cache. A part with no body exports without the cache. Not a
    backup: undo history and other documents are not in it. If the cached body
    would take the file over a `.loft` size limit it is left out (an import
    rebuilds from the tree anyway); only trees over a limit are refused, with
    their `loft_*` code.
    """
    tree = LoftTree.model_validate_json(
        await _documents_json(http_request, user, f"/api/v1/parts/{part_id}/loft-tree")
    )
    versions = LoftVersionList.model_validate_json(
        await _documents_json(
            http_request, user, f"/api/v1/parts/{part_id}/loft-versions"
        )
    ).versions
    evaluation, result = await _evaluate(http_request, user, part_id)

    body_step: bytes | None = None
    properties: LoftCacheProperties | None = None
    if result.properties is not None:
        export = ExportTreeRequest.model_validate(
            {**evaluation.model_dump(mode="json"), "format": "step", "name": tree.name}
        )
        exported = await forward_geometry(
            http_request,
            str(user.id),
            "POST",
            "/api/v1/export/tree",
            service=_GEOMETRY,
            json_content=export.model_dump_json(),
        )
        if exported.status_code == status.HTTP_200_OK:
            body_step = exported.content
            properties = LoftCacheProperties(
                volume_mm3=result.properties.volume,
                area_mm2=result.properties.surface_area,
                bbox=result.properties.bounding_box,
            )
        elif exported.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise_upstream_error(exported, service=_GEOMETRY)

    try:
        # Packing hashes and deflates up to the caps: off the event loop too.
        data = await asyncio.to_thread(
            pack_part,
            document_id=part_id,
            tree=tree,
            loft_version=LOFT_VERSION,
            body_step=body_step,
            properties=properties,
            versions=versions,
        )
    except LoftFileError as exc:
        # The part is over a cap the reader enforces: refuse rather than write
        # a file no Loft could open.
        raise ValidationApiError(
            exc.message, code=exc.code, details=exc.details
        ) from exc
    filename = loft_filename(tree.name, part_id)
    return Response(
        content=data,
        media_type=LOFT_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _compare(archive: LoftArchive, result: EvaluateTreeResult) -> list[LoftWarning]:
    """What the rebuild says about the file, as warnings (never refusals)."""
    warnings: list[LoftWarning] = []
    failed = [feature for feature in result.features if feature.status == "error"]
    if failed:
        warnings.append(
            LoftWarning(
                code="loft_rebuild_errors",
                message=f"{len(failed)} feature(s) failed to rebuild; the part "
                "was imported with its errors so you can fix them.",
            )
        )
    cached = archive.cache.properties if archive.cache is not None else None
    if cached is not None:
        rebuilt = result.properties.volume if result.properties is not None else None
        if rebuilt is None or not math.isclose(
            rebuilt,
            cached.volume_mm3,
            rel_tol=LOFT_VOLUME_REL_TOLERANCE,
            abs_tol=LOFT_VOLUME_REL_TOLERANCE,
        ):
            warnings.append(
                LoftWarning(
                    code="loft_volume_mismatch",
                    message=f"The rebuilt volume ({rebuilt} mm³) differs from the "
                    f"volume recorded in the file ({cached.volume_mm3} mm³). Check "
                    "the part before you rely on it.",
                )
            )
    return warnings


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_IMPORT_BODY,
    dependencies=[COMPUTE_RATE_LIMIT],
)
async def import_part_loft(
    user: CurrentUser,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> LoftImportResponse:
    """Import a `.loft` file as a new part (201, with any warnings).

    The file is the raw request body, capped at the upload limit while it
    streams and read in memory only. Refusals are 422s with a `loft_*` code: a
    damaged or hostile zip, a file from a newer Loft (`loft_format_too_new`,
    or `loft_feature_too_new` naming the feature), or a tree the feature
    routes would refuse. The part keeps the file's ids unless they already
    exist here; importing the same file twice gives a copy named
    "<name> copy". The file's named versions are imported with their numbers.
    The part is rebuilt from its tree; a hand-edited tree or version, a
    volume that differs from the file's, or features that fail to rebuild are
    reported in `warnings`, not refused.
    """
    raw = await read_capped_body(
        http_request,
        max_bytes=MAX_LOFT_UPLOAD_BYTES,
        what=".loft upload",
        code="loft_too_large",
    )
    try:
        # Unzipping and hashing up to the caps is CPU work: off the event loop.
        archive = await asyncio.to_thread(read_loft, raw)
    except LoftFileError as exc:
        raise ValidationApiError(
            exc.message, code=exc.code, details=exc.details
        ) from exc

    created = await forward_documents(
        http_request,
        user,
        "POST",
        "/api/v1/parts/import-loft",
        LoftImportRequest(
            document_id=archive.manifest.document_id,
            tree=archive.tree,
            versions=list(archive.versions),
        ).model_dump_json(),
    )
    if created.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(created, service=_DOCUMENTS)
    part = PartResponse.model_validate_json(created.content)

    warnings = list(archive.warnings)
    try:
        _, result = await _evaluate(http_request, user, part.id)
    except Exception as exc:  # the part exists: a failed check must not hide it
        _logger.warning(
            "loft_import_verify_failed", part_id=str(part.id), reason=type(exc).__name__
        )
        warnings.append(
            LoftWarning(
                code="loft_verify_unavailable",
                message="The part was imported but could not be rebuilt to check "
                "it; open it to rebuild.",
            )
        )
    else:
        warnings += _compare(archive, result)
        background_tasks.add_task(
            record_last_evaluation, http_request, user, part.id, result
        )
    _logger.info(
        "part_imported_from_loft",
        part_id=str(part.id),
        warnings=[warning.code for warning in warnings],
    )
    return LoftImportResponse(part=part, warnings=warnings)
