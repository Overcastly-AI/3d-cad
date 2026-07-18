"""``POST /api/v1/parts/{part_id}/features/import`` — STEP file upload.

The Interop upload leg (docs/design/step-import.md §8): a user uploads an
external STEP part and the gateway turns it into an ``import`` base feature on
the target part, reusing the existing feature-append path in the documents
service (import rides the ordinary feature-tree persistence — no new storage,
§2b). The uploaded bytes become the inline ``ImportParamsV1.data`` (STEP AP214
part-21 text); every later feature (fillet/cut/shell/sketch-on-face) then
models on the imported body with no new machinery.

Shape: the STEP file is the RAW request body (streamed), not a multipart part.
This is deliberate and is the strongest DoS guard the design mandates (§6): the
size cap is enforced WHILE the body streams in, so an oversize payload is
rejected with a 422 *before* the whole body is ever read into memory and long
before documents stores it or geometry parses it. A buffered ``UploadFile``
would have Starlette read the entire (spooled) body before this handler could
reject it — the opposite of "bound untrusted input at the earliest point". The
feature name and optimistic-concurrency token ride as query parameters, exactly
as the other feature-mutation routes carry ``expected_tree_version``.

Auth-gated like every authoring route (:mod:`gateway.parts` /
:mod:`gateway.features`): the caller is resolved through the JWT bearer
dependency and forwarded to the internal documents service with the verified
principal attached; the documents 422 ``import_with_prior_body`` envelope (an
import onto a part that already has a body) is re-surfaced verbatim.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from py_kit import ValidationApiError
from py_kit.schemas.features import (
    FEATURE_NAME_MAX_LENGTH,
    MAX_INLINE_STEP_CHARS,
    FeatureCreate,
    FeatureMutationResponse,
    ImportFeature,
    ImportParamsV1,
)

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

#: Byte ceiling for a streamed STEP upload. The inline STEP text is bounded to
#: ``MAX_INLINE_STEP_CHARS`` characters (py-kit, docs/design/step-import.md §6);
#: a UTF-8 decode yields at most one character per byte, so capping the RAW
#: BYTES at that same number guarantees the decoded ``data`` string satisfies
#: :class:`ImportParamsV1`'s ``max_length`` — while never buffering more than
#: this ceiling (plus one stream chunk) in memory.
MAX_STEP_UPLOAD_BYTES = MAX_INLINE_STEP_CHARS

#: ISO 10303-21 part-21 files begin with this token. A cheap gateway-side
#: "is this even a STEP file?" guard so an obvious non-STEP upload (an image,
#: a JSON blob) is a clean 4xx here; a genuinely malformed-but-STEP-shaped file
#: still reaches the geometry service's per-feature ``import_parse_failed``.
_STEP_MAGIC = "ISO-10303-21"

router = APIRouter(prefix="/api/v1/parts", tags=["features"])


def _too_large(*, content_length: int | None) -> ValidationApiError:
    """The oversize-upload 422 (docs/design/step-import.md §6)."""
    details: dict[str, Any] = {"max_bytes": MAX_STEP_UPLOAD_BYTES}
    if content_length is not None:
        details["content_length"] = content_length
    return ValidationApiError(
        f"STEP upload exceeds the maximum inline size ({MAX_STEP_UPLOAD_BYTES} bytes).",
        code="import_too_large",
        details=details,
    )


async def _read_capped_body(http_request: Request, *, max_bytes: int) -> bytes:
    """Stream the request body, rejecting once it exceeds *max_bytes*.

    Two guards, earliest-first (§6): a declared ``Content-Length`` over the
    ceiling is a 422 before a single body byte is read; then the stream itself
    is bounded chunk-by-chunk (a missing or lying header cannot slip past),
    aborting the moment the running total crosses the cap so memory stays
    bounded to ``max_bytes`` plus one chunk regardless of what is sent.
    """
    declared = http_request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise _too_large(content_length=int(declared))
    chunks: list[bytes] = []
    total = 0
    async for chunk in http_request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(content_length=None)
        chunks.append(chunk)
    return b"".join(chunks)


#: The upload body is the STEP file itself (raw, streamed — see the module
#: docstring). FastAPI cannot infer a body schema for a handler that reads the
#: stream directly, so declare it explicitly: an ``application/octet-stream``
#: binary payload, so the contract + generated client describe the real shape.
_UPLOAD_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        },
        "description": "The STEP part-21 file bytes (raw request body).",
    }
}


@router.post(
    "/{part_id}/features/import",
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_UPLOAD_BODY,
)
async def import_step(
    part_id: uuid.UUID,
    user: CurrentUser,
    http_request: Request,
    expected_tree_version: Annotated[
        int,
        Query(
            ge=0,
            description="Optimistic-concurrency guard: the tree_version the "
            "client last saw (as on every feature mutation)",
        ),
    ],
    name: Annotated[
        str,
        Query(
            min_length=1,
            max_length=FEATURE_NAME_MAX_LENGTH,
            description="User-facing name for the created import feature",
        ),
    ] = "Imported STEP",
) -> FeatureMutationResponse:
    """Import an uploaded STEP file as the part's base body.

    The STEP file is the raw request body. It is size-capped as it streams
    (oversize → 422 ``import_too_large`` before the body is fully read — §6),
    then decoded and mapped to an ``import`` feature whose inline
    ``params.data`` is the STEP text (§2b). Persistence reuses the ordinary
    documents feature-append path (``POST /features``), so an import onto a
    part that already has a body is documents' legible 422
    ``import_with_prior_body`` envelope, re-surfaced verbatim (§1). An empty
    upload or a file lacking the ISO-10303-21 header is a clean 422 here,
    before anything goes upstream.
    """
    raw = await _read_capped_body(http_request, max_bytes=MAX_STEP_UPLOAD_BYTES)
    if not raw.strip():
        raise ValidationApiError("STEP upload was empty.", code="import_empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationApiError(
            "STEP upload is not valid text — expected a UTF-8/ASCII STEP part-21 file.",
            code="import_not_step",
        ) from exc
    if not text.lstrip().startswith(_STEP_MAGIC):
        raise ValidationApiError(
            "Uploaded file is not a STEP part-21 file (missing the "
            "ISO-10303-21 header).",
            code="import_not_step",
        )

    create = FeatureCreate(
        name=name,
        feature=ImportFeature(
            type="import",
            version=1,
            params=ImportParamsV1(kind="inline", format="step", data=text),
        ),
        expected_tree_version=expected_tree_version,
    )
    upstream = await forward_documents(
        http_request,
        user,
        "POST",
        f"/api/v1/parts/{part_id}/features",
        create.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_201_CREATED:
        raise_upstream_error(upstream, service=_SERVICE)
    return FeatureMutationResponse.model_validate_json(upstream.content)
