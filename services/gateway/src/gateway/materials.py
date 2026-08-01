"""``/api/v1/materials`` — the material library, proxied from documents.

apps/web talks ONLY to the gateway (CLAUDE.md service boundaries), so the
material picker reads the library through here; the documents route
(:mod:`documents.materials`) stays internal.

PROXY, not a second reader of ``py_kit.schemas.materials.MATERIALS``: the
gateway imports py-kit and could serve the table itself in-process, but then
TWO services would own "what the library is" and the answer would fork the
moment the library stops being a frozen constant (user-defined materials are
documents-stored state, materials.md §5). One owner, one hop.

Auth-gated like every other gateway route: nothing about the library is
secret, but a uniform "the gateway needs a bearer" posture is one rule to
reason about instead of a per-route exception list. Unlike the parts routes
the principal is not a scope — the library is the same for every caller — it
just rides along on the shared forwarding path.
"""

from fastapi import APIRouter, Request, status
from py_kit.schemas.materials import MaterialLibraryResponse

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

#: Human-readable upstream name for shared error surfaces.
_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("")
async def list_materials(
    user: CurrentUser, http_request: Request
) -> MaterialLibraryResponse:
    """The built-in materials with their densities, in display order.

    The same table the kernel multiplies by (docs/design/materials.md §1), so a
    picker and a mass readout can never disagree about what "6061-T6" weighs.
    """
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/materials")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return MaterialLibraryResponse.model_validate_json(upstream.content)
