"""``/api/v1/parts/{part_id}/parameters`` — the part's parameter table.

Thin, auth-gated forwards over :mod:`documents.parameters` (PART-PARAMETERS,
RESEARCH §20), like every feature route: the caller is resolved from the JWT,
documents scopes the part to that owner (another owner's part is a 404), and
upstream 404/422 envelopes are re-surfaced verbatim. Bodies are the shared
:mod:`loft_wire.parameters` models, validated here before anything goes
upstream.
"""

import uuid

from fastapi import APIRouter, Request, status
from loft_wire.parameters import PartParametersResponse, PartParametersUpdate

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/parts", tags=["parameters"])


@router.get("/{part_id}/parameters")
async def get_part_parameters(
    part_id: uuid.UUID, user: CurrentUser, http_request: Request
) -> PartParametersResponse:
    """The part's parameter table, in order, with each resolved value."""
    upstream = await forward_documents(
        http_request, user, "GET", f"/api/v1/parts/{part_id}/parameters"
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartParametersResponse.model_validate_json(upstream.content)


@router.put("/{part_id}/parameters")
async def put_part_parameters(
    part_id: uuid.UUID,
    request: PartParametersUpdate,
    user: CurrentUser,
    http_request: Request,
) -> PartParametersResponse:
    """Replace the whole parameter table, as one undoable edit.

    A stale `expected_tree_version` is a 422 `stale_tree_version`. A table
    that does not evaluate is a 422 carrying the expression error's code
    (`expression_syntax`, `expression_unknown_name`, `expression_cycle` with
    its `chain`, `expression_name_invalid`, `expression_units`,
    `expression_domain`, `expression_too_complex`). Deleting a parameter a
    feature still reads is a 409 `parameter_in_use` naming the features; a
    rename rewrites every feature's references; the same table again changes
    nothing.
    """
    upstream = await forward_documents(
        http_request,
        user,
        "PUT",
        f"/api/v1/parts/{part_id}/parameters",
        request.model_dump_json(),
    )
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PartParametersResponse.model_validate_json(upstream.content)
